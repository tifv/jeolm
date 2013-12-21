import collections.abc
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

class FlagSet:
    __slots__ = [
        'flags', 'utilized_flags', 'children',
        'origin', 'origin_tb' ]

    def __new__(cls, iterable=(), *, origin=None):
        instance = super().__new__(cls)
        instance.flags = frozenset(iterable)
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

    def __contains__(self, flag, utilize=True):
        if not flag.startswith('-'):
            if flag in self.flags:
                if utilize:
                    self.utilized_flags.add(flag)
                return True
            return False
        else:
            if flag.startswith('--'):
                raise ValueError(flag)
            return not self.__contains__(flag[1:], utilize=utilize)

    def issuperset(self, iterable):
        return all([flag in self for flag in iterable])

    def intersection(self, iterable):
        return {flag for flag in iterable if flag in self}

    def union(self, iterable, overadd=True, origin=None):
        assert not isinstance(iterable, str)
        iterable = [
            flag for flag in iterable
            if overadd or not self.__contains__(flag, utilize=False) ]
        if iterable:
            return self.child(iterable, PositiveFlagSet, origin=origin)
        else:
            return self

    def difference(self, iterable, underremove=True, origin=None):
        assert not isinstance(iterable, str)
        iterable = [
            flag for flag in iterable
            if underremove or self.__contains__(flag, utilize=False) ]
        if iterable:
            child = self.child(iterable, NegativeFlagSet, origin=origin)
        else:
            child = self
        assert all( not child.__contains__(flag, utilize=False)
            for flag in iterable ), child.as_set()
        return child

    def bastard(self, iterable, origin=None):
        iterable = list(iterable)
        if iterable:
            return self.child(iterable, ChildFlagSet, origin=origin)
        else:
            return self

    def child(self, iterable, ChildFlagSet, *, origin=None):
        child = ChildFlagSet(iterable, parent=self, origin=origin)
        self.children.append(child)
        return child

    def clean_copy(self, origin=None):
        return FlagSet(self.as_set(), origin=origin)

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
        return '{instance.__class__.__qualname__}({flags})'.format(
            instance=self,
            flags=', '.join( repr(flag) for flag in sorted(self.as_set()) )
        )

    def as_flags(self):
        sorted_flags = sorted(self.as_set())
        if not sorted_flags:
            return ''
        return '[{}]'.format(','.join(sorted_flags))

class ChildFlagSet(FlagSet):
    __slots__ = ['parent']

    def __new__(cls, iterable, parent, **kwargs):
        instance = super().__new__(cls, iterable, **kwargs)
        instance.parent = parent
        return instance

class PositiveFlagSet(ChildFlagSet):
    def __contains__(self, flag, utilize=True):
        if super().__contains__(flag, utilize=utilize):
            return True
        elif self.parent.__contains__(flag, utilize=utilize):
            return True
        else:
            return False

    def as_set(self):
        return self.parent.as_set().union(self.flags)

class NegativeFlagSet(ChildFlagSet):
    def __contains__(self, flag, utilize=True):
        if super().__contains__(flag, utilize=utilize):
            return False
        elif self.parent.__contains__(flag, utilize=utilize):
            return True
        else:
            return False

    @property
    def unutilized_flags(self):
        return {'-' + flag for flag in self.flags - self.utilized_flags}

    def as_set(self):
        return self.parent.as_set().difference(self.flags)

