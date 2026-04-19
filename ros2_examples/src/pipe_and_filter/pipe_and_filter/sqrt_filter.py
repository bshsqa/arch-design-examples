from pipe_and_filter.core.filter import Filter
from math import sqrt

class SQRTFilter(Filter):

    def __init__(self, name='sqrt', **args):
        super().__init__(name, **args)

    def process_number(self, number):
        return int(sqrt(number))
