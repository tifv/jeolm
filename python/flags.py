import collections.abc
import traceback

import logging
logger = logging.getLogger(__name__)

class UnutilizedFlagsError(Exception):
    def __init__(self, *args, origin_tb=None):
        super().__init__(*args)
        self.origin_tb = origin_tb

class FlagSet:
    __slots__ = ['flags', 'utilized_flags', 'children', 'origin_tb', 'user']

    def __new__(cls, iterable=(), *, user):
        instance = super().__new__(cls)
        instance.flags = frozenset(iterable)
        instance.utilized_flags = set()
        instance.children = []
        instance.user = user
        if not user:
            instance.origin_tb = traceback.extract_stack()
        else:
            instance.origin_tb = None
        return instance

    def __iter__(self):
        raise NotImplementedError('you do not need this')

    def __len__(self):
        raise NotImplementedError('you do not need this')

    def __hash__(self):
        raise NotImplementedError('you do not need this')

    def __contains__(self, x):
        if x in self.flags:
            self.utilized_flags.add(x)
            return True
        return False

    def issuperset(self, iterable):
        return all([x in self for x in iterable])

    def intersection(self, iterable):
        return {x for x in iterable if x in self}

    def union(self, iterable, overadd=True, user=False):
        assert not isinstance(iterable, str)
        iterable = [x for x in iterable if overadd or x not in self]
        if iterable:
            return self.child(iterable, PositiveFlagSet, user=user)
        else:
            return self

    def difference(self, iterable, user=False):
        assert not isinstance(iterable, str)
        iterable = list(iterable)
        if iterable:
            return self.child(iterable, NegativeFlagSet, user=user)
        else:
            return self

    def bastard(self, iterable, user=False):
        iterable = list(iterable)
        if iterable:
            return self.child(iterable, ChildFlagSet, user=user)
        else:
            return self

    def child(self, iterable, ChildFlagSet, *, user):
        child = ChildFlagSet(iterable, parent=self, user=user)
        self.children.append(child)
        return child

#    @property
#    def level(self):
#        return 1

    def clean_copy(self):
        return FlagSet(self.as_set(), user=True)

    @property
    def unutilized_flags(self):
        return self.flags - self.utilized_flags

    def check_unutilized_flags(self, recursive=False):
        unutilized_flags = self.unutilized_flags
        if unutilized_flags:
            raise UnutilizedFlagsError(unutilized_flags,
                origin_tb=self.origin_tb )
        if recursive:
            for child in self.children:
                child.check_unutilized_flags(recursive=recursive)

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

#    @property
#    def level(self):
#        return 1 + self.parent.level

class PositiveFlagSet(ChildFlagSet):
    def __contains__(self, x):
        return super().__contains__(x) or self.parent.__contains__(x)

    def as_set(self):
        return self.parent.as_set().union(self.flags)

class NegativeFlagSet(ChildFlagSet):
    def __contains__(self, x):
        return not super().__contains__(x) and self.parent.__contains__(x)

    @property
    def unutilized_flags(self):
        return {'-' + flag for flag in self.flags - self.utilized_flags}

    def as_set(self):
        return self.parent.as_set().difference(self.flags)

