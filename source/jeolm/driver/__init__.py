import abc
from inspect import isgeneratorfunction
from functools import wraps
from collections import namedtuple
from contextlib import contextmanager
import re
from pathlib import PurePosixPath

from jeolm.records import ( RecordPath, RecordError, Record, Records,
    NAME_PATTERN, RELATIVE_NAME_PATTERN )
from jeolm.target import ( Flag, FlagContainer, Target,
    FlagError, TargetError,
    RELATIVE_FLAGS_PATTERN_TIGHT )

import logging
logger = logging.getLogger(__name__)

from typing import ( TypeVar, Type, NewType, ClassVar, overload,
    Any, Union, Optional,
    Callable, Hashable, Iterable, Iterator, Collection, Sequence, Mapping,
    Tuple, List, Set, FrozenSet, Dict,
    Generator, Pattern )
T = TypeVar('T')
R = TypeVar('R')

ATTRIBUTE_KEY_PATTERN = (
    r'(?P<stem>'
        r'(?:\$\w+(?:-\w+)*)+'
    r')'
    r'(?:\['
        r'(?P<flags>' + RELATIVE_FLAGS_PATTERN_TIGHT + r')'
    r'\])?'
)

FIGURE_REF_PATTERN = (
    r'(?P<figure>'
        '/?'
        '(?:(?:' + RELATIVE_NAME_PATTERN + ')/)*'
        '(?:' + NAME_PATTERN + ')'
    r')'
    r'(?::(?P<figure_code>'
        + NAME_PATTERN +
    r'))?'
)

class DriverRecords(Records):

    name_regex: ClassVar[Pattern] = \
        re.compile(NAME_PATTERN)

    _attribute_key_regex: ClassVar[Pattern] = \
        re.compile(ATTRIBUTE_KEY_PATTERN)

    dropped_keys: ClassVar[Dict[str, str]] = {
    }

    def _absorb_attribute_into( self,
        key: str, value: Any, path: RecordPath, record: Record, *,
        overwrite: bool = True,
    ) -> None:
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

    @classmethod
    def select_flagged_item( cls,
        mapping: Mapping[str, T],
        key_stem: str, flags: FlagContainer,
        *, required_flags: Collection[Flag] = frozenset()
    ) -> Tuple[Optional[str], Optional[T]]:
        """Return (key, value) from mapping."""
        if not isinstance(key_stem, str):
            raise TypeError(type(key_stem))
        if not key_stem.startswith('$'):
            raise ValueError(key_stem)
        if not isinstance(flags, FlagContainer):
            raise TypeError(type(flags))

        flag_set_map: Dict[
            FrozenSet[Flag],
            Tuple[Optional[str], Optional[T]]
        ] = dict()
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


class DocumentTemplate:

    class Key(Hashable):
        __slots__ = ()

    _items: List[Union[str, Key]]
    _key_set: Set[Key]
    _keys: List[Key]

    def __init__(self) -> None:
        self._items = []
        self._key_set = set()
        self._keys = list()

    def append_text(self, string: str) -> None:
        self._items.append(str(string))

    def extend_text(self, strings: Iterable[str]) -> None:
        self._items.extend(str(string) for string in strings)

    def append_key(self, key: Key) -> None:
        if key not in self._key_set:
            self._key_set.add(key)
            self._keys.append(key)
        self._items.append(key)

    def keys(self) -> Sequence['DocumentTemplate.Key']:
        return tuple(self._keys)

    def substitute(self, mapping: Mapping[Key, str]) -> str:
        if not self._key_set >= mapping.keys():
            raise ValueError
        return ''.join(
            item
                if isinstance(item, str) else
            mapping[item]
            for item in self._items )


Compiler = NewType('Compiler', str)

class DocumentRecipe:

    __slots__ = ['_outname', '_compiler', '_document']

    _outname: str
    _compiler: Compiler
    _document: DocumentTemplate

    @property
    def outname(self) -> str:
        return self._outname

    @outname.setter
    def outname(self, outname: str) -> None:
        if '/' in outname:
            raise ValueError(outname)
        self._outname = outname

    @property
    def compiler(self) -> Compiler:
        return self._compiler

    @compiler.setter
    def compiler(self, compiler: Compiler) -> None:
        if compiler not in {'latex', 'pdflatex', 'xelatex', 'lualatex'}:
            raise ValueError(compiler)
        self._compiler = compiler

    class SourceKey(DocumentTemplate.Key):
        __slots__ = ['source_path']
        def __init__(self, source_path: RecordPath) -> None:
            self.source_path = source_path
        def __eq__(self, other: Any) -> bool:
            return ( isinstance(other, type(self)) and
                self.source_path == other.source_path )
        def __hash__(self) -> Any:
            return hash((self.__class__.__name__, self.source_path))

    class PackageKey(DocumentTemplate.Key):
        __slots__ = ['package_path']
        def __init__(self, package_path: RecordPath) -> None:
            self.package_path = package_path
        def __eq__(self, other: Any) -> bool:
            return ( isinstance(other, type(self)) and
                self.package_path == other.package_path )
        def __hash__(self) -> Any:
            return hash((self.__class__.__name__, self.package_path))
        def __repr__(self) -> str:
            return f"{self.__class__.__qualname__}({self.package_path!r})"

    class BaseFigureKey(DocumentTemplate.Key):
        __slots__ = ['figure_path', 'figure_index']
        def __init__( self, figure_path: RecordPath, figure_index: int,
        ) -> None:
            self.figure_path = figure_path
            self.figure_index = figure_index
        def __eq__(self, other: Any) -> bool:
            return ( isinstance(other, type(self)) and
                self.figure_path == other.figure_path and
                self.figure_index == other.figure_index )
        def __hash__(self) -> Any:
            return hash(( self.__class__.__name__,
                self.figure_path, self.figure_index ))

    class FigureKey(BaseFigureKey):
        __slots__ = ()

    class FigureSizeKey(BaseFigureKey):
        __slots__ = ()

    _key_types = (SourceKey, PackageKey, FigureKey, FigureSizeKey)

    @property
    def document(self) -> DocumentTemplate:
        return self._document

    @document.setter
    def document(self, document: DocumentTemplate) -> None:
        for key in document.keys():
            if not isinstance(key, self._key_types):
                raise TypeError(type(key))
        self._document = document


class PackageRecipe:

    __slots__ = ['_source_type', '_source', '_name']

    _source_type: str
    _source: PurePosixPath
    _name: str

    def __init__( self, source_type: str, source: PurePosixPath, name: str
    ) -> None:
        self.source_type = source_type
        self.source = source
        self.name = name

    @property
    def source_type(self) -> str:
        return self._source_type

    @source_type.setter
    def source_type(self, source_type: str) -> None:
        if source_type not in {'dtx', 'sty'}:
            raise ValueError(source_type)
        self._source_type = source_type

    @property
    def source(self) -> PurePosixPath:
        return self._source

    @source.setter
    def source(self, source: PurePosixPath) -> None:
        if not isinstance(source, PurePosixPath):
            raise TypeError(type(source))
        self._source = source

    @property
    def name(self) -> str:
        """Package name, as in ProvidesPackage."""
        return self._name

    @name.setter
    def name(self, name: str) -> None:
        if not isinstance(name, str):
            raise TypeError(type(name))
        self._name = name


class FigureRecipe:

    __slots__ = ['_figure_type', '_source_type', '_source', '_other_sources']

    _figure_type: str
    _source_type: str
    _source: PurePosixPath
    _other_sources: Dict[str, PurePosixPath]

    def __init__( self,
        figure_type: str, source_type: str, source: PurePosixPath,
    ) -> None:
        self.figure_type = figure_type
        self.source_type = source_type
        self.source = source

    @property
    def figure_type(self) -> str:
        return self._figure_type

    @figure_type.setter
    def figure_type(self, figure_type: str) -> None:
        if figure_type not in {'pdf', 'eps', 'png', 'jpg'}:
            raise ValueError(figure_type)
        self._figure_type = figure_type

    @property
    def source_type(self) -> str:
        return self._source_type

    @source_type.setter
    def source_type(self, source_type: str) -> None:
        if source_type not in {'asy', 'svg', 'pdf', 'eps', 'png', 'jpg'}:
            raise ValueError(source_type)
        self._source_type = source_type

    @property
    def source(self) -> PurePosixPath:
        return self._source

    @source.setter
    def source(self, source: PurePosixPath) -> None:
        if not isinstance(source, PurePosixPath):
            raise TypeError(type(source))
        self._source = source

    @property
    def other_sources(self) -> Dict[str, PurePosixPath]:
        """{accessed_name : source_path for each accessed source_path}
        where accessed_name is a filename with '.asy' extension,
        and source_path has '.asy' extension"""
        return self._other_sources

    @other_sources.setter
    def other_sources(self, other_sources: Dict[str, PurePosixPath]) -> None:
        if not isinstance(other_sources, dict):
            raise TypeError(type(other_sources))
        self._other_sources = other_sources

    def __repr__(self) -> str:
        return ( f"{self.__class__.__name__}("
            f"{self._figure_type}, {self._source_type}, "
            f"{self._source})")

class Driver(DriverRecords, metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def list_targetable_paths(self) -> Iterable[RecordPath]:
        raise NotImplementedError

    @abc.abstractmethod
    def path_is_targetable(self, record_path: RecordPath) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def list_targetable_children( self, record_path: RecordPath,
    ) -> Iterable[RecordPath]:
        raise NotImplementedError

    @abc.abstractmethod
    def list_delegated_targets( self, *targets: Target
    ) -> Iterable[Target]:
        raise NotImplementedError

    @abc.abstractmethod
    def produce_document_recipe( self, target: Target,
    ) -> DocumentRecipe:
        raise NotImplementedError

    @abc.abstractmethod
    def produce_document_asy_context( self, target: Target,
    ) -> Tuple[Compiler, str]:
        """Return (latex_compiler, latex_preamble)."""
        raise NotImplementedError

    @abc.abstractmethod
    def produce_package_recipe( self, package_path: RecordPath,
    ) -> PackageRecipe:
        raise NotImplementedError

    @abc.abstractmethod
    def produce_figure_recipe( self, figure_path: RecordPath,
        *, figure_types: FrozenSet[str] = frozenset(('pdf', 'png', 'jpg')),
    ) -> Dict[str, Any]:
        raise NotImplementedError


class DriverError(Exception):
    pass

_DRIVER_ERRORS = (DriverError, TargetError, RecordError, FlagError)

if not __debug__:

    @contextmanager
    def _fold_driver_errors() -> Generator[None, None, None]:
        try:
            yield
        except DriverError as error:
            driver_messages = []
            chain_error: Optional[BaseException] = error
            while isinstance(chain_error, DriverError):
                # pylint: disable=unpacking-non-sequence
                message, = chain_error.args
                # pylint: enable=unpacking-non-sequence
                driver_messages.append(str(message))
                chain_error = chain_error.__cause__
            raise DriverError(
                'Driver error stack:\n' +
                '\n'.join(driver_messages)
            ) from error

#    @overload
#    def folding_driver_errors( function: Callable[..., Generator[T, None, R]],
#    ) -> Callable[..., Generator[T, None, R]]:
#        pass
#
#    @overload
#    def folding_driver_errors( function: Callable[..., Iterator[T]],
#    ) -> Callable[..., Iterator[T]]:
#        pass
#
#    @overload
#    def folding_driver_errors( function: Callable[..., T],
#    ) -> Callable[..., T]:
#        pass

    def folding_driver_errors(function: Callable) -> Callable:
        """Decorator."""
        if not isgeneratorfunction(function):
            @wraps(function)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with _fold_driver_errors():
                    return function(*args, **kwargs)
            return wrapper
        else:
            @wraps(function)
            def wrapper_g(*args: Any, **kwargs: Any) -> Any:
                with _fold_driver_errors():
                    return ( yield from
                        function(*args, **kwargs)
                    )
            return wrapper_g

else:

    @contextmanager
    def _fold_driver_errors_dummy() -> Generator[None, None, None]:
        yield

    def folding_driver_errors_dummy(function: Callable) -> Callable:
        return function

    _fold_driver_errors = _fold_driver_errors_dummy
    folding_driver_errors = folding_driver_errors_dummy

def checking_target_recursion(
    *, skip_check: Optional[Callable] = None,
) -> Callable[[Callable[..., Generator]], Callable[..., Generator]]:
    """Decorator factory."""
    def decorator( method: Callable[..., Generator[T, None, R]],
    ) -> Callable[..., Generator[T, None, R]]:
        assert isgeneratorfunction(method)
        @wraps(method)
        def wrapper( self: Any, target: Target, *args: Any,
            _seen_targets: Optional[Set[Target]] = None,
            **kwargs: Any
        ) -> Any:
            if _seen_targets is None:
                _seen_targets = set()
            if skip_check is None:
                checking = True
            else:
                checking = not skip_check(self, target, *args, **kwargs)
            if checking:
                if target in _seen_targets:
                    raise DriverError(f"Cycle detected from {target}")
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
def process_target_aspect( target: Union[Target, RecordPath], aspect: str,
) -> Generator[None, None, None]:
    try:
        yield
    except _DRIVER_ERRORS as error:
        raise DriverError(f"{target} {aspect}") from error

@contextmanager
def process_target_key( target: Union[Target, RecordPath], key: str,
) -> Generator[None, None, None]:
    assert key is not None
    with process_target_aspect(target, aspect=f'key {key}'):
        yield

#@overload
#def processing_target( method: Callable[..., Generator[T, None, R]],
#) -> Callable[..., Generator[T, None, R]]:
#    pass
#
#@overload
#def processing_target( method: Callable[..., Iterator[T]],
#) -> Callable[..., Iterator[T]]:
#    pass
#
#@overload
#def processing_target( method: Callable[..., T],
#) -> Callable[..., T]:
#    pass

def processing_target(method: Callable) -> Callable:
    """Decorator."""
    aspect = method.__qualname__
    if not isgeneratorfunction(method):
        @wraps(method)
        def wrapper( self: Any, target: Target,
            *args: Any, **kwargs: Any
        ) -> Any:
            with process_target_aspect(target, aspect=aspect):
                return method(self, target, *args, **kwargs)
        return wrapper
    else:
        @wraps(method)
        def wrapper_g( self: Any, target: Target,
            *args: Any, **kwargs: Any
        ) -> Any:
            with process_target_aspect(target, aspect=aspect):
                return ( yield from
                    method(self, target, *args, **kwargs)
                )
        return wrapper_g

#@overload
#def processing_package_path( method: Callable[..., Generator[T, None, R]],
#) -> Callable[..., Generator[T, None, R]]:
#    pass
#
#@overload
#def processing_package_path( method: Callable[..., Iterator[T]],
#) -> Callable[..., Iterator[T]]:
#    pass
#
#@overload
#def processing_package_path( method: Callable[..., T],
#) -> Callable[..., T]:
#    pass

def processing_package_path(method: Callable) -> Callable:
    """Decorator."""
    aspect = method.__qualname__
    if not isgeneratorfunction(method):
        @wraps(method)
        def wrapper( self: Any, package_path: RecordPath,
            *args: Any, **kwargs: Any
        ) -> Any:
            with process_target_aspect(package_path, aspect=aspect):
                return method(self, package_path, *args, **kwargs)
        return wrapper
    else:
        @wraps(method)
        def wrapper_g( self: Any, package_path: RecordPath,
            *args: Any, **kwargs: Any
        ) -> Any:
            with process_target_aspect(package_path, aspect=aspect):
                return ( yield from
                    method(self, package_path, *args, **kwargs)
                )
        return wrapper_g

#@overload
#def processing_figure_path( method: Callable[..., Generator[T, None, R]],
#) -> Callable[..., Generator[T, None, R]]:
#    pass
#
#@overload
#def processing_figure_path( method: Callable[..., Iterator[T]],
#) -> Callable[..., Iterator[T]]:
#    pass
#
#@overload
#def processing_figure_path( method: Callable[..., T],
#) -> Callable[..., T]:
#    pass

def processing_figure_path(method: Callable) -> Callable:
    """Decorator."""
    if not isgeneratorfunction(method):
        @wraps(method)
        def wrapper( self: Any, figure_path: RecordPath,
            *args: Any, **kwargs: Any
        ) -> Any:
            with process_target_aspect( figure_path,
                    aspect=method.__qualname__ ):
                return method(self, figure_path, *args, **kwargs)
        return wrapper
    else:
        @wraps(method)
        def wrapper_g( self: Any, figure_path: RecordPath,
            *args: Any, **kwargs: Any
        ) -> Any:
            with process_target_aspect( figure_path,
                    aspect=method.__qualname__ ):
                return ( yield from
                    method(self, figure_path, *args, **kwargs)
                )
        return wrapper_g

# XXX this will eventually be obsoleted by static type checking
def ensure_type_items( typespec: Union[Tuple[Type, ...], Type]
) -> Callable[[Callable[..., Generator]], Callable[..., Generator]]:
    def decorator( method: Callable[..., Generator]
    ) -> Callable[..., Generator]:
        assert isgeneratorfunction(method)
        @wraps(method)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Generator:
            for item in method(self, *args, **kwargs):
                if isinstance(item, typespec):
                    yield item
                else:
                    raise RuntimeError(
                        f"Generator {method.__qualname__} yielded value "
                        f"of type {type(item)}" )
        return wrapper
    return decorator


