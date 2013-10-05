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
                root = root.parent()
            else:
                self.report_failed_check()
                raise RootNotFoundError()
        self.root = root
        self.build_dir = self.root/'build'
        self.source_dir = self.root/'source'
        self.inrecords_path = self.root/'.jeolm/in.yaml'
        self.metarecords_cache_path = self.build_dir/'meta.cache.yaml'
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
            path.relative(self.root)
            for path in self.iter_broken_links(self.root, recursive=False) }
        if broken_links:
            logger.warning(
                '<BOLD>Found broken links: {}<RESET>'.format(', '.join(
                    "'<YELLOW>{}<NOCOLOUR>'".format(x)
                    for x in sorted(broken_links)
                )) )

    @classmethod
    def iter_broken_links(cls, root, *, recursive):
        for path in root:
            if not path.exists():
                yield path
                continue
            if recursive and path.is_dir():
                yield from cls.iter_broken_links(path, recursive=recursive)

    @classmethod
    def clean_broken_links(cls, root, *, recursive):
        trash = list(cls.iter_broken_links(root, recursive=recursive))
        for path in trash:
            logger.info("Removing broken link at '{}'"
                .format(path.relative(root)) )
            path.unlink()

    def get_driver(self):
        """
        Return driver.
        """
        Driver = self.get_driver_class()
        inrecords = self.load_inrecords()
        outrecords = self.load_outrecords()
        return Driver(inrecords, outrecords)

    def get_driver_class(self):
        """
        Return appropriate Driver class.
        """
        Driver = self.get_local_driver_class()
        if Driver is None:
            from jeolm.driver import Driver
        return Driver

    def get_local_driver_class(self):
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

    def get_reviewer(self):
        """
        Return inrecord reviewer.
        """
        InrecordReviewer = self.get_reviewer_class()
        return InrecordReviewer(fsmanager=self)

    def get_reviewer_class(self):
        """
        Return appropriate InrecordReviewer class.
        """
        InrecordReviewer = self.get_local_reviewer_class()
        if InrecordReviewer is None:
            from jeolm.inrecords import InrecordReviewer
        return InrecordReviewer

    def get_local_reviewer_class(self):
        """
        Return InrecordReviewer class from local_module, or None.
        """
        local_module = self.load_local_module()
        if local_module is None:
            return None
        try:
            return local_module.InrecordReviewer
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

    def load_inrecords(self):
        try:
            with self.inrecords_path.open('r') as f:
                s = f.read()
        except FileNotFoundError:
            from collections import OrderedDict
            return OrderedDict()
        else:
            from jeolm.yaml import load
            return load(s)

    def dump_inrecords(self, inrecords):
        from jeolm import yaml
        s = yaml.dump(inrecords, default_flow_style=False)
        new_path = Path('.in.yaml.new')
        with new_path.open('w') as f:
            f.write(s)
        new_path.rename(self.inrecords_path)

    def load_outrecords(self):
        from jeolm.yaml import load
        outrecords = {}
        for outrecords_path in self.list_outrecords_paths():
            with outrecords_path.open('r') as f:
                s = f.read()
            outrecords.update(load(s))
        return outrecords

    def list_outrecords_paths(self):
        yield from self._list_outrecords_paths(self.root)

    @staticmethod
    @lru_cache()
    def _list_outrecords_paths(root):
        return [ path
            for path in root/'.jeolm'
            if path.name == 'out.yaml' or path.name.endswith('.out.yaml')
        ]

    def load_metarecords_cache(self):
        try:
            with self.metarecords_cache_path.open('r') as f:
                s = f.read()
        except FileNotFoundError:
            return {}
        else:
            from jeolm.yaml import load
            return load(s)

    def dump_metarecords_cache(self, metarecords_cache):
        self.ensure_build_dir()
        from jeolm import yaml
        s = yaml.dump(metarecords_cache, default_flow_style=False)
        new_path = Path('.meta.cache.yaml.new')
        with new_path.open('w') as f:
            f.write(s)
        new_path.rename(self.metarecords_cache_path)

    def load_updated_completion_cache(self):
        cache_path = self.completion_cache_path
        if not cache_path.exists():
            return None
        if cache_path.st_mtime_ns <= self.records_mtime:
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
    def records_mtime(self):
        mtimes = [self.inrecords_path.st_mtime_ns]
        mtimes.extend(outrecords_path.st_mtime_ns
            for outrecords_path in self.list_outrecords_paths() )
        return max(mtimes)

    def ensure_build_dir(self):
        if self.build_dir.exists():
            if self.build_dir.is_symlink() or not self.build_dir.is_dir():
                raise NotADirectoryError(str(self.build_dir))
        else:
            self.build_dir.mkdir(mode=0b111101101, parents=False)

