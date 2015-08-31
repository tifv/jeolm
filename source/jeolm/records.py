import re
from collections import OrderedDict
from contextlib import suppress

from .utils import unique, mapping_ordered_keys, mapping_ordered_items

from .record_path import RecordPath, NAME_PATTERN
from .flags import ( FlagContainer,
    RELATIVE_FLAGS_PATTERN_TIGHT as FLAGS_PATTERN )

import logging
logger = logging.getLogger(__name__)


class RecordError(Exception):
    pass

class RecordNotFoundError(RecordError, LookupError):
    pass

class Records:
    Dict = OrderedDict
    Path = RecordPath
    name_regex = re.compile(r'(?!\$).+')

    @classmethod
    def _check_name(cls, name, path=None):
        if not cls.name_regex.fullmatch(name):
            message = ( "Nonconforming record name {name}"
                .format(name=name) )
            if path is not None:
                message += " (path {path})".format(path=path)
            raise ValueError(message)

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
            self._check_name(part, path=path)
            data = {part : data}
        self._absorb_into( data, self.Path(), self._records,
            overwrite=overwrite )
        self._clear_cache()

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
                path/key, parent_record=record )
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

    def _create_record(self, path, parent_record):
        name = path.name
        self._check_name(name, path=path)
        record = parent_record[name] = self.Dict()
        return record

    def reorder(self, path, sample):
        self._reorder_omap(self.get(path, original=True), sample)

    @staticmethod
    def _reorder_omap(omap, sample):
        if not isinstance(omap, OrderedDict):
            raise RuntimeError(type(omap))
        swap = omap.copy()
        for key in mapping_ordered_keys(sample):
            omap[key] = swap.pop(key)
        omap.update(swap)

    def clear(self, path=None):
        if path is None:
            path = self.Path()
        if not isinstance(path, self.Path):
            raise TypeError(type(path))
        self._clear_record(path)
        self._clear_cache()

    def delete(self, path):
        if not isinstance(path, self.Path):
            raise TypeError(type(path))
        if path.is_root():
            raise RuntimeError("Deleting root is impossible")
        self._delete_record(path)
        self._clear_cache()

    def _clear_record(self, path, record=None):
        if record is None:
            record = self.get(path, original=True)
        while record:
            key, subrecord = record.popitem()
            if key.startswith('$'):
                continue
            self._delete_record(path/key, popped_record=subrecord)

    def _delete_record(self, path, parent_record=None, popped_record=None):
        if popped_record is None:
            if parent_record is None:
                parent_record = self.get(path.parent, original=True)
            popped_record = parent_record.pop(path.name)
        else:
            if parent_record is not None:
                raise RuntimeError
        self._clear_record(path, popped_record)

    def get(self, path, *, original=False):
        if not isinstance(path, self.Path):
            raise TypeError(type(path))
        with suppress(KeyError):
            return self._records_cache[path, original]

        if path.is_root():
            record = self._get_root(original=original)
        else:
            try:
                # Recurse, making use of cache
                parent_record = self.get(path.parent, original=original)
                record = self._get_child(
                    parent_record, path, original=original )
            except RecordNotFoundError as error:
                if error.args == ():
                    raise RecordNotFoundError(
                        "Record {} not found".format(path) ) from None
                raise

        self._records_cache[path, original] = record
        return record

    def _get_root(self, original=False):
        record = self._records
        if not original:
            record = record.copy()
            self._derive_record({}, record, path=RecordPath())
        return record

    def _get_child(self, parent_record, path, *, original=False):
        name = path.name
        self._check_name(name, path=path)
        try:
            child_record = parent_record[name]
        except KeyError:
            raise RecordNotFoundError from None
        assert isinstance(child_record, dict), child_record
        if not original:
            child_record = child_record.copy()
            self._derive_record(parent_record, child_record, path)
        return child_record

    # pylint: disable=unused-argument
    def _derive_record(self, parent_record, child_record, path):
        pass
    # pylint: enable=unused-argument

    def items(self, path=None):
        """Yield (path, record) pairs."""
        if path is None:
            path = self.Path()
        record = self.get(path)
        yield path, record
        for key in mapping_ordered_keys(record):
            if key.startswith('$'):
                continue
            yield from self.items(path=path/key)

    # pylint: disable=unused-variable

    def paths(self, path=None):
        """Yield paths."""
        if path is None:
            path = self.Path()
        for subpath, subrecord in self.items(path=path):
            yield subpath

    # pylint: enable=unused-variable

    def __contains__(self, path):
        try:
            self.get(path)
        except RecordNotFoundError:
            return False
        else:
            return True

    @classmethod
    def compare_items(cls, records1, records2, path=None,
        *, original=False
    ):
        """
        Yield (path, record1, record2) triples.
        """
        if path is None:
            path = cls.Path()

        try:
            record1 = records1.get(path, original=original)
        except RecordNotFoundError:
            record1 = None
            keys1 = ()
        else:
            keys1 = mapping_ordered_keys(record1)

        try:
            record2 = records2.get(path, original=original)
        except RecordNotFoundError:
            record2 = None
            keys2 = ()
        else:
            keys2 = mapping_ordered_keys(record1)

        yield path, record1, record2

        for key in unique(keys1, keys2):
            if key.startswith('$'):
                continue
            yield from cls.compare_items(records1, records2, path/key,
                original=original )


ATTRIBUTE_KEY_PATTERN = (
    r'(?P<stem>'
        r'(?:\$\w+(?:-\w+)*)+'
    r')'
    r'(?:\['
        r'(?P<flags>' + FLAGS_PATTERN + r')'
    r'\])?'
)

class MetaRecords(Records):
    name_regex = re.compile(NAME_PATTERN)

    attribute_key_regex = re.compile(ATTRIBUTE_KEY_PATTERN)

    # pylint: disable=unused-argument,no-self-use

    def _absorb_attribute_into( self,
        key, value, path, record, *,
        overwrite=True
    ):
        match = self.attribute_key_regex.fullmatch(key)
        if match is None:
            raise RecordError(
                "Nonconforming attribute key {key} (path {path})"
                .format(key=key, path=path)
            )
        key_stem = match.group('stem')
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
            match = cls.attribute_key_regex.fullmatch(key)
            if match is None or match.group('stem') != key_stem:
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

