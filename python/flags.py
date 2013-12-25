import collections.abc
from functools import partial
import traceback

import logging
logger = logging.getLogger(__name__)

class UnutilizedFlagsError(Exception):
    def __init__(self, unutilized_flags, origin=None):
        unutilized_flags = ', '.join(
            "'{}'".format(flag) for flag in sorted(unutilized_flags) )
        message = "Unutilized flags {flags} originating from {origin}".format(
            flags=unutilized_flags, origin=origin )
        super().__init__(message)

class FlagContainer(collections.abc.Container):
    __slots__ = [
        'flags', 'utilized_flags', 'children',
        'origin', 'origin_tb' ]

    def __new__(cls, iterable=(), *, origin=None):
        instance = super().__new__(cls)
        instance.flags = flags = frozenset(iterable)
        assert not any(flag.startswith('-') for flag in flags)
        instance.utilized_flags = set()
        instance.children = []
        instance.origin = origin
        if origin is None:
            instance.origin = '\n' + ''.join(traceback.format_stack())
        return instance

    def __iter__(self):
        raise NotImplementedError('you do not need this')

    def __len__(self):
        raise NotImplementedError('you do not need this')

    def __hash__(self):
        raise NotImplementedError('you do not need this')

    def __eq__(self):
        raise NotImplementedError('you do not need this')

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
                raise ValueError(flag)
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

    def union(self, iterable, overadd=True, origin=None):
        assert not isinstance(iterable, str)
        iterable = [
            flag for flag in iterable
            if overadd or not self.__contains__(flag, utilize=False) ]
        if iterable:
            return self.child(iterable, PositiveFlagContainer, origin=origin)
        else:
            return self

    def difference(self, iterable, underremove=True, origin=None):
        assert not isinstance(iterable, str)
        iterable = [
            flag for flag in iterable
            if underremove or self.__contains__(flag, utilize=False) ]
        if iterable:
            return self.child(iterable, NegativeFlagContainer, origin=origin)
        else:
            return self

    def bastard(self, iterable, origin=None):
        iterable = list(iterable)
        if iterable:
            return self.child(iterable, ChildFlagContainer, origin=origin)
        else:
            return self

    def child(self, iterable, ChildFlagContainer, *, origin=None):
        child = ChildFlagContainer(iterable, parent=self, origin=origin)
        self.children.append(child)
        return child

    def clean_copy(self, origin=None):
        return FlagContainer(self.as_set(), origin=origin)

    @property
    def unutilized_flags(self):
        return self.flags - self.utilized_flags

    def check_unutilized_flags(self):
        unutilized_flags = self.unutilized_flags
        if unutilized_flags:
            raise UnutilizedFlagsError(unutilized_flags, origin=self.origin)
        for child in self.children:
            child.check_unutilized_flags()

    def as_set(self):
        return self.flags

    def as_frozenset(self):
        the_set = self.as_set()
        assert isinstance(the_set, frozenset), type(the_set)
        return the_set

    def __repr__(self):
        return '{classname}([{flags}])'.format(
            classname=self.__class__.__qualname__,
            flags=', '.join( repr(flag) for flag in sorted(self.as_set()) )
        )

    def as_flags(self):
        sorted_flags = sorted(self.as_set())
        if not sorted_flags:
            return ''
        return '[{}]'.format(','.join(sorted_flags))

class ChildFlagContainer(FlagContainer):
    __slots__ = ['parent']

    def __new__(cls, iterable, parent, **kwargs):
        instance = super().__new__(cls, iterable, **kwargs)
        instance.parent = parent
        return instance

class PositiveFlagContainer(ChildFlagContainer):
    def _contains(self, flag, **kwargs):
        if super()._contains(flag, **kwargs):
            return True
        elif self.parent._contains(flag, **kwargs):
            return True
        else:
            return False

    def as_set(self):
        return self.parent.as_set().union(super().as_set())

class NegativeFlagContainer(ChildFlagContainer):
    def _contains(self, flag,
        *, utilize_present=True, utilize_missing=True
    ):
        if super()._contains(flag,
            utilize_present=utilize_missing, utilize_missing=utilize_present
        ):
            return False
        elif self.parent._contains(flag,
            utilize_present=utilize_present, utilize_missing=utilize_missing
        ):
            return True
        else:
            return False

    @property
    def unutilized_flags(self):
        return {'-' + flag for flag in self.flags - self.utilized_flags}

    def as_set(self):
        return self.parent.as_set().difference(self.flags)

