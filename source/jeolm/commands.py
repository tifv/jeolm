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

def review(paths, *, local, md, viewpoint=None, recursive=False):
    inpaths = resolve_inpaths(paths,
        source_dir=local.source_dir, viewpoint=viewpoint )
    for inpath in inpaths:
        md.review(inpath, recursive=recursive)

def print_source_list(targets, *, local, driver, viewpoint=None,
    source_type='tex'
):
    paths = list(list_sources(targets,
        local=local, driver=driver, source_type=source_type ))
    if viewpoint is not None:
        paths = [ path.relative_to(viewpoint)
            for path in paths ]
    for path in paths:
        print(path)

def check_spelling(targets, *, local, driver, context=0, colour=True):
    from . import spell
    from .spell import LaTeXSpeller, CorrectWord, IncorrectWord
    if colour:
        from .fancify import fancifying_print as fprint
    else:
        logger.warn('Spelling is nearly useless in colourless mode.')
        from .fancify import unfancifying_print as fprint

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
    def piece_to_string(piece):
        if isinstance(piece, CorrectWord):
            return '<GREEN>{}<NOCOLOUR>'.format(piece.s)
        elif isinstance(piece, IncorrectWord):
            return '<RED>{}<NOCOLOUR>'.format(piece.s)
        else:
            return piece.s

    path_generator = list_sources(targets,
        local=local, driver=driver, source_type='tex' )
    for path in path_generator:
        indicator_clean()
        indicator_show(str(path))

        with path.open('r') as f:
            text = f.read()
        lines = ['']
        printed_line_numbers = set()
        try:
            for piece in spell.LaTeXSpeller(text, lang='ru_RU'):
                if isinstance(piece, IncorrectWord):
                    lineno = len(lines) - 1
                    printed_line_numbers.update(
                        range(lineno-context, lineno+context+1) )
                piece_sl = piece_to_string(piece).split('\n')
                lines[-1] += piece_sl[0]
                for subpiece in piece_sl[1:]:
                    lines.append(subpiece)
        except ValueError as error:
            raise ValueError(
                "Error while spell-checking {}"
                .format(path.relative_to(local.source_dir))
            ) from error
        if not printed_line_numbers:
            continue
        indicator_clean()
        fprint(
            '<BOLD><YELLOW>{}<NOCOLOUR> possible misspellings<RESET>'
            .format(path.relative_to(local.source_dir)) )
        line_range = range(len(lines))
        lineno_offset = len(str(len(lines)))
        for lineno in sorted(printed_line_numbers):
            if lineno not in line_range:
                continue
            fprint(
                '<MAGENTA>{lineno: >{lineno_offset}}<NOCOLOUR>:{line}'
                .format( lineno=lineno+1, lineno_offset=lineno_offset,
                    line=lines[lineno] )
            )
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

def simple_load_driver(local):
    from jeolm.metadata import MetadataManager
    md = MetadataManager(local=local)
    md.load_metadata_cache()
    return md.feed_metadata(local.driver_class())

def list_sources(targets, *, local, driver, source_type='tex'):
    source_dir = local.source_dir
    for target in driver.list_delegated_targets(*targets, recursively=True):
        inpath_generator = driver.list_inpaths(
            target.flags_clean_copy(origin='target'),
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
    """
    Silence CalledProcessError, avoiding unnecessary traceback print.

    Experiencing subprocess.CalledProcessError usually means error in
    external application, so Python traceback is usually useless.
    """
    try:
        yield
    except CalledProcessError as exception:
        if getattr(exception, 'reported', False):
            return
        logger.critical(
            "Command {exc.cmd} returned code {exc.returncode}"
            .format(exc=exception) )

def iter_broken_links(directory, *, recursive):
    """
    Yield all paths in directory that are broken links.

    Args:
      directory (Path): directory to search for broken links.
      recursive (bool): if the search should dwell into subdirectories.

    Yields:
      Broken links in the directory. If recursive argument is true, then
      all subdirectories are also searched.

    Raises:
      FileNotFoundError: if the given directory does not exist.
    """
    if not isinstance(directory, Path):
        raise TypeError(type(directory))
    if not directory.exists():
        raise FileNotFoundError(directory)
    for path in directory.iterdir():
        if not path.exists():
            yield path
            continue
        if recursive and path.is_dir():
            yield from iter_broken_links(path, recursive=recursive)

def clean_broken_links(directory, *, recursive):
    """
    Unlink all paths in directory that are broken links.

    Args:
      directory (Path): directory to search for broken links.
      recursive (bool): if the search should dwell into subdirectories.

    Returns nothing. Removes all broken links in the directory.
    If recursive argument is true, then all subdirectories are also
    searched and cleaned.

    Raises:
      FileNotFoundError: if the given directory does not exist.
    """
    for path in iter_broken_links(directory, recursive=recursive):
        logger.info("Removing broken link at '{}'"
            .format(path) )
        path.unlink()

