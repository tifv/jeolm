from collections import OrderedDict
from contextlib import contextmanager
from itertools import chain

import difflib

import jeolm.yaml

from jeolm.driver import DriverRecords

import logging
logger = logging.getLogger(__name__)


class _Dumper(jeolm.yaml.JeolmDumper):
    def represent_Ellipsis(self, data):
        assert data is Ellipsis
        return self.represent_scalar( 'tag:yaml.org,2002:str',
            '\N{Horizontal Ellipsis}' )

_Dumper.add_representer(type(Ellipsis), _Dumper.represent_Ellipsis)

def _dump(data, Dumper=_Dumper, default_flow_style=False, **kwargs):
    return jeolm.yaml.dump( data,
        Dumper=Dumper, default_flow_style=default_flow_style, **kwargs )

@contextmanager
def log_metadata_diff(metadata, logger=logger):
    old_metarecords = DriverRecords()
    metadata.feed_metadata(old_metarecords)

    yield

    new_metarecords = DriverRecords()
    metadata.feed_metadata(new_metarecords)

    comparing_iterator = DriverRecords.compare_items(
        old_metarecords, new_metarecords, original=True )
    for inpath, old_record, new_record in comparing_iterator:
        old_record = old_record.copy() if old_record is not None else None
        new_record = new_record.copy() if new_record is not None else None
        _wipe_subrecords(old_record)
        _wipe_subrecords(new_record)
        _wipe_equal_large_keys(old_record, new_record)
        assert old_record is not None or new_record is not None, inpath
        if old_record == new_record:
            continue
        old_dump = _dump(old_record).splitlines()
        new_dump = _dump(new_record).splitlines()
        if old_record is None:
            header = ( '<BOLD><GREEN>{}<NOCOLOUR> metarecord added<REGULAR>'
                .format(inpath) )
            old_dump = []
        elif new_record is None:
            header = ( '<BOLD><RED>{}<NOCOLOUR> metarecord removed<REGULAR>'
                .format(inpath) )
            new_dump = []
        else:
            header = ( '<BOLD><YELLOW>{}<NOCOLOUR> metarecord changed<REGULAR>'
                .format(inpath) )
        delta = difflib.ndiff(a=old_dump, b=new_dump)
        lines = format_ndiff_delta(delta, fix_newlines=True)
        logger.info('\n'.join(chain((header,), lines)))

def _wipe_subrecords(record):
    if record is None:
        return
    for key in record:
        if key.startswith('$'):
            continue
        record[key] = Ellipsis
    return record

def _wipe_equal_large_keys(record1, record2):
    if record1 is None:
        record1 = {}
    if record2 is None:
        record2 = {}
    keys = set().union(record1, record2)
    for key in keys:
        if not key.startswith('$'):
            continue
        if not (record1.get(key) == record2.get(key) is not None):
            continue
        large_key = '$large' + key
        if record1.get(large_key, False) and record2.get(large_key, False):
            record1[key] = record2[key] = Ellipsis
            if record1[large_key] == record2[large_key]:
                record1.pop(large_key)
                record2.pop(large_key)

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

