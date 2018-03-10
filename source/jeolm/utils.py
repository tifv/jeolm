import re
from collections import OrderedDict

import logging
logger = logging.getLogger(__name__)

class ClashingValueError(ValueError):
    pass

def check_and_set(mapping, key, value):
    """
    Set mapping[key] to value if key is not in mapping.

    Return True if key is not present in mapping.
    Return False if key is present and values was the same.
    Raise DriverError if key is present, but value is different.
    """
    try:
        other = mapping[key]
    except KeyError:
        mapping[key] = value
        return True
    if other == value:
        return False
    else:
        raise ClashingValueError(
            "Key {} has clashing values: {} and {}"
            .format(key, value, other) )

def unique(*iterables):
    """
    Return list of unique values from iterables.
    """
    seen_items = set()
    unique_items = list()
    for iterable in iterables:
        for item in iterable:
            if item not in seen_items:
                unique_items.append(item)
                seen_items.add(item)
    return unique_items

def natural_keyfunc(string, regex=re.compile(r'(\d+)|\.')):
    assert isinstance(string, str), type(string)
    key = list()
    for item in regex.split(string):
        if item is None:
            key.append(-1)
        elif item.isdigit():
            key.append(int(item))
        key.append(item)
    return key

def mapping_is_ordered(mapping):
    return isinstance(mapping, OrderedDict) or len(mapping) <= 1

# pylint: disable=unidiomatic-typecheck

def mapping_ordered_keys(mapping, *, keyfunc=None):
    """
    Return persistently ordered mapping keys.

    Only works with string keys.
    """
    if mapping_is_ordered(mapping):
        return list(mapping.keys())
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

# pylint: enable=unidiomatic-typecheck

