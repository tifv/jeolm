"""
Tweaking of the PyYAML.

This module provides dump() and load() functions, corresponding to
original yaml.dump() and yaml.load().

Features:
    collections.OrderedDict is serialized as !!omap
    pathlib.PurePosixPath is serialized as !path

Additionally, dump() enables unicode serializing by default.

"""

from collections import OrderedDict

from pathlib import PurePosixPath

import yaml as the_yaml
from yaml.nodes import SequenceNode, MappingNode

from yaml import load as original_load, dump as original_dump

class JeolmLoader(the_yaml.loader.SafeLoader):
    def construct_yaml_omap(self, node):
        omap = OrderedDict()
        yield omap
        if not isinstance(node, SequenceNode):
            raise the_yaml.constructor.ConstructorError(
                "while constructing an ordered map", node.start_mark,
                "expected a sequence, but found %s" % node.id,
                node.start_mark )
        for subnode in node.value:
            if not isinstance(subnode, MappingNode):
                raise the_yaml.constructor.ConstructorError(
                    "while constructing an ordered map", node.start_mark,
                    "expected a mapping of length 1, but found %s"
                        % subnode.id,
                    subnode.start_mark )
            if len(subnode.value) != 1:
                raise the_yaml.constructor.ConstructorError(
                    "while constructing an ordered map", node.start_mark,
                    "expected a single mapping item, but found %d items"
                        % len(subnode.value),
                    subnode.start_mark )
            key_node, value_node = subnode.value[0]
            key = self.construct_object(key_node)
            value = self.construct_object(value_node)
            omap[key] = value
        if len(omap) < len(node.value):
            raise the_yaml.constructor.ConstructorError(
                "while constructing an ordered map", node.start_mark,
                "found duplicate keys", node.start_mark )

    def construct_path(self, node):
        return PurePosixPath(self.construct_scalar(node))

JeolmLoader.add_constructor(
        'tag:yaml.org,2002:omap',
        JeolmLoader.construct_yaml_omap)

JeolmLoader.add_constructor(
        '!path',
        JeolmLoader.construct_path)

class JeolmDumper(the_yaml.dumper.SafeDumper):
    def represent_OrderedDict(self, data):
        value = [{key : value} for key, value in data.items()]
        return self.represent_sequence('tag:yaml.org,2002:omap', value)

    def represent_PurePosixPath(self, data):
        return self.represent_scalar('!path', str(data))

    def ignore_aliases(self, data):
        return True

JeolmDumper.add_representer(OrderedDict,
        JeolmDumper.represent_OrderedDict)

JeolmDumper.add_representer(PurePosixPath,
        JeolmDumper.represent_PurePosixPath)

def load(stream, Loader=JeolmLoader):
    return original_load(stream, Loader=Loader)

def dump(data, Dumper=JeolmDumper, allow_unicode=True, **kwargs):
    return original_dump(data,
        Dumper=Dumper, allow_unicode=allow_unicode,
        **kwargs )

