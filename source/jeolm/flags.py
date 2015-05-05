from functools import partial
from collections.abc import Container
import traceback

import logging
logger = logging.getLogger(__name__)


class FlagError(Exception):
    pass

class UnutilizedFlagError(FlagError):
    def __init__(self, unutilized_flags, *, origin=None):
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
    __slots__ = [
        'flags', 'utilized_flags', 'children',
        'origin', '_as_frozenset' ]

    def __init__(self, iterable=(), *, origin=None):
        super().__init__()
        self.flags = flags = frozenset(iterable)
        if any(flag.startswith('-') for flag in flags):
            raise RuntimeError(flags)
        self._as_frozenset = None
        self.utilized_flags = set()
        self.children = []
        self.origin = origin
        if origin is None:
            self.origin = ( '(traceback):\n' +
                ''.join(traceback.format_stack()) )

    def __hash__(self):
        return hash(self.as_frozenset)

    def __eq__(self, other):
        if not isinstance(other, FlagContainer):
            return NotImplemented
        return self.as_frozenset == other.as_frozenset

    def __contains__(self, flag,
        *, utilize_present=True, utilize_missing=True, utilize=None
    ):
        if utilize is not None:
            utilize_present = utilize_missing = utilize
        if not flag.startswith('-'):
            return self._contains(flag,
                utilize_present=utilize_present,
                utilize_missing=utilize_missing )
        else:
            if flag.startswith('--'):
                raise FlagError(flag)
            return not self._contains(flag[1:],
                utilize_present=utilize_missing,
                utilize_missing=utilize_present )

    def _contains(self, flag,
        *, utilize_present=True, utilize_missing=True
    ):
        assert not flag.startswith('-'), flag
        if flag in self.flags:
            if utilize_present:
                self.utilized_flags.add(flag)
            return True
        return False

    def issuperset(self, iterable, **kwargs):
        contains = partial(self.__contains__, **kwargs)
        return all([contains(flag) for flag in iterable])

    def intersection(self, iterable, **kwargs):
        contains = partial(self.__contains__, **kwargs)
        return {flag for flag in iterable if contains(flag)}

    def utilize(self, iterable):
        """
        Ensure that iterable elements are present in container and utilized.
        """
        if not self.issuperset(iterable):
            raise RuntimeError(self, iterable)

    @property
    def as_frozenset(self):
        as_frozenset = self._as_frozenset
        if as_frozenset is None:
            as_frozenset = self._as_frozenset = self.reconstruct_as_frozenset()
        return as_frozenset

    #@property
    #def as_set(self):
    #    return set(self.as_frozenset)

    def reconstruct_as_frozenset(self):
        # Useful for overriding
        return self.flags

    def check_condition(self, condition):
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

    def select_matching_value(self, flagset_mapping, default=None):
        issuperset = partial( self.issuperset,
            utilize_present=False, utilize_missing=True )
        matched_items = dict()
        for flagset, value in flagset_mapping.items():
            if not isinstance(flagset, frozenset):
                raise RuntimeError(type(flagset))
            if not issuperset(flagset):
                continue
            overmatched = { a_flagset
                for a_flagset in matched_items
                if a_flagset < flagset }
            overmatching = { a_flagset
                for a_flagset in matched_items
                if a_flagset > flagset }
            assert not overmatching or not overmatched
            if overmatching:
                continue
            for a_flagset in overmatched:
                del matched_items[a_flagset]
            matched_items[flagset] = value
        if not matched_items:
            return default
        if len(matched_items) > 1:
            raise FlagError(
                "Multiple flag sets matched, ambiguity unresolved: {}"
                .format(', '.join(
                    "{!r}".format(flagset) for flagset in matched_items
                )) )
        (matched_flagset, matched_value), = matched_items.items()
        self.utilize(matched_flagset)
        return matched_value

    def union(self, iterable, *, overadd=True, origin=None):
        assert not isinstance(iterable, str)
        iterable = [
            flag for flag in iterable
            if overadd or not self.__contains__(flag, utilize=False) ]
        if iterable:
            return self.child(iterable, PositiveFlagContainer, origin=origin)
        else:
            return self

    def difference(self, iterable, *, underremove=True, origin=None):
        assert not isinstance(iterable, str)
        iterable = [
            flag for flag in iterable
            if underremove or self.__contains__(flag, utilize=False) ]
        if iterable:
            return self.child(iterable, NegativeFlagContainer, origin=origin)
        else:
            return self

    def delta(self, *, difference, union, origin=None):
        difference = frozenset(difference)
        union = frozenset(union)
        if difference & union:
            raise FlagError("Adding and removing the same flag at once.")
        return ( self
            .difference(difference, origin=origin)
            .union(union, origin=origin) )

    def bastard(self, iterable, *, origin=None):
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

    def child(self, iterable, child_class, *, origin=None):
        child = child_class(iterable, parent=self, origin=origin)
        self.children.append(child)
        return child

    def clean_copy(self, *, origin=None):
        return FlagContainer(self.as_frozenset, origin=origin)

    def check_unutilized_flags(self):
        unutilized_flags = self.flags - self.utilized_flags
        if unutilized_flags:
            raise UnutilizedFlagError(unutilized_flags, origin=self.origin)
        for child in self.children:
            child.check_unutilized_flags()

    @classmethod
    def split_flags_group(cls, flags_group):
        if flags_group is None:
            return frozenset()
        flag_list = []
        for piece in flags_group.split(','):
            flag = piece.strip()
            if not flag:
                continue
            elif ' ' in flag:
                raise FlagError("Flag '{}' contains a space".format(piece))
            flag_list.append(flag)
        flags = frozenset(flag_list)
        if len(flags) != len(flag_list):
            raise FlagError("Duplicated flags detected.")
        return flags

    def __format__(self, fmt):
        if fmt == 'optional':
            sorted_flags = sorted(self.as_frozenset)
            if not sorted_flags:
                return ''
            return '[{}]'.format(','.join(sorted_flags))
        return super().__format__(fmt)

    @property
    def _flags_repr(self):
        return '{{{}}}'.format(', '.join(
            "'{}'".format(flag) for flag in self.flags
        ))

    def __repr__(self):
        return ( '{flags.__class__.__name__}({flags._flags_repr})'
            .format(flags=self) )

class ChildFlagContainer(FlagContainer):
    __slots__ = ['parent']
    constructor_name = 'bastard'

    def __init__(self, iterable, parent, **kwargs):
        super().__init__(iterable, **kwargs)
        self.parent = parent

    def __repr__(self):
        return ( '{flags.parent!r}.{flags.constructor_name}({flags._flags_repr})'
            .format(flags=self) )

class PositiveFlagContainer(ChildFlagContainer):
    __slots__ = []
    constructor_name = 'union'

    def _contains(self, flag, **kwargs):
        if super()._contains(flag, **kwargs):
            return True
        elif self.parent._contains(flag, **kwargs):
            return True
        else:
            return False

    def reconstruct_as_frozenset(self):
        return self.parent.as_frozenset.union(self.flags)

class NegativeFlagContainer(ChildFlagContainer):
    __slots__ = []
    constructor_name = 'difference'

    def _contains(self, flag,
        *, utilize_present=True, utilize_missing=True
    ):
        if super()._contains( flag,
            utilize_present=utilize_missing, utilize_missing=utilize_present
        ):
            return False
        elif self.parent._contains( flag,
            utilize_present=utilize_present, utilize_missing=utilize_missing
        ):
            return True
        else:
            return False

    @property
    def unutilized_flags(self):
        return {'-' + flag for flag in self.flags - self.utilized_flags}

    def reconstruct_as_frozenset(self):
        return self.parent.as_frozenset.difference(self.flags)

