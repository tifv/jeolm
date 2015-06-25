import sys

# Terminal colour codes
# http://en.wikipedia.org/wiki/ANSI_escape_code#Colors
FANCIFY_REPLACEMENTS = (
    ('<RESET>',    '\033[0m'),
    ('<NOCOLOUR>', '\033[39m'),

    ('<BOLD>',     '\033[1m'),
    ('<REGULAR>',  '\033[22m'),

    ('<ITALIC>',   '\033[3m'),
    ('<UPRIGHT>',  '\033[23m'),

    ('<BLACK>',    '\033[30m'),
    ('<RED>',      '\033[31m'),
    ('<GREEN>',    '\033[32m'),
    ('<YELLOW>',   '\033[33m'),
    ('<BLUE>',     '\033[34m'),
    ('<MAGENTA>',  '\033[35m'),
    ('<CYAN>',     '\033[36m'),
    ('<WHITE>',    '\033[37m'),
)
UNFANCIFY_REPLACEMENTS = tuple(
    (key, '')
    for key, value in FANCIFY_REPLACEMENTS )

def fancify(text, replacements=FANCIFY_REPLACEMENTS):
    for key, value in replacements:
        text = text.replace(key, value)
    return text

def unfancify(text, replacements=UNFANCIFY_REPLACEMENTS):
    return fancify(text, replacements=replacements)

class FancifyingWrapper:
    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        self.stream.write(self.fancify(text))

    @staticmethod
    def fancify(text):
        return fancify(text)

class UnfancifyingWrapper(FancifyingWrapper):
    @staticmethod
    def fancify(text):
        return unfancify(text)

def fancifying_print(*args, file=FancifyingWrapper(sys.stdout), **kwargs):
    return print(*args, file=file, **kwargs)

def unfancifying_print(*args, file=UnfancifyingWrapper(sys.stdout), **kwargs):
    return print(*args, file=file, **kwargs)

