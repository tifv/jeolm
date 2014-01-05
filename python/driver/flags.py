from functools import partial
from collections.abc import Container, Sequence, Mapping
import traceback

class FlagError(ValueError):
    pass

class UnutilizedFlagError(FlagError):
    def __init__(self, unutilized_flags, origin=None):
        joined_flags = ', '.join(
            "'{}'".format(flag) for flag in sorted(unutilized_flags) )
        message = "Unutilizd flags {flags}".format(flags=joined_flags)
        if origin is not None:
            message += " originating from {origin}".format(origin=origin)
        super().__init__(message)

class FlagContainer(Container):
    __slots__ = [
        'flags', 'utilized_flags', 'children',
        'origin', '_as_set' ]

    def __new__(cls, iterable=(), *, origin=None):
        self = super().__new__(cls)
        self.flags = flags = frozenset(iterable)
        if any(flag.startswith('-') for flag in flags):
            raise RuntimeError(flags)
        self.utilized_flags = set()
        self.children = []
        self.origin = origin
        if origin is None:
            self.origin = '\n' + ''.join(traceback.format_stack())
        return self

    def __iter__(self):
        raise NotImplementedError('you do not need this')

    def __len__(self):
        raise NotImplementedError('you do not need this')

    def __hash__(self):
        raise NotImplementedError('you do not need this')

    def __eq__(self, other):
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
        if not self.issuperset(iterable): # implicit utilize
            raise RuntimeError(self, iterable)

    @property
    def as_set(self):
        try:
            return self._as_set
        except AttributeError:
            as_set = self._as_set = self.reconstruct_as_set()
            return as_set

    def reconstruct_as_set(self):
        return self.flags

    def check_condition(self, condition):
        if isinstance(condition, str):
            return condition in self
        elif isinstance(condition, list):
            return all(self.check_condition(item) for item in condition)
        elif isinstance(condition, dict):
            if len(condition) > 1:
                raise FlagError('Condition, if a dict, must be of length 1')
            (key, value), = condition.items()
            if key == 'not':
                return not self.check_condition(value)
            elif key == 'or':
                if not isinstance(value, list):
                    raise FlagError("'or' conditioin value must be a list")
                return any(self.check_condition(item) for item in value)

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
            joined_flagsets = ', '.join(
                "{!r}".format(flagset) for flagset in matched_items )
            raise FlagError(
                "Multiple flag sets matched, ambiguity unresolved: {}"
                .format(joined_flagsets) )
        (matched_flagset, matched_value), = matched_items.items()
        self.utilize(matched_flagset)
        return matched_value

#    def get_flagged_item(self, mapping, metakey, *, default=None):
#        assert isinstance(metakey, str), type(metakey)
#        assert metakey.startswith('$'), metakey
#
#        matched_items = dict()
#        exact_matched_item = None
#        for key, value in mapping.items():
#            if not key.startswith(metakey):
#                continue
#            flagset_match = self.flag_pattern.match(key[len(metakey):])
#            if flagset_match is None:
#                continue
#            flagset_s = flagset_match.group('flags')
#            if flagset_s is None:
#                flagset = frozenset()
#            else:
#                flagset = frozenset(flagset_s.split(','))
#                if flagset_match.group('braket') is not None:
#                    if flagset == self.as_set:
#                        exact_matched_item = key, value
#                    continue
#                if not self.issuperset(flagset,
#                    utilize_present=False, utilize_missing=True
#                ):
#                    continue
#                assert flagset_match.group('brace') is not None, key
#            overmatched_flagsets = set()
#            flagset_is_overmatched = False
#            for a_flagset in matched_items:
#                if flagset < a_flagset:
#                    flagset_is_overmatched = True
#                    break
#                elif flagset > a_flagset:
#                    overmatched_flagsets.add(a_flagset)
#                elif flagset == a_flagset:
#                    raise DriverError("Clashing keys '{}' and '{}'"
#                        .format(key, matched_items[a_flagset][0]) )
#            if flagset_is_overmatched:
#                continue
#            for a_flagset in overmatched_flagsets:
#                del matched_items[a_flagset]
#            assert not any( af < flagset or af > flagset or af == flagset
#                for af in matched_items )
#            matched_items[flagset] = (key, value)
#        if not matched_items and exact_matched_item is None:
#            return None, default
#        if len(matched_items) > 1:
#            raise DriverError(
#                'Multiple keys matched, ambiguity unresolved: {}'
#                .format(', '.join(
#                    "'{}'".format(key)
#                    for key, value in matched_items.values() ))
#            )
#        if exact_matched_item is not None:
#            self.utilize(self.as_set)
#            return exact_matched_item
#        (matched_flagset, matched_item), = matched_items.items()
#        self.utilize(matched_flagset)
#        #matched_key, matched_value = matched_item
#        return matched_item
#
#    flag_pattern=re.compile(
#        r'(?:'
#            r'(?:(?P<braket>\[)|(?P<brace>\{))'
#            r'(?P<flags>.+)'
#            r'(?(braket)\])(?(brace)\})'
#        r')?$' )

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
        return FlagContainer(self.as_set, origin=origin)

    def check_unutilized_flags(self):
        unutilized_flags = self.flags - self.utilized_flags
        if unutilized_flags:
            raise UnutilizedFlagError(unutilized_flags, origin=self.origin)
        for child in self.children:
            child.check_unutilized_flags()

    def __str__(self):
        sorted_flags = sorted(self.as_set)
        if not sorted_flags:
            return ''
        return '[{}]'.format(','.join(sorted_flags))

    def __repr__(self):
        return ( '{self.__class__.__qualname__}({self.as_set})'
            .format(self=self) )

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

    def reconstruct_as_set(self):
        return self.parent.as_set.union(self.flags)

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

    def reconstruct_as_set(self):
        return self.parent.as_set.difference(self.flags)

