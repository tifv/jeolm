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
    for x in root:
        if not x.is_symlink():
            continue;
        target = os.readlink(str(x))
        if target.startswith('build/'):
            x.unlink()

def print_source_list(targets, *, fsmanager, viewpoint, source_type):
    path_generator = list_sources(targets,
        fsmanager=fsmanager, source_type=source_type )
    for path in path_generator:
        print(path.relative(viewpoint))

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
            lineterm='', fromfile=path.relative(fsmanager.source_dir),
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
    from difflib import unified_diff as diff
    from . import yaml

    inpaths = resolve_inpaths(paths,
        source_dir=fsmanager.source_dir, viewpoint=viewpoint )
    metadata_manager = fsmanager.get_metadata_manager()

    old_dump = yaml.dump(metadata_manager.construct_metarecords().records)
    for inpath in inpaths:
        metadata_manager.review(inpath, recursive=recursive)

    new_dump = yaml.dump(metadata_manager.construct_metarecords().records)
    delta = diff(
        old_dump.splitlines(), new_dump.splitlines(), n=4,
        lineterm='', fromfile='old/metarecords.yaml', tofile='new/metarecords.yaml',
    )
    for line in delta:
        if line.startswith('--- '):
            pass
        elif line.startswith('+++ '):
            pass
        elif line.startswith('-'):
            difflogger.info('<RED>{}<RESET>'.format(line))
        elif line.startswith('+'):
            difflogger.info('<GREEN>{}<RESET>'.format(line))
        elif line.startswith('@'):
            difflogger.info('<MAGENTA>{}<RESET>'.format(line))
        else:
            difflogger.info(line)

    fsmanager.dump_metadata(metadata_manager.records)

def list_sources(targets, *, fsmanager, source_type):
    driver = fsmanager.get_driver()
    source_dir = fsmanager.source_dir
    inpath_generator = driver.list_inpaths(targets, source_type=source_type)
    for inpath in inpath_generator:
        yield source_dir/inpath

def resolve_inpaths(inpaths, *, source_dir, viewpoint):
    for inpath in inpaths:
        path = Path(viewpoint, inpath)
        try:
            path = path.resolve()
        except FileNotFoundError:
            pass
        yield PurePath(path).relative(source_dir)

