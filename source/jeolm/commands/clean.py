import os

from pathlib import Path

import logging
logger = logging.getLogger(__name__)


def clean_build_links(directory):
    """
    Remove all symbolic links to 'build/*whatever*' from the directory.
    """
    assert isinstance(directory, Path), directory
    for path in directory.iterdir():
        if not path.is_symlink():
            continue
        target = os.readlink(str(path))
        if target.startswith('build/'):
            path.unlink()

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

