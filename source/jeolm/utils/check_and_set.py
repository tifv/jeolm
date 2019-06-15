import logging
logger = logging.getLogger(__name__)

from typing import TypeVar, Hashable, MutableMapping
K = TypeVar('K', bound=Hashable)
V = TypeVar('V')

class ClashingValueError(ValueError):
    pass

def check_and_set( mapping: MutableMapping[K, V],
    key: K, value: V,
) -> bool:
    """
    Set mapping[key] to value if key is not in mapping.

    Return True if key is not present in mapping.
    Return False if key is present and values was the same.
    Raise ClashingValueError if key is present, but value is different.
    """
    try:
        other: V = mapping[key]
    except KeyError:
        mapping[key] = value
        return True
    if other == value:
        return False
    else:
        raise ClashingValueError(
            "Key {} has clashing values: {} and {}"
            .format(key, value, other) )

