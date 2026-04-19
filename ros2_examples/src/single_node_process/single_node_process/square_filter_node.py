import rclpy
from pipe_and_filter.square_filter import SquareFilter

def main(args=None):
    rclpy.init(args=args)

    node = SquareFilter()
    rclpy.spin(node)

    # Destroy the node explicitly
    # (optional - otherwise it will be done automatically
    # when the garbage collector destroys the node object)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()