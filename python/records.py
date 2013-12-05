from collections import OrderedDict

from pathlib import PurePosixPath as PurePath

from .utils import unique, dict_ordered_keys, dict_ordered_items

import logging
logger = logging.getLogger(__name__)

class RecordNotFoundError(KeyError):
    pass

class Records:
    @staticmethod
    def empty_dict(): return OrderedDict()

    def __init__(self):
        self.records = self.empty_dict()
        self.cache = dict()

    def invalidate_cache(self):
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
        assert isinstance(omap, OrderedDict), type(omap)
        swap = omap.copy()
        for key in dict_ordered_keys(sample):
            omap[key] = swap.pop(key)
        omap.update(swap)

    def _merge_item(self, key, value, *, overwrite, record):
        if isinstance(key, PurePath):
            return self.merge(value,
                record=self.getitem( key, record=record,
                    create_path=True, original=True ),
                overwrite=overwrite, )
        elif isinstance(key, str):
            pass
        else: raise TypeError(key)

        if key.startswith('$'):
            if key not in record or overwrite:
                record[key] = value
                self.invalidate_cache()
            else:
                pass # discard value
        else:
            child_record = record.get(key)
            if child_record is None:
                child_record = record[key] = self.empty_dict()
                self.invalidate_cache()
            self.merge(value, overwrite=overwrite, record=child_record)

    def getitem(self, path, *, record=None,
        create_path=False, original=False
    ):
        use_cache = record is None and not create_path and not original
        if use_cache:
            try:
                return self.cache[path]
            except KeyError:
                pass

        if path.is_absolute():
            raise ValueError(path)

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
                    error.args = (path,)
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
                child_record = record[name] = self.empty_dict()
                self.invalidate_cache()
            else:
                raise RecordNotFoundError from None
        assert isinstance(child_record, dict), child_record
        if not create_path and not original:
            child_record = child_record.copy()
            self.derive_attributes(record, child_record, name)
        return child_record

    def derive_attributes(self, parent_record, child_record, name):
        pass

    def items(self, path=PurePath()):
        """Yield (path, record) pairs."""
        record = self.getitem(path)
        yield path, record
        for key in dict_ordered_keys(record):
            if key.startswith('$'):
                continue
            yield from self.items(path=path/key)

    def keys(self, path=PurePath()):
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

#    @classmethod
#    def is_ordered_dict(cls, d):
#        if isinstance(d, (OrderedDict, NaturallyOrderedDict)):
#            return True
#        return False
#
#    @classmethod
#    def ordered_items(cls, d):
#        if cls.is_ordered_dict(d):
#            return d.items()
#        else:
#            return NaturallyOrderedDict(d).items()

    @classmethod
    def compare_items(cls, records1, records2, path=PurePath(),
        *, wipe_subrecords=False
    ):
        """
        Yield (path, record1, record2) triples.
        """

        record1 = records1.get(path, {})
        record2 = records2.get(path, {})
        if wipe_subrecords:
            record1 = cls._wipe_subrecords(record1)
            record2 = cls._wipe_subrecords(record2)
        yield path, record1, record2

        keys = unique(
            dict_ordered_keys(record1),
            dict_ordered_keys(record2) )
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
                record[key] = cls.empty_dict()
        return record

