"""
This module manages local features of jeolm project.
"""

import shutil
from contextlib import contextmanager, suppress
import dbm.gnu
import shelve

from pathlib import Path, PurePosixPath

import logging
logger = logging.getLogger(__name__) # pylint: disable=invalid-name


class RootNotFoundError(FileNotFoundError):
    pass


class LocalManager:
    """
    This class manages local features related to a jeolm project.

    Features include build and source directory, local module (if it
    exists) and Driver class defined (or not defined) in this module.

    Attributes:
      root (Path):
        the toplevel directory of a project.
      build_dir (Path):
        directory for files created in build process. All files created by
        jeolm in any mode should be restricted to this directory (and
        nested directories). Exceptions include source files recreated by
        'jeolm init' and symbolic links in toplevel.
      source_dir (Path):
        directory for source files of project. 'jeolm' in any mode should
        not modify any of these files. Exception is 'jeolm init'.
      local_module (module or None):
        local module of jeolm project, loaded from '.jeolm/local.py'.
      driver_class (type):
        Either Driver class from local module or a jeolm.driver.regular.Driver.
    """

    def __init__(self, root=None):
        """
        Find jeolm root and initialize an instance.

        Args:
          root (Path or str, optional): predefined jeolm root.

        If root argument is given, check corresponding directory for presence
        of required paths (see documentation of is_root() method). Otherwise,
        try current working directory, then its parent, etc.

        Check for presence of source/ and .jeolm/ directories.
        Create the build/ directory, if it does not exist.

        Raises:
          RootNotFoundError: If root argument is given and check failed, or if
            root argument is not given and root is not found when walking up
            the filesystem.
          NotADirectoryError:
            if one of build/, source/ or .jeolm/ paths exists but is not a
            directory.
          FileNotFoundError:
            if source/ or .jeolm/ path does not exist.
        """
        if root is not None:
            root = Path(root)
            try:
                root = root.resolve()
            except FileNotFoundError as error:
                raise RootNotFoundError(root) from error
            else:
                if not self.is_root(root):
                    raise RootNotFoundError(root)
        else:
            root = Path.cwd()
            while len(root.parts) > 1:
                if self.is_root(root):
                    break
                root = root.parent
            else:
                raise RootNotFoundError()
        self.root = root
        self.jeolm_dir = self._init_jeolm_dir()
        self.source_dir = self._init_source_dir()
        self.build_dir = self._init_build_dir()
        self._local_module = None

    @classmethod
    def is_root(cls, root):
        """
        Test if the directory may be jeolm root.

        Check for presence of '.jeolm' path.

        Args:
          root (Path): proposed jeolm root

        Return:
          bool: True if root may be jeolm root, False otherwise.
        """
        if not isinstance(root, Path):
            raise TypeError( "Expected pathlib.Path instance, got {!r}"
                .format(type(Path)) )
        return (root / '.jeolm').exists()

    def _init_jeolm_dir(self):
        jeolm_dir = self._jeolm_dir_path
        if not jeolm_dir.exists():
            raise FileNotFoundError(str(jeolm_dir))
        if not jeolm_dir.is_dir():
            raise NotADirectoryError(str(jeolm_dir))
        return jeolm_dir

    @property
    def _jeolm_dir_path(self):
        return self.root / '.jeolm'

    def _init_source_dir(self):
        source_dir = self._source_dir_path
        if not source_dir.exists():
            raise FileNotFoundError(str(source_dir))
        if not source_dir.is_dir():
            raise NotADirectoryError(str(source_dir))
        return source_dir

    @property
    def _source_dir_path(self):
        return self.root / 'source'

    def _init_build_dir(self):
        build_dir = self._build_dir_path
        if not build_dir.exists():
            build_dir.mkdir(parents=False)
        elif not build_dir.is_dir():
            raise NotADirectoryError(str(build_dir))
        return build_dir

    @property
    def _build_dir_path(self):
        return self.root / 'build'

    @property
    def local_module(self):
        if self._local_module is None:
            self._load_local_module()
        assert self._local_module is not None
        if self._local_module is False:
            return None
        else:
            return self._local_module

    def _load_local_module(self, *, module_name=None):
        assert self._local_module is None, self._local_module

        module_path = self.jeolm_dir / 'local.py'
        if not module_path.exists():
            self._local_module = False
            return

        import importlib.machinery
        if module_name is None:
            # We most probably exclude the possibility of loading module with
            # normal import statement by inserting strange characters in module
            # name.
            module_name = 'jeolm.local_module:{}'.format(self.root)
        loader = importlib.machinery.SourceFileLoader(
            module_name, str(module_path) )
        self._local_module = loader.load_module()
        logger.debug("Loaded '{}' as module '{}'"
            .format(module_path, module_name) )

    @property
    def driver_class(self):
        local_module = self.local_module
        assert not isinstance(local_module, bool)
        if local_module is not None:
            with suppress(AttributeError):
                return local_module.Driver
        import jeolm.driver.regular
        return jeolm.driver.regular.Driver

    @contextmanager
    def open_text_node_shelf(self):
        shelf_db = dbm.gnu.open(str(self.build_dir / 'textnodes.db'), 'cf')
        with shelve.Shelf(shelf_db) as shelf:
            yield shelf

def report_missing_root():
    logger.critical(
        "<BOLD>Missing <RED>.jeolm<NOCOLOUR> path "
        "that would indicate a jeolm project." )


class InitLocalManager(LocalManager):
    def __init__(self, root=None, resources=()):
        if root is None:
            root = Path.cwd()
        super().__init__(root=root)
        self._resource_tables_cache = None
        for resource_name in resources:
            self.fetch_resource(resource_name)

    @classmethod
    def is_root(cls, root):
        return root.exists()

    def _init_source_dir(self):
        source_dir = self._source_dir_path
        if not source_dir.exists():
            source_dir.mkdir(parents=False)
        return super()._init_source_dir()

    def _init_jeolm_dir(self):
        jeolm_dir = self._jeolm_dir_path
        if not jeolm_dir.exists():
            jeolm_dir.mkdir(parents=False)
        return super()._init_jeolm_dir()

    def fetch_resource(self, resource_name):
        resource_table = self._resource_tables[resource_name]
        for destination, source_name in resource_table.items():
            source_subpath = PurePosixPath(source_name)
            if (
                source_subpath.is_absolute() or
                len(source_subpath.parts) > 1 or '..' in source_subpath.parts
            ):
                raise RuntimeError(source_name)
            source_path = self._resource_dir_path / source_name
            destination_subpath = PurePosixPath(destination)
            if (
                destination_subpath.is_absolute() or
                '..' in destination_subpath.parts
            ):
                raise RuntimeError(destination)
            destination_path = self.root / destination_subpath
            if not destination_path.parent.exists():
                destination_path.parent.mkdir(parents=True)
            if destination_path.is_dir():
                raise IsADirectoryError()
            shutil.copyfile(str(source_path), str(destination_path))

    _resource_dir_path = Path(__file__).parent / 'resources'
    _resource_manifest_path = _resource_dir_path / 'MANIFEST.yaml'

    @property
    def _resource_tables(self):
        if self._resource_tables_cache is not None:
            return self._resource_tables_cache
        import yaml
        with self._resource_manifest_path.open() as manifest_file:
            resource_tables = self._resource_tables_cache = (
                yaml.load(manifest_file) )
            return resource_tables

