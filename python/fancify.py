from sys import stdout
from logging import Formatter

# Terminal colour codes
FANCIFY_REPLACEMENTS = {
    '<RESET>' : '\033[0m', '<BOLD>' : '\033[1m',
    '<NOCOLOUR>' : '\033[39m',

    '<BLACK>' : '\033[30m', '<RED>'     : '\033[31m',
    '<GREEN>' : '\033[32m', '<YELLOW>'  : '\033[33m',
    '<BLUE>'  : '\033[34m', '<MAGENTA>' : '\033[35m',
    '<CYAN>'  : '\033[36m', '<WHITE>'   : '\033[37m',
}

UNFANCIFY_REPLACEMENTS = {key : '' for key in FANCIFY_REPLACEMENTS}


def fancify(text, replacements=FANCIFY_REPLACEMENTS):
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text

def unfancify(text, replacements=FANCIFY_REPLACEMENTS):
    return fancify(text, replacements=replacements)


class FancifyingFormatter(Formatter):
    def format(self, record):
        return self.fancify(super().format(record))

    @staticmethod
    def fancify(s):
        return fancify(s)

class UnfancifyingFormatter(FancifyingFormatter):
    @staticmethod
    def fancify(s):
        return unfancify(s)


class FancifyingWrapper:
    def __init__(self, stream):
        self.stream = stream

    def write(self, s):
        self.stream.write(self.fancify(s))

    @staticmethod
    def fancify(s):
        return fancify(s)

class UnfancifyingWrapper(FancifyingWrapper):
    @staticmethod
    def fancify(s):
        return unfancify(s)

if stdout.isatty():
    fancifying_stdout = FancifyingWrapper(stdout)
else:
    fancifying_stdout = UnfancifyingWrapper(stdout)

def fancifying_print(*args, file=fancifying_stdout, **kwargs):
    return print(*args, file=file, **kwargs)

