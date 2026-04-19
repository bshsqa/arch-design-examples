import rclpy
from rclpy.executors import SingleThreadedExecutor
from pipe_and_filter.random_source import RandomSource
from pipe_and_filter.square_filter import SquareFilter
from pipe_and_filter.logger_sink import LoggerSink

def main(args=None):
    rclpy.init(args=args)

    node1 = RandomSource(cli_args=['--remap', 'output:=number1'])
    node2 = SquareFilter(name='square1', cli_args=['--remap', 'input:=number1', '--remap', 'output:=number2'])
    node3 = SquareFilter(name='square2', cli_args=['--remap', 'input:=number2', '--remap', 'output:=number3'])
    node4 = LoggerSink(cli_args=['--remap', 'input:=number3'])

    executor = rclpy.get_global_executor()
    executor.add_node(node1)
    executor.add_node(node2)
    executor.add_node(node3)
    executor.add_node(node4)

    executor.spin()

    # Destroy the node explicitly
    # (optional - otherwise it will be done automatically
    # when the garbage collector destroys the node object)
    node1.destroy_node()
    node2.destroy_node()
    node3.destroy_node()
    node4.destroy_node()
    
    rclpy.shutdown()


if __name__ == '__main__':
    main()