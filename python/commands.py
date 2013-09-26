import os

from pathlib import Path

import logging
logger = logging.getLogger(__name__)

def clean(root):
    """
    Remove all <root>/build/** symbolic links from the toplevel.
    """
    assert isinstance(root, Path), root
    for x in root:
        if not x.is_symlink():
            continue;
        target = os.readlink(str(x))
        if target.startswith('build/'):
            x.unlink()

def print_source_list(targets, *, fsmanager, viewpoint, **kwargs):
    driver = fsmanager.get_driver()
    inpath_list = driver.list_inpaths(targets, **kwargs)
    source_dir = fsmanager.source_dir
    for inpath in inpath_list:
        print(str(
            (source_dir/inpath).relative(viewpoint) ))

