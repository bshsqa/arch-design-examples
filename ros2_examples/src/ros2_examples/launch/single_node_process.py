from launch import LaunchDescription
from launch_ros.actions import LifecycleNode

def generate_launch_description():
    return LaunchDescription([
        LifecycleNode( package='single_node_process',
                       executable='random',
                       name='random',
                       namespace='single_node_process',
                       remappings=[
                            ('output', 'number1')
                       ],
        ),
        LifecycleNode( package='single_node_process',
                       executable='square',
                       name='square1',
                       namespace='single_node_process',
                       remappings=[
                            ('input', 'number1'),
                            ('output', 'number2')
                       ],
        ),
        LifecycleNode( package='single_node_process',
                       executable='square',
                       name='square2',
                       namespace='single_node_process',
                       remappings=[
                            ('input', 'number2'),
                            ('output', 'number3')
                       ],
        ),
        LifecycleNode( package='single_node_process',
                       executable='logger',
                       name='logger',
                       namespace='single_node_process',
                       remappings=[
                            ('input', 'number3')
                       ],
        ),
        LifecycleNode( package='elapsed_time',
                       executable='elapsed_time',
                       name='elapsed_time',
                       namespace='single_node_process',
        ),
    ])
