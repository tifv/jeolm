import re

from .record_path import RecordPath
from .flags import FlagContainer, UnutilizedFlagError


class TargetError(Exception):
    pass


class Target:
    __slots__ = ['path', 'flags']

    def __init__(self, path, flags, *, origin=None):
        super().__init__()
        if not isinstance(path, RecordPath):
            raise TypeError(type(path))
        self.path = path
        if not isinstance(flags, FlagContainer):
            flags = FlagContainer(flags, origin=origin)
        elif origin is not None:
            raise RuntimeError(origin)
        self.flags = flags

    _pattern = re.compile(
        r'^(?P<path>[^\[\]]+)'
        r'(?:\['
            r'(?P<flags>[^\[\]]*)'
        r'\])?$' )

    @classmethod
    def from_string(cls, string, *, origin=None):
        if not isinstance(string, str):
            raise TargetError(type(string))
        match = cls._pattern.match(string)
        if match is None:
            raise TargetError( "Failed to parse target '{}'."
                .format(string) )
        assert match.group(0) == string, string
        return cls._from_match(match, origin=origin)

    @classmethod
    def _from_match(cls, match, *, origin=None):
        path = RecordPath(match.group('path'))
        flags_group = match.group('flags')
        try:
            flags = FlagContainer.split_flags_group(flags_group)
        except TargetError as error:
            raise TargetError( "Error while parsing subtarget '{}' flags."
                .format(match.group(0))) from error
        if any(flag.startswith('-') for flag in flags):
            raise TargetError( "Target '{}' contains a negative flag."
                .format(match.group(0)) )
        return cls(path, flags, origin=origin)

    def derive_from_string(self, string, *, origin=None):
        if not isinstance(string, str):
            raise TargetError(type(string))
        match = self._pattern.match(string)
        if match is None:
            raise TargetError( "Failed to parse subtarget '{}'."
                .format(string) )
        assert match.group(0) == string, string
        return self._derive_from_match(match)

    def _derive_from_match(self, match, *, origin=None):
        subpath = RecordPath(self.path, match.group('path'))
        flags_group = match.group('flags')
        try:
            flags = FlagContainer.split_flags_group(flags_group)
        except TargetError as error:
            raise TargetError( "Error while parsing subtarget '{}' flags."
                .format(match.group(0)) ) from error
        positive = set()
        negative = set()
        for flag in flags:
            if not flag.startswith('-'):
                positive.add(flag)
            else:
                negative.add(flag[1:])
        if any(flag.startswith('-') for flag in negative):
            raise TargetError(
                "Subtarget '{}' contains a double-negative flag."
                .format(match.group(0)) )
        subflags = self.flags.delta(
            union=positive, difference=negative, origin=origin )
        return self.__class__(subpath, subflags)

    def __hash__(self):
        return hash((self.path, self.flags))

    def __eq__(self, other):
        if not isinstance(other, Target):
            return NotImplemented
        return self.path == other.path and self.flags == other.flags

    def flags_union(self, iterable, *, origin=None, **kwargs):
        return self.__class__( self.path,
            self.flags.union(iterable, origin=origin, **kwargs) )

    def flags_difference(self, iterable, *, origin=None, **kwargs):
        return self.__class__( self.path,
            self.flags.difference(iterable, origin=origin, **kwargs) )

    def flags_delta(self, *, difference, union, origin=None):
        return self.__class__( self.path,
            self.flags.delta( difference=difference, union=union,
                origin=origin )
        )

    def flags_clean_copy(self, *, origin):
        return self.__class__(self.path, self.flags.clean_copy(origin=origin))

    def path_derive(self, *pathparts):
        return self.__class__(RecordPath(self.path, *pathparts), self.flags)

    def check_unutilized_flags(self):
        try:
            self.flags.check_unutilized_flags()
        except UnutilizedFlagError as error:
            raise TargetError( "Unutilized flags in target {target}"
                .format(target=self)
            ) from error

    def __str__(self):
        return '{self.path!s}{self.flags:optional}'.format(self=self)

    def __repr__(self):
        return ( '{self.__class__.__qualname__}'
            '({self.path!r}, {self.flags!r})'
            .format(self=self) )

