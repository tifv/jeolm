import re
from collections import OrderedDict

import logging
logger = logging.getLogger(__name__)

from typing import ( TypeVar, Any,
    Callable, Sequence, Mapping,
    List, Tuple, Pattern, )
V = TypeVar('V')

KeyFunc = Callable[[str], Any]

def natural_keyfunc( string: str,
    *, _digit_regex: Pattern = re.compile(r'(\d+)')
) -> Any:
    assert isinstance(string, str), type(string)
    return [
        item
            if i % 2 == 0 else
        (int(item), item)
        for i, item in enumerate(_digit_regex.split(string))
    ]

def filename_keyfunc( string: str, *,
    basename_keyfunc: KeyFunc = natural_keyfunc,
    extension_keyfunc: KeyFunc = lambda x: x,
) -> Any:
    assert isinstance(string, str), type(string)
    dot = string.rfind('.')
    if dot < 0:
        return (basename_keyfunc(string),)
    else:
        return ( basename_keyfunc(string[:dot]),
            extension_keyfunc(string[dot+1:]) )

def mapping_is_ordered(mapping: Mapping) -> bool:
    return isinstance(mapping, OrderedDict) or len(mapping) <= 1

def mapping_ordered_keys( mapping: Mapping[str, Any],
    *, keyfunc: KeyFunc = natural_keyfunc
) -> Sequence[str]:
    """
    Return persistently ordered mapping keys.

    Only works with string keys.
    """
    if mapping_is_ordered(mapping):
        return list(mapping.keys())
    return sorted(mapping.keys(), key=keyfunc)

def mapping_ordered_items( mapping: Mapping[str, V],
    *, keyfunc: KeyFunc = natural_keyfunc
) -> Sequence[Tuple[str, V]]:
    """
    Return persistently ordered dictionary items.

    Only works with string keys.
    """
    if mapping_is_ordered(mapping):
        return list(mapping.items())
    def item_keyfunc(item: Tuple[str, V]) -> Any:
        key, value = item # pylint: disable=unused-variable
        return keyfunc(key)
    return sorted(mapping.items(), key=item_keyfunc)

