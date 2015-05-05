import re
from collections import OrderedDict

import logging
logger = logging.getLogger(__name__)


def unique(*iterables):
    seen_items = set()
    unique_items = list()
    for iterable in iterables:
        for item in iterable:
            if item not in seen_items:
                unique_items.append(item)
                seen_items.add(item)
    return unique_items

def natural_keyfunc(string, pattern=re.compile(r'(\d+)|\.')):
    assert isinstance(string, str), type(string)
    return [
        int(item) if item.isdigit() else item
        for item in pattern.split(string)
        if item is not None
    ]

def mapping_is_ordered(mapping):
    return isinstance(mapping, OrderedDict) or len(mapping) <= 1

def mapping_ordered_keys(mapping, *, keyfunc=None):
    """
    Return persistently ordered mapping keys.

    Only works with string keys.
    """
    if mapping_is_ordered(mapping):
        return mapping.keys()
    assert type(mapping) is dict, type(mapping)
    if keyfunc is None:
        keyfunc = natural_keyfunc
    return sorted(mapping.keys(), key=keyfunc)

def mapping_ordered_items(mapping, *, keyfunc=None):
    """
    Return persistently ordered dictionary items.

    Only works with string keys.
    """
    if mapping_is_ordered(mapping):
        return mapping.items()
    assert type(mapping) is dict, type(mapping)
    if keyfunc is None:
        keyfunc = natural_keyfunc
    def item_keyfunc(item):
        key, value = item # pylint: disable=unused-variable
        return keyfunc(key)
    return sorted(mapping.items(), key=item_keyfunc)

