import re
import datetime
from functools import wraps, partial
from collections import OrderedDict
from contextlib import contextmanager
import abc
from string import Template

from pathlib import PurePosixPath

from .. import records
from ..records import RecordPath, RecordError, RecordNotFoundError
from . import target
from .target import TargetError, FlagError

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
        return namespace

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
        namespace['_inclass_decorators'] = inclass_objects
        return super().__new__(metacls, name, bases, namespace, **kwargs)

class DriverMetaclass(Substitutioner, Decorationer):
    pass

class Driver(metaclass=DriverMetaclass):
    """
    Driver for course-like projects.
    """

    driver_errors = (DriverError, TargetError, RecordError, FlagError)

    ##########
    # Interface functions

    def __init__(self, metarecords):
        self.metarecords = metarecords
        assert isinstance(metarecords, self.Metarecords)

        self.outrecords = OrderedDict()
        self.figrecords = OrderedDict()
        self.outnames_by_target = dict()

    def produce_outrecords(self, targets_s):
        """
        Target flags (some of):
            'no-delegate'
                ignore delegation mechanics
            'multidate'
                place date after each file instead of in header
        """
        try:
            undelegated_targets = [
                self.parse_target_string(target_s, origin='undelegated target')
                for target_s in targets_s ]
            targets = [ target
                for undelegated_target in undelegated_targets
                for target in self.trace_delegators(undelegated_target) ]

            # Generate outrecords and store them in self.outrecords
            outnames = [
                self.form_outrecord(target)
                for target in targets ]

            # Extract requested outrecords
            outrecords = OrderedDict(
                (outname, self.outrecords[outname])
                for outname in outnames )

            # Extract requested figrecords
            figrecords = OrderedDict(
                (figname, self.figrecords[figname])
                for outrecord in outrecords.values()
                for figname in outrecord['fignames'] )

            return outrecords, figrecords
        except self.driver_errors as error:
            driver_messages = []
            while isinstance(error, self.driver_errors):
                message, = error.args
                driver_messages.append(str(message))
                error = error.__cause__
            raise DriverError(
                'Driver error stack:\n' +
                '\n'.join(driver_messages)
            ) from error

    def list_targets(self):
        """
        List some (usually most of) metapaths sufficient as targets.
        """
        yield from self.metarecords.list_targets()

    def list_inpaths(self, targets_s, *, source_type='tex'):
        outrecords, figrecords = self.produce_outrecords(targets_s)
        if 'tex' == source_type:
            for outrecord in outrecords.values():
                for inpath in outrecord['inpaths']:
                    if inpath.suffix == '.tex':
                        yield inpath
        elif 'asy' == source_type:
            for figrecord in figrecords.values():
                yield figrecord['source']


    ##########
    # Target

    class Target(target.Target):
        @contextmanager
        def processing(self, aspect):
            try:
                yield
            except (RecordError, TargetError, DriverError) as error:
                raise DriverError(
                    "Error encountered while processing "
                    "{target:target} {aspect}"
                    .format(target=self, aspect=aspect)
                ) from error

        @contextmanager
        def processing_key(self, key):
            if key is None: # no-op
                yield; return
            with self.processing(aspect='key {}'.format(key)):
                yield

    def processing_target(*, aspect, wrap_generator=False):
        """Decorator factory."""
        def decorator(method):
            if not wrap_generator:
                @wraps(method)
                def wrapper(self, target, *args, **kwargs):
                    with target.processing(aspect=aspect):
                        return method(self, target, *args, **kwargs)
            else:
                @wraps(method)
                def wrapper(self, target, *args, **kwargs):
                    with target.processing(aspect=aspect):
                        yield from method(self, target, *args, **kwargs)
            return wrapper
        return decorator
    processing_target.is_inclass_decorator = True


    ##########
    # High-level functions
    # (not dealing with metarecords and LaTeX strings directly)

    @processing_target(aspect='outrecord')
    def form_outrecord(self, target):
        """
        Return outname; outrecord is self.outrecords[outname].

        Update self.outrecords and self.figrecords.
        """
        try:
            return self.outnames_by_target[target.key]
        except KeyError:
            pass

        outrecord = self.produce_protorecord(target)
        target.check_unutilized_flags()
        assert outrecord.keys() >= {
            'date', 'inpaths', 'fignames', 'metapreamble', 'metabody'
        }, outrecord.keys()

        outname = self.select_outname(target, date=outrecord['date'])
        outrecord['outname'] = outname
        if outname in self.outrecords:
            raise DriverError("Outname '{}' duplicated.".format(outname))
        self.outrecords[outname] = outrecord

        self.revert_aliases(outrecord)

        with target.processing('document'):
            outrecord['document'] = self.constitute_document(
                outrecord,
                metapreamble=outrecord.pop('metapreamble'),
                metabody=outrecord.pop('metabody'), )
        self.outnames_by_target[target.key] = outname
        return outname

    def revert_aliases(self, outrecord):
        """
        Based on outrecord['aliases'], define outrecord['sources'].

        Check for alias clash.
        """
        outrecord['sources'] = {
            alias : inpath
            for inpath, alias in outrecord['aliases'].items() }
        if len(outrecord['sources']) < len(outrecord['aliases']):
            screened_inpaths = frozenset(outrecord['inpaths']).difference(
                outrecord['sources'].values() )
            clashed_aliases = {
                outrecord['aliases'][inpath]
                for inpath in screened_inpaths }
            clashed_inpaths = {
                inpath
                for inpath, alias in outrecord['aliases'].items()
                if alias in clashed_aliases }
            raise DriverError(
                "Clashed inpaths: {}"
                .format(', '.join(
                    "'{}'".format(inpath)
                    for inpath in sorted(clashed_inpaths)
                )) )

    def produce_figname_map(self, figures):
        """
        Return { figalias : figname
            for figalias, figpath in figures.items() }

        Update self.figrecords.
        """
        if not figures:
            return {}
        assert isinstance(figures, OrderedDict), type(figures)
        return OrderedDict(
            (figalias, self.form_figrecord(figpath))
            for figalias, figpath in figures.items() )

    def form_figrecord(self, figpath):
        """
        Return figname.

        Update self.figrecords.
        """
        assert isinstance(figpath, RecordPath), type(figpath)
        figtype, inpath = self.find_figure_type(figpath)
        assert isinstance(inpath, PurePosixPath), type(inpath)
        assert not inpath.is_absolute(), inpath

        figname = '-'.join(figpath.parts[1:])
        if figname in self.figrecords:
            alt_inpath = self.figrecords[figname]['source']
            if alt_inpath != inpath:
                raise DriverError(figname, inpath, alt_inpath)
            return figname

        figrecord = self.figrecords[figname] = dict()
        figrecord['figname'] = figname
        assert '/' not in figname, figname
        figrecord['source'] = inpath
        figrecord['type'] = figtype

        if figtype == 'asy':
            used_items = list(self.trace_asy_used(figpath))
            used = figrecord['used'] = dict(used_items)
            if len(used) != len(used_items):
                raise DriverError(inpath, used_items)

        return figname


    ##########
    # Metabody and metastyle items

    class MetabodyItem(metaclass=abc.ABCMeta):
        __slots__ = []

        @abc.abstractmethod
        def __init__(self):
            super().__init__()

    class VerbatimBodyItem(MetabodyItem):
        __slots__ = ['verbatim']

        def __init__(self, verbatim):
            self.verbatim = str(verbatim)
            super().__init__()

    class InpathBodyItem(MetabodyItem):
        __slots__ = ['inpath', 'alias', 'figname_map']

        def __init__(self, inpath):
            self.inpath = PurePosixPath(inpath)
            if self.inpath.is_absolute():
                raise RuntimeError(inpath)
            super().__init__()

    class MetapreambleItem(metaclass=abc.ABCMeta):
        __slots__ = []

        @abc.abstractmethod
        def __init__(self):
            super().__init__()

    class VerbatimPreambleItem(MetapreambleItem):
        __slots__ = ['verbatim']

        def __init__(self, verbatim):
            self.verbatim = str(verbatim)
            super().__init__()

    class PackagePreambleItem(MetapreambleItem):
        __slots__ = ['package', 'options']

        def __init__(self, package, options=()):
            self.package = str(package)
            if not isinstance(options, (list, tuple)):
                raise DriverError(
                    "Options must be a list, found {.__class__.__name__}"
                    .format(options) )
            self.options = list(options)
            super().__init__()

    class InpathPreambleItem(MetapreambleItem):
        __slots__ = ['inpath', 'alias']

        def __init__(self, inpath):
            self.inpath = PurePosixPath(inpath)
            if self.inpath.is_absolute():
                raise RuntimeError(inpath)
            super().__init__()

    @classmethod
    def classify_metabody_item(cls, item, *, default):
        assert default in {None, 'verbatim'}, default
        if isinstance(item, cls.MetabodyItem):
            return item
        if isinstance(item, str):
            if default == 'verbatim':
                return cls.VerbatimBodyItem(item)
            else:
                raise RuntimeError(item)
        if not isinstance(item, dict):
            raise RuntimeError(item)
        if 'verbatim' in item:
            if not item.keys() == {'verbatim'}:
                raise DriverError(item)
            return cls.VerbatimBodyItem(**item)
        elif 'inpath' in item:
            if not item.keys() == {'inpath'}:
                raise DriverError(item)
            return cls.InpathBodyItem(**item)
        else:
            raise DriverError(item)

    @classmethod
    def classify_matter_item(cls, item, *, default):
        if isinstance(item, cls.Target):
            return item
        return cls.classify_metabody_item(item, default=default)

    @classmethod
    def classify_metapreamble_item(cls, item, *, default):
        assert default in {None, 'verbatim'}, default
        if isinstance(item, cls.MetapreambleItem):
            return item
        if isinstance(item, str):
            if default == 'verbatim':
                return cls.VerbatimPreambleItem(item)
            else:
                raise RuntimeError(item)
        if not isinstance(item, dict):
            raise RuntimeError(item)
        if 'verbatim' in item:
            if not item.keys() == {'verbatim'}:
                raise DriverError(item)
            return cls.VerbatimPreambleItem(**item)
        elif 'package' in item:
            if not {'package'} <= item.keys() <= {'package', 'options'}:
                raise DriverError(item)
            return cls.PackagePreambleItem(**item)
        elif 'inpath' in item:
            if not item.keys() == {'inpath'}:
                raise DriverError(item)
            return cls.InpathPreambleItem(**item)
        else:
            raise DriverError(item)

    @classmethod
    def classify_style_item(cls, item, *, default):
        if isinstance(item, cls.Target):
            return item
        return cls.classify_metapreamble_item(item, default=default)

    def classify_items(*, aspect, default):
        """Decorator factory."""
        classify_name = 'classify_{}_item'.format(aspect)
        def decorator(method):
            @wraps(method)
            def wrapper(self, *args, **kwargs):
                classify_item = getattr(self, classify_name)
                for item in method(self, *args, **kwargs):
                    yield classify_item(item, default=default)
            return wrapper
        return decorator
    classify_items.is_inclass_decorator = True

    ##########
    # Advanced target manipulation

    flagged_pattern = re.compile(
        r'^(?P<key>[^\[\]]+)'
        r'(?:\['
            r'(?P<flags>.+)'
        r'\])?$' )

    @classmethod
    def parse_target_string(cls, string, *, origin):
        """Return target."""
        flagged_match = cls.flagged_pattern.match(string)
        if flagged_match is None:
            raise DriverError(
                "Failed to parse target '{}'.".format(string) )
        path = RecordPath(flagged_match.group('key'))
        flags_s = flagged_match.group('flags')
        if flags_s is not None:
            flags = frozenset(flags_s.split(','))
        else:
            flags = frozenset()
        if any(flag.startswith('-') for flag in flags):
            raise DriverError(
                "Target '{}' contains negative flags.".format(string) )
        return cls.Target(path, flags, origin=origin)

    @classmethod
    def derive_target(cls, target, delegator, *, origin):
        """Return target."""
        if not isinstance(delegator, str):
            raise DriverError(type(delegator))
        flagged_match = cls.flagged_pattern.match(delegator)
        subpath = target.path / flagged_match.group('key')
        flags_s = flagged_match.group('flags')
        if flags_s is not None:
            flags = frozenset(flags_s.split(','))
        else:
            flags = frozenset()
        positive = {flag for flag in flags if not flag.startswith('-')}
        negative = {flag[1:] for flag in flags if flag.startswith('-')}
        if any(flag.startswith('-') for flag in negative):
            raise DriverError("Double-negative flag in delegator '{}'"
                .format(delegator) )
        subflags = target.flags.delta(
            union=positive, difference=negative, origin=origin )
        return cls.Target(subpath, subflags)

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


    ##########
    # Record-level functions

    def fetch_metarecord(method):
        """Decorator."""
        @wraps(method)
        def wrapper(self, target, metarecord=None, **kwargs):
            assert target is not None
            if metarecord is None:
                assert '..' not in target.path.parts, repr(target.path)
                metarecord = self.metarecords[target.path]
            return method(self, target, metarecord=metarecord, **kwargs)
        return wrapper
    fetch_metarecord.is_inclass_decorator = True

    def check_target_recursion(method):
        """Decorator."""
        @wraps(method)
        def wrapper(self, target, *args,
            seen_targets=frozenset(), **kwargs
        ):
            if target.key in seen_targets:
                raise DriverError(
                    "Cycle detected from {target:target}"
                    .format(target=target) )
            seen_targets |= {target.key}
            return method(self, target, *args,
                seen_targets=seen_targets, **kwargs )
        return wrapper
    check_target_recursion.is_inclass_decorator = True

    class NoDelegators(Exception):
        pass

    @fetch_metarecord
    @check_target_recursion
    @processing_target(aspect='delegation', wrap_generator=True)
    def trace_delegators(self, target, metarecord,
        *, seen_targets
    ):
        """Yield targets."""
        if 'no-delegate' in target.flags:
            yield ( target
                .flags_difference({'no-delegate'})
                .flags_clean_copy(origin='target') )
            return

        try:
            for item in self.generate_delegators(target, metarecord):
                if isinstance(item, self.Target):
                    yield from self.trace_delegators(item,
                        seen_targets=seen_targets )
                else:
                    raise RuntimeError(item)
        except self.NoDelegators:
            yield target.flags_clean_copy(origin='target')

    def generate_delegators(self, target, metarecord):
        """Yield targets."""
        delegate_key, pre_delegators = self.select_flagged_item(
            metarecord, '$delegate', target.flags )
        if delegate_key is None:
            raise self.NoDelegators
        with target.processing_key(delegate_key):
            if not isinstance(pre_delegators, list):
                raise DriverError(type(delegators))
            derive_target = partial( self.derive_target,
                origin='delegate {target:target}, key {key}'
                .format(target=target, key=delegate_key) )
            for item in pre_delegators:
                if isinstance(item, str):
                    yield derive_target(target, item)
                    continue
                if not isinstance(item, dict):
                    raise DriverError(type(item))
                item = item.copy()
                condition = item.pop('condition', [])
                if not target.flags.check_condition(condition):
                    continue
                if item.keys() == {'delegate'}:
                    yield derive_target(target, item['delegate'])
                else:
                    raise DriverError(item)

    @fetch_metarecord
    @processing_target(aspect='protorecord')
    def produce_protorecord(self, target, metarecord):
        """
        Return protorecord.
        """
        date_set = set()

        protorecord = {}
        options_key, options = self.select_flagged_item(
            metarecord, '$manner$options', target.flags )
        if options is not None:
            with target.processing_key(options_key):
                if not isinstance(options, dict):
                    raise DriverError(type(options))
                protorecord.update(options)
        # We must exhaust generate_metabody() to fill date_set
        metabody = list(self.generate_metabody(
            target, metarecord, date_set=date_set ))
        metapreamble = list(self.generate_metapreamble(
            target, metarecord ))

        inpaths = protorecord['inpaths'] = list()
        aliases = protorecord['aliases'] = dict()
        fignames = protorecord['fignames'] = list()
        tex_packages = protorecord['tex packages'] = list()
        protorecord.setdefault('date', self.min_date(date_set))

        protorecord['metabody'] = list(self.digest_metabody(
            metabody, inpaths=inpaths, aliases=aliases,
            fignames=fignames, tex_packages=tex_packages ))

        protorecord['metapreamble'] = list(self.digest_metapreamble(
            metapreamble, inpaths=inpaths, aliases=aliases ))

        # dropped keys
        assert 'preamble' not in protorecord, '$manner$style'
        assert 'style' not in protorecord, '$manner$style'
        assert '$out$options' not in metarecord, '$manner$options'
        assert '$rigid' not in metarecord, '$manner'
        assert '$rigid$opt' not in metarecord, '$manner$options'
        assert '$fluid' not in metarecord, '$matter'
        assert '$fluid$opt' not in metarecord
        assert '$manner$opt' not in metarecord, '$manner$options'
        assert 'classoptions' not in protorecord, 'class options'
        assert 'selectsize' not in protorecord, 'scale font'
        assert 'selectfont' not in protorecord, 'scale font'

        return protorecord

    @fetch_metarecord
    @processing_target(aspect='metabody', wrap_generator=True)
    @classify_items(aspect='metabody', default=None)
    def generate_metabody(self, target, metarecord,
        *, date_set
    ):
        """
        Yield metabody items. Update date_set.
        """
        manner_key, manner = self.select_flagged_item(
            metarecord, '$manner', target.flags )
        with target.processing_key(manner_key):
            yield from self.generate_matter_metabody(target, metarecord,
                date_set=date_set, pre_matter=manner )

    @fetch_metarecord
    @check_target_recursion
    @processing_target(aspect='matter metabody', wrap_generator=True)
    @classify_items(aspect='metabody', default=None)
    def generate_matter_metabody(self, target, metarecord,
        *, date_set, seen_targets, pre_matter=None
    ):
        """
        Yield metabody items.

        Update date_set.
        """
        if pre_matter is not None:
            seen_targets -= {target.key}
        if '$date' in metarecord:
            date_set.add(metarecord['$date']); date_set = set()

        if 'header' in target.flags:
            date_subset = set()
            # exhaust iterator to find date_subset
            metabody = list(self.generate_matter_metabody(
                target
                    .flags_difference({'header'})
                    .flags_union({'no-header'}),
                metarecord,
                date_set=date_subset, pre_matter=pre_matter,
                seen_targets=seen_targets ))
            yield from self.generate_header_metabody(
                target, metarecord,
                date=self.min_date(date_subset) )
            yield from metabody
            date_set.update(date_subset)
            return # recurse

        matter_generator = self.generate_matter(
            target, metarecord, pre_matter=pre_matter )
        for item in matter_generator:
            if isinstance(item, self.MetabodyItem):
                yield item
            elif isinstance(item, self.Target):
                yield from self.generate_matter_metabody(
                    item, date_set=date_set, seen_targets=seen_targets )
            else:
                raise RuntimeError(type(item))

    @processing_target(aspect='header metabody', wrap_generator=True)
    @classify_items(aspect='metabody', default='verbatim')
    def generate_header_metabody(self, target, metarecord, *, date):
        if 'multidate' not in target.flags:
            yield self.constitute_datedef(date=date)
        else:
            yield self.constitute_datedef(date=None)
        yield self.substitute_jeolmheader()
        yield self.substitute_resetproblem()

    @processing_target(aspect='matter', wrap_generator=True)
    @classify_items(aspect='matter', default='verbatim')
    def generate_matter(self, target, metarecord,
        pre_matter=None, recursed=False
    ):
        """Yield matter items."""
        if pre_matter is None:
            matter_key, pre_matter = self.select_flagged_item(
                metarecord, '$matter', target.flags )
        else:
            matter_key = None
        if pre_matter is None:
            if not metarecord.get('$source', False):
                return
            if '$tex$source' in metarecord:
                yield from self.generate_tex_matter(
                    target, metarecord )
            for name in metarecord:
                if name.startswith('$'):
                    continue
                if metarecord[name].get('$source', False):
                    yield target.path_derive(name)
            return
        with target.processing_key(matter_key):
            if not isinstance(pre_matter, list):
                raise DriverError(type(pre_matter))
            derive_target = partial( self.derive_target,
                origin='matter {target:target}, key {key}'
                .format(target=target, key=matter_key) )
            for item in pre_matter:
                if isinstance(item, str):
                    yield derive_target(target, item)
                    continue
                if isinstance(item, list):
                    if recursed:
                        raise DriverError(
                            "Matter allows two folding levels at most" )
                    if not item:
                        yield self.substitute_emptypage()
                    else:
                        yield from self.generate_matter(
                            target, metarecord,
                            pre_matter=item, recursed=True )
                        yield self.substitute_clearpage()
                    continue
                if not isinstance(item, dict):
                    raise DriverError(type(item))
                item = item.copy()
                condition = item.pop('condition', [])
                if not target.flags.check_condition(condition):
                    continue
                if item.keys() == {'delegate'}:
                    yield derive_target(target, item['delegate'])
                else:
                    yield item

    @processing_target(aspect='tex matter', wrap_generator=True)
    @classify_items(aspect='matter', default='verbatim')
    def generate_tex_matter(self, target, metarecord):
        assert metarecord.get('$tex$source', False)
        if not target.flags.intersection(('header', 'no-header')):
            yield target.flags_union({'header'})
            return # recurse
        yield {'inpath' : target.path.as_inpath(suffix='.tex')}
        if '$date' in metarecord and 'multidate' in target.flags:
            date = metarecord['$date']
            yield self.constitute_datedef(date=date)
            yield self.substitute_datestamp()

    @fetch_metarecord
    @processing_target(aspect='metapreamble', wrap_generator=True)
    @classify_items(aspect='metapreamble', default=None)
    def generate_metapreamble(self, target, metarecord):
        manner_style_key, manner_style = self.select_flagged_item(
            metarecord, '$manner$style', target.flags )
        with target.processing_key(manner_style_key):
            yield from self.generate_style_metapreamble(
                target, metarecord, pre_style=manner_style )

    @fetch_metarecord
    @check_target_recursion
    @processing_target(aspect='style', wrap_generator=True)
    @classify_items(aspect='metapreamble', default=None)
    def generate_style_metapreamble(self, target, metarecord,
        *, seen_targets, pre_style=None
    ):
        if pre_style is not None:
            seen_targets -= {target.key}

        style_generator = self.generate_style(
            target, metarecord, pre_style=pre_style )
        for item in style_generator:
            if isinstance(item, self.MetapreambleItem):
                yield item
            elif isinstance(item, self.Target):
                yield from self.generate_style_metapreamble(
                    item, seen_targets=seen_targets )
            else:
                raise RuntimeError(type(item))

    @classify_items(aspect='style', default=None)
    def generate_style(self, target, metarecord, pre_style):
        if pre_style is None:
            style_key, pre_style = self.select_flagged_item(
                metarecord, '$style', target.flags )
        else:
            style_key = None
        if pre_style is None:
            if '$sty$source' in metarecord:
                yield {'inpath' : target.path.as_inpath(suffix='.sty')}
            else:
                yield target.path_derive('..')
            return
        with target.processing_key(style_key):
            if not isinstance(pre_style, list):
                raise DriverError(type(pre_style))
            derive_target = partial( self.derive_target,
                origin='style {target:target}, key {key}'
                .format(target=target, key=style_key) )
            for item in pre_style:
                if isinstance(item, str):
                    yield derive_target(target, item)
                    continue
                if not isinstance(item, dict):
                    raise DriverError(type(item))
                item = item.copy()
                condition = item.pop('condition', [])
                if not target.flags.check_condition(condition):
                    continue
                if item.keys() == {'delegate'}:
                    yield derive_target(target, item['delegate'])
                else:
                    yield item

    def digest_metabody(self, metabody, *,
        inpaths, aliases, fignames, tex_packages
    ):
        """
        Yield metabody items.

        Extend inpaths, aliases, fignames.
        """
        for item in metabody:
            assert isinstance(item, self.MetabodyItem), type(item)
            if isinstance(item, self.InpathBodyItem):
                inpath = item.inpath
                metarecord = self.metarecords[
                    RecordPath(inpath.with_suffix('')) ]
                if not metarecord.get('$tex$source', False):
                    raise RecordNotFoundError(inpath)
                inpaths.append(inpath)
                aliases[inpath] = item.alias = self.select_alias(
                    inpath, suffix='.in.tex' )
                figures = OrderedDict(
                    (figalias, RecordPath(figpath))
                    for figalias, figpath
                    in metarecord.get('$tex$figures', {}).items() )
                figname_map = item.figname_map = \
                    self.produce_figname_map(figures)
                for figname in figname_map.values():
                    if figname not in fignames:
                        fignames.append(figname)
                for tex_package in metarecord.get('$tex$packages', ()):
                    if tex_package not in tex_packages:
                        tex_packages.append(tex_package)
            yield item

    def digest_metapreamble(self, metapreamble, *,
        inpaths, aliases
    ):
        """
        Yield metapreamble items.

        Extend inpaths, aliases.
        """
        for item in metapreamble:
            assert isinstance(item, self.MetapreambleItem), type(item)
            if isinstance(item, self.InpathPreambleItem):
                inpath = item.inpath
                metarecord = self.metarecords[
                    RecordPath(inpath.with_suffix('')) ]
                if not metarecord.get('$sty$source', False):
                    raise RecordNotFoundError(inpath)
                inpaths.append(inpath)
                aliases[inpath] = item.alias = self.select_alias(
                    'local', inpath, suffix='.sty' )
            yield item

    # List of (figtype, figkey, figsuffix)
    figtypes = (
        ('asy', '$asy$source', '.asy'),
        ('eps', '$eps$source', '.eps'),
    )

    def find_figure_type(self, figpath):
        """
        Return (figtype, inpath).

        figtype is one of 'asy', 'eps'.
        """
        try:
            metarecord = self.metarecords[figpath]
        except RecordNotFoundError as error:
            raise DriverError('Figure not found') from error
        for figtype, figkey, figsuffix in self.figtypes:
            if not metarecord.get(figkey, False):
                continue
            return figtype, figpath.as_inpath(suffix=figsuffix)
        raise DriverError("Figure '{}' not found".format(figpath))

    def trace_asy_used(self, figpath, *, seen_paths=frozenset()):
        if figpath in seen_paths:
            raise DriverError(figpath)
        seen_paths |= {figpath}
        metarecord = self.metarecords[figpath]
        for used_name, used_path in metarecord.get('$asy$used', {}).items():
            inpath = PurePosixPath(used_path)
            yield used_name, inpath
            yield from self.trace_asy_used(
                RecordPath(inpath.with_suffix('')),
                seen_paths=seen_paths )


    ##########
    # Record accessor

    class Metarecords(records.Records):

        def list_targets(self, path=None):
            if path is None:
                path = RecordPath()
                root = True
            else:
                root = False
            record = self.getitem(path)
            if not record.get('$targetable', True):
                return
            if not root:
                yield str(path)
            for key in record:
                if key.startswith('$'):
                    continue
                yield from self.list_targets(path=path/key)

        def derive_attributes(self, parent_record, child_record, name):
            parent_path = parent_record.get('$path')
            if parent_path is None:
                path = RecordPath()
            else:
                path = parent_path/name
            child_record['$path'] = path
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
            if library_name == 'pgfpages':
                logger.debug('pgfpages metadata library loaded')
                return cls.pgfpages_library
            else:
                raise DriverError("Unknown library '{}'".format(library_name))

        pgfpages_library = OrderedDict([
            ('$targetable', False),
            ('$style', [
                {'package' : 'pgfpages'},
                {'delegate' : 'uselayout'},
            ]),
            ('uselayout', OrderedDict([
                ('$style', [{'verbatim' :
                    '\\pgfpagesuselayout{resize to}[a4paper]'
                }]),
                ('$style[2on1]', [{'verbatim' :
                    '\\pgfpagesuselayout{2 on 1}[a4paper,landscape]'
                }]),
                ('$style[2on1-portrait]', [{'verbatim' :
                    '\\pgfpagesuselayout{2 on 1}[a4paper]'
                }]),
                ('$style[4on1]', [{'verbatim' :
                    '\\pgfpagesuselayout{4 on 1}[a4paper,landscape]'
                }]),
            ]))
        ])


    ##########
    # LaTeX-level functions

    @classmethod
    def constitute_document(cls, outrecord, metapreamble, metabody):
        documentclass = cls.select_documentclass(outrecord)
        classoptions = cls.generate_classoptions(outrecord)

        return cls.substitute_document(
            documentclass=documentclass,
            classoptions=cls.constitute_options(classoptions),
            preamble=cls.constitute_preamble(outrecord, metapreamble),
            body=cls.constitute_body(outrecord, metabody)
        )

    document_template = (
        r'% Auto-generated by jeolm' '\n'
        r'\documentclass$classoptions{$documentclass}' '\n\n'
        r'$preamble' '\n\n'
        r'\begin{document}' '\n\n'
        r'$body' '\n\n'
        r'\end{document}' '\n'
    )

    @classmethod
    def select_documentclass(cls, outrecord):
        return outrecord.get('class', 'article')

    @classmethod
    def generate_classoptions(cls, outrecord):
        paper_option = outrecord.get('paper', 'a5paper')
        yield str(paper_option)
        font_option = outrecord.get('font', '10pt')
        yield str(font_option)
        class_options = outrecord.get('class options', ())
        if isinstance(class_options, str):
            raise DriverError( "'class options' must be a list, "
                "found {.__class__}".format(class_options) )
        for option in class_options:
            yield str(option)

        if paper_option not in {'a4paper', 'a5paper'}:
            logger.warning(
                "<BOLD><MAGENTA>{name}<NOCOLOUR> uses "
                "bad paper option '<YELLOW>{option}<NOCOLOUR>'<RESET>"
                .format(name=outrecord.outname, option=paper_option) )
        if font_option not in {'10pt', '11pt', '12pt'}:
            logger.warning(
                "<BOLD><MAGENTA>{name}<NOCOLOUR> uses "
                "bad font option '<YELLOW>{option}<NOCOLOUR>'<RESET>"
                .format(name=outrecord.outname, option=font_option) )

    @classmethod
    def constitute_preamble(cls, outrecord, metapreamble):
        preamble_items = []
        for item in metapreamble:
            preamble_items.append(cls.constitute_preamble_item(item))
        for tex_package in outrecord['tex packages']:
            preamble_items.append(cls.constitute_preamble_item(
                cls.PackagePreambleItem(tex_package) ))
        if 'scale font' in outrecord:
            font, skip = outrecord['scale font']
            preamble_items.append(
                cls.substitute_selectfont(font=font, skip=skip) )
        return '\n'.join(preamble_items)

    selectfont_template = (
        r'\AtBeginDocument{\fontsize{$font}{$skip}\selectfont}' )

    @classmethod
    def constitute_preamble_item(cls, item):
        assert isinstance(item, cls.MetapreambleItem), type(item)
        if isinstance(item, cls.VerbatimPreambleItem):
            return item.verbatim
        elif isinstance(item, cls.PackagePreambleItem):
            return cls.substitute_usepackage(
                package=item.package,
                options=cls.constitute_options(item.options) )
        elif isinstance(item, cls.InpathPreambleItem):
            alias = item.alias
            assert alias.endswith('.sty')
            return cls.substitute_uselocalpackage(
                package=alias[:-len('.sty')], inpath=item.inpath )
        else:
            raise RuntimeError(type(item))

    usepackage_template = r'\usepackage$options{$package}'
    uselocalpackage_template = r'\usepackage{$package}% $inpath'

    @classmethod
    def constitute_options(cls, options):
        if not options:
            return ''
        if not isinstance(options, str):
            options = ','.join(options)
        return '[' + options + ']'

    @classmethod
    def constitute_body(cls, outrecord, metabody):
        body_items = []
        for item in metabody:
            body_items.append(cls.constitute_body_item(item))
        return '\n'.join(body_items)

    @classmethod
    def constitute_body_item(cls, item):
        assert isinstance(item, cls.MetabodyItem), item
        if isinstance(item, cls.VerbatimBodyItem):
            return item.verbatim
        elif isinstance(item, cls.InpathBodyItem):
            return cls.constitute_body_input(
                inpath=item.inpath, alias=item.alias,
                figname_map=item.figname_map )
        else:
            raise RuntimeError(type(item))

    @classmethod
    def constitute_body_input(cls, inpath,
        *, alias, figname_map
    ):
        body = cls.substitute_input(filename=alias, inpath=inpath )
        if figname_map:
            body = cls.constitute_figname_map(figname_map) + '\n' + body
        return body

    input_template = r'\input{$filename}% $inpath'

    @classmethod
    def constitute_figname_map(cls, figname_map):
        return '\n'.join(
            cls.substitute_jeolmfiguremap(alias=figalias, name=figname)
            for figalias, figname in figname_map.items() )

    jeolmfiguremap_template = r'\jeolmfiguremap{$alias}{$name}'

    @classmethod
    def constitute_datedef(cls, date):
        if date is None:
            return cls.substitute_dateundef()
        return cls.substitute_datedef(date=cls.constitute_date(date))

    datedef_template = r'\def\jeolmdate{$date}'
    dateundef_template = r'\let\jeolmdate\relax'

    @classmethod
    def constitute_date(cls, date):
        if not isinstance(date, datetime.date):
            return str(date)
        return cls.substitute_date(
            year=date.year,
            month=cls.ru_monthes[date.month-1],
            day=date.day )

    date_template = r'$day~$month~$year'
    ru_monthes = [
        'января', 'февраля', 'марта', 'апреля',
        'мая', 'июня', 'июля', 'августа',
        'сентября', 'октября', 'ноября', 'декабря' ]

    clearpage_template = '\n' r'\clearpage' '\n'
    emptypage_template = r'\strut\clearpage'
    resetproblem_template = r'\resetproblem'
    jeolmheader_template = r'\jeolmheader'
    datestamp_template = (
        r'    \begin{flushright}\small' '\n'
        r'    \jeolmdate' '\n'
        r'    \end{flushright}'
    )


    ##########
    # Supplementary finctions

    @staticmethod
    def select_outname(target, date=None):
        outname = '{target:outname}'.format(target=target)
        if isinstance(date, datetime.date):
            date_prefix = '{0.year:04}-{0.month:02}-{0.day:02}'.format(date)
            outname = date_prefix + '-' + outname
        assert '/' not in outname, repr(outname)
        return outname

    @staticmethod
    def select_alias(*parts, suffix=None):
        path = PurePosixPath(*parts)
        assert len(path.suffixes) == 1, path
        if suffix is not None:
            path = path.with_suffix(suffix)
        assert not path.is_absolute(), path
        return '-'.join(path.parts)

    @staticmethod
    def min_date(date_set):
        datetime_date_set = {date for date in date_set
            if isinstance(date, datetime.date) }
        if datetime_date_set:
            return min(datetime_date_set)
        elif len(date_set) == 1:
            date, = date_set
            return date
        else:
            return None

