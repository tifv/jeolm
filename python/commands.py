"""
Miscellaneous and relatively simple commands, not deserving their own
module.
"""
import os
from contextlib import contextmanager
from subprocess import CalledProcessError

from pathlib import Path, PurePosixPath

import logging
logger = logging.getLogger(__name__)


##########
# High-level subprograms

@contextmanager
def print_metadata_diff(md):
    import difflib
    from . import yaml, diffprint
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
        diffprint.print_ndiff_delta(delta, fix_newlines=True)

def review(paths, *, fs, md, viewpoint=None, recursive=False):
    inpaths = resolve_inpaths(paths,
        source_dir=fs.source_dir, viewpoint=viewpoint )
    for inpath in inpaths:
        md.review(inpath, recursive=recursive)

def print_source_list(targets, *, fs, driver, viewpoint=None,
    source_type='tex'
):
    paths = list(list_sources(targets,
        fs=fs, driver=driver, source_type=source_type ))
    if viewpoint is not None:
        paths = [ path.relative_to(viewpoint)
            for path in paths ]
    for path in paths:
        print(path)

def check_spelling(targets, *, fs, driver, context=0):
    from . import spell
    from .spell import IncorrectWord
    from . import cleanlogger

    indicator_length = 0
    def indicator_clean():
        nonlocal indicator_length
        if indicator_length:
            print(' ' * indicator_length, end='\r')
        indicator_length = 0
    def indicator_show(s):
        nonlocal indicator_length
        print(s, end='\r')
        indicator_length = len(str(s))

    path_generator = list_sources(targets,
        fs=fs, driver=driver, source_type='tex' )
    for path in path_generator:
        indicator_clean()
        indicator_show(str(path))

        with path.open('r') as f:
            text = f.read()
        lines = ['']
        printed_line_numbers = set()
        try:
            for text_piece in spell.Speller(text, lang='ru_RU'):
                if isinstance(text_piece, IncorrectWord):
                    lineno = len(lines) - 1
                    printed_line_numbers.update(
                        range(lineno-context, lineno+context+1) )
                text_piece = str(text_piece).split('\n')
                lines[-1] += text_piece[0]
                for subpiece in text_piece[1:]:
                    lines.append(subpiece)
        except ValueError as error:
            raise ValueError(
                "Error while spell-checking {}"
                .format(path.relative_to(fs.root))
            ) from error
        if not printed_line_numbers:
            continue
        indicator_clean()
        cleanlogger.info(
            '<BOLD><YELLOW>{}<NOCOLOUR> possible misspellings<RESET>'
            .format(path.relative_to(fs.source_dir)) )
        line_range = range(len(lines))
        for lineno in sorted(printed_line_numbers):
            if lineno not in line_range:
                continue
            cleanlogger.info(
                '<MAGENTA>{}<NOCOLOUR>:{}'.format(lineno+1, lines[lineno]) )
    indicator_clean()

def clean(root):
    """
    Remove all symbolic links to 'build/*whatever*' from the toplevel.
    """
    assert isinstance(root, Path), root
    for x in root.iterdir():
        if not x.is_symlink():
            continue
        target = os.readlink(str(x))
        if target.startswith('build/'):
            x.unlink()


##########
# Supplementary subprograms

def simple_load_driver(fs):
    from jeolm.metadata import MetadataManager
    md = MetadataManager(fs=fs)
    md.load_metadata()
    return md.feed_metadata(fs.find_driver_class()())

def list_sources(targets, *, fs, driver, source_type='tex'):
    source_dir = fs.source_dir
    for target in driver.list_delegators(*targets, recursively=True):
        inpath_generator = driver.list_inpaths( target,
            inpath_type=source_type )
        for inpath in inpath_generator:
            yield source_dir/inpath

def resolve_inpaths(paths, *, source_dir, viewpoint=None):
    if viewpoint is not None:
        if not isinstance(viewpoint, Path) or not viewpoint.is_absolute():
            raise RuntimeError(viewpoint)
        paths = [Path(viewpoint, path) for path in paths]
    else:
        paths = [Path(path) for path in paths]
        for path in paths:
            if not path.is_absolute():
                raise RuntimeError(path)
    for path in paths:
        try:
            path = path.resolve()
        except FileNotFoundError:
            pass
            # TODO new version of resolve() (in 3.5) should solve this issue
        yield PurePosixPath(path).relative_to(source_dir)

@contextmanager
def refrain_called_process_error():
    try:
        yield
    except CalledProcessError as exception:
        if getattr(exception, 'reported', False):
            return
        logger.critical(
            "Command {exc.cmd} returned code {exc.returncode}"
            .format(exc=exception) )

