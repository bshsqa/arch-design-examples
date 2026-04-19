# ROS2 examples
ROS2 examples for deployment

## ros2 vnc environment
```
C:\> docker run -p 8080:80 -it --name ros2 tiryoh/ros2-desktop-vnc:humble
```
connect to localhost:8008 in the browser (Edge is better)

## build
1. update packages
```
$ sudo apt update && sudo apt upgrade
```
2. git clone
```
$ git clone https://github.com/bosornd/ros2_examples.git
$ cd ros2_examples
```
3. install dependencies
```
$ rosdep install --from-paths src --ignore-src --rosdistro humble -y
```
4. build
```
$ colcon build
$ source install/setup.bash
```

## launch
- case 1, each node is deployed on each process (default).
```
$ ros2 launch ros2_examples single_node_process.py
```
- case 2, multiple nodes are deployed on a single process using a single-threaded executor.
```
$ ros2 launch ros2_examples multi_node_single_threaded_process.py
```
- case 3, multiple nodes are deployed on a single process using a multi-threaded executor.
```
$ ros2 launch ros2_examples multi_node_multi_threaded_process.py
```
