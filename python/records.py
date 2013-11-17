from collections import OrderedDict

from pathlib import PurePosixPath as PurePath

from .utils import dict_ordered_keys, dict_ordered_items

import logging
logger = logging.getLogger(__name__)
from jeolm import difflogger

class RecordNotFoundError(KeyError):
    pass

class Records:
    dict_type = OrderedDict

    def __init__(self):
        self.records = self.dict_type()
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
        self.reorder_omap(self.get(path, original=True), sample)

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
                record=self.get(key, record=record, create_path=True),
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
                child_record = record[key] = self.dict_type()
                self.invalidate_cache()
            self.merge(value, overwrite=overwrite, record=child_record)

    def get(self, path, *, record=None, create_path=False, original=False):
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
            # Recurse, making use of cache
            parent_record = self.get(path.parent(), record=record,
                create_path=create_path, original=original )
            try:
                record = self._get_child(parent_record, name,
                    create_path=create_path, original=original )
            except RecordNotFoundError as error:
                error.args += (path,)
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
                child_record = record[name] = self.dict_type()
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

    def items(self, path=PurePath(), *, keyfunc=None):
        """Yield (path, record) pairs."""
        record = self.get(path)
        yield path, record
        for key in dict_ordered_keys(record, keyfunc=keyfunc):
            if key.startswith('$'):
                continue
            yield from self.items(path=path/key)

    def keys(self, path=PurePath()):
        """Yield paths."""
        for path, record in self.items():
            yield path

    __getitem__ = get

    def __contains__(self, path):
        try:
            self.get(path, create_path=False)
        except KeyError:
            return False
        else:
            self.get(path, create_path=False, original=True)
            return True

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

