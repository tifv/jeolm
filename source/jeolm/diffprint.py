from collections import OrderedDict
from contextlib import contextmanager

from jeolm import cleanlogger

@contextmanager
def log_metadata_diff(md):
    import difflib
    from . import yaml
    from . import cleanlogger
    from .records import RecordsManager

    old_metarecords = RecordsManager()
    md.feed_metadata(old_metarecords)

    yield

    new_metarecords = RecordsManager()
    md.feed_metadata(new_metarecords)

    comparing_iterator = RecordsManager.compare_items(
        old_metarecords, new_metarecords, wipe_subrecords=True )
    for inpath, old_record, new_record in comparing_iterator:
        assert old_record is not None or new_record is not None, inpath
        if old_record == new_record:
            continue
        old_dump = yaml.dump(old_record).splitlines()
        new_dump = yaml.dump(new_record).splitlines()
        if old_record is None:
            cleanlogger.info(
                '<BOLD><GREEN>{}<NOCOLOUR> metarecord added<RESET>'
                .format(inpath) )
            old_dump = []
        elif new_record is None:
            cleanlogger.info(
                '<BOLD><RED>{}<NOCOLOUR> metarecord removed<RESET>'
                .format(inpath) )
            new_dump = []
        else:
            cleanlogger.info(
                '<BOLD><YELLOW>{}<NOCOLOUR> metarecord changed<RESET>'
                .format(inpath) )
        delta = difflib.ndiff(a=old_dump, b=new_dump)
        print_ndiff_delta(delta, fix_newlines=True)

def print_delta(delta, *, line_formats, fix_newlines=False):
    for line in delta:
        if fix_newlines and line.endswith('\n'):
            line = line[:-1]
        for prefix, fmt in line_formats.items():
            if line.startswith(prefix):
                if fmt is not None:
                    cleanlogger.info(fmt.format(line))
                break
        else:
            raise RuntimeError(
                "line_formats does not describe delta line '{}'"
                .format(line) )

NDIFF_LINE_FORMATS = OrderedDict((
    ('- ', '<RED>{}<RESET>'),
    ('+ ', '<GREEN>{}<RESET>'),
    ('? ', '<MAGENTA>{}<RESET>'),
    ('  ', '{}'),
))

def print_ndiff_delta(delta, **kwargs):
    return print_delta( delta,
        line_formats=NDIFF_LINE_FORMATS, **kwargs )

UNIFIED_DIFF_LINE_FORMATS = OrderedDict((
    ('--- ', '<RED><BOLD>{}<RESET>'),
    ('+++ ', '<GREEN><BOLD>{}<RESET>'),
    ('-', '<RED>{}<RESET>'),
    ('+', '<GREEN>{}<RESET>'),
    ('@', '<MAGENTA>{}<RESET>'),
    (' ', '{}'),
))

def print_unified_diff_delta(delta, **kwargs):
    return print_delta( delta,
        line_formats=UNIFIED_DIFF_LINE_FORMATS, **kwargs )

