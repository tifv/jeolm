from functools import partial
from collections import OrderedDict
from contextlib import suppress
import re
from pathlib import PurePosixPath

from jeolm.utils.unique import unique
from jeolm.utils.ordering import ( natural_keyfunc, KeyFunc,
    mapping_ordered_keys, mapping_ordered_items )

import logging
logger = logging.getLogger(__name__)

from typing import ( NewType, Type, ClassVar, Any, Union, Optional, cast,
    Callable, Iterable, Container, Sequence, Mapping,
    Tuple, List, Dict,
    Pattern )

NAME_PATTERN = r'\w+(?:-\w+)*'
RELATIVE_NAME_PATTERN = (
    NAME_PATTERN + '|' + '.' + '|' + '..'
)

def _path_pattern(name_pattern: str) -> str:
    return (
        r'/?'
        '(?:(?:' + name_pattern + ')/)*'
        '(?:' + name_pattern + ')?'
    )
PATH_PATTERN = _path_pattern(NAME_PATTERN)
RELATIVE_PATH_PATTERN = _path_pattern(RELATIVE_NAME_PATTERN)

class RecordPathError(ValueError):
    pass

Name = NewType('Name', str)

class RecordPath:
    __slots__ = ['_parts', '_parent']

    _parts: Tuple[Name, ...]
    _parent: Optional['RecordPath']

    def __init__(self, *parts: Union[str, 'RecordPath']) -> None:
        super().__init__()
        self._parts = tuple(self._digest_parts(parts))
        self._parent = None

    @classmethod
    def _digest_parts( cls, parts: Iterable[Union[str, 'RecordPath']]
    ) -> List[Name]:
        digested: List[Name] = []
        for part in parts:
            if isinstance(part, str):
                if part.startswith('/'):
                    digested.clear()
                for piece in part.split('/'):
                    if not piece or piece == '.':
                        continue
                    elif piece == '..':
                        try:
                            digested.pop()
                        except IndexError:
                            raise RecordPathError(parts)
                    else:
                        digested.append(Name(piece))
            elif isinstance(part, RecordPath):
                digested.clear()
                digested.extend(part.parts)
            else:
                raise TypeError(type(part))
        assert not any('/' in part for part in digested)
        return digested

    @classmethod
    def from_parts(cls, parts: Iterable[str]) -> 'RecordPath':
        if any('/' in part for part in parts):
            raise ValueError(parts)
        return cls(*parts)

    @classmethod
    def from_source_path( cls, source_path: PurePosixPath
    ) -> 'RecordPath':
        if source_path.is_absolute():
            raise ValueError(source_path)
        return cls.from_parts(source_path.parts)

    @property
    def parts(self) -> Tuple[Name, ...]:
        return self._parts

    def is_root(self) -> bool:
        return not self._parts

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, RecordPath):
            return NotImplemented
        return self.parts == other.parts

    def __ne__(self, other: Any) -> bool:
        if not isinstance(other, RecordPath):
            return NotImplemented
        return self.parts != other.parts

    def __hash__(self) -> Any:
        return hash(self.parts)

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, RecordPath):
            return NotImplemented
        return self.sorting_key() < other.sorting_key()

    def __le__(self, other: Any) -> bool:
        if not isinstance(other, RecordPath):
            return NotImplemented
        return self.sorting_key() <= other.sorting_key()

    def __gt__(self, other: Any) -> bool:
        if not isinstance(other, RecordPath):
            return NotImplemented
        return self.sorting_key() > other.sorting_key()

    def __ge__(self, other: Any) -> bool:
        if not isinstance(other, RecordPath):
            return NotImplemented
        return self.sorting_key() >= other.sorting_key()

    def sorting_key(self, keyfunc: KeyFunc = natural_keyfunc) -> Any:
        return [keyfunc(part) for part in self.parts]

    def __truediv__(self, other: Any) -> 'RecordPath':
        if not isinstance(other, str):
            return NotImplemented
        if other.startswith('/'):
            raise ValueError(other)
        return type(self)(self, other)

    @property
    def parent(self) -> 'RecordPath':
        parent = self._parent
        if parent is not None:
            return parent
        if not self.parts:
            raise ValueError("Root does not have a parent.")
        self._parent = parent = type(self)(*self.parts[:-1])
        return parent

    @property
    def name(self) -> Name:
        try:
            return self.parts[-1]
        except IndexError:
            raise ValueError("Root does not have a name.")

    @property
    def ancestry(self) -> Iterable['RecordPath']:
        yield self
        if self.parts:
            yield from self.parent.ancestry

    def as_source_path( self, *, suffix: Optional[str] = None
    ) -> PurePosixPath:
        source_path = PurePosixPath(*self.parts)
        if suffix is not None:
            source_path = source_path.with_suffix(suffix)
        return source_path

    def __repr__(self) -> str:
        return '{cls.__qualname__}({parts})'.format(
            cls=type(self),
            parts=', '.join("'{}'".format(part) for part in self.parts) )

    def __str__(self) -> str:
        return '/'.join(['', *self.parts, ''])


class RecordError(Exception):
    pass

class RecordNotFoundError(RecordError, LookupError):
    pass

Record = Dict[str, Any]

class Records:

    _records: Record
    _records_cache: Dict[Tuple[RecordPath, bool], Record]
    _cache_is_clear: bool

    _Dict: ClassVar[Type[Dict]] = OrderedDict
    _Path: ClassVar[Type[RecordPath]] = RecordPath
    name_regex: ClassVar[Pattern] = re.compile(r'(?!\$).+')
    ordering_keyfunc: ClassVar[KeyFunc] = natural_keyfunc

    @classmethod
    def _check_name( cls, name: Name, path: Optional[RecordPath] = None
    ) -> None:
        if not cls.name_regex.fullmatch(name):
            message = ( "Nonconforming record name {name}"
                .format(name=name) )
            if path is not None:
                message += " (path {path})".format(path=path)
            raise ValueError(message)

    def __init__(self) -> None:
        self._records = self._Dict()
        self._records_cache = {}
        self._cache_is_clear = True

    def _clear_cache(self) -> None:
        self._records_cache.clear()
        self._cache_is_clear = True

    def absorb( self, data: Record, path: RecordPath = None,
        *, overwrite: bool = True
    ) -> None:
        if path is None:
            path = self._Path()
        if not isinstance(path, self._Path):
            raise TypeError(type(path))
        for part in reversed(path.parts):
            self._check_name(part, path=path)
            data = {part : data}
        self._absorb_into( data, self._Path(), self._records,
            overwrite=overwrite )
        if not self._cache_is_clear:
            self._clear_cache()

    def _absorb_into( self, data: Record,
        path: RecordPath, record: Record, *, overwrite: bool = True
    ) -> None:
        if data is None:
            return
        if not isinstance(data, dict):
            raise TypeError("Only able to absorb a dict, found {!r}"
                .format(type(data)) )
        for key, value in mapping_ordered_items( data,
                keyfunc=type(self).ordering_keyfunc ):
            self._absorb_item_into(
                key, value, path, record, overwrite=overwrite )

    def _absorb_item_into( self,
        key: str, value: Any, path: RecordPath, record: Record, *,
        overwrite: bool = True,
    ) -> None:
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

    def _absorb_attribute_into( self,
        key: str, value: Any, path: RecordPath, record: Record, *,
        overwrite: bool = True,
    ) -> None:
        if overwrite or key not in record:
            record[key] = value
        else:
            pass # discard value

    def _create_record( self, path: RecordPath,
        parent_record: Record,
    ) -> Record:
        name = path.name
        self._check_name(name, path=path)
        record = parent_record[name] = self._Dict()
        return record

    def clear(self, path: RecordPath = None) -> None:
        if path is None:
            path = self._Path()
        if not isinstance(path, self._Path):
            raise TypeError(type(path))
        self._clear_record(path)
        if not self._cache_is_clear:
            self._clear_cache()

    def delete(self, path: RecordPath) -> None:
        if not isinstance(path, self._Path):
            raise TypeError(type(path))
        if path.is_root():
            raise RuntimeError("Deleting root is impossible")
        self._delete_record(path)
        if not self._cache_is_clear:
            self._clear_cache()

    def _clear_record( self, path: RecordPath,
        record: Optional[Record]=None
    ) -> None:
        if record is None:
            record = self.get(path, original=True)
        while record:
            key, subrecord = record.popitem()
            if key.startswith('$'):
                continue
            self._delete_record(path/key, popped_record=subrecord)

    def _delete_record( self, path: RecordPath,
        parent_record: Optional[Record] = None,
        popped_record: Optional[Record] = None,
    ) -> None:
        if popped_record is None:
            if parent_record is None:
                parent_record = self.get(path.parent, original=True)
            popped_record = parent_record.pop(path.name)
        else:
            if parent_record is not None:
                raise RuntimeError
        self._clear_record(path, popped_record)

    def get(self, path: RecordPath, *, original: bool = False) -> Record:
        if not isinstance(path, self._Path):
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
        self._cache_is_clear = False
        return record

    def _get_root(self, original: bool = False) -> Record:
        record = self._records
        if not original:
            record = record.copy()
            self._derive_record({}, record, path=RecordPath())
        return record

    def _get_child( self, parent_record: Record, path: RecordPath,
        *, original: bool = False
    ) -> Record:
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
    def _derive_record( self,
        parent_record: Record, child_record: Record, path: RecordPath,
    ) -> None:
        pass
    # pylint: enable=unused-argument

    def items( self, path: Optional[RecordPath] = None
    ) -> Iterable[Tuple[RecordPath, Record]]:
        """Yield (path, record) pairs."""
        if path is None:
            path = self._Path()
        record = self.get(path)
        yield path, record
        assert all(isinstance(key, str) for key in record)
        for key in mapping_ordered_keys( record,
                keyfunc=type(self).ordering_keyfunc ):
            if key.startswith('$'):
                continue
            yield from self.items(path=path/key)

    # pylint: disable=unused-variable

    def paths(self, path: RecordPath=None) -> Iterable[RecordPath]:
        """Yield paths."""
        if path is None:
            path = self._Path()
        for subpath, subrecord in self.items(path=path):
            yield subpath

    # pylint: enable=unused-variable

    def __contains__(self, path: RecordPath) -> bool:
        if not isinstance(path, self._Path):
            raise TypeError(path)
        try:
            self.get(path)
        except RecordNotFoundError:
            return False
        else:
            return True

    @classmethod
    def compare_items( cls, records1: 'Records', records2: 'Records',
        path: Optional[RecordPath] = None,
        *, original: bool = False
    ) -> Iterable[Tuple[RecordPath, Optional[Record], Optional[Record]]]:
        """
        Yield (path, record1, record2) triples.
        """
        if path is None:
            _path = cls._Path()
        else:
            _path = path

        def maybe_get_record_and_keys( records: 'Records',
        ) -> Tuple[Optional[Record], Sequence[str]]:
            record: Optional[Record]
            keys: Sequence[str]
            try:
                record = records.get(_path, original=original)
            except RecordNotFoundError:
                record = None
                keys = ()
            else:
                keys = mapping_ordered_keys( record,
                    keyfunc=type(records).ordering_keyfunc )
            return record, keys

        record1, keys1 = maybe_get_record_and_keys(records1)
        record2, keys2 = maybe_get_record_and_keys(records2)

        yield _path, record1, record2

        for key in unique(keys1, keys2):
            if key.startswith('$'):
                continue
            yield from cls.compare_items(records1, records2, _path/key,
                original=original )


