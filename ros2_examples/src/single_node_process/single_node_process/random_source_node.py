import rclpy
from pipe_and_filter.random_source import RandomSource

def main(args=None):
    rclpy.init(args=args)

    node = RandomSource()
    rclpy.spin(node)

    # Destroy the node explicitly
    # (optional - otherwise it will be done automatically
    # when the garbage collector destroys the node object)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()