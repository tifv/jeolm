import logging

from pathlib import Path

logger = logging.getLogger(__name__)

required_directories = frozenset(('meta', 'source', 'build', ))
required_meta_files = frozenset(('in.yaml', 'out.yaml', ))

# It is expected that nothing but this directories will be found on the
# toplevel.
expected_directories = required_directories.union(('misc', ))

# It is expected that nothing but this files will be found in the
# meta/ directory.
expected_meta_files = required_meta_files.union(('local.sty', 'local.py', ))
expected_meta_dirs = frozenset(('__pycache__', ))

def check_root(root):
    if not isinstance(root, Path):
        raise TypeError("Expected pathlib.Path instance, got {!s}"
            .format(type(Path)) )
    directories = {
        x.name for x in root
        if not x.is_symlink()
        if x.is_dir()
        if not x.name.startswith('.') }
    broken_links = {x.name for x in root if not x.exists()}
    if not required_directories.issubset(directories):
        return False
    meta_paths = {p for p in root['meta'] if not p.name.startswith('.')}
    meta_items = {i.name for i in meta_paths}
    meta_files = {i.name for i in meta_paths if i.is_file()}
    if not required_meta_files.issubset(meta_files):
        return False
    unexpected_directories = directories - expected_directories
    unexpected_meta_items = \
        (meta_files - expected_meta_files) | \
        (meta_items - meta_files - expected_meta_dirs)
    if broken_links:
        logger.warning("Found broken links: '{}'".format(
            "', '".join(sorted(broken_links))
        ))
    if unexpected_directories:
        logger.warning("Found unexpected directories: '{}'.".format(
            "', '".join(sorted(unexpected_directories))
        ))
    if unexpected_meta_items:
        logger.warning("Found unexpected items in 'meta/': '{}'.".format(
            "', '".join(sorted(unexpected_meta_items))
        ))
    return True

def find_root():
    root = Path.cwd()
    if not check_root(root):
        while len(root.parts) > 2:
            root, tail = root.parent(), root.name
            if tail not in expected_directories:
                continue
            if check_root(root):
                break
        else:
            return None
    return root

def load_localmodule(root, *, module_name='jeolm.local'):
    module_path = root['meta/local.py']
    if not module_path.exists():
        return None

    import importlib.machinery
    localmodule = importlib.machinery.SourceFileLoader(
        module_name, str(module_path)
    ).load_module()
    logger.debug("Loaded meta/local.py as '{}'".format(module_name))
    return localmodule

def repr_required():
    return ', '.join(["'{}/'".format(d) for d in required_directories] + ["'meta/{}'".format(f) for f in required_meta_files])

