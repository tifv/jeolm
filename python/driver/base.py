import re
from functools import wraps
from contextlib import contextmanager
from string import Template
import abc

from ..target import Target, TargetError
from ..records import RecordsManager, RecordPath, RecordError

import logging
logger = logging.getLogger(__name__)

class DriverError(Exception):
    pass

class Substitutioner(type):
    """
    Metaclass for a driver.

    For any '*_template' attribute create 'substitute_*' attribute, like
    cls.substitute_* = Template(cls.*_template).substitute
    """
    def __new__(metacls, name, bases, namespace, **kwargs):
        substitute_items = list()
        for key, value in namespace.items():
            if key.endswith('_template'):
                substitute_key = 'substitute_' + key[:-len('_template')]
                substitute_items.append(
                    (substitute_key, Template(value).substitute) )
        namespace.update(substitute_items)
        return super().__new__(metacls, name, bases, namespace, **kwargs)

class Decorationer(type):
    """
    Metaclass for a driver.

    For any object in namespace with 'is_inclass_decorator' attribute set
    to True, hide this object in a '_inclass_decorators' dictionary in
    namespace. If a subclass is also driven by this metaclass, than reveal
    these objects for the definition of subclass.

    An @inclass_decorator decorator is introduced into the class namespace
    for convenience (and removed upon class definition).
    """

    @classmethod
    def __prepare__(metacls, name, bases, **kwargs):
        namespace = super().__prepare__(name, bases, **kwargs)
        for base in bases:
            base_inclass_objects = getattr(base, '_inclass_decorators', None)
            if not base_inclass_objects:
                continue
            for key, value in base_inclass_objects.items():
                if not getattr(value, 'is_inclass_decorator', False):
                    raise RuntimeError
                if key in namespace:
                    # ignore this version of decorator, since it is coming
                    # from the 'later' base.
                    continue
                namespace[key] = value
        namespace['inclass_decorator'] = metacls.mark_inclass_decorator
        return namespace

    @staticmethod
    def mark_inclass_decorator(decorator):
        """Decorator."""
        decorator.is_inclass_decorator = True
        return decorator

    def __new__(metacls, name, bases, namespace, **kwargs):
        if '_inclass_decorators' in namespace:
            raise RuntimeError
        inclass_objects = namespace.__class__()
        for key, value in namespace.items():
            if not getattr(value, 'is_inclass_decorator', False):
                continue
            inclass_objects[key] = value
        for key in inclass_objects:
            del namespace[key]
        del namespace['inclass_decorator']
        namespace['_inclass_decorators'] = inclass_objects
        return super().__new__(metacls, name, bases, namespace, **kwargs)

class DriverMetaclass(Substitutioner, Decorationer, abc.ABCMeta):
    pass

class BaseDriver(RecordsManager, metaclass=DriverMetaclass):

    driver_errors = frozenset((DriverError, TargetError, RecordError))

    def __init__(self):
        super().__init__()
        self.clear_cache()

    def clear_cache(self):
        super().clear_cache()
        self.outrecords_cache = dict()
        self.figrecords_cache = dict()
        self.delegators_cache = dict()
        self.metapath_list_cache = None

    ##########
    # Advanced error reporting

    @classmethod
    @contextmanager
    def fold_driver_errors(cls):
        try:
            yield
        except tuple(cls.driver_errors) as error:
            driver_messages = []
            while isinstance(error, tuple(cls.driver_errors)):
                message, = error.args
                driver_messages.append(str(message))
                error = error.__cause__
            raise DriverError(
                'Driver error stack:\n' +
                '\n'.join(driver_messages)
            ) from error

    @inclass_decorator
    def folding_driver_errors(method):
        """In-class decorator."""
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            with self.fold_driver_errors():
                return method(self, *args, **kwargs)
        return wrapper

    @classmethod
    @contextmanager
    def process_target_aspect(cls, target, aspect):
        try:
            yield
        except tuple(cls.driver_errors) as error:
            raise DriverError(
                "Error encountered while processing "
                "{target:target} {aspect}"
                .format(target=target, aspect=aspect)
            ) from error

    @classmethod
    @contextmanager
    def process_target_key(cls, target, key):
        if key is None: # no-op
            yield
            return
        with cls.process_target_aspect(target, aspect='key {}'.format(key)):
            yield

    @inclass_decorator
    def processing_target_aspect(*, aspect, wrap_generator=False):
        """Decorator factory."""
        def decorator(method):
            if not wrap_generator:
                @wraps(method)
                def wrapper(self, target, *args, **kwargs):
                    with self.process_target_aspect(target, aspect=aspect):
                        return method(self, target, *args, **kwargs)
            else:
                @wraps(method)
                def wrapper(self, target, *args, **kwargs):
                    with self.process_target_aspect(target, aspect=aspect):
                        yield from method(self, target, *args, **kwargs)
            return wrapper
        return decorator

    ##########
    # Interface methods and attributes

    @folding_driver_errors
    def produce_outrecord(self, target):
        """
        Return outrecord.

        Each outrecord must contain the following fields:
        'outname'
            string equal to the corresponding outname
        'sources'
            {alias_name : inpath for each inpath}
            where alias_name is a filename with '.tex' extension,
            and inpath also has '.tex' extension.
        'fignames'
            an iterable of strings; all of them must be contained
            in figrecords.keys()
        'document'
            LaTeX document as a string
        """
        try:
            return self.outrecords_cache[target]
        except KeyError:
            pass
        outrecord = self.outrecords_cache[target] = \
            self.generate_outrecord(target)
        return outrecord

    @folding_driver_errors
    def produce_figrecord(self, figpath):
        """
        Return figrecord.

        Each figrecord must contain the following fields:
        'figname'
            string equal to the corresponding figname
        'source'
            inpath with '.asy' or '.eps' extension
        'type'
            string, either 'asy' or 'eps'

        In case of Asymptote file ('asy' type), figrecord must also
        contain:
        'used'
            {used_name : inpath for each used inpath}
            where used_name is a filename with '.asy' extension,
            and inpath has '.asy' extension
        """
        try:
            return self.figrecords_cache[figpath]
        except KeyError:
            pass
        figrecord = self.figrecords_cache[figpath] = \
            self.generate_figrecord(figpath)
        return figrecord

    def list_inpaths(self, *targets, inpath_type='tex'):
        for target in targets:
            outrecord = self.produce_outrecord(target)
            if inpath_type == 'tex':
                for inpath in outrecord['inpaths'].values():
                    if inpath.suffix == '.tex':
                        yield inpath
            elif inpath_type == 'asy':
                for figpath in outrecord['figpaths'].values():
                    figrecord = self.produce_figrecord(figpath)
                    if figrecord['type'] == 'asy':
                        yield figrecord['source']

    class NoDelegators(Exception):
        pass

    @folding_driver_errors
    def list_delegators(self, *targets, recursively=True):
        if len(targets) != 1 and not recursively:
            raise RuntimeError
        for target in targets:
            try:
                delegators = self.delegators_cache[target, recursively]
            except KeyError:
                if recursively:
                    delegators = list(self.trace_delegators(target))
                else:
                    try:
                        delegators = list(self.generate_delegators(target))
                    except self.NoDelegators:
                        delegators = None
                self.delegators_cache[target, recursively] = delegators
            if delegators is None:
                assert not recursively, target
                raise self.NoDelegators
            else:
                yield from delegators

    def list_metapaths(self):
        if self.metapath_list_cache is not None:
            return iter(self.metapath_list_cache)
        else:
            metapath_list = self.metapath_list_cache = \
                list(self.generate_metapaths())
            return iter(metapath_list)


    ##########
    # High-level functions
    # (not dealing with metarecords and LaTeX strings directly)

    @abc.abstractmethod
    def generate_outrecord(self, target):
        raise NotImplementedError

    @abc.abstractmethod
    def generate_figrecord(self, target):
        raise NotImplementedError

    @abc.abstractmethod
    def trace_delegators(self, target, *, seen_targets):
        raise NotImplementedError

    ##########
    # Record-level functions

    @abc.abstractmethod
    def generate_delegators(self, target, metarecord):
        raise NotImplementedError

    ##########
    # Record extension

    def derive_attributes(self, parent_record, child_record, name):
        parent_path = parent_record.get('$path')
        if parent_path is None:
            path = RecordPath()
        else:
            path = parent_path/name
        child_record['$path'] = path
        child_record.setdefault('$targetable',
            parent_record.get('$targetable', True) )
        super().derive_attributes(parent_record, child_record, name)

    def _get_child(self, record, name, *, original, **kwargs):
        child_record = super()._get_child(
            record, name, original=original, **kwargs )
        if original:
            return child_record
        if '$import' in child_record:
            for name in child_record.pop('$import'):
                child_record.update(self.load_library(name))
        if '$include' in child_record:
            path = child_record['$path']
            for name in child_record.pop('$include'):
                included = self.getitem(path/name, original=True)
                child_record.update(included)
        return child_record

    @classmethod
    def load_library(cls, library_name):
        raise DriverError("Unknown library '{}'".format(library_name))

    flagged_pattern = re.compile(
        r'^(?P<key>[^\[\]]+)'
        r'(?:\['
            r'(?P<flags>.+)'
        r'\])?$' )

    @classmethod
    def select_flagged_item(cls, mapping, stemkey, flags):
        assert isinstance(stemkey, str), type(stemkey)
        assert stemkey.startswith('$'), stemkey

        flagset_mapping = dict()
        for key, value in mapping.items():
            flagged_match = cls.flagged_pattern.match(key)
            if flagged_match is None:
                continue
            if flagged_match.group('key') != stemkey:
                continue
            flagset_s = flagged_match.group('flags')
            if flagset_s is None:
                flagset = frozenset()
            else:
                flagset = frozenset(flagset_s.split(','))
            if flagset in flagset_mapping:
                raise DriverError("Clashing keys '{}' and '{}'"
                    .format(key, flagset_mapping[flagset][0]) )
            flagset_mapping[flagset] = (key, value)
        return flags.select_matching_value( flagset_mapping,
            default=(None, None) )

    @inclass_decorator
    def fetching_metarecord(method):
        """Decorator."""
        @wraps(method)
        def wrapper(self, target, metarecord=None, **kwargs):
            assert target is not None
            if metarecord is None:
                metarecord = self.getitem(target.path)
            return method(self, target, metarecord=metarecord, **kwargs)
        return wrapper

    @inclass_decorator
    def checking_target_recursion(method):
        """Decorator."""
        @wraps(method)
        def wrapper(self, target, *args, seen_targets=frozenset(), **kwargs):
            if target in seen_targets:
                raise DriverError(
                    "Cycle detected from {:target}".format(target) )
            seen_targets |= {target}
            return method(self, target, *args,
                seen_targets=seen_targets, **kwargs )
        return wrapper

    def generate_metapaths(self, path=None):
        """Yield metapaths."""
        if path is None:
            path = RecordPath()
            root = True
        else:
            root = False
        record = self.getitem(path)
        if not record.get('$targetable', True):
            return
        if not root:
            yield path
        for key in record:
            if key.startswith('$'):
                continue
            yield from self.generate_metapaths(path=path/key)

