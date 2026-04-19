from rclpy.node import Node
from std_msgs.msg import Int64

class ElapsedTime(Node):
    @staticmethod
    def get_source_time_topic():
        return 'source_time'

    @staticmethod
    def get_sink_time_topic():
        return 'sink_time'

    def __init__(self, name='elapsed_time', **args):
        super().__init__(name, **args)

        self.source_subscription = self.create_subscription(Int64, ElapsedTime.get_source_time_topic(), self.source_time_callback, 10)
        self.sink_subscription   = self.create_subscription(Int64, ElapsedTime.get_sink_time_topic(), self.sink_time_callback, 10)

        self.source_time = 0

    def source_time_callback(self, msg):
        self.source_time = msg.data

    def sink_time_callback(self, msg):
        delta = msg.data - self.source_time
        self.get_logger().info('elasped time = %9sns' % format(delta,','))
