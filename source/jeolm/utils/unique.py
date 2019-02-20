import logging
logger = logging.getLogger(__name__)

from typing import (TypeVar, Iterable, Hashable, Set, List)
T = TypeVar('T')

def unique(*iterables: Iterable[T]) -> List[T]:
    """
    Return list of unique values from iterables.
    """
    seen_items: Set[T] = set()
    unique_items: List[T] = list()
    for iterable in iterables:
        for item in iterable:
            if item not in seen_items:
                unique_items.append(item)
                seen_items.add(item)
    return unique_items

