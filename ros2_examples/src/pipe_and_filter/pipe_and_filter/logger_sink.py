from pipe_and_filter.core.sink import Sink

class LoggerSink(Sink):

    def __init__(self, name='logger', **args):
        super().__init__(name, **args)

    def process_number(self, number):
        self.get_logger().info(str(number))
