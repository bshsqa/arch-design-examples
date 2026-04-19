from launch import LaunchDescription
from launch_ros.actions import LifecycleNode

def generate_launch_description():
    return LaunchDescription([
        LifecycleNode( package='multi_node_process',
                       executable='multi_threaded',
                       name='multi_threaded',
                       namespace='multi_node_multi_threaded_process',
        ),
        LifecycleNode( package='elapsed_time',
                       executable='elapsed_time',
                       name='elapsed_time',
                       namespace='multi_node_multi_threaded_process',
        ),
    ])
