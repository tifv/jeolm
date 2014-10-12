from collections import OrderedDict
from contextlib import contextmanager
from itertools import chain

import difflib

from jeolm import yaml
from jeolm.records import RecordsManager

import logging
logger = logging.getLogger(__name__) # pylint: disable=invalid-name

@contextmanager
def log_metadata_diff(md, logger=logger):
    old_metarecords = RecordsManager()
    md.feed_metadata(old_metarecords, warn_dropped_keys=False)

    yield

    new_metarecords = RecordsManager()
    md.feed_metadata(new_metarecords)

    comparing_iterator = RecordsManager.compare_items(
        old_metarecords, new_metarecords, wipe_subrecords=True )
    for inpath, old_record, new_record in comparing_iterator:
        assert old_record is not None or new_record is not None, inpath
        if old_record == new_record:
            continue
        old_dump = yaml.dump(old_record, default_flow_style=False).splitlines()
        new_dump = yaml.dump(new_record, default_flow_style=False).splitlines()
        if old_record is None:
            header = ( '<BOLD><GREEN>{}<NOCOLOUR> metarecord added<RESET>'
                .format(inpath) )
            old_dump = []
        elif new_record is None:
            header = ( '<BOLD><RED>{}<NOCOLOUR> metarecord removed<RESET>'
                .format(inpath) )
            new_dump = []
        else:
            header = ( '<BOLD><YELLOW>{}<NOCOLOUR> metarecord changed<RESET>'
                .format(inpath) )
        delta = difflib.ndiff(a=old_dump, b=new_dump)
        lines = format_ndiff_delta(delta, fix_newlines=True)
        logger.info('\n'.join(chain((header,), lines)))

def format_delta(delta, *, line_formats, fix_newlines=False):
    for line in delta:
        if fix_newlines and line.endswith('\n'):
            line = line[:-1]
        for prefix, fmt in line_formats.items():
            if line.startswith(prefix):
                if fmt is not None:
                    yield fmt.format(line)
                break
        else:
            raise RuntimeError(
                "line_formats does not describe delta line '{}'"
                .format(line) )

NDIFF_LINE_FORMATS = OrderedDict((
    ('  ', '{}'),
    ('- ', '<RED>{}<RESET>'),
    ('+ ', '<GREEN>{}<RESET>'),
    ('? ', '<MAGENTA>{}<RESET>'),
))

def format_ndiff_delta(delta, **kwargs):
    return format_delta( delta,
        line_formats=NDIFF_LINE_FORMATS, **kwargs )

UNIFIED_DIFF_LINE_FORMATS = OrderedDict((
    (' ', '{}'),
    ('--- ', '<RED><BOLD>{}<RESET>'),
    ('+++ ', '<GREEN><BOLD>{}<RESET>'),
    ('-', '<RED>{}<RESET>'),
    ('+', '<GREEN>{}<RESET>'),
    ('@', '<MAGENTA>{}<RESET>'),
))

def format_unified_diff_delta(delta, **kwargs):
    return format_delta( delta,
        line_formats=UNIFIED_DIFF_LINE_FORMATS, **kwargs )

