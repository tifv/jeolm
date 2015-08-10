from inspect import isgeneratorfunction
from functools import wraps
from contextlib import contextmanager

from jeolm.flags import FlagError
from jeolm.target import TargetError
from jeolm.records import RecordError

import logging
logger = logging.getLogger(__name__)

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
    aspect = method.__name__
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
    aspect = method.__name__
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

