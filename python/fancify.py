from logging import Formatter

class FancyFormatter(Formatter):
    # Terminal colour codes
    fancy_replacements = {
        '<RESET>' : '\033[0m', '<BOLD>' : '\033[1m',
        '<NOCOLOUR>' : '\033[39m',

        '<BLACK>' : '\033[30m', '<RED>'     : '\033[31m',
        '<GREEN>' : '\033[32m', '<YELLOW>'  : '\033[33m',
        '<BLUE>'  : '\033[34m', '<MAGENTA>' : '\033[35m',
        '<CYAN>'  : '\033[36m', '<WHITE>'   : '\033[37m',
    }

    def format(self, record):
        return self.fancify(super().format(record))

    @classmethod
    def fancify(cls, s):
        for k, v in cls.fancy_replacements.items():
            if k in s:
                s = s.replace(k, v)
        return s

fancify = FancyFormatter.fancify

class NotSoFancyFormatter(FancyFormatter):
    fancy_replacements = {
        k : ''
        for k in FancyFormatter.fancy_replacements
    }

