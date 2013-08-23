from logging import *

class FancyFormatter(Formatter):
    fancy_replacements = {
        '<RESET>' : '\033[0m', '<BOLD>' : '\033[1m',
        '<NOCOLOUR>' : '\033[39m',

        '<BLACK>' : '\033[30m', '<RED>'     : '\033[31m',
        '<GREEN>' : '\033[32m', '<YELLOW>'  : '\033[33m',
        '<BLUE>'  : '\033[34m', '<MAGENTA>' : '\033[35m',
        '<CYAN>'  : '\033[36m', '<WHITE>'   : '\033[37m',
    }

    def __init__(self, *args, fancy=False, **kwargs):
        self.fancy = fancy
        return super().__init__(*args, **kwargs)

    def format(self, record):
        s = super().format(record)
        if self.fancy:
            s = self.fancify(s)
        return s

    @classmethod
    def fancify(cls, s):
        for k, v in cls.fancy_replacements.items():
            s = s.replace(k, v)
        return s

