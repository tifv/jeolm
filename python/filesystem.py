from functools import lru_cache

from pathlib import Path

import logging
logger = logging.getLogger(__name__)

class RootNotFoundError(Exception):
    pass

class FSManager:
    def __init__(self, root=None):
        if root is not None:
            try:
                root = Path(root).resolve()
            except FileNotFoundError:
                raise
            else:
                if not self.check_root(root):
                    self.report_failed_check()
                    raise RootNotFoundError(root)
        else:
            root = Path.cwd()
            # jeolm root can never be a filesystem root
            while len(root.parts) > 1:
                if self.check_root(root):
                    break
                root = root.parent
            else:
                self.report_failed_check()
                raise RootNotFoundError()
        self.root = root
        self.build_dir = self.root/'build'
        self.source_dir = self.root/'source'
        self.metadata_path = self.build_dir/'metadata.pickle'
        self.outrecords_cache_path = self.build_dir/'outrecords.cache.pickle'
        self.completion_cache_path = self.build_dir/'completion.cache.list'

    @classmethod
    def check_root(cls, root):
        if not isinstance(root, Path):
            raise TypeError("Expected pathlib.Path instance, got {!r}"
                .format(type(Path)) )
        jeolm_dir = root/'.jeolm'
        if not jeolm_dir.exists() or not jeolm_dir.is_dir():
            return False
        return True

    @classmethod
    def report_failed_check(cls):
        logger.critical(
            '<BOLD><RED>Missing directory and file layout '
            'required for jeolm.<RESET>' )
        logger.warning("<BOLD>Required layout: '.jeolm'<RESET>")

    def report_broken_links(self):
        broken_links = {
            path.relative_to(self.root)
            for path in self.iter_broken_links(self.root, recursive=False) }
        if broken_links:
            logger.warning(
                '<BOLD>Found broken links: {}<RESET>'.format(', '.join(
                    "'<YELLOW>{}<NOCOLOUR>'".format(x)
                    for x in sorted(broken_links)
                )) )

    @classmethod
    def iter_broken_links(cls, root, *, recursive):
        if not root.exists():
            return
        for path in root.iterdir():
            if not path.exists():
                yield path
                continue
            if recursive and path.is_dir():
                yield from cls.iter_broken_links(path, recursive=recursive)

    @classmethod
    def clean_broken_links(cls, root, *, recursive):
        for path in cls.iter_broken_links(root, recursive=recursive):
            logger.info("Removing broken link at '{}'"
                .format(path.relative_to(root)) )
            path.unlink()

#    def get_driver(self):
#        """
#        Return driver.
#        """
#        Driver = self.get_driver_class()
#        metarecords = self.load_metarecords()
#        return Driver(metarecords)

    def load_driver(self):
        metadata_manager = self.load_metadata_manager()
        Driver = self.find_driver_class()
        return metadata_manager.construct_metarecords(Metarecords=Driver)

    def find_driver_class(self):
        """
        Return appropriate Driver class.
        """
        Driver = self.find_local_driver_class()
        if Driver is None:
            from .driver.regular import Driver
        return Driver

    def find_local_driver_class(self):
        """
        Return Driver class from local_module, or None.

        Requires load_local_module() called beforehand.
        """
        local_module = self.load_local_module()
        if local_module is None:
            return None
        try:
            return local_module.Driver
        except AttributeError:
            return None

    def load_local_module(self, *, module_name='jeolm.local'):
        try:
            return self.local_module
        except AttributeError:
            pass

        module_path = self.root/'.jeolm/local.py'
        if not module_path.exists():
            self.local_module = None
            return None

        import importlib.machinery
        loader = importlib.machinery.SourceFileLoader(
            module_name, str(module_path) )
        self.local_module = local_module = loader.load_module()
        logger.debug("Loaded '.jeolm/local.py' as {} module"
            .format(module_name) )
        return local_module

    def load_metadata_manager(self):
        metadata = self.load_metadata()
        from .metadata import MetadataManager
        metadata_manager = MetadataManager(fsmanager=self)
        metadata_manager.merge(metadata)
        return metadata_manager

    def load_metadata(self):
        try:
            with self.metadata_path.open('rb') as f:
                s = f.read()
        except FileNotFoundError:
            return {}
        else:
            from pickle import loads
            return loads(s)

    def dump_metadata(self, metadata):
        self.ensure_build_dir()
        from pickle import dumps
        s = dumps(metadata)
        new_path = Path('.metadata.new')
        with new_path.open('wb') as f:
            f.write(s)
        new_path.rename(self.metadata_path)

    def load_outrecords_cache(self):
        try:
            with self.outrecords_cache_path.open('rb') as f:
                s = f.read()
        except FileNotFoundError:
            return {}
        else:
            from pickle import loads
            return loads(s)

    def dump_outrecords_cache(self, outrecords_cache):
        self.ensure_build_dir()
        from pickle import dumps
        s = dumps(outrecords_cache)
        new_path = Path('.outrecords.cache.new')
        with new_path.open('wb') as f:
            f.write(s)
        new_path.rename(self.outrecords_cache_path)

    def load_updated_completion_cache(self):
        cache_path = self.completion_cache_path
        if not cache_path.exists():
            return None
        if cache_path.stat().st_mtime_ns <= self.metadata_mtime:
            # Do not load if the cache is outdated
            return None
        from pathlib import PurePosixPath as PurePath
        with cache_path.open() as f:
            return [
                PurePath(x)
                for x in f.read().split('\n') if x != '' ]

    def dump_completion_cache(self, target_list):
        self.ensure_build_dir()
        s = '\n'.join(str(target) for target in target_list)
        new_path = Path('.completion.cache.list.new')
        with new_path.open('w') as f:
            f.write(s)
        new_path.rename(self.completion_cache_path)

    @property
    def metadata_mtime(self):
        try:
            return self.metadata_path.stat().st_mtime_ns
        except FileNotFoundError as error:
            raise FileNotFoundError(
                "No metadata (create it with 'jeolm review')" ) from error

    def ensure_build_dir(self):
        if self.build_dir.exists():
            if self.build_dir.is_symlink() or not self.build_dir.is_dir():
                raise NotADirectoryError(str(self.build_dir))
        else:
            self.build_dir.mkdir(mode=0b111101101, parents=False)

