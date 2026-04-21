# 이슈1 + 이슈2 통합 수정 설계: Zero-Copy 패킷 처리 + 더블 버퍼 스캔 포인트

---

## 1. 문제 범위

이슈1(패킷 복사)과 이슈2(스캔 버퍼 복사)는 **동일한 데이터 파이프라인의 연속된 구간**에서 발생한다.
두 이슈를 함께 설계하지 않으면 중간 버퍼의 존재 이유가 모호해지므로, 하나의 설계 원칙으로 통합 해결한다.

---

## 2. 현재 구조 — 문제

### 2-1. 현재 데이터 흐름

```mermaid
flowchart TD
    subgraph POLL["polling()  ·  240회/초 (M10 기준)"]
        NET["recvfrom()"]
        PKT["packet→data[2000]\nheap · LslidarPacket"]
        PB["packet_bytes[500]\nnew / delete  per call"]
        NET -->|수신| PKT
        PKT -->|"① byte-by-byte 루프 복사\n  불필요한 2차 복사"| PB
    end

    subgraph PROC["data_processing()  ·  sweep 완료 시 10회/초"]
        SP["scan_points_[6000]\n쓰기 버퍼"]
        COPY["② assign()  144 KB 복사\n   mutex 보호 구간 안  O(n)"]
        ZERO["③ fill()  144 KB 초기화\n   mutex 보호 구간 안  O(n)"]
        SPBAK["scan_points_bak_[6000]\n읽기 버퍼"]
        PB -->|포인트 쓰기| SP
        SP --> COPY --> SPBAK
        SP --> ZERO
    end

    subgraph PUB["pubScanThread()"]
        GS1["getScan() 1차\nassign() 144 KB"]
        GS2["getScan() 2차\nassign() 144 KB"]
        SC["LaserScan publish"]
        PC["PointCloud2 publish"]
        SPBAK --> GS1 --> SC
        SPBAK --> GS2 --> PC
    end

    style PB  fill:#fbb,stroke:#c00
    style COPY fill:#fbb,stroke:#c00
    style ZERO fill:#fbb,stroke:#c00
```

### 2-2. 핵심 문제

| # | 위치 | 문제 | 부하 |
|---|---|---|---|
| ① | `polling()` | 패킷마다 heap `new/delete` + byte-by-byte 루프 복사 | 240회/초 힙 할당, 캐시 오염 |
| ② | `data_processing()` | mutex 내 `assign()` 144 KB 복사 | mutex 점유 O(n), publisher 블로킹 |
| ③ | `data_processing()` | mutex 내 `fill()` 144 KB 초기화 | mutex 점유 추가 O(n) |

`pubScanThread`는 ②③이 끝날 때까지 mutex를 얻지 못해 **LaserScan / PointCloud2 발행이 수백 µs 지연**된다.

---

## 3. 통합 설계 원칙

> **패킷 버퍼는 복사하지 않고 직접 전달한다.**
>
> **스캔 버퍼는 두 개를 사전 할당하고, mutex 구간에서는 포인터 교환(swap)만 수행한다.**

---

## 4. 수정 설계 — 제안

### 4-1. 제안 데이터 흐름

```mermaid
flowchart TD
    subgraph POLL2["polling()  ·  240회/초"]
        NET2["recvfrom()"]
        PKT2["packet→data[2000]\nheap · LslidarPacket"]
        NET2 -->|수신| PKT2
    end

    subgraph PROC2["data_processing()  ·  sweep 완료 시 10회/초"]
        SP2["scan_points_\n쓰기 버퍼  (사전 할당)"]
        SWAP["std::swap()  O(1)\nmutex 보호 구간  ≈ 수 ns"]
        FILL2["fill_n()  초기화\nmutex 밖  (병렬 가능)"]
        SPBAK2["scan_points_bak_\n읽기 버퍼  (사전 할당)"]
        PKT2 -->|"직접 포인터 전달\n복사 없음"| SP2
        SP2 --> SWAP --> SPBAK2
        SWAP -.->|swap 후 구 버퍼 재사용| FILL2
        FILL2 -.->|초기화 완료| SP2
    end

    subgraph PUB2["pubScanThread()"]
        GS3["getScan()  1회\nassign() 144 KB"]
        SC2["LaserScan publish"]
        PC2["PointCloud2 publish"]
        SPBAK2 --> GS3
        GS3 --> SC2
        GS3 --> PC2
    end

    style SWAP fill:#bfb,stroke:#080
    style FILL2 fill:#dfd,stroke:#080
```

### 4-2. 구간별 변경 설계

#### ● 패킷 경로 (이슈1 해결)

| 항목 | 현재 | 제안 |
|---|---|---|
| 버퍼 할당 | `new unsigned char[500]` per call | `packet->data.data()` 직접 참조 — 할당 없음 |
| 복사 방식 | byte-by-byte 루프 | 복사 없음 (직접 전달) |
| 해제 | `delete` per call | 없음 |
| double free 위험 | 있음 (이슈5) | 제거됨 |

`polling()` 이 `data_processing()` 을 호출할 때 `packet->data.data()` 를 직접 전달한다.
`packet` 객체는 `polling()` 스코프 내에서 유효하므로 dangling pointer 위험 없다.

---

#### ● 스캔 버퍼 경로 (이슈2 해결)

| 항목 | 현재 | 제안 |
|---|---|---|
| `scan_points_bak_` 초기화 | sweep마다 런타임 `resize()` | `loadParameters()` 에서 동일 크기로 사전 할당 |
| sweep 완료 시 mutex 내 작업 | `assign()` 144 KB + `fill()` 144 KB | `std::swap()` O(1) 포인터 교환만 |
| 버퍼 초기화 위치 | mutex 내부 | mutex 해제 후 (`fill_n`), publisher와 병렬 실행 가능 |

### 4-3. mutex 점유 시간 비교

```mermaid
sequenceDiagram
    participant D as 드라이버 스레드
    participant M as Mutex
    participant P as pubScanThread

    Note over D,P: ── 현재 구조 ──
    D->>M: lock 획득
    D->>D: assign()  144 KB  (수백 µs)
    D->>D: fill()    144 KB  (수백 µs)
    Note over P: ❌ 블로킹 — publish 지연
    D->>M: unlock
    P->>M: lock 획득
    P->>P: publish

    Note over D,P: ── 제안 구조 ──
    D->>M: lock 획득
    D->>D: std::swap()  O(1)  (수 ns)
    D->>M: unlock
    P->>M: lock 획득 즉시 ✅
    P->>P: publish (지연 없음)
    D->>D: fill_n()  mutex 밖 (병렬 실행)
```

---

## 5. 전제 조건

- `scan_points_bak_` 는 `loadParameters()` 에서 `scan_points_` 와 **동일한 크기로 사전 할당 및 0-초기화** 한다.  
  (M10_DOUBLE 모델은 `idx + 3000` 까지 접근하므로 크기는 `points_size_ + 3000` 이상)
- `data_processing()` 함수 시그니처 `unsigned char *` 는 유지하고, 호출부에서 `packet->data.data()` 를 전달한다.
- 시리얼 경로(`interface_selection == "serial"`) 에서는 `receive_data()` 가 채우는 스택 버퍼를 동일하게 직접 전달한다.

---

## 6. 기대 효과

| 지표 | 현재 | 제안 |
|---|---|---|
| 패킷당 heap 할당 | 240회/초 | **0회** |
| 패킷당 복사 횟수 | 2회 | **0회** |
| mutex 점유 시간 | O(n) · ~수백 µs | **O(1) · ~수 ns** |
| pubScanThread 블로킹 | 있음 | **없음** |
| double free 버그 (이슈5) | 존재 | **자동 제거** |
