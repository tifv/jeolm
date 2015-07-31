from itertools import chain

from pathlib import PurePosixPath

from .utils import natural_keyfunc

import logging
logger = logging.getLogger(__name__)


NAME_PATTERN = r'\w+(?:-\w+)*'
RELATIVE_NAME_PATTERN = (
    NAME_PATTERN + '|' + '.' + '|' + '..'
)

def _path_pattern(name_pattern):
    return (
        r'/?'
        '(?:(?:' + name_pattern + ')/)*'
        '(?:' + name_pattern + ')?'
    )
PATH_PATTERN = _path_pattern(NAME_PATTERN)
RELATIVE_PATH_PATTERN = _path_pattern(RELATIVE_NAME_PATTERN)


class RecordPath:
    __slots__ = ['_parts', '_parent']

    def __init__(self, *parts):
        super().__init__()
        parts = self._digest_parts(parts)
        self._parts = tuple(parts)
        self._parent = None

    @classmethod
    def _digest_parts(cls, parts):
        digested = []
        for part in parts:
            if isinstance(part, str):
                if part.startswith('/'):
                    digested.clear()
                for piece in part.split('/'):
                    if not piece or piece == '.':
                        continue
                    elif piece == '..':
                        digested.pop()
                    else:
                        digested.append(piece)
            elif isinstance(part, RecordPath):
                digested.clear()
                digested.extend(part.parts)
            else:
                raise TypeError(type(part))
        assert not any('/' in part for part in digested)
        return digested

    @classmethod
    def from_parts(cls, parts):
        if any('/' in part for part in parts):
            raise ValueError(parts)
        if any(part in {'.', '..'} for part in parts):
            raise ValueError(parts)
        self = cls()
        self._parts = parts # pylint: disable=protected-access
        return self

    @classmethod
    def from_inpath(cls, inpath):
        if inpath.is_absolute():
            raise ValueError(inpath)
        return cls.from_parts(inpath.parts)

    @property
    def parts(self):
        return self._parts

    def is_root(self):
        return not self._parts

    def __eq__(self, other):
        if not isinstance(other, RecordPath):
            return NotImplemented
        return self.parts == other.parts

    def __ne__(self, other):
        if not isinstance(other, RecordPath):
            return NotImplemented
        return self.parts != other.parts

    def __hash__(self):
        return hash(self.parts)

    def __lt__(self, other):
        if not isinstance(other, RecordPath):
            return NotImplemented
        return self.sorting_key() < other.sorting_key()

    def __le__(self, other):
        if not isinstance(other, RecordPath):
            return NotImplemented
        return self.sorting_key() <= other.sorting_key()

    def __gt__(self, other):
        if not isinstance(other, RecordPath):
            return NotImplemented
        return self.sorting_key() > other.sorting_key()

    def __ge__(self, other):
        if not isinstance(other, RecordPath):
            return NotImplemented
        return self.sorting_key() >= other.sorting_key()

    def sorting_key(self, keyfunc=natural_keyfunc):
        return [keyfunc(part) for part in self.parts]

    def __truediv__(self, other):
        if not isinstance(other, str):
            return NotImplemented
        if other.startswith('/'):
            raise ValueError(other)
        return type(self)(self, other)

    @property
    def parent(self):
        parent = self._parent
        if parent is not None:
            return parent
        if not self.parts:
            raise ValueError("Root does not have a parent.")
        self._parent = parent = type(self)(*self.parts[:-1])
        return parent

    @property
    def name(self):
        try:
            return self.parts[-1]
        except IndexError:
            raise ValueError("Root does not have a name.")

    @property
    def ancestry(self):
        yield self
        if self.parts:
            yield from self.parent.ancestry

    def as_inpath(self, *, suffix=None):
        inpath = PurePosixPath(*self.parts)
        assert inpath.suffix == '', inpath
        if suffix is not None:
            inpath = inpath.with_suffix(suffix)
        return inpath

    def __repr__(self):
        return '{cls.__qualname__}({parts})'.format(
            cls=type(self),
            parts=', '.join("'{}'".format(part) for part in self.parts) )

    def __str__(self):
        return '/'.join(chain(('',), self.parts, ('',)))

