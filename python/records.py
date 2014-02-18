from collections import OrderedDict

import pathlib
from pathlib import Path, PurePosixPath

from .utils import unique, dict_ordered_keys, dict_ordered_items

import logging
logger = logging.getLogger(__name__)

class RecordError(Exception):
    pass

class RecordNotFoundError(RecordError, LookupError):
    pass

class _RecordPathFlavour(pathlib._PosixFlavour):
    def parse_parts(self, parts):
        drv, root, parsed = super().parse_parts(parts)
        if root != '/':
            root = '/'
            parsed[0:0] = '/',
        while '..' in parsed:
            i = parsed.index('..')
            j = max(i-1, 1)
            del parsed[j:i+1]
        assert parsed[0] == '/' and '..' not in parsed, parsed
        return drv, root, parsed

class RecordPath(pathlib.PurePosixPath):
    _flavour = _RecordPathFlavour()

    def as_inpath(self, *, suffix=None):
        assert self.is_absolute(), repr(self)
        inpath = pathlib.PurePosixPath(*self.parts[1:])
        if suffix is not None:
            inpath = inpath.with_suffix(suffix)
        return inpath

    def __truediv__(self, other):
        return RecordPath(self, other)

    def __format__(self, fmt):
        if fmt == 'join':
            assert self.parts[0] == '/', self
            return '-'.join(self.parts[1:])
        return super().__format__(fmt)

class RecordsManager:
    Dict = OrderedDict

    def __init__(self):
        self.records = self.Dict()
        self._create_record(RecordPath(), self.records)
        self.cache = dict()

    def clear_cache(self):
        self.cache.clear()

    def merge(self, data, *, overwrite=True):
        self._merge(RecordPath(), self.records, data, overwrite=overwrite)
        self.clear_cache()

    def unmerge(self, path):
        if path.name == '':
            raise RuntimeError(path)
        self._destroy_record(path,
            self.getitem(path.parent, original=True).pop(path.name) )
        self.clear_cache()

    def clear(self, path=RecordPath()):
        self._clear_record(path, self.getitem(path, original=True))
        self.clear_cache()

    def reorder(self, path, sample):
        self.reorder_omap(self.getitem(path, original=True), sample)

    @staticmethod
    def reorder_omap(omap, sample):
        if not isinstance(omap, OrderedDict):
            raise RuntimeError(type(omap))
        swap = omap.copy()
        for key in dict_ordered_keys(sample):
            omap[key] = swap.pop(key)
        omap.update(swap)

    def _merge(self, path, record, data, *, overwrite=True):
        if data is None:
            return
        if not isinstance(data, dict):
            raise RecordError("Only able to merge a dict, found {!r}"
                .format(type(data)) )
        for key, value in dict_ordered_items(data):
            self._merge_item(path, record, key, value, overwrite=overwrite)

    def _merge_item(self, path, record, key, value, *, overwrite=True):
        if isinstance(key, RecordPath):
            if key == RecordPath():
                return self._merge( path, record, value,
                    overwrite=overwrite )
            return self._merge_item( path, record,
                key.parent, {key.name : value},
                overwrite=overwrite )
        elif isinstance(key, str):
            pass
        else:
            raise RecordError("Only able to merge string keys, found {!r}"
                .format(type(key)) )

        if key.startswith('$'):
            if overwrite or key not in record:
                record[key] = value
            else:
                pass # discard value
        else:
            child_record = record.get(key)
            if child_record is None:
                child_record = self._create_subrecord(path, record, key)
            self._merge(path/key, child_record, value, overwrite=overwrite)

    def _create_subrecord(self, path, record, key):
        child_record = record[key] = self.Dict()
        return self._create_record(path/key, child_record)

    def _create_record(self, path, record):
        # To insert the record in the parent
        # is the resposibility of caller!
        return record

    def _clear_record(self, path, record):
        while record:
            key, value = record.popitem()
            if key.startswith('$'):
                continue
            self._destroy_record(path/key, value)

    def _destroy_record(self, path, record):
        # To pop the record out of parent
        # is the resposibility of caller!
        self._clear_record(path, record)

    def getitem(self, path, *, original=False):
        if not isinstance(path, RecordPath):
            raise RuntimeError(type(path))
        use_cache = not original
        if use_cache:
            try:
                return self.cache[path]
            except KeyError:
                pass

        name = path.name
        if name == '':
            record = self._get_root(original=original)
        elif name.startswith('$'):
            raise ValueError(path)
        else:
            try:
                # Recurse, making use of cache
                parent_record = self.getitem(path.parent, original=original)
                record = self._get_child(parent_record, name, original=original)
            except RecordNotFoundError as error:
                if error.args == ():
                    raise RecordNotFoundError(
                        "Record {} not found".format(path) ) from None
                raise

        if use_cache:
            self.cache[path] = record
        return record

    def _get_root(self, original=False):
        record = self.records
        if not original:
            record = record.copy()
            self.derive_attributes({}, record, name=None)
        return record

    def _get_child(self, record, name, *, original=False):
        try:
            child_record = record[name]
        except KeyError:
            raise RecordNotFoundError from None
        assert isinstance(child_record, dict), child_record
        if not original:
            child_record = child_record.copy()
            self.derive_attributes(record, child_record, name)
        return child_record

    def derive_attributes(self, parent_record, child_record, name):
        pass

    def items(self, path=RecordPath()):
        """Yield (path, record) pairs."""
        record = self.getitem(path)
        yield path, record
        for key in dict_ordered_keys(record):
            if key.startswith('$'):
                continue
            yield from self.items(path=path/key)

    def keys(self, path=RecordPath()):
        """Yield paths."""
        for path, record in self.items():
            yield path

    def __contains__(self, path):
        try:
            self.getitem(path)
        except RecordNotFoundError:
            return False
        else:
            return True

    def __getitem__(self, path):
        return self.getitem(path)

    def get(self, path, default=None):
        try:
            return self.getitem(path)
        except RecordNotFoundError:
            return default

    @classmethod
    def compare_items(cls, records1, records2, path=RecordPath(),
        *, wipe_subrecords=False
    ):
        """
        Yield (path, record1, record2) triples.
        """

        record1 = records1.get(path)
        record2 = records2.get(path)
        if wipe_subrecords:
            record1 = cls._wipe_subrecords(record1)
            record2 = cls._wipe_subrecords(record2)
        yield path, record1, record2

        keys = unique(
            dict_ordered_keys(record1 if record1 is not None else {}),
            dict_ordered_keys(record2 if record2 is not None else {}) )
        for key in keys:
            if key.startswith('$'):
                continue
            yield from cls.compare_items(records1, records2, path/key,
                wipe_subrecords=wipe_subrecords )

    @classmethod
    def _wipe_subrecords(cls, record):
        if record is None:
            return record
        record = record.copy()
        for key in record:
            if not key.startswith('$'):
                record[key] = cls.Dict()
        return record

