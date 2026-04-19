from pipe_and_filter.core.filter import Filter

class SquareFilter(Filter):

    def __init__(self, name='square', **args):
        super().__init__(name, **args)

    def process_number(self, number):
        return number * number
