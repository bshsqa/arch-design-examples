# Lslidar ROS2 Driver — 메모리 복사 성능 이슈 분석 및 설계 대안

---

## 이슈 1. 패킷 수신 시 이중 버퍼 복사

### 문제

`polling()` 함수는 네트워크 패킷을 수신할 때마다 **힙(heap) 버퍼를 동적 할당**하고, `LslidarPacket` 메시지 버퍼에 이미 채워진 데이터를 **byte-by-byte 루프로 재복사**한다.

```cpp
// lslidar_driver.cc : polling()
unsigned char *packet_bytes = new unsigned char[500];   // ← 매 호출마다 힙 할당
// ...
// recvfrom() → packet->data[] 에 이미 수신 완료
for (int i = 0; i < len; i++) {
    packet_bytes[i] = packet->data[i];   // ← 불필요한 2차 복사
}
// ...
delete packet_bytes;   // 매 호출마다 해제
```

**데이터 흐름:**
```
recvfrom()  →  packet->data[2000]  →  packet_bytes[500]  →  data_processing()
                   (1차 수신)              (2차 복사)
```

- `polling()` 은 lidar 회전 주파수 × 패킷 수(M10 기준 10Hz × 24 = 240 회/초) 호출됨
- 매 호출마다 힙 alloc/free → TLB miss, 힙 단편화, 캐시 오염

---

### 대안 설계

**스택 버퍼** 또는 **멤버 버퍼**를 사전 할당하고, 루프 대신 `std::memcpy`를 사용한다.  
더 나아가 네트워크 경로에서는 `packet->data.data()`를 `data_processing()`에 **직접 전달**하여 복사 자체를 제거한다.

```
[대안 A — 스택 버퍼 + memcpy]
unsigned char packet_bytes[500];          // 스택: 힙 할당/해제 0회
std::memcpy(packet_bytes, packet->data.data(), len);  // SIMD 최적화 가능

[대안 B — 직접 전달 (제로 복사)]
data_processing(packet->data.data(), len);  // 복사 없음
// packet 객체는 polling() 스코프 내에서 유효하므로 안전
```

| | 현재 | 대안 A | 대안 B |
|---|---|---|---|
| 힙 할당 횟수 | 240회/초 | 0 | 0 |
| 복사 횟수 | 2회 | 1회 (memcpy) | 0회 |

---

## 이슈 2. 스윕 완료 시 뮤텍스 구간에서 전체 벡터 복사

### 문제

360° 스캔이 완료될 때마다 `data_processing()` 안에서 `scan_points_`(쓰기 버퍼)를 `scan_points_bak_`(읽기 버퍼)로 **`assign()`으로 전체 복사**하고, 이어서 `scan_points_` 전체를 **제로 초기화 루프**로 지운다. 두 작업 모두 **mutex 보호 구간 안**에서 실행된다.

```cpp
// lslidar_driver.cc : data_processing() — 스윕 완료 시
boost::unique_lock<boost::mutex> lock(mutex_);

scan_points_bak_.resize(scan_points_.size());          // 크기 재설정
scan_points_bak_.assign(scan_points_.begin(),          // ← O(n) 전체 복사
                         scan_points_.end());           //   6000 × 24 B = 144 KB

for (long unsigned int k = 0; k < scan_points_.size(); k++) {
    scan_points_[k].range     = 0;                     // ← O(n) 전체 초기화
    scan_points_[k].degree    = 0;                     //   또 144 KB 쓰기
    scan_points_[k].intensity = 0;
}
pre_time_ = time_;
lock.unlock();
```

- mutex 점유 시간 ∝ 포인트 수 (O(n))
- mutex를 기다리는 `pubScanThread`가 블로킹되어 퍼블리시 지연 발생
- M10 기준 스윕 10회/초 → 초당 288 KB 무의미한 복사

---

### 대안 설계

**더블 버퍼링(Double Buffering) + `std::swap`** 패턴을 적용한다.  
두 버퍼의 포인터를 O(1) 스왑만 mutex 안에서 수행하고, 버퍼 초기화는 mutex 밖에서 처리한다.

```
[현재 구조]
 드라이버 스레드        mutex 보호 구간           퍼블리셔 스레드
 ────────────          ──────────────────        ──────────────
 scan_points_ 쓰기  →  assign() 144KB 복사    →  scan_points_bak_ 읽기
                        clear()  144KB 초기화

[대안 구조 — std::swap]
 드라이버 스레드        mutex 보호 구간           퍼블리셔 스레드
 ────────────          ──────────────────        ──────────────
 scan_points_ 쓰기  →  swap() O(1) 포인터 교환  →  scan_points_bak_ 읽기
 ↑                      (수 나노초)
 fill_n() 초기화   ←   mutex 해제 후 수행
 (mutex 밖)
```

```cpp
// 대안 설계 의사 코드 (data_processing 스윕 완료 시점)
{
    boost::unique_lock<boost::mutex> lock(mutex_);
    std::swap(scan_points_, scan_points_bak_);   // O(1) — mutex 최소 점유
    pre_time_ = time_;
}
// mutex 해제 후, 새로운 쓰기 버퍼(구 bak_)를 초기화
std::fill_n(scan_points_.begin(), points_size_, ScanPoint{0.0, 0.0, 0.0});
```

| | 현재 | 대안 |
|---|---|---|
| mutex 점유 시간 | O(n) · 144KB 쓰기 | O(1) swap |
| 총 메모리 접근 | 288 KB/sweep (복사+초기화) | 144 KB/sweep (초기화만, mutex 밖) |
| pubScanThread 블로킹 | 있음 | 없음 |

**전제 조건:** `scan_points_bak_`도 `loadParameters()`에서 `scan_points_`와 동일한 크기로 사전 초기화해야 한다.

---

## 이슈 3. pubScanThread에서 getScan() 중복 호출

### 문제

`pubScanThread()`에서 `pubScan`과 `pubPointCloud2`가 모두 활성화된 경우, `getScan()`이 **동일한 스윕에 대해 두 번 호출**된다. 각 호출마다 `scan_points_bak_`→ 로컬 `points` 벡터로 **전체 복사**가 발생한다.

```cpp
// lslidar_driver.cc : pubScanThread()
if (pubScan) {
    std::vector<ScanPoint> points;
    rclcpp::Time start_time;
    float scan_time;
    this->getScan(points, start_time, scan_time);  // ← 1차 복사 (144 KB)
    // LaserScan 퍼블리시...
}
if (pubPointCloud2) {
    std::vector<ScanPoint> points;
    rclcpp::Time start_time;
    float scan_time;
    this->getScan(points, start_time, scan_time);  // ← 2차 복사 (144 KB, 동일 데이터)
    // PointCloud2 퍼블리시...
}
```

```cpp
// getScan() 내부 — 매 호출마다 전체 할당+복사
int LslidarDriver::getScan(...) {
    boost::unique_lock<boost::mutex> lock(mutex_);
    points.assign(scan_points_bak_.begin(), scan_points_bak_.end());  // O(n)
    ...
}
```

- 같은 스윕 데이터를 두 번 복사 (최대 288 KB/sweep 추가 낭비)

---

### 대안 설계

`getScan()`을 **한 번만** 호출하고, 반환된 `points`, `start_time`, `scan_time`을 두 퍼블리셔가 **공유**한다.

```
[현재 구조]
getScan() → points_a → LaserScan 발행
getScan() → points_b → PointCloud2 발행   (동일 데이터를 두 번 복사)

[대안 구조]
getScan() → points ─┬→ LaserScan 발행
                    └→ PointCloud2 발행   (단일 복사 공유)
```

```cpp
// 대안 설계 의사 코드 (pubScanThread 루프 내부)
std::vector<ScanPoint> points;   // 한 번만 선언
rclcpp::Time start_time;
float scan_time;
this->getScan(points, start_time, scan_time);   // 한 번만 호출

if (pubScan) {
    // points 사용 (복사 없음)
}
if (pubPointCloud2) {
    // 동일 points 재사용 (복사 없음)
}
```

| | 현재 | 대안 |
|---|---|---|
| getScan() 호출 횟수 | 2회/sweep | 1회/sweep |
| 복사 비용 | 288 KB/sweep | 144 KB/sweep |

---

## 이슈 4. PointCloud2 메시지 발행 시 불필요한 복사

### 문제

PointCloud2를 발행할 때 `pcl::toROSMsg()`로 PCL 포인트클라우드를 ROS 메시지로 변환한 뒤, **값(value) 형태**로 `publish()`에 전달한다. publish() 내부에서 메시지를 다시 직렬화 버퍼로 복사한다.

```cpp
// lslidar_driver.cc : pubScanThread()
sensor_msgs::msg::PointCloud2 pc_msg;
pcl::toROSMsg(*point_cloud, pc_msg);   // ← PCL → ROS 변환 복사
point_cloud_pub->publish(pc_msg);      // ← 값 전달 → publish 내부 재복사
```

반면 LaserScan은 `UniquePtr`과 `std::move`를 활용하여 복사를 회피하고 있다.

```cpp
// LaserScan은 이미 올바르게 처리 (참고)
auto scan = sensor_msgs::msg::LaserScan::UniquePtr(...);
scan_pub->publish(std::move(scan));    // ← 소유권 이전, 복사 없음
```

---

### 대안 설계

`sensor_msgs::msg::PointCloud2`를 `std::move`로 전달하거나, `UniquePtr`을 사용하여 소유권을 이전한다.

```
[현재 구조]
pc_msg (스택)  →  publish(pc_msg)  →  내부 복사 후 직렬화

[대안 구조 A — std::move]
pc_msg (스택)  →  publish(std::move(pc_msg))  →  소유권 이전, 복사 없음

[대안 구조 B — UniquePtr (LaserScan과 일관성 유지)]
auto pc_msg = std::make_unique<sensor_msgs::msg::PointCloud2>();
pcl::toROSMsg(*point_cloud, *pc_msg);
point_cloud_pub->publish(std::move(pc_msg));
```

---

## 이슈 5. data_processing 에서 packet_bytes 이중 해제(Double Free) 버그

### 문제

`data_processing()`과 `data_processing_2()`는 함수 내부의 얼리 리턴 경로에서 `packet_bytes`를 `delete`하고 반환한다. 그런데 호출자인 `polling()`도 함수 반환 후 동일한 포인터를 `delete`한다. 이로 인해 특정 조건(invalidValue ≤ 1)에서 **이중 해제(double free)**가 발생한다.

```cpp
// data_processing() 내부 — 얼리 리턴 경로
if (invalidValue <= 1) {
    delete packet_bytes;   // ← 1차 해제
    return;
}

// polling() — 함수 반환 후
LslidarDriver::data_processing(packet_bytes, len);
delete packet_bytes;       // ← 2차 해제 (UB: double free)
```

또한 함수 말미의 정상 경로에도 **무효화 후 조건 검사**하는 구조적 오류가 있다.

```cpp
// data_processing() 말미 — 정상 경로
packet_bytes = {0x00};    // 포인터를 0(nullptr)으로 덮어씀
if (packet_bytes) {       // 항상 false → 실행되지 않음 (dead code)
    packet_bytes = NULL;
    delete packet_bytes;  // delete nullptr — 무해하지만 의미 없음
}
// polling()이 원래 포인터(이미 소멸됨)를 delete → 실제로는 여기서 이중 해제 없음
// 그러나 얼리 리턴 경로에서는 이중 해제 발생
```

---

### 대안 설계

**소유권(ownership)을 명확히** 하여 해제 책임을 한 곳에만 둔다.

`data_processing()`은 메모리 소유권을 갖지 않는다(뷰(view) 역할만 수행). `polling()`이 버퍼의 유일한 소유자가 된다.

```
[현재 소유권 모델 — 불명확]
polling()          data_processing()
    new ──────────→  (경우에 따라) delete   ← 얼리 리턴 시
    delete  ←────────────────────────────── 항상 delete → 이중 해제

[대안 소유권 모델 — 단일 소유자]
polling()          data_processing()
    new ──────────→  (소유권 없음, 뷰만 수행)
    delete           (delete 없음)
```

이슈 1의 대안(스택 버퍼)을 적용하면 `new`/`delete` 자체가 사라져 이 버그는 근본적으로 제거된다.

---

## 요약

| # | 위치 | 문제 유형 | 영향 | 대안 설계 핵심 |
|---|---|---|---|---|
| 1 | `polling()` | 패킷마다 힙 alloc + 2차 루프 복사 | 240회/초 힙 할당, 캐시 오염 | 스택 버퍼 + `memcpy` 또는 직접 포인터 전달 |
| 2 | `data_processing()` | mutex 내 O(n) 벡터 assign + 전체 초기화 | mutex 점유 시간 O(n), publisher 블로킹 | 더블 버퍼링 + `std::swap` (O(1) mutex 구간) |
| 3 | `pubScanThread()` | 동일 스윕 데이터에 `getScan()` 2회 호출 | 288 KB/sweep 추가 복사 | `getScan()` 1회 → 두 publisher가 공유 |
| 4 | `pubScanThread()` | `PointCloud2` 값 전달로 publish 시 재복사 | 메시지 크기만큼 추가 복사 | `std::move` 또는 `UniquePtr` 소유권 이전 |
| 5 | `data_processing()` | 이중 해제(Double Free) | 정의되지 않은 동작(UB), 크래시 위험 | 소유권 단일화 (스택 버퍼로 대체 시 근본 해결) |
