from inspect import isgeneratorfunction
from functools import wraps
from collections import namedtuple
from contextlib import contextmanager
import re

from jeolm.records import ( Records, RecordError,
    NAME_PATTERN )
from jeolm.target import ( FlagContainer,
    FlagError, TargetError,
    RELATIVE_FLAGS_PATTERN_TIGHT )

import logging
logger = logging.getLogger(__name__)

ATTRIBUTE_KEY_PATTERN = (
    r'(?P<stem>'
        r'(?:\$\w+(?:-\w+)*)+'
    r')'
    r'(?:\['
        r'(?P<flags>' + RELATIVE_FLAGS_PATTERN_TIGHT + r')'
    r'\])?'
)

class DriverRecords(Records):

    name_regex = re.compile(NAME_PATTERN)

    _attribute_key_regex = re.compile(ATTRIBUTE_KEY_PATTERN)

    dropped_keys = {
    }

    # pylint: disable=unused-argument,no-self-use

    def _absorb_attribute_into( self,
        key, value, path, record, *,
        overwrite=True
    ):
        match = self._attribute_key_regex.fullmatch(key)
        if match is None:
            raise RecordError(
                "Nonconforming attribute key {key} (path {path})"
                .format(key=key, path=path)
            )
        key_stem = match.group('stem')
        if key_stem in self.dropped_keys:
            logger.warning(
                "Dropped key <RED>%(key)s<NOCOLOUR> "
                "detected in <YELLOW>%(path)s<NOCOLOUR> "
                "(replace it with %(modern_key)s)",
                dict(
                    key=key_stem, path=path,
                    modern_key=self.dropped_keys[key_stem], )
            )
        super()._absorb_attribute_into(
            key, value, path, record,
            overwrite=overwrite )

    # pylint: enable=unused-argument,no-self-use

    @classmethod
    def select_flagged_item( cls, mapping, key_stem, flags,
        *, required_flags=frozenset()
    ):
        """Return (key, value) from mapping."""
        if not isinstance(key_stem, str):
            raise TypeError(type(key_stem))
        if not key_stem.startswith('$'):
            raise ValueError(key_stem)
        if not isinstance(flags, FlagContainer):
            raise TypeError(type(flags))

        flag_set_map = dict()
        for key, value in mapping.items():
            match = cls._attribute_key_regex.fullmatch(key)
            if match is None or match.group('stem') != key_stem:
                continue
            flags_string = match.group('flags')
            flag_set = frozenset(flags.split_flags_string(flags_string))
            if not flag_set.issuperset(required_flags):
                continue
            if flag_set in flag_set_map:
                raise RecordError("Clashing keys '{}' and '{}'"
                    .format(key, flag_set_map[flag_set][0]) )
            flag_set_map[flag_set] = (key, value)
        flag_set_map.setdefault(frozenset(), (None, None))
        return flags.select_matching_value(flag_set_map)

class DriverError(Exception):
    pass

_DRIVER_ERRORS = (DriverError, TargetError, RecordError, FlagError)

if not __debug__:

    @contextmanager
    def _fold_driver_errors():
        try:
            yield
        except DriverError as error:
            driver_messages = []
            while isinstance(error, DriverError):
                # pylint: disable=unpacking-non-sequence
                message, = error.args
                # pylint: enable=unpacking-non-sequence
                driver_messages.append(str(message))
                error = error.__cause__
            raise DriverError(
                'Driver error stack:\n' +
                '\n'.join(driver_messages)
            ) from error

    def folding_driver_errors(function):
        """Decorator."""
        if not isgeneratorfunction(function):
            @wraps(function)
            def wrapper(*args, **kwargs):
                with _fold_driver_errors():
                    return function(*args, **kwargs)
        else:
            @wraps(function)
            def wrapper(*args, **kwargs):
                with _fold_driver_errors():
                    return ( yield from
                        function(*args, **kwargs)
                    )
        return wrapper

else:

    @contextmanager
    def _fold_driver_errors():
        yield

    def folding_driver_errors(function):
        return function

def checking_target_recursion(*, skip_check=None):
    """Decorator factory."""
    def decorator(method):
        assert isgeneratorfunction(method)
        @wraps(method)
        def wrapper(self, target, *args, _seen_targets=None, **kwargs):
            if _seen_targets is None:
                _seen_targets = set()
            if skip_check is None:
                checking = True
            else:
                checking = not skip_check(self, target, *args, **kwargs)
            if checking:
                if target in _seen_targets:
                    raise DriverError( "Cycle detected from {target}"
                        .format(target=target) )
                else:
                    _seen_targets.add(target)
            try:
                return ( yield from
                    method( self, target, *args,
                        _seen_targets=_seen_targets, **kwargs )
                )
            finally:
                if checking:
                    _seen_targets.discard(target)
        return wrapper
    return decorator

@contextmanager
def process_target_aspect(target, aspect):
    try:
        yield
    except _DRIVER_ERRORS as error:
        raise DriverError( "{target} {aspect}"
            .format(target=target, aspect=aspect)
        ) from error

@contextmanager
def process_target_key(target, key):
    assert key is not None
    with process_target_aspect(target, aspect='key {}'.format(key)):
        yield

def processing_target(method):
    """Decorator."""
    aspect = method.__qualname__
    if not isgeneratorfunction(method):
        @wraps(method)
        def wrapper(self, target, *args, **kwargs):
            with process_target_aspect(target, aspect=aspect):
                return method(self, target, *args, **kwargs)
    else:
        @wraps(method)
        def wrapper(self, target, *args, **kwargs):
            with process_target_aspect(target, aspect=aspect):
                return ( yield from
                    method(self, target, *args, **kwargs)
                )
    return wrapper

def processing_package_path(method):
    """Decorator."""
    aspect = method.__qualname__
    if not isgeneratorfunction(method):
        @wraps(method)
        def wrapper(self, package_path, *args, **kwargs):
            with process_target_aspect(package_path, aspect=aspect):
                return method(self, package_path, *args, **kwargs)
    else:
        @wraps(method)
        def wrapper(self, package_path, *args, **kwargs):
            with process_target_aspect(package_path, aspect=aspect):
                return ( yield from
                    method(self, package_path, *args, **kwargs)
                )
    return wrapper

def processing_figure_path(method):
    """Decorator."""
    aspect = method.__qualname__
    if not isgeneratorfunction(method):
        @wraps(method)
        def wrapper(self, figure_path, *args, **kwargs):
            with process_target_aspect(figure_path, aspect=aspect):
                return method(self, figure_path, *args, **kwargs)
    else:
        @wraps(method)
        def wrapper(self, figure_path, *args, **kwargs):
            with process_target_aspect(figure_path, aspect=aspect):
                return ( yield from
                    method(self, figure_path, *args, **kwargs)
                )
    return wrapper

def ensure_type_items(typespec):
    def decorator(method):
        assert isgeneratorfunction(method)
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            for item in method(self, *args, **kwargs):
                if isinstance(item, typespec):
                    yield item
                else:
                    raise RuntimeError(
                        "Generator {method} yielded value of type {type}"
                        .format(method=method.__qualname__, type=type(item)) )
        return wrapper
    return decorator


class DocumentTemplate:

    def __init__(self):
        self._items = []
        self._key_set = set()
        self._keys = list()
        self._frozen = False

    def append_text(self, string):
        if self._frozen:
            raise RuntimeError
        self._items.append(str(string))

    def extend_text(self, strings):
        if self._frozen:
            raise RuntimeError
        self._items.extend(str(string) for string in strings)

    def append_key(self, key):
        if self._frozen:
            raise RuntimeError
        if key not in self._key_set:
            self._key_set.add(key)
            self._keys.append(key)
        self._items.append({'key' : key})

    def freeze(self):
        self._frozen = True
        self._key_set = frozenset(self._key_set)
        self._keys = tuple(self._keys)

    def keys(self):
        return tuple(self._keys)

    def substitute(self, mapping):
        if not self._key_set >= mapping.keys():
            raise ValueError
        return ''.join(
            mapping[item['key']]
                if isinstance(item, dict) else
            item
            for item in self._items )

