from pipe_and_filter.core.source import Source
from random import randint

class RandomSource(Source):

    def __init__(self, name='random', **args):
        super().__init__(name, **args)

    def generate_number(self):
        return randint(1, 100)
