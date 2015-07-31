import re
from collections import OrderedDict
from contextlib import suppress

from .utils import unique, mapping_ordered_keys, mapping_ordered_items

from .record_path import RecordPath
from .flags import FlagContainer

import logging
logger = logging.getLogger(__name__)


class RecordError(Exception):
    pass

class RecordNotFoundError(RecordError, LookupError):
    pass

class Records:
    Dict = OrderedDict
    Path = RecordPath
    name_pattern = re.compile(r'^.+$')

    def __init__(self):
        self._records = self.Dict()
        self._records_cache = {}
        self._cache = {'records' : self._records_cache}

    def _clear_cache(self):
        for cache_piece in self._cache.values():
            cache_piece.clear()

    def absorb(self, data, path=None, *, overwrite=True):
        if path is None:
            path = self.Path()
        if not isinstance(path, self.Path):
            raise TypeError(type(path))
        for part in reversed(path.parts):
            data = {part : data}
        self._absorb_into( data, self.Path(), self._records,
            overwrite=overwrite )
        self._clear_cache()

    def delete(self, path):
        if not isinstance(path, self.Path):
            raise TypeError(type(path))
        if path.is_root():
            raise RuntimeError("Deleting root is impossible")
        self._delete_record(path)
        self._clear_cache()

    def clear(self, path=None):
        if path is None:
            path = self.Path()
        if not isinstance(path, self.Path):
            raise TypeError(type(path))
        self._clear_record(path)
        self._clear_cache()

    def reorder(self, path, sample):
        self.reorder_omap(self.getitem(path, original=True), sample)

    @staticmethod
    def reorder_omap(omap, sample):
        if not isinstance(omap, OrderedDict):
            raise RuntimeError(type(omap))
        swap = omap.copy()
        for key in mapping_ordered_keys(sample):
            omap[key] = swap.pop(key)
        omap.update(swap)

    def _absorb_into(self, data, path, record, *, overwrite=True):
        if data is None:
            return
        if not isinstance(data, dict):
            raise TypeError("Only able to absorb a dict, found {!r}"
                .format(type(data)) )
        for key, value in mapping_ordered_items(data):
            self._absorb_item_into(
                key, value, path, record, overwrite=overwrite )

    def _absorb_item_into( self,
        key, value, path, record, *,
        overwrite=True
    ):
        if not isinstance(key, str):
            raise TypeError("Only able to absorb string keys, found {!r}"
                .format(type(key)) )
        if key.startswith('$'):
            self._absorb_attribute_into(
                key, value, path, record,
                overwrite=overwrite )
            return
        if '/' in key:
            raise ValueError(key)

        child_record = record.get(key)
        if child_record is None:
            child_record = self._create_record(
                path/key, parent_record=record, key=key )
        self._absorb_into(
            value, path/key, child_record, overwrite=overwrite )

    # pylint: disable=unused-argument,no-self-use

    def _absorb_attribute_into( self,
        key, value, path, record, *,
        overwrite=True
    ):
        if overwrite or key not in record:
            record[key] = value
        else:
            pass # discard value

    # pylint: enable=unused-argument,no-self-use

    def _create_record(self, path, parent_record, key):
        if not self.name_pattern.match(key):
            raise ValueError(
                "Nonconforming record name {name} (path {path})"
                .format(name=key, path=path) )
        record = parent_record[key] = self.Dict()
        return record

    def _clear_record(self, path, record=None):
        if record is None:
            record = self.getitem(path, original=True)
        while record:
            key, subrecord = record.popitem()
            if key.startswith('$'):
                continue
            self._delete_record(path/key, popped_record=subrecord)

    def _delete_record(self, path, parent_record=None, popped_record=None):
        if popped_record is None:
            if parent_record is None:
                parent_record = self.getitem(path.parent, original=True)
            popped_record = parent_record.pop(path.name)
        self._clear_record(path, popped_record)

    def getitem(self, path, *, original=False):
        if not isinstance(path, self.Path):
            raise TypeError(type(path))
        use_cache = not original
        if use_cache:
            with suppress(KeyError):
                return self._records_cache[path]

        if path.is_root():
            record = self._get_root(original=original)
        else:
            name = path.name
            if name.startswith('$'):
                raise ValueError(path)
            try:
                # Recurse, making use of cache
                parent_record = self.getitem(path.parent, original=original)
                record = self._get_child(
                    parent_record, name, original=original )
            except RecordNotFoundError as error:
                if error.args == ():
                    raise RecordNotFoundError(
                        "Record {} not found".format(path) ) from None
                raise

        if use_cache:
            self._records_cache[path] = record
        return record

    def _get_root(self, original=False):
        record = self._records
        if not original:
            record = record.copy()
            self._derive_attributes({}, record, name=None)
        return record

    def _get_child(self, record, name, *, original=False):
        try:
            child_record = record[name]
        except KeyError:
            raise RecordNotFoundError from None
        assert isinstance(child_record, dict), child_record
        if not original:
            child_record = child_record.copy()
            self._derive_attributes(record, child_record, name)
        return child_record

    def _derive_attributes(self, parent_record, child_record, name):
        parent_path = parent_record.get('$path')
        if parent_path is None:
            path = self.Path()
        else:
            path = parent_path / name
        child_record['$path'] = path

    def items(self, path=None):
        """Yield (path, record) pairs."""
        if path is None:
            path = self.Path()
        record = self.getitem(path)
        yield path, record
        for key in mapping_ordered_keys(record):
            if key.startswith('$'):
                continue
            yield from self.items(path=path/key)

    # pylint: disable=unused-variable

    def keys(self, path=None):
        """Yield paths."""
        if path is None:
            path = self.Path()
        for subpath, subrecord in self.items(path=path):
            yield subpath

    def values(self, path=None):
        """Yield paths."""
        if path is None:
            path = self.Path()
        for subpath, subrecord in self.items(path=path):
            yield subrecord

    # pylint: enable=unused-variable

    def __contains__(self, path):
        try:
            self.getitem(path)
        except RecordNotFoundError:
            return False
        else:
            return True

    def __getitem__(self, path):
        return self.getitem(path)

    def get(self, path, default=None, original=False):
        try:
            return self.getitem(path, original=original)
        except RecordNotFoundError:
            return default

    @classmethod
    def compare_items(cls, records1, records2, path=None,
        *, original=False
    ):
        """
        Yield (path, record1, record2) triples.
        """
        if path is None:
            path = cls.Path()

        record1 = records1.get(path, original=original)
        record2 = records2.get(path, original=original)
        yield path, record1, record2

        keys = unique(
            mapping_ordered_keys(record1 if record1 is not None else {}),
            mapping_ordered_keys(record2 if record2 is not None else {}) )
        for key in keys:
            if key.startswith('$'):
                continue
            yield from cls.compare_items(records1, records2, path/key,
                original=original )

class MetaRecords(Records):
    name_pattern = re.compile(r'^(?:\w+-)*\w+$')

    flagged_pattern = re.compile(
        r'^(?P<key>\$[^\[\]]+)'
        r'(?:\['
            r'(?P<flags>[^\[\]]*)'
        r'\])?$' )

    @classmethod
    def select_flagged_item(cls, mapping, key_stem, flags):
        """Return (key, value) from mapping."""
        if not isinstance(key_stem, str):
            raise TypeError(type(key_stem))
        if not key_stem.startswith('$'):
            raise ValueError(key_stem)
        if not isinstance(flags, FlagContainer):
            raise TypeError(type(flags))

        flagset_mapping = dict()
        for key, value in mapping.items():
            match = cls.flagged_pattern.match(key)
            if match is None or match.group('key') != key_stem:
                continue
            flags_group = match.group('flags')
            flagset = flags.split_flags_group(flags_group)
            assert isinstance(flagset, frozenset)
            if flagset in flagset_mapping:
                raise RecordError("Clashing keys '{}' and '{}'"
                    .format(key, flagset_mapping[flagset][0]) )
            flagset_mapping[flagset] = (key, value)
        flagset_mapping.setdefault(frozenset(), (None, None))
        return flags.select_matching_value(flagset_mapping)

    dropped_keys = {
    }

    # pylint: disable=unused-argument,no-self-use

    def _absorb_attribute_into( self,
        key, value, path, record, *,
        overwrite=True
    ):
        match = self.flagged_pattern.match(key)
        if match is None:
            raise RecordError(
                "Nonconforming attribute key {key} (path {path})"
                .format(key=key, path=path)
            )
        key_stem = match.group('key')
        if key_stem in self.dropped_keys:
            logger.warning(
                "Dropped key <RED>%(key)s<NOCOLOUR> "
                "detected in <YELLOW>%(path)s<NOCOLOUR> "
                "(replace it with %(modern_key)s)",
                dict(
                    key=key_stem, path=path,
                    modern_key=self.dropped_keys[key_stem], )
            )
        super()._absorb_attribute_into(
            key, value, path, record,
            overwrite=overwrite )

    # pylint: enable=unused-argument,no-self-use

