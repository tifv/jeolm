import os

from pathlib import Path

import logging
logger = logging.getLogger(__name__)

def cleanview(root):
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

def unbuild(root):
    """
    Run cleanview() plus remove all generated build/**.dvi files
    """
    cleanview(root)
    _unbuild_recursive(root/'build', suffixes={'.dvi'})

def _unbuild_recursive(builddir, *, suffixes):
    for x in builddir:
        if x.is_symlink():
            continue;
        if x.is_dir():
            _unbuild_recursive(x, suffixes=suffixes)
            continue;
        if x.suffix not in suffixes:
            continue;
        x.unlink()

def print_source_list(targets, *, fsmanager, viewpoint, **kwargs):
    driver = fsmanager.get_driver()
    inpath_list = driver.list_inpaths(targets, **kwargs)
    source_dir = fsmanager.source_dir
    for inpath in inpath_list:
        print(str(
            (source_dir/inpath).relative(viewpoint) ))

def archive(*, fsmanager=None,
    target='archive', archive_name='archive.tar.xz', compression='xz'
):
    if fsmanager is None:
        import jeolm.filesystem
        fsmanager = jeolm.filesystem.FSManager()

    import jeolm.builder
    builder = jeolm.builder.Builder([target], fsmanager=fsmanager)
    builder.update()

    import tarfile
    from pathlib import PurePath

    root = fsmanager.root

    with tarfile.open(str(root/archive_name), 'w:' + compression) as af:

        def add(sourcepath, *alias_parts, suffix=None):
            aliaspath = PurePath(*alias_parts)
            if suffix is not None:
                aliaspath = aliaspath.with_suffix(suffix)
            return af.add(str(sourcepath), str(aliaspath))

        for name, node in builder.source_nodes.items():
            add(node.path, 'source', name)
        for metaname, node in builder.pdf_nodes.items():
            add(node.path, 'pdf', metaname, suffix='.pdf')
        for metaname, node in builder.autosource_nodes.items():
            add(node.path, 'autosource', metaname, suffix='.tex')
        for figname, node in builder.eps_nodes.items():
            add(node.path, 'eps', figname, suffix='.eps')
        fsmanager.populate_archive(af)

