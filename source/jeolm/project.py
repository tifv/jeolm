"""
This module manages filesystem-related properties of a jeolm project.
"""

import shutil
from contextlib import suppress

from pathlib import PosixPath, PurePosixPath

import jeolm

import logging
logger = logging.getLogger(__name__)

import typing
from typing import Type, Union, Optional, Any, Sequence, Dict
if typing.TYPE_CHECKING:
    import jeolm.driver
    import jeolm.metadata


# pylint: disable=unbalanced-tuple-unpacking

def _get_jeolm_package_path() -> PosixPath:
    path_s, = jeolm.__path__ # type: ignore
    return PosixPath(path_s)

# pylint: enable=unbalanced-tuple-unpacking


class RootNotFoundError(FileNotFoundError):
    pass


class Project:
    """
    This class manages filesystem-related properties of a jeolm project.

    Properties include build and source directory and local module (if it
    exists). Also, implementations of Driver and Metadata class relevant
    to the jeolm project are provided.

    Attributes:
      root (PosixPath):
        the toplevel directory of a project.
      build_dir (PosixPath):
        directory for files created in build process. All files created by
        jeolm in any mode should be restricted to this directory (and
        nested directories). Exceptions are source files recreated by
        'jeolm init' and symbolic links in toplevel.
      source_dir (PosixPath):
        directory for source files of project. 'jeolm' in any mode should
        not modify any of these files. Exception is 'jeolm init'.
      local_module (module or None):
        local module of jeolm project, loaded from '.jeolm/local.py'.
      driver_class (type):
        Either Driver class from local_module or
        jeolm.driver.regular.RegularDriver.
      metadata_class (type):
        Either Metadata class from local_module or
        jeolm.metadata.Metadata.
    """

    root: PosixPath
    jeolm_dir: PosixPath
    build_dir: PosixPath
    source_dir: PosixPath
    driver_class: Type['jeolm.driver.Driver']
    metadata_class: Type['jeolm.metadata.Metadata']
    _local_module_loaded: bool
    _local_module: Optional[Any]

    def __init__(self, root: Union[None, str, PosixPath] = None) -> None:
        """
        Find jeolm root and initialize an instance.

        Args:
          root (PosixPath or str, optional): predefined jeolm root.

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
            root_path = PosixPath(root)
            try:
                root_path = root_path.resolve()
            except FileNotFoundError as error:
                raise RootNotFoundError(root_path) from error
            else:
                if not self.is_root(root_path):
                    raise RootNotFoundError(root_path)
        else:
            root_path = PosixPath.cwd()
            while len(root_path.parts) > 1:
                if self.is_root(root_path):
                    break
                root_path = root_path.parent
            else:
                raise RootNotFoundError()
        self.root = root_path
        self.jeolm_dir = self._init_jeolm_dir()
        self.source_dir = self._init_source_dir()
        self.build_dir = self._init_build_dir()
        self._local_module_loaded = False
        self._local_module = None

    @classmethod
    def is_root(cls, root: PosixPath) -> bool:
        """
        Test if the directory may be jeolm root.

        Check for presence of '.jeolm' path.

        Args:
          root (PosixPath): proposed jeolm root

        Return:
          bool: True if root may be jeolm root, False otherwise.
        """
        if not isinstance(root, PosixPath):
            raise TypeError( "Expected pathlib.PosixPath instance, got {!r}"
                .format(type(PosixPath)) )
        return (root / '.jeolm').exists()

    def _init_jeolm_dir(self) -> PosixPath:
        jeolm_dir = self._jeolm_dir_path
        if not jeolm_dir.exists():
            raise FileNotFoundError(str(jeolm_dir))
        if not jeolm_dir.is_dir():
            raise NotADirectoryError(str(jeolm_dir))
        return jeolm_dir

    @property
    def _jeolm_dir_path(self) -> PosixPath:
        return self.root / '.jeolm'

    def _init_source_dir(self) -> PosixPath:
        source_dir = self._source_dir_path
        if not source_dir.exists():
            raise FileNotFoundError(str(source_dir))
        if not source_dir.is_dir():
            raise NotADirectoryError(str(source_dir))
        return source_dir

    @property
    def _source_dir_path(self) -> PosixPath:
        return self.root / 'source'

    def _init_build_dir(self) -> PosixPath:
        build_dir = self._build_dir_path
        if not build_dir.exists():
            build_dir.mkdir(parents=False)
        elif not build_dir.is_dir():
            raise NotADirectoryError(str(build_dir))
        return build_dir

    @property
    def _build_dir_path(self) -> PosixPath:
        return self.root / 'build'

    @property
    def local_module(self) -> Optional[Any]:
        if not self._local_module_loaded:
            self._load_local_module()
        assert self._local_module_loaded
        return self._local_module

    def _load_local_module( self,
        *, module_name: Optional[str] = None
    ) -> None:
        assert not self._local_module_loaded

        module_path: PosixPath = self.jeolm_dir / 'local.py'
        if not module_path.exists():
            self._local_module_loaded = True
            return

        import importlib.util
        if module_name is None:
            # Exclude the possibility of loading module with normal
            # import statement by inserting '/' and ':' characters
            # in module name.
            module_name = 'jeolm.local_module:{}'.format(self.root)
        spec = importlib.util.spec_from_file_location( # type: ignore
            module_name, module_path )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module) # type: ignore
        self._local_module = module
        self._local_module_loaded = True
        logger.debug( "Loaded '%(path)s' as module '%(name)s'",
            dict(path=module_path, name=module_name) )

    @property
    def driver_class(self) -> Type['jeolm.driver.Driver']:
        local_module = self.local_module
        if local_module is not None:
            with suppress(AttributeError):
                return local_module.Driver
        from jeolm.driver.regular import RegularDriver
        return RegularDriver

    @property
    def metadata_class(self) -> Type['jeolm.metadata.Metadata']:
        local_module = self.local_module
        if local_module is not None:
            with suppress(AttributeError):
                return local_module.Metadata
        from jeolm.metadata import Metadata
        return Metadata


def report_missing_root() -> None:
    logger.critical(
        "Missing <RED>.jeolm<NOCOLOUR> path "
        "that would indicate a jeolm project." )


class InitProject(Project):

    _resource_tables_cache: Optional[Dict[str, Dict[str, str]]]

    def __init__( self, root: PosixPath,
        resources: Sequence[str] = ()
    ) -> None:
        assert isinstance(root, PosixPath)
        super().__init__(root=root)
        self._resource_tables_cache = None
        for resource_name in resources:
            self.fetch_resource(resource_name)

    @classmethod
    def is_root(cls, root: PosixPath) -> bool:
        return root.exists()

    def _init_source_dir(self) -> PosixPath:
        source_dir = self._source_dir_path
        if not source_dir.exists():
            source_dir.mkdir(parents=False)
        return super()._init_source_dir()

    def _init_jeolm_dir(self) -> PosixPath:
        jeolm_dir = self._jeolm_dir_path
        if not jeolm_dir.exists():
            jeolm_dir.mkdir(parents=False)
        return super()._init_jeolm_dir()

    def fetch_resource(self, resource_name: str) -> None:
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
            destination_path: PosixPath = self.root / destination_subpath
            if not destination_path.parent.exists():
                destination_path.parent.mkdir(parents=True)
            if destination_path.is_dir():
                raise IsADirectoryError(str(destination))
            if destination_path.is_symlink():
                destination_path.unlink()
            shutil.copyfile(str(source_path), str(destination_path))

    _resource_dir_path = PosixPath(_get_jeolm_package_path(), 'resources')
    _resource_manifest_path = PosixPath(_resource_dir_path, 'RESOURCES.yaml')

    @property
    def _resource_tables(self) -> Dict[str, Dict[str, str]]:
        if self._resource_tables_cache is not None:
            return self._resource_tables_cache
        resource_tables = self._resource_tables_cache = \
            self._load_resource_tables()
        return resource_tables

    @classmethod
    def _load_resource_tables(cls) -> Dict[str, Dict[str, str]]:
        import yaml
        with cls._resource_manifest_path.open(encoding='utf-8') \
                as manifest_file:
            return yaml.safe_load(manifest_file)

