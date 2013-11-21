import re
from collections import OrderedDict

from pathlib import PurePosixPath as PurePath

from . import yaml

def pure_join(*paths):
    """
    Join PurePaths, resolving '..' parts.

    Resolve any appearence of 'whatever/..' to ''.
    The resulting path must not contain '..' parts.
    The leading '/', if any, will be stripped from the result.
    """
    path = PurePath(*paths)
    parts = path.parts
    if path.is_absolute():
        parts = parts[1:]
    path = PurePath()
    for part in parts:
        if part != '..':
            path /= part
        else:
            path = path.parent
    return path

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


#class NaturallyOrderedDict(dict):
#    """
#    Yields its keys in natural order.
#    """
#    def __iter__(self):
#        return iter(sorted(super().__iter__(), key=natural_key))
#
#    def keys(self):
#        return sorted(super().keys(), key=natural_key)
#
#    def items(self):
#        return sorted(super().items(), key=lambda kv: natural_key(kv[0]))
#
#    def values(self):
#        return [value for key, value in self.items()]
#
#    def copy(self):
#        return type(self)(self)
#
#yaml.JeolmDumper.add_representer(NaturallyOrderedDict,
#    yaml.JeolmDumper.represent_dict )



