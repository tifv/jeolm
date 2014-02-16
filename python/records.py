from collections import OrderedDict

import pathlib

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
        assert parsed[0] == '/', parsed
        while '..' in parsed:
            i = parsed.index('..')
            j = max(i-1, 1)
            del parsed[j:i+1]
        assert parsed[0] == '/' and '..' not in parsed, parsed
        return drv, root, parsed

class RecordPath(pathlib.PurePosixPath):
    _flavour = _RecordPathFlavour()

#    def _init(self):
#        self._root = '/'
#        while '..' in self._parts:
#            i = self._parts.index('..')
#            self._parts = self._parts[:i-1] + self._parts[i+1:]
#        assert '..' not in self._parts, repr(self)
#        super()._init()

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

class Records:
    Dict = OrderedDict

    def __init__(self):
        self.records = self.Dict()
        self.cache = dict()

    def clear_cache(self):
        self.cache.clear()

    def merge(self, piece, *, overwrite=True, record=None):
        if piece is None:
            return
        if not isinstance(piece, dict):
            raise TypeError(piece)
        if record is None:
            record = self.records
        for key, value in dict_ordered_items(piece):
            self._merge_item(key, value, overwrite=overwrite, record=record)

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

    def _merge_item(self, key, value, *, overwrite, record):
        if isinstance(key, RecordPath):
            return self.merge(value,
                record=self.getitem( key, record=record,
                    create_path=True, original=True ),
                overwrite=overwrite, )
        elif isinstance(key, str):
            pass
        else:
            raise TypeError(key)

        if key.startswith('$'):
            if key not in record or overwrite:
                record[key] = value
                self.clear_cache()
            else:
                pass # discard value
        else:
            child_record = record.get(key)
            if child_record is None:
                child_record = record[key] = self.Dict()
                self.clear_cache()
            self.merge(value, overwrite=overwrite, record=child_record)

    def getitem(self, path, *, record=None,
        create_path=False, original=False
    ):
        if not isinstance(path, RecordPath):
            raise RuntimeError(type(path))
        use_cache = record is None and not create_path and not original
        if use_cache:
            try:
                return self.cache[path]
            except KeyError:
                pass

        name = path.name
        if name == '':
            if record is None:
                record = self.get_root(
                    create_path=create_path, original=original )
        elif name.startswith('$'):
            raise ValueError(path)
        else:
            try:
                # Recurse, making use of cache
                parent_record = self.getitem(path.parent, record=record,
                    create_path=create_path, original=original )
                record = self._get_child(parent_record, name,
                    create_path=create_path, original=original )
            except RecordNotFoundError as error:
                if error.args == ():
                    raise RecordNotFoundError(
                        "Record {} not found".format(path) ) from None
                raise

        if use_cache:
            self.cache[path] = record
        return record

    def get_root(self, create_path=False, original=False):
        record = self.records
        if not create_path and not original:
            record = record.copy()
            self.derive_attributes({}, record, name=None)
        return record

    def _get_child(self, record, name, *, create_path, original):
        try:
            child_record = record[name]
        except KeyError:
            if create_path:
                child_record = record[name] = self.Dict()
                self.clear_cache()
            else:
                raise RecordNotFoundError from None
        assert isinstance(child_record, dict), child_record
        if not create_path and not original:
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

