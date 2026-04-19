from rclpy.node import Node
from std_msgs.msg import Int64

class Filter(Node):

    def __init__(self, name='filter', input='input', output='output', **args):
        super().__init__(name, **args)

        self.publisher = self.create_publisher(Int64, output, 10)
        self.subscription = self.create_subscription(Int64, input, self.callback, 10)

    def process_number(self, number):
        return number

    def callback(self, msg):
        out = Int64()
        out.data = self.process_number(msg.data)
        self.publisher.publish(out)
