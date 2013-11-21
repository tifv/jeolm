"""
Miscellaneous and relatively simple commands, not deserving their own
module.
"""
import os

from pathlib import Path, PurePosixPath as PurePath

import logging
logger = logging.getLogger(__name__)
from jeolm import difflogger

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

def print_source_list(targets, *, fsmanager, viewpoint, source_type):
    path_generator = list_sources(targets,
        fsmanager=fsmanager, source_type=source_type )
    for path in path_generator:
        print(path.relative_to(viewpoint))

def check_spelling(targets, *, fsmanager):
    from difflib import unified_diff as diff
    from .spell import prepare_original, correct

    path_generator = list_sources(targets,
        fsmanager=fsmanager, source_type='tex' )
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
    for path in path_generator:
        indicator_clean()
        indicator_show(str(path))

        with path.open('r') as f:
            original = f.read()
        original = prepare_original(original, lang='ru_RU')
        corrected = correct(original, lang='ru_RU')
        if original == corrected:
            continue
        indicator_clean()
        delta = diff(
            original.splitlines(), corrected.splitlines(),
            lineterm='', fromfile=path.relative_to(fsmanager.source_dir),
            tofile='*autocorrector*'
        )
        for line in delta:
            if line.startswith('--- '):
                difflogger.info('<YELLOW>*** <BOLD>{}<RESET>'.format(line[4:]))
            elif line.startswith('+++ '):
                pass
            elif line.startswith('-'):
                difflogger.info('<RED><BOLD>{}<RESET>'.format(line))
            elif line.startswith('+'):
                difflogger.info('<GREEN>{}<RESET>'.format(line))
            elif line.startswith('@'):
                difflogger.info('<MAGENTA>{}<RESET>'.format(line))
            else:
                difflogger.info(line)
    indicator_clean()

def review(paths, *, fsmanager, viewpoint, recursive):
    import difflib
    from . import yaml, diffprint

    inpaths = resolve_inpaths(paths,
        source_dir=fsmanager.source_dir, viewpoint=viewpoint )
    metadata_manager = fsmanager.get_metadata_manager()

    old_metarecords = metadata_manager.construct_metarecords()
    for inpath in inpaths:
        metadata_manager.review(inpath, recursive=recursive)
    new_metarecords = metadata_manager.construct_metarecords()
    Metarecords = type(old_metarecords)
    assert isinstance(new_metarecords, Metarecords)

    comparing_iterator = Metarecords.compare_items(
        old_metarecords, new_metarecords, wipe_subrecords=True )
    for inpath, old_record, new_record in comparing_iterator:
        assert old_record is not None or new_record is not None, inpath
        if old_record == new_record:
            continue
        old_dump = yaml.dump(old_record).splitlines()
        new_dump = yaml.dump(new_record).splitlines()
        if old_record is None:
            diffprint.difflogger.info(
                '<BOLD><GREEN>{}<NOCOLOUR> metarecord added<RESET>'
                .format(inpath) )
            old_dump = []
        elif new_record is None:
            diffprint.difflogger.info(
                '<BOLD><RED>{}<NOCOLOUR> metarecord removed<RESET>'
                .format(inpath) )
            new_dump = []
        else:
            diffprint.difflogger.info(
                '<BOLD><YELLOW>{}<NOCOLOUR> metarecord changed<RESET>'
                .format(inpath) )
        delta = difflib.ndiff(a=old_dump, b=new_dump)
        diffprint.print_ndiff_delta(delta, fix_newlines=True)

    fsmanager.dump_metadata(metadata_manager.records)

def list_sources(targets, *, fsmanager, source_type):
    driver = fsmanager.get_driver()
    source_dir = fsmanager.source_dir
    inpath_generator = driver.list_inpaths(targets, source_type=source_type)
    for inpath in inpath_generator:
        yield source_dir/inpath

def resolve_inpaths(inpaths, *, source_dir, viewpoint):
    assert isinstance(viewpoint, Path), viewpoint
    assert viewpoint.is_absolute(), viewpoint
    for inpath in inpaths:
        path = Path(viewpoint, inpath)
        try:
            path = path.resolve()
        except FileNotFoundError:
            pass
        yield PurePath(path).relative_to(source_dir)

