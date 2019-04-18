from functools import partial, wraps
from collections.abc import Container
import re
import traceback

from typing import ( NewType, TypeVar, Type, Any, Union, Optional,
    Callable, Iterable, Sequence, Mapping,
    Tuple, List, FrozenSet, Set, Dict,
    Pattern, Match )
T = TypeVar('T')

from jeolm.records import ( RecordPath, RecordPathError,
    NAME_PATTERN, PATH_PATTERN, RELATIVE_PATH_PATTERN )

import logging
logger = logging.getLogger(__name__)

FLAG_PATTERN = r'\w+(?:-\w+)*'
RELATIVE_FLAG_PATTERN = r'-?' + FLAG_PATTERN

def _flags_pattern_tight(flag_pattern: str) -> str:
    return ( r'(?:'
        r'(?:' + flag_pattern + r')'
        r'(?:,(?:' + flag_pattern + r'))*'
    r')?' )
def _flags_pattern_loose(flag_pattern: str) -> str:
    return ( r'(?:'
        r'(?: *(?:' + flag_pattern + r'))?'
        r'(?: *, *(?:' + flag_pattern + r')| *,)*'
    r' *)' )
FLAGS_PATTERN_TIGHT = _flags_pattern_tight(FLAG_PATTERN)
FLAGS_PATTERN_LOOSE = _flags_pattern_loose(FLAG_PATTERN)
RELATIVE_FLAGS_PATTERN_TIGHT = _flags_pattern_tight(RELATIVE_FLAG_PATTERN)
RELATIVE_FLAGS_PATTERN_LOOSE = _flags_pattern_loose(RELATIVE_FLAG_PATTERN)

TARGET_PATTERN = (
    r'(?P<path>' + PATH_PATTERN + r')'
    r'(?:\['
        r'(?P<flags>' + FLAGS_PATTERN_LOOSE + r')'
    r'\])?'
)
RELATIVE_TARGET_PATTERN = (
    r'(?P<path>' + RELATIVE_PATH_PATTERN + r')'
    r'(?:\['
        r'(?P<flags>' + RELATIVE_FLAGS_PATTERN_LOOSE + r')'
    r'\])?'
)
OUTNAME_PATTERN = (
    r'(?P<name>' + NAME_PATTERN + r')'
    r'(?:\['
        r'(?P<flags>' + FLAGS_PATTERN_TIGHT + r')'
    r'\])?'
)


Flag = NewType('Flag', str)

class FlagError(Exception):
    pass

class UnutilizedFlagError(FlagError):
    def __init__( self, unutilized_flags: Iterable[Flag],
        *, origin: Optional[str] = None
    ) -> None:
        joined_flags = ', '.join(
            "'{}'".format(flag) for flag in sorted(unutilized_flags) )
        message = "Unutilized flags {flags}".format(flags=joined_flags)
        if origin is not None:
            if not isinstance(origin, str):
                try:
                    origin = origin()
                except TypeError:
                    origin = str(origin)
            message += " originating from {origin}".format(origin=origin)
        super().__init__(message)


class FlagContainer(Container):
    """
    An immutable set-like container, which tracks usage of its elements.
    """

    flags: FrozenSet[Flag]

    utilized_flags: Set[Flag]
    children: List['FlagContainer']
    origin: str
    _as_frozenset: Optional[FrozenSet[Flag]]
    _contains_cache: Dict[Tuple[Flag, bool], bool]

    def __init__( self, iterable: Iterable[Flag] = (),
        *, origin: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.flags = flags = frozenset(iterable)
        if any(flag.startswith('-') for flag in flags):
            raise ValueError(flags)
        self._as_frozenset = None
        self._contains_cache = dict()
        self.utilized_flags = set()
        self.children = []
        if origin is None:
            self.origin = ( '(traceback):\n' +
                ''.join(traceback.format_stack()) )
        else:
            self.origin = origin

    def __hash__(self) -> Any:
        return hash(self.as_frozenset)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, FlagContainer):
            return NotImplemented
        return self.as_frozenset == other.as_frozenset

    def __contains__(self, flag: Any) -> bool:
        if not isinstance(flag, str):
            raise TypeError(type(flag))
        return self._contains_indefinite(flag)

    def _contains_indefinite(self, flag: str, *, utilize: bool = True) -> bool:
        if not flag.startswith('-'):
            return self._contains(Flag(flag), utilize=utilize)
        else:
            anti_flag = flag[1:]
            if anti_flag.startswith('-'):
                raise FlagError(flag)
            return not self._contains(Flag(anti_flag), utilize=utilize)

    def _contains(self, flag: Flag, *, utilize: bool = True) -> bool:
        key = (flag, utilize)
        try:
            return self._contains_cache[key]
        except KeyError:
            pass
        answer = self._contains_cache[key] = \
            self._contains_compute(flag, utilize=utilize)
        return answer

    def _contains_compute(self, flag: Flag, *, utilize: bool = True) -> bool:
        assert not flag.startswith('-'), flag
        return self._contains_self(flag, utilize=utilize)

    def _contains_self(self, flag: Flag, *, utilize: bool = True) -> bool:
        assert not flag.startswith('-'), flag
        if flag in self.flags:
            if utilize:
                self.utilized_flags.add(flag)
            return True
        return False

    def issuperset( self, iterable: Iterable[Flag], utilize: bool = True
    ) -> bool:
        contains = partial(self._contains_indefinite, utilize=utilize)
        return all([contains(flag) for flag in iterable])

    def intersection( self, iterable: Iterable[Flag], utilize: bool = True
    ) -> Set[Flag]:
        contains = partial(self._contains_indefinite, utilize=utilize)
        return {flag for flag in iterable if contains(flag)}

    def utilize(self, flag: Flag) -> None:
        """
        Ensure that flag is present in the container and utilized.

        Raise RuntimeError if flag is missing from the container.
        """
        if flag not in self:
            raise RuntimeError(self, flag)

    def utilize_flags(self, iterable: Iterable[Flag]) -> None:
        for flag in iterable:
            self.utilize(flag)

    def utilize_missing(self, flag: Flag) -> None:
        if flag in self:
            raise RuntimeError(self, flag)

    def utilize_missing_flags(self, iterable: Iterable[Flag]) -> None:
        for flag in iterable:
            self.utilize_missing(flag)

    @property
    def as_frozenset(self) -> FrozenSet[Flag]:
        as_frozenset = self._as_frozenset
        if as_frozenset is None:
            as_frozenset = self._as_frozenset = \
                self.reconstruct_as_frozenset()
        return as_frozenset

    #@property
    #def as_set(self):
    #    return set(self.as_frozenset)

    def reconstruct_as_frozenset(self) -> FrozenSet[Flag]:
        return self.flags

    def check_condition(self, condition: Any) -> bool:
        if isinstance(condition, bool):
            return condition
        elif isinstance(condition, str):
            return condition in self
        elif isinstance(condition, list):
            return all(self.check_condition(item) for item in condition)
        elif isinstance(condition, dict):
            if len(condition) > 1:
                raise FlagError('Condition, if a dict, must be of length 1')
            (key, value), = condition.items()
            if key == 'or':
                if not isinstance(value, list):
                    raise FlagError("'or' condition value must be a list")
                return any(self.check_condition(item) for item in value)
            elif key == 'and':
                if not isinstance(value, list):
                    raise FlagError("'and' condition value must be a list")
                return all(self.check_condition(item) for item in value)
            elif key == 'not':
                return not self.check_condition(value)
            else:
                raise FlagError(
                    "Condition, if a dict, must have key 'not' or 'or'" )
        else:
            raise FlagError(type(condition))

    def select_matching_value( self,
        flagset_mapping: Mapping[FrozenSet[Flag], T]
    ) -> T:
        issuperset = partial(self.issuperset, utilize=False)
        intersection = partial(self.intersection, utilize=False)
        matched_items: Dict[FrozenSet[Flag], Any] = dict()
        for flagset, value in flagset_mapping.items():
            if not isinstance(flagset, frozenset):
                raise RuntimeError(type(flagset))
            if not issuperset(flagset):
                missing_flags = flagset - intersection(flagset)
                if len(missing_flags) < 2:
                    missing_flag, = missing_flags
                    self.utilize_missing(missing_flag)
                continue
            lesser_flagsets = { other_flagset
                for other_flagset in matched_items
                if other_flagset < flagset }
            greater_flagsets = { other_flagset
                for other_flagset in matched_items
                if other_flagset > flagset }
            assert not lesser_flagsets or not greater_flagsets
            if greater_flagsets:
                continue
            for other_flagset in lesser_flagsets:
                del matched_items[other_flagset]
            matched_items[flagset] = value
        if not matched_items:
            raise FlagError("No matches")
        if len(matched_items) > 1:
            raise FlagError(
                "Multiple flag sets matched, ambiguity unresolved: {}"
                .format(', '.join(
                    "{!r}".format(flagset) for flagset in matched_items
                )) )
        (flagset, value), = matched_items.items()
        self.utilize_flags(flagset)
        return value

    def union( self, iterable: Iterable[Flag],
        *, overadd: bool = True, origin: Optional[str] = None,
    ) -> 'FlagContainer':
        assert not isinstance(iterable, str)
        iterable = [
            flag for flag in iterable
            if overadd or not self._contains(flag, utilize=False) ]
        if iterable:
            return self.child(iterable, PositiveFlagContainer, origin=origin)
        else:
            return self

    def difference( self, iterable: Iterable[Flag],
        *, underremove: bool = True, origin: Optional[str] = None,
    ) -> 'FlagContainer':
        assert not isinstance(iterable, str)
        iterable = [
            flag for flag in iterable
            if underremove or self._contains(flag, utilize=False) ]
        if iterable:
            return self.child(iterable, NegativeFlagContainer, origin=origin)
        else:
            return self

    def delta( self,
        *, difference: Iterable[Flag], union: Iterable[Flag],
        origin: Optional[str] = None
    ) -> 'FlagContainer':
        difference = frozenset(difference)
        union = frozenset(union)
        if difference & union:
            raise FlagError("Adding and removing the same flag at once.")
        return ( self
            .difference(difference, origin=origin)
            .union(union, origin=origin) )

    def delta_mixed( self,
        *, flags: Iterable[str], origin: Optional[str] = None
    ) -> 'FlagContainer':
        positive: Set[Flag] = set()
        negative: Set[Flag] = set()
        for flag in flags:
            if not flag.startswith('-'):
                positive.add(Flag(flag))
            else:
                flag = flag[1:]
                if flag.startswith('-'):
                    raise FlagError(
                        f"Encountered double-negative flag {flag}" )
                negative.add(Flag(flag))
        return self.delta( union=positive, difference=negative,
            origin=origin )

    def bastard( self, iterable: Iterable[Flag],
        *, origin: Optional[str] = None
    ) -> 'FlagContainer':
        """
        This child that will just override all the flags.

        Useful in case where flag usage tracking is still needed on
        a completely new set of flags.
        """
        iterable = list(iterable)
        if iterable:
            return self.child(iterable, ChildFlagContainer, origin=origin)
        else:
            return self

    def child( self,
        iterable: Iterable[Flag], child_class: Type['ChildFlagContainer'],
        *, origin: Optional[str] = None,
    ) -> 'FlagContainer':
        child = child_class(iterable, parent=self, origin=origin)
        self.children.append(child)
        return child

    def clean_copy( self, *, origin: Optional[str] = None,
    ) -> 'FlagContainer':
        return FlagContainer(self.as_frozenset, origin=origin)

    def check_unutilized_flags(self) -> None:
        unutilized_flags = self.flags - self.utilized_flags
        if unutilized_flags:
            raise UnutilizedFlagError(unutilized_flags, origin=self.origin)
        for child in self.children:
            child.check_unutilized_flags()

    def abandon_children(self) -> None:
        """Break some references."""
        for child in self.children:
            child.abandon_children()
        self.children.clear()

    flag_regex = re.compile(FLAG_PATTERN)
    relative_flag_regex = re.compile(RELATIVE_FLAG_PATTERN)

    @classmethod
    def split_flags_string( cls, flags_string: str,
        *, flag_regex: Optional[Pattern[str]] = None,
        relative_flags: Optional[bool] = None
    ) -> Sequence[Flag]:
        # by default relative flags are parsed
        if flag_regex is None:
            if relative_flags is None or relative_flags:
                flag_regex = cls.relative_flag_regex
            else:
                flag_regex = cls.flag_regex
        else:
            if relative_flags is not None:
                raise RuntimeError
        if flags_string is None:
            return []
        flag_list: List[Flag] = []
        for piece in flags_string.split(','):
            flag = piece.strip()
            if not flag:
                continue
            elif flag_regex.match(flag) is None:
                raise FlagError(flag)
            flag_list.append(Flag(flag))
        flag_set = frozenset(flag_list)
        if len(flag_set) != len(flag_list):
            raise FlagError("Duplicated flags detected.")
        return flag_list

    def __format__(self, fmt: str,
        *, sorted_flags: Optional[Sequence[Flag]] = None
    ) -> str:
        if fmt == 'optional':
            if sorted_flags is None:
                sorted_flags = sorted(self.as_frozenset)
            if not sorted_flags:
                return ''
            return '[{}]'.format(','.join(sorted_flags))
        return super().__format__(fmt)

    @property
    def _flags_repr(self) -> str:
        return '{{{}}}'.format(', '.join(
            "'{}'".format(flag) for flag in self.flags
        ))

    def __repr__(self) -> str:
        return ( '{flags.__class__.__name__}({flags._flags_repr})'
            .format(flags=self) )

class ChildFlagContainer(FlagContainer):
    parent: FlagContainer
    constructor_name = 'bastard'

    def __init__( self, iterable: Iterable[Flag], parent: FlagContainer,
        *, origin: Optional[str] = None,
    ) -> None:
        super().__init__(iterable, origin=origin)
        self.parent = parent

    def __repr__(self) -> str:
        return (
            '{flags.parent!r}.{flags.constructor_name}'
            '({flags._flags_repr})'
            .format(flags=self) )

class PositiveFlagContainer(ChildFlagContainer):
    constructor_name = 'union'

    # pylint: disable=protected-access

    # Override
    def _contains_compute(self, flag: Flag, *, utilize: bool = True) -> bool:
        assert not flag.startswith('-'), flag
        if self.parent._contains(flag, utilize=utilize):
            return True
        elif self._contains_self(flag, utilize=utilize):
            return True
        else:
            return False

    # pylint: enable=protected-access

    def reconstruct_as_frozenset(self) -> FrozenSet[Flag]:
        return self.parent.as_frozenset.union(self.flags)

class NegativeFlagContainer(ChildFlagContainer):
    constructor_name = 'difference'

    # pylint: disable=protected-access

    # Override
    def _contains_compute(self, flag: Flag, *, utilize: bool = True) -> bool:
        assert not flag.startswith('-'), flag
        if not self.parent._contains(flag, utilize=utilize):
            return False
        elif self._contains_self(flag, utilize=utilize):
            return False
        else:
            return True

    # pylint: enable=protected-access

    @property
    def unutilized_flags(self) -> Set[str]:
        return {'-' + flag for flag in self.flags - self.utilized_flags}

    def reconstruct_as_frozenset(self) -> FrozenSet[Flag]:
        return self.parent.as_frozenset.difference(self.flags)


class TargetError(Exception):
    pass


class Target:
    path: RecordPath
    flags: FlagContainer

    def __init__( self,
        path: RecordPath, flags: Union[FlagContainer, Iterable[Flag]],
        *, origin: Optional[str] = None
    ) -> None:
        super().__init__()
        if not isinstance(path, RecordPath):
            raise TypeError(type(path))
        self.path = path
        if not isinstance(flags, FlagContainer):
            flags = FlagContainer(flags, origin=origin)
        elif origin is not None:
            raise ValueError
        self.flags = flags

    _regex = re.compile(TARGET_PATTERN)

    @classmethod
    def from_string( cls, string: str,
        *, origin: Optional[str] = None,
    ) -> 'Target':
        if not isinstance(string, str):
            raise TargetError(type(string))
        match = cls._regex.fullmatch(string)
        if match is None:
            raise TargetError( "Failed to parse target '{}'."
                .format(string) )
        return cls._from_match(match, origin=origin)

    @classmethod
    def _from_match( cls, match: Match,
        *, origin: Optional[str] = None,
    ) -> 'Target':
        path = RecordPath(match.group('path'))
        flags_group = match.group('flags')
        try:
            flags = FlagContainer.split_flags_string( flags_group,
                relative_flags=False )
        except FlagError as error:
            raise TargetError( "Error while parsing target '{}' flags."
                .format(match.group(0))) from error
        if any(flag.startswith('-') for flag in flags):
            raise RuntimeError
        return cls(path, flags, origin=origin)

    _relative_regex = re.compile(RELATIVE_TARGET_PATTERN)

    def derive_from_string( self, string: str,
        *, origin: Optional[str] = None,
    ) -> 'Target':
        if not isinstance(string, str):
            raise TargetError(type(string))
        match = self._relative_regex.fullmatch(string)
        if match is None:
            raise TargetError( "Failed to parse subtarget '{}'."
                .format(string) )
        return self._derive_from_match(match, origin=origin)

    def _derive_from_match( self, match: Match,
        *, origin: Optional[str] = None,
    ) -> 'Target':
        try:
            subpath = RecordPath(self.path, match.group('path'))
        except RecordPathError as error:
            raise TargetError(self, match.group(0)) from error
        flags_group = match.group('flags')
        try:
            flags = FlagContainer.split_flags_string(flags_group)
        except FlagError as error:
            raise TargetError(self, match.group(0)) from error
        subflags = self.flags.delta_mixed(flags=flags, origin=origin)
        return self.__class__(subpath, subflags)

    def __hash__(self) -> Any:
        return hash((self.path, self.flags))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Target):
            return NotImplemented
        return self.path == other.path and self.flags == other.flags

    def flags_union( self, iterable: Iterable[Flag],
        *, origin: Optional[str] = None,
        overadd: bool = True,
    ) -> 'Target':
        return self.__class__( self.path,
            self.flags.union( iterable,
                origin=origin, overadd=overadd )
        )

    def flags_difference( self, iterable: Iterable[Flag],
        *, origin: Optional[str] = None,
        underremove: bool = True,
    ) -> 'Target':
        return self.__class__( self.path,
            self.flags.difference( iterable,
                origin=origin, underremove=underremove )
        )

    def flags_delta( self,
        *, difference: Iterable[Flag], union: Iterable[Flag],
        origin: Optional[str] = None,
    ) -> 'Target':
        return self.__class__( self.path,
            self.flags.delta( difference=difference, union=union,
                origin=origin )
        )

    def flags_delta_mixed( self,
        flags: Iterable[str],
        *, origin: Optional[str] = None,
    ) -> 'Target':
        return self.__class__( self.path,
            self.flags.delta_mixed(flags=flags, origin=origin) )

    def flags_clean_copy( self,
        *, origin: Optional[str] = None,
    ) -> 'Target':
        return self.__class__(self.path, self.flags.clean_copy(origin=origin))

    def path_derive( self, *pathparts: Union[str, RecordPath]
    ) -> 'Target':
        return self.__class__(RecordPath(self.path, *pathparts), self.flags)

    def check_unutilized_flags(self) -> None:
        try:
            self.flags.check_unutilized_flags()
        except UnutilizedFlagError as error:
            raise TargetError( "Unutilized flags in target {target}"
                .format(target=self)
            ) from error

    def abandon_children(self) -> None:
        self.flags.abandon_children()

    def __str__(self) -> str:
        return '{target.path!s}{target.flags:optional}'.format(target=self)

    def __repr__(self) -> str:
        return ( '{target.__class__.__name__}'
            '({target.path!r}, {target.flags!r})'
            .format(target=self) )

