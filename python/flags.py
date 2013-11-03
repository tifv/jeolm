import collections.abc
import traceback

import logging
logger = logging.getLogger(__name__)

class UnutilizedError(Exception):
    pass

class FlagSet:
    __slots__ = ['flags', 'utilized', 'children', 'tb']

    def __new__(cls, iterable=()):
        instance = super().__new__(cls)
        instance.flags = frozenset(iterable)
        instance.utilized = set()
        instance.children = []
        instance.tb = traceback.extract_stack()
        return instance

    def __iter__(self):
        raise NotImplementedError('you do not need this')

    def __len__(self):
        raise NotImplementedError('you do not need this')

    def __hash__(self):
        raise NotImplementedError('you do not need this')

    def __contains__(self, x):
        if x in self.flags:
            self.utilized.add(x)
            return True
        return False

    def issuperset(self, iterable):
        return all(x in self for x in iterable)

    def intersection(self, iterable):
        return {x for x in iterable if x in self}

    def union(self, iterable):
        iterable = list(iterable)
        return self.child(iterable, PositiveFlagSet) if iterable else self

    def difference(self, iterable):
        iterable = list(iterable)
        return self.child(iterable, NegativeFlagSet) if iterable else self

    def bastard(self, iterable):
        iterable = list(iterable)
        return self.child(iterable, ChildFlagSet) if iterable else self

    def child(self, iterable, child_class):
        child = child_class(iterable, parent=self)
        self.children.append(child)
        return child

    @property
    def _unutilized(self):
        return self.flags - self.utilized

    def check_unutilized_flags(self, recursive=False):
        if self._unutilized:
            logger.error(''.join(traceback.format_list(self.tb)))
            raise UnutilizedError(self._unutilized)
        if recursive:
            for child in self.children:
                child.check_unutilized_flags()

    def as_set(self):
        """Debug only."""
        return self.flags

class ChildFlagSet(FlagSet):
    __slots__ = ['parent']

    def __new__(cls, iterable, parent):
        instance = super().__new__(cls, iterable)
        instance.parent = parent
        return instance

    def as_set(self):
        """Debug only."""
        return self.flags.union(parent.as_set())

class PositiveFlagSet(ChildFlagSet):
    def __contains__(self, x):
        return super().__contains__(x) or self.parent.__contains__(x)

class NegativeFlagSet(ChildFlagSet):
    def __contains__(self, x):
        return not super().__contains__(x) and self.parent.__contains__(x)

    @property
    def _unutilized(self):
        return {'-' + flag for flag in self.flags - self.utilized}

