import re
from collections import OrderedDict

def unique(*iterables):
    seen = set()
    unique = list()
    for iterable in iterables:
        for i in iterable:
            if i not in seen:
                unique.append(i)
                seen.add(i)
    return unique

def natural_keyfunc(s, pattern=re.compile(r'(\d+)')):
    assert isinstance(s, str), type(s)
    return [
         [
            int(r) if r.isdigit() else r
            for r in pattern.split(q)
        ]
        for q in s.split('.')
    ]

def dict_is_ordered(d):
    return isinstance(d, OrderedDict) or len(d) <= 1

def dict_ordered_keys(d, *, keyfunc=None):
    """Provide persistently ordered dictionary items."""
    if dict_is_ordered(d):
        return d.keys()
    assert type(d) is dict, type(d)
    if keyfunc is None:
        keyfunc = natural_keyfunc
    return sorted(d.keys(), key=keyfunc)

def dict_ordered_items(d, *, keyfunc=None):
    """Provide persistently ordered dictionary items."""
    if dict_is_ordered(d):
        return d.items()
    assert type(d) is dict, type(d)
    if keyfunc is None:
        keyfunc = natural_keyfunc
    def item_keyfunc(item):
        key, value = item
        return keyfunc(key)
    return sorted(d.items(), key=item_keyfunc)

