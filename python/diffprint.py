from collections import OrderedDict
from jeolm import difflogger

UNIFIED_DIFF_LINE_FORMATS = OrderedDict((
    ('--- ', '<RED><BOLD>{}<RESET>'),
    ('+++ ', '<GREEN><BOLD>{}<RESET>'),
    ('-', '<RED>{}<RESET>'),
    ('+', '<GREEN>{}<RESET>'),
    ('@', '<MAGENTA>{}<RESET>'),
    (' ', '{}'),
))

NDIFF_LINE_FORMATS = OrderedDict((
    ('- ', '<RED>{}<RESET>'),
    ('+ ', '<GREEN>{}<RESET>'),
    ('? ', '<MAGENTA>{}<RESET>'),
    ('  ', '{}'),
))

def print_delta(delta, *, line_formats, fix_newlines=False):
    for line in delta:
        if fix_newlines and line.endswith('\n'):
            line = line[:-1]
        for prefix, fmt in line_formats.items():
            if line.startswith(prefix):
                if fmt is not None:
                    difflogger.info(fmt.format(line))
                break
        else:
            raise RuntimeError(
                "line_formats does not describe delta line '{}'"
                .format(line) )

def print_ndiff_delta(delta, **kwargs):
    return print_delta( delta,
        line_formats=NDIFF_LINE_FORMATS, **kwargs )

def print_unified_diff_delta(delta, **kwargs):
    return print_delta( delta,
        line_formats=UNIFIED_DIFF_LINE_FORMATS, **kwargs )

