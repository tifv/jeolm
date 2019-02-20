"""
Tweaking of the PyYAML.

This module provides dump() and load() functions, corresponding to
original yaml.dump() and yaml.load().

Features:
    collections.OrderedDict is serialized as !!omap
    jeolm.records.RecordPath is serialized as !path

Additionally, dump() enables unicode serializing by default.

"""

from collections import OrderedDict
import re

import yaml
from yaml.nodes import SequenceNode, MappingNode

from jeolm.records import RecordPath
from jeolm.date import Date

import logging
logger = logging.getLogger(__name__)


class JeolmLoader(yaml.loader.SafeLoader):

    def construct_yaml_omap(self, node):
        omap = OrderedDict()
        yield omap
        if not isinstance(node, SequenceNode):
            raise yaml.constructor.ConstructorError(
                "while constructing an ordered map", node.start_mark,
                "expected a sequence, but found %s" % node.id,
                node.start_mark )
        for subnode in node.value:
            if not isinstance(subnode, MappingNode):
                raise yaml.constructor.ConstructorError(
                    "while constructing an ordered map", node.start_mark,
                    "expected a mapping of length 1, but found %s"
                        % subnode.id,
                    subnode.start_mark )
            if len(subnode.value) != 1:
                raise yaml.constructor.ConstructorError(
                    "while constructing an ordered map", node.start_mark,
                    "expected a single mapping item, but found %d items"
                        % len(subnode.value),
                    subnode.start_mark )
            key_node, value_node = subnode.value[0]
            key = self.construct_object(key_node)
            value = self.construct_object(value_node)
            omap[key] = value
        if len(omap) < len(node.value):
            raise yaml.constructor.ConstructorError(
                "while constructing an ordered map", node.start_mark,
                "found duplicate keys", node.start_mark )

    def construct_path(self, node):
        return RecordPath(self.construct_scalar(node))

    def construct_date(self, node):
        return Date.from_string(self.construct_scalar(node))

JeolmLoader.add_constructor(
    'tag:yaml.org,2002:omap',
    JeolmLoader.construct_yaml_omap )

JeolmLoader.add_constructor(
    '!path',
    JeolmLoader.construct_path )

JeolmLoader.add_constructor(
    '!date',
    JeolmLoader.construct_date )

JeolmLoader.add_implicit_resolver(
    '!date',
    re.compile(r'^(?:[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ \-]p[0-9]+)$'),
    list('0123456789') )

class JeolmDumper(yaml.dumper.SafeDumper):
    def represent_OrderedDict(self, data):
        value = [{key : value} for key, value in data.items()]
        return self.represent_sequence('tag:yaml.org,2002:omap', value)

    def represent_RecordPath(self, data):
        return self.represent_scalar('!path', str(data))

    def represent_Date(self, data):
        return self.represent_scalar('!date', str(data))

    def ignore_aliases(self, data):
        return True

JeolmDumper.add_representer( OrderedDict,
        JeolmDumper.represent_OrderedDict )

JeolmDumper.add_representer( RecordPath,
        JeolmDumper.represent_RecordPath )

JeolmDumper.add_representer( Date,
        JeolmDumper.represent_Date )

def load(stream, Loader=JeolmLoader):
    return yaml.load(stream, Loader=Loader)

def dump(data, Dumper=JeolmDumper, allow_unicode=True, **kwargs):
    return yaml.dump(data,
        Dumper=Dumper, allow_unicode=allow_unicode,
        **kwargs )

