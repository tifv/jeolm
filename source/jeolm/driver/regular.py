"""
Keys recognized in metarecords:
  $target$able (boolean)
    - if false then raise error on delegate and outrecord stages
    - propagates to children, assumed true by default
  $build$able (boolean)
    - if false then raise error on outrecord stage
    - propagates to children, assumed true by default
  $build$special  (one of 'standalone', 'latexdoc')
    - if present then outrecord generation will trigger a special case
    - set to 'latexdoc' by metadata grabber on .dtx files
  $source$able (boolean)
    - if false then raise error on auto metabody stage
      (hence, not checked if a suitable $matter key is found)
    - false by default
    - set to true by metadata grabber on .tex files
    - set to false by metadata grabber on .tex files with
      $build$special set to 'standalone'
  $source$figures (ordered dict)
    { alias_name : accessed_path for all accessed paths }
    - set by metadata grabber
  $figure$able (boolean)
    - if false then raise error on figure_record stage
    - assumed false by default
    - set to true by metadata grabber on .asy, .svg and .eps files
  $figure$type$* (boolean)
    - set to true by metadata grabber on respectively .asy, .svg, .pdf,
      .eps, .png and .jpg files
  $figure$asy$accessed (dict)
    - set by metadata grabber
  $package$able (boolean)
    - if false then raise error on package_record stage
    - assumed false by default
    - set to true by metadata grabber on .dtx and .sty files
  $package$format$dtx, $package$format$sty (boolean)
    - set to true by metadata grabber on respectively .dtx and .sty
      files
  $package$name
    - in build process, the package is symlinked with that very name
      (with .sty extension added)
    - extracted by metadata grabber from \\ProvidesPackage command in
      .sty or .dtx file
    - in absence of \\ProvidesPackage, borrowed by metadata grabber
      from the filename

  $build$compiler$default
    - string, name of default 'compiler' value in outrecords
      (e. g. 'latex')

  $include
    list of subpaths for direct metadata inclusion.

  $delegate$stop[*]
    Value: condition to stop delegation at this target.

  $delegate[*]
    Values:
    - <delegator (string)>
    - delegate: <delegator (string)>
    Non-string values may be extended with conditions.

  $build$options[*]
    Contents is included in protorecord

  $build$matter[*]
    Values are same as of $matter
  $build$style[*]
    Values are same as of $style

  $matter[*]
    Values expected from metadata:
    - verbatim: <string>
    - <delegator (string)>
    - delegate: <delegator (string)>
    - preamble verbatim: <string>
      provide: <key (string)>
    - preamble package: <package name>
    - preamble package: <package name>
      options: [<package options>]
    Non-string values may be extended with conditions.
  $style[*]
    Values expected from metadata:
    - verbatim: <string>
    - verbatim: <string>
      provide: <key (string)>
    - <delegator (string)>
    - delegate: <delegator (string)>
    - document class: <LaTeX class name>
      options: [<LaTeX class options>]
    - package: <package name>
    - package: <package name>
      options: [<package options>]
    - resize font: [<size>, <skip>]
        # best used with anyfontsize package
        # only affects font size at the beginning of document
        # (like, any size command including \\normalsize will undo this)
    Non-string values may be extended with conditions.

  $date

  $path:
    Used internally.

"""

from functools import wraps, partial
from contextlib import contextmanager, suppress
from collections import OrderedDict
from string import Template
import datetime
import re

from pathlib import PurePosixPath

from jeolm.record_path import RecordPath
from jeolm.target import Target
from jeolm.records import RecordsManager

from jeolm.flags import FlagError
from jeolm.target import TargetError
from jeolm.records import RecordError, RecordNotFoundError

from jeolm.utils import check_and_set

import logging
logger = logging.getLogger(__name__)


class Substitutioner(type):
    """
    Metaclass for a driver.

    For any '*_template' attribute create 'substitute_*' attribute, like
    cls.substitute_* = Template(cls.*_template).substitute
    """
    def __new__(mcs, name, bases, namespace, **kwargs):
        substitute_items = list()
        for key, value in namespace.items():
            if key.endswith('_template'):
                substitute_key = 'substitute_' + key[:-len('_template')]
                substitute_items.append(
                    (substitute_key, Template(value).substitute) )
        namespace.update(substitute_items)
        return super().__new__(mcs, name, bases, namespace, **kwargs)

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
    def __prepare__(mcs, name, bases, **kwargs):
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
                    # from the later base.
                    continue
                namespace[key] = value
        namespace['inclass_decorator'] = mcs.mark_inclass_decorator
        return namespace

    @staticmethod
    def mark_inclass_decorator(decorator):
        """Decorator."""
        decorator.is_inclass_decorator = True
        return decorator

    def __new__(mcs, name, bases, namespace, **kwargs):
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
        return super().__new__(mcs, name, bases, namespace, **kwargs)

class DriverError(Exception):
    pass

class DriverMetaclass(Substitutioner, Decorationer):
    pass

class RegularDriver(RecordsManager, metaclass=DriverMetaclass):

    driver_errors = (DriverError, TargetError, RecordError, FlagError)

    def __init__(self):
        super().__init__()
        self._cache.update(
            outrecords=dict(), package_records=dict(), figure_records=dict(),
            delegated_targets=dict() )

    ##########
    # Advanced error reporting

    @classmethod
    @contextmanager
    def fold_driver_errors(cls):
        try:
            yield
        except cls.driver_errors as error:
            driver_messages = []
            while isinstance(error, cls.driver_errors):
                message, = error.args
                driver_messages.append(str(message))
                error = error.__cause__
            raise DriverError(
                'Driver error stack:\n' +
                '\n'.join(driver_messages)
            ) from error

    if __debug__:
        @classmethod
        @contextmanager
        def fold_driver_errors(cls):
            yield

    @inclass_decorator
    def folding_driver_errors(*, wrap_generator=False):
        """In-class decorator factory."""
        def decorator(method):
            if not wrap_generator:
                @wraps(method)
                def wrapper(self, *args, **kwargs):
                    with self.fold_driver_errors():
                        return method(self, *args, **kwargs)
            else:
                @wraps(method)
                def wrapper(self, *args, **kwargs):
                    with self.fold_driver_errors():
                        yield from method(self, *args, **kwargs)
            return wrapper
        return decorator

    if __debug__:
        @inclass_decorator
        def folding_driver_errors(*, wrap_generator=False):
            """In-class decorator factory."""
            def decorator(method):
                return method
            return decorator


    @classmethod
    @contextmanager
    def process_target_aspect(cls, target, aspect):
        try:
            yield
        except cls.driver_errors as error:
            raise DriverError(
                "Error encountered while processing "
                "{target} {aspect}"
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

    @inclass_decorator
    def checking_target_recursion(method):
        """Decorator."""
        @wraps(method)
        def wrapper(self, target, *args, seen_targets=frozenset(), **kwargs):
            if target in seen_targets:
                raise DriverError(
                    "Cycle detected from {}".format(target) )
            seen_targets |= {target}
            return method(self, target, *args,
                seen_targets=seen_targets, **kwargs )
        return wrapper

    ##########
    # Interface methods and attributes

    class NoDelegators(Exception):
        pass

    class StopDelegation(NoDelegators):
        pass

    @folding_driver_errors(wrap_generator=True)
    def list_delegated_targets(self, *targets, recursively=True):
        if not recursively and len(targets) != 1:
            raise RuntimeError
        for target in targets:
            try:
                delegators = \
                    self._cache['delegated_targets'][target, recursively]
            except KeyError:
                if not recursively:
                    try:
                        delegators = list(self.generate_delegators(target))
                    except self.NoDelegators:
                        delegators = None
                else:
                    delegators = list(self.generate_delegated_targets(target))
                self._cache['delegated_targets'][target, recursively] = \
                    delegators
            if delegators is None:
                raise self.NoDelegators
            else:
                yield from delegators

    @folding_driver_errors(wrap_generator=True)
    def list_metapaths(self):
        # Caching is not necessary since no use-case involves calling this
        # method several times.
        yield from self.generate_metapaths()

    @folding_driver_errors(wrap_generator=False)
    def metapath_is_targetable(self, metapath):
        return self.getitem(metapath)['$target$able']

    @folding_driver_errors(wrap_generator=False)
    def list_targetable_children(self, metapath):
        for name in self.getitem(metapath):
            if name.startswith('$'):
                continue
            assert '/' not in name
            submetapath = metapath / name
            if self.getitem(submetapath)['$target$able']:
                yield submetapath

    @folding_driver_errors(wrap_generator=False)
    def produce_outrecord(self, target):
        """
        Return outrecord.

        Each outrecord must contain the following fields:
        'outname'
            string
        'buildname'
            string
        'type'
            one of 'regular', 'standalone', 'latexdoc'
        'compiler'
            one of 'latex', 'pdflatex', 'xelatex', 'lualatex'

        regular outrecord must also contain fields:
        'sources'
            {alias_name : inpath for each inpath}
            where alias_name is a filename with '.tex' extension, and inpath
            also has '.tex' extension.
        'figures'
            {alias_name : (figure_path, figure_type) for each figure}
        'document'
            LaTeX document as a string

        regular and latexdoc outrecord must contain field:
        'package_paths'
            {alias_name : package_path for each local package}
            (for latexdoc, this is the corresponding package)

        standalone and latexdoc outrecord must also contain field:
        'source'
            inpath with '.tex' or '.dtx' extension, depending on outrecord
            type

        latexdoc outrecord must contain field:
        'name'
            package name, as in ProvidesPackage.
        """
        with suppress(KeyError):
            return self._cache['outrecords'][target]
        outrecord = self._cache['outrecords'][target] = \
            self.generate_outrecord(target)
        keys = outrecord.keys()
        if not keys >= {'outname', 'buildname', 'type', 'compiler'}:
            raise RuntimeError(keys)
        if outrecord['type'] not in {'regular', 'standalone', 'latexdoc'}:
            raise RuntimeError
        if outrecord['type'] in {'regular'}:
            if not keys >= {'sources', 'figures', 'document'}:
                raise RuntimeError
            for figure_path, figure_type in outrecord['figures'].values():
                if figure_type not in { None,
                        'asy', 'svg', 'eps', 'pdf', 'png', 'jpg'}:
                    raise RuntimeError(figure_type)
        if outrecord['type'] in {'regular', 'latexdoc'}:
            if 'package_paths' not in keys:
                raise RuntimeError
        if outrecord['type'] in {'standalone', 'latexdoc'}:
            if 'source' not in keys:
                raise RuntimeError
        if outrecord['type'] in {'latexdoc'}:
            if 'name' not in keys:
                raise RuntimeError
        if outrecord['compiler'] not in {
                'latex', 'pdflatex', 'xelatex', 'lualatex' }:
            raise RuntimeError
        return outrecord

    @folding_driver_errors(wrap_generator=False)
    def produce_package_records(self, package_path):
        """
        Return {package_type : package_record} dictionary.

        Each package_record must contain the following fields:
        'type'
            one of 'dtx', 'sty'
        'source'
            inpath
        'name'
            package name, as in ProvidesPackage.
        """
        assert isinstance(package_path, RecordPath), type(package_path)
        with suppress(KeyError):
            return self._cache['package_records'][package_path]
        package_records = self._cache['package_records'][package_path] = \
            dict(self._generate_package_records(package_path))
        # QA
        if not package_records:
            raise RuntimeError(package_path)
        for package_type, package_record in package_records.items():
            keys = package_record.keys()
            if not keys >= {'type', 'source', 'name'}:
                raise RuntimeError(keys)
            if package_type not in {'dtx', 'sty'}:
                raise RuntimeError(package_type)
            if package_record['type'] != package_type:
                raise RuntimeError
        return package_records

    @folding_driver_errors(wrap_generator=False)
    def produce_figure_records(self, figure_path):
        """
        Return {figure_type : figure_record} dictionary.

        Each figure_record must contain the following fields:
        'type':
            one of 'asy', 'svg', 'pdf', 'eps', 'png', 'jpg'
        'source'
            inpath

        In case of Asymptote file ('asy' type), figure_record must also
        contain:
        'accessed_sources'
            {accessed_name : inpath for each accessed inpath}
            where accessed_name is a filename with '.asy' extension,
            and inpath has '.asy' extension
        """
        assert isinstance(figure_path, RecordPath), type(figure_path)
        with suppress(KeyError):
            return self._cache['figure_records'][figure_path]
        figure_records = self._cache['figure_records'][figure_path] = \
            dict(self._generate_figure_records(figure_path))
        # QA
        if not figure_records:
            raise RuntimeError(figure_path)
        for figure_type, figure_record in figure_records.items():
            keys = figure_record.keys()
            if not keys >= {'type', 'source'}:
                raise RuntimeError(keys)
            if figure_type not in {'asy', 'svg', 'eps'}:
                raise RuntimeError(figure_type)
            if figure_record['type'] != figure_type:
                raise RuntimeError
            if figure_record['type'] == 'asy':
                if 'accessed_sources' not in keys:
                    raise RuntimeError
        return figure_records

    @folding_driver_errors(wrap_generator=True)
    def list_inpaths(self, *targets, inpath_type='tex'):
        if inpath_type not in {'tex', 'asy'}:
            raise RuntimeError(inpath_type)
        for target in targets:
            outrecord = self.produce_outrecord(target)
            if outrecord['type'] not in {'regular'}:
                raise DriverError(
                    "Can only list inpaths for regular documents: {target}"
                    .format(target=target) )
            if inpath_type == 'tex':
                for inpath in outrecord['sources'].values():
                    if inpath.suffix == '.tex':
                        yield inpath
            elif inpath_type == 'asy':
                yield from self._list_inpaths_asy(target, outrecord)

    def _list_inpaths_asy(self, target, outrecord):
        for figure_path, figure_type in outrecord['figures'].values():
            if figure_type != 'asy':
                continue
            for figure_record in self.produce_figure_records(figure_path):
                if figure_record['type'] != 'asy':
                    continue
                yield figure_record['source']
                break
            else:
                raise DriverError(
                    "No 'asy' type figure found for {path} in {target}"
                    .format(path=figure_path, target=target) )

    ##########
    # Record extension

    def _derive_attributes(self, parent_record, child_record, name):
        super()._derive_attributes(parent_record, child_record, name)
        path = child_record['$path']
        child_record.setdefault('$target$able',
            parent_record.get('$target$able', True) )
        child_record.setdefault('$build$able',
            parent_record.get('$build$able', True) )
        self._derive_compiler_default(parent_record, child_record, path=path)
        if '$include' in child_record:
            already_included = set()
            included_paths = [
                RecordPath(path, include_name)
                for include_name in reversed(child_record.pop('$include')) ]
            while included_paths:
                included_path = included_paths.pop()
                if included_path in already_included:
                    raise RecordError( "Double-inclusion of path {} in {}"
                        .format(included_path, path) )
                included_value = self.getitem(included_path, original=True)
                if '$include' in included_value:
                    included_value = included_value.copy()
                    included_paths.extend(
                        RecordPath(included_path, include_name)
                        for include_name
                        in reversed(included_value.pop('$include')) )
                self._include_dict(child_record, included_value)
                already_included.add(included_path)

    @classmethod
    def _derive_compiler_default( cls, parent_record, child_record, *, path,
        _compiler_default_key = '$build$compiler$default'
    ):
        if _compiler_default_key not in child_record:
            if _compiler_default_key not in parent_record:
                compiler_default = 'latex'
                logger.warning(
                    "No <MAGENTA>%(key)s<NOCOLOUR> key set "
                    "at %(path)s, asserting '<CYAN>%(compiler)s<NOCOLOUR>'",
                    extra=dict(
                        key=_compiler_default_key, path=path,
                        compiler=compiler_default )
                )
            else:
                compiler_default = parent_record[_compiler_default_key]
            child_record[_compiler_default_key] = compiler_default

    @classmethod
    def _include_dict(cls, dest_dict, source_dict):
        for key, source_value in source_dict.items():
            dest_value = dest_dict.get(key)
            if dest_value is None:
                dest_dict[key] = source_value
            elif key.startswith('$'):
                # No override
                continue
            else:
                dest_dict[key] = dest_value = dest_value.copy()
                assert isinstance(dest_value, dict)
                assert isinstance(source_value, dict)
                cls._include_dict(dest_value, source_value)

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

    def generate_metapaths(self, path=None):
        """Yield metapaths."""
        if path is None:
            path = RecordPath()
        record = self.getitem(path)
        if record.get('$target$able', True):
            yield path
        for key in record:
            if key.startswith('$'):
                continue
            assert '/' not in key
            yield from self.generate_metapaths(path=path/key)

    ##########
    # Record-level functions (delegate)

    @fetching_metarecord
    @checking_target_recursion
    @processing_target_aspect(aspect='delegated_targets', wrap_generator=True)
    def generate_delegated_targets(self, target, metarecord,
        *, seen_targets
    ):
        try:
            delegators = list(self.generate_delegators(target, metarecord))
        except self.NoDelegators:
            yield target
        else:
            for delegator in delegators:
                yield from self.generate_delegated_targets(
                    delegator, seen_targets=seen_targets )

    @fetching_metarecord
    @processing_target_aspect(aspect='delegators', wrap_generator=True)
    def generate_delegators(self, target, metarecord):
        """Yield targets."""
        if not metarecord.get('$target$able', True):
            raise DriverError( "Target {target} is not targetable"
                .format(target=target) )
        delegate_stop_key, delegate_stop = self.select_flagged_item(
            metarecord, '$delegate$stop', target.flags )
        if delegate_stop_key is not None:
            if target.flags.check_condition(delegate_stop):
                raise self.StopDelegation
        delegate_key, delegators = self.select_flagged_item(
            metarecord, '$delegate', target.flags )
        if delegate_key is None:
            raise self.NoDelegators
        with self.process_target_key(target, delegate_key):
            if not isinstance(delegators, list):
                raise DriverError(type(delegators))
            derive_target = partial( target.derive_from_string,
                origin='delegate {target}, key {key}'
                    .format(target=target, key=delegate_key)
            )
            for item in delegators:
                if isinstance(item, str):
                    yield derive_target(item)
                    continue
                if not isinstance(item, dict):
                    raise DriverError(type(item))
                item = item.copy()
                condition = item.pop('condition', True)
                if not target.flags.check_condition(condition):
                    continue
                if item.keys() == {'delegate'}:
                    yield derive_target(item['delegate'])
                else:
                    raise DriverError(item)


    ##########
    # Metabody and metapreamble items

    class MetabodyItem:
        __slots__ = []

    class VerbatimBodyItem(MetabodyItem):
        """These items represent a piece of LaTeX code."""
        __slots__ = ['value']

        def __init__(self, value):
            self.value = str(value)
            super().__init__()

    class ControlBodyItem(MetabodyItem):
        """These items has no representation in document body."""
        __slots__ = []

    class SourceBodyItem(MetabodyItem):
        """These items represent inclusion of a source file."""
        __slots__ = ['metapath', 'alias', 'figure_map']

        def __init__(self, metapath):
            if not isinstance(metapath, RecordPath):
                raise RuntimeError(metapath)
            self.metapath = metapath
            super().__init__()

        @property
        def inpath(self):
            return self.metapath.as_inpath(suffix='.tex')

    class ClearPageBodyItem(VerbatimBodyItem):
        __slots__ = []

        def __init__(self, value=r'\clearpage'):
            super().__init__(value=value)

    class EmptyPageBodyItem(VerbatimBodyItem):
        __slots__ = []

        def __init__(self, value=r'\strut\clearpage'):
            super().__init__(value=value)

    class RequirePreambleBodyItem(ControlBodyItem):
        __slots__ = ['key', 'value']

        def __init__(self, key, value):
            self.key = key
            self.value = value
            super().__init__()

    class RequirePackageBodyItem(ControlBodyItem):
        __slots__ = ['package', 'options']

        def __init__(self, package, options=()):
            self.package = str(package)
            if isinstance(options, str):
                raise DriverError(
                    "Package options must not be a single string, "
                    "but a sequence." )
            self.options = [str(item) for item in options]
            super().__init__()

    @classmethod
    def classify_resolved_metabody_item(cls, item, *, default):
        assert default in {None, 'verbatim'}, default
        if isinstance(item, cls.MetabodyItem):
            return item
        elif isinstance(item, str):
            if default == 'verbatim':
                return cls.VerbatimBodyItem(value=item)
            else:
                raise RuntimeError(item)
        elif not isinstance(item, dict):
            raise RuntimeError(item)
        elif item.keys() == {'verbatim'}:
            return cls.VerbatimBodyItem(value=item['verbatim'])
        elif item.keys() == {'preamble verbatim', 'provide'}:
            return cls.RequirePreambleBodyItem(
                value=item['preamble verbatim'], key=item['provide'] )
        elif item.keys() == {'preamble package'}:
            return cls.RequirePackageBodyItem(
                package=item['preamble package'] )
        elif item.keys() == {'preamble package', 'options'}:
            return cls.RequirePackageBodyItem(
                package=item['preamble package'], options=item['options'] )
        else:
            raise DriverError(item)

    @classmethod
    def classify_metabody_item(cls, item, *, default):
        if isinstance(item, Target):
            return item
        else:
            return cls.classify_resolved_metabody_item( item,
                default=default )

    class MetapreambleItem:
        __slots__ = []

        def __init__(self):
            super().__init__()

    class VerbatimPreambleItem(MetapreambleItem):
        __slots__ = ['value']

        def __init__(self, value):
            self.value = str(value)
            super().__init__()

    class DocumentClassItem(MetapreambleItem):
        __slots__ = ['document_class', 'options']

        def __init__(self, document_class, options=()):
            self.document_class = str(document_class)
            if isinstance(options, str):
                raise DriverError(
                    "Class options must not be a single string, "
                    "but a sequence." )
            self.options = [str(item) for item in options]
            super().__init__()

    class LocalPackagePreambleItem(MetapreambleItem):
        __slots__ = ['package_path', 'package_type', 'package_name']

        def __init__(self, package_path, package_type):
            if not isinstance(package_path, RecordPath):
                raise RuntimeError(package_path)
            self.package_path = package_path
            self.package_type = package_type
            super().__init__()

    class ProvidePreamblePreambleItem(VerbatimPreambleItem):
        __slots__ = ['key']

        def __init__(self, key, value):
            assert isinstance(key, str), type(key)
            self.key = key
            super().__init__(value=value)

    class ProvidePackagePreambleItem(MetapreambleItem):
        __slots__ = ['package', 'options']

        def __init__(self, package, options=()):
            self.package = str(package)
            if isinstance(options, str):
                raise DriverError(
                    "Package options must not be a single string, "
                    "but a sequence." )
            self.options = [str(item) for item in options]
            super().__init__()

    @classmethod
    def classify_resolved_metapreamble_item(cls, item, *, default):
        assert default in {None, 'verbatim'}, default
        if isinstance(item, cls.MetapreambleItem):
            return item
        elif isinstance(item, str):
            if default == 'verbatim':
                return cls.VerbatimPreambleItem(value=item)
            else:
                raise RuntimeError(item)
        elif not isinstance(item, dict):
            raise RuntimeError(item)
        elif item.keys() == {'verbatim'}:
            return cls.VerbatimPreambleItem(
                value=item['verbatim'] )
        elif item.keys() == {'verbatim', 'provide'}:
            return cls.ProvidePreamblePreambleItem(
                value=item['verbatim'], key=item['provide'] )
        elif item.keys() == {'package'}:
            return cls.ProvidePackagePreambleItem(
                package=item['package'] )
        elif item.keys() == {'package', 'options'}:
            return cls.ProvidePackagePreambleItem(
                package=item['package'], options=item['options'] )
        elif item.keys() == {'resize font'}:
            size, skip = item['font size']
            return cls.ProvidePreamblePreambleItem(
                value=cls.substitute_selectfont(
                    size=float(size), skip=float(skip)
                ), key='AtBeginDocument:fontsize' )
        elif item.keys() == {'document class'}:
            return cls.DocumentClassItem(
                document_class=item['document class'] )
        elif item.keys() == {'document class', 'options'}:
            return cls.DocumentClassItem(
                document_class=item['document class'],
                options=item['options'] )
        else:
            raise DriverError(item)

    @classmethod
    def classify_metapreamble_item(cls, item, *, default):
        if isinstance(item, Target):
            return item
        return cls.classify_resolved_metapreamble_item(item, default=default)

    @inclass_decorator
    def classifying_items(*, aspect, default):
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


    ##########
    # Record-level functions (outrecord)

    @fetching_metarecord
    @processing_target_aspect(aspect='outrecord')
    def generate_outrecord(self, target, metarecord):
        if not metarecord.get('$target$able', True) or \
                not metarecord.get('$build$able', True):
            raise DriverError( "Target {target} is not buildable"
                .format(target=target) )
        if target.path.is_root():
            raise DriverError("Direct building of '/' is prohibited." )
        if '$build$special' in metarecord:
            return self.generate_special_outrecord(target, metarecord)
        else:
            return self.generate_regular_outrecord(target)

    @fetching_metarecord
    @processing_target_aspect(aspect='special outrecord')
    def generate_special_outrecord(self, target, metarecord):
        special_type = metarecord['$build$special']
        if special_type not in {'standalone', 'latexdoc'}:
            raise DriverError(
                "Unknown type of special '{}'".format(special_type) )
        outrecord = {'type' : special_type}
        self._set_outrecord_compiler(target, metarecord, outrecord=outrecord)
        outrecord['outname'] = outrecord['buildname'] = \
            self.select_outname(target, metarecord, date=None)
        suffix = {'latexdoc' : '.dtx', 'standalone' : '.tex'}[special_type]
        outrecord['source'] = target.path.as_inpath(suffix=suffix)
        if special_type == 'latexdoc':
            package_name_key = self._get_package_name_key('dtx')
            package_name = outrecord['name'] = metarecord[package_name_key]
            outrecord['package_paths'] = {package_name : target.path}
        return outrecord

    @fetching_metarecord
    @processing_target_aspect(aspect='regular outrecord')
    def generate_regular_outrecord(self, target, metarecord):
        """
        Return protorecord.
        """
        date_set = set()
        additional_flags = set()

        outrecord = {'type' : 'regular'}
        outrecord.update(self._find_build_options(target, metarecord))
        additional_flags.update(
            self._set_outrecord_compiler( target, metarecord,
                outrecord=outrecord )
        )
        extended_target = target.flags_union(additional_flags)
        extended_target.flags.utilize(additional_flags)

        # We must exhaust generate_metabody() to fill date_set
        metabody = list(self.generate_metabody(
            extended_target, metarecord, date_set=date_set ))
        metapreamble = list(self.generate_metapreamble(
            extended_target, metarecord ))

        sources = outrecord['sources'] = OrderedDict()
        figures = outrecord['figures'] = OrderedDict()
        package_paths = outrecord['package_paths'] = OrderedDict()
        outrecord.setdefault('date', self.min_date(date_set))

        metabody = list(self._digest_metabody(
            extended_target, metabody,
            sources=sources, figures=figures,
            metapreamble=metapreamble ))
        metapreamble = list(self._digest_metapreamble(
            extended_target, metapreamble,
            package_paths=package_paths ))

        target.check_unutilized_flags()

        if 'outname' not in outrecord:
            outrecord['outname'] = self.select_outname(
                target, metarecord, date=outrecord['date'] )
        if 'buildname' not in outrecord:
            outrecord['buildname'] = self.select_outname(
                target, metarecord, date=None )

        with self.process_target_aspect(target, 'document'):
            outrecord['document'] = self.constitute_document(
                outrecord,
                metapreamble=metapreamble, metabody=metabody, )
        return outrecord

    def _find_build_options(self, target, metarecord):
        options_key, options = self.select_flagged_item(
            metarecord, '$build$options', target.flags )
        if options is None:
            return ()
        with self.process_target_key(target, options_key):
            if not isinstance(options, dict):
                raise DriverError(
                    "Build options must be a dictionary, not {}"
                    .format(type(options).__name__) )
            if options.keys() & {
                    'type', 'document', 'sources',
                    'figures', 'package_paths', }:
                raise DriverError("Bad options {}".format(options) )
            return options

    @processing_target_aspect(aspect='outrecord compiler')
    def _set_outrecord_compiler(self, target, metarecord, *, outrecord):
        """Return additional flags for the target."""
        if 'compiler' not in outrecord:
            outrecord['compiler'] = metarecord['$build$compiler$default']
        if outrecord['compiler'] not in {
                'latex', 'pdflatex', 'xelatex', 'lualatex' }:
            raise DriverError( "Unknown compiler detected: {}"
                .format(outrecord['compiler']) )
        return {'compiler-{}'.format(outrecord['compiler'])}

    def select_outname(self, target, metarecord, date=None):
        outname_pieces = []
        if isinstance(date, datetime.date):
            outname_pieces.append(date.isoformat())
        outname_pieces.extend(target.path.parts)
        outname = '-'.join(outname_pieces) + '{:optional}'.format(target.flags)
        assert '/' not in outname, repr(outname)
        return outname

    @fetching_metarecord
    @processing_target_aspect(aspect='metabody', wrap_generator=True)
    @classifying_items(aspect='resolved_metabody', default=None)
    def generate_metabody(self, target, metarecord,
        *, date_set
    ):
        """
        Yield metabody items.
        Update date_set.
        """
        matter_key, matter = self.select_flagged_item(
            metarecord, '$build$matter', target.flags )
        with self.process_target_key(target, matter_key):
            yield from self.generate_resolved_metabody( target, metarecord,
                matter_key=matter_key, matter=matter, date_set=date_set )

    @fetching_metarecord
    @checking_target_recursion
    @processing_target_aspect(aspect='resolved_metabody', wrap_generator=True)
    @classifying_items(aspect='resolved_metabody', default=None)
    def generate_resolved_metabody(self, target, metarecord,
        *, date_set, matter_key=None, matter=None,
        seen_targets
    ):
        """
        Yield metabody items.
        Update date_set.
        """
        if matter is not None:
            seen_targets -= {target}
        date = self._find_date(target, metarecord)
        if date is not None:
            date_set.add(date)
            date_set = set()

        if 'header' in target.flags:
            date_subset = set()
            # exhaust iterator to find date_subset
            metabody = list(self.generate_resolved_metabody(
                target.flags_delta(
                    difference={'header'},
                    union={'no-header'} ),
                metarecord,
                date_set=date_subset, matter_key=matter_key, matter=matter,
                seen_targets=seen_targets ))
            yield from self.generate_header_metabody( target, metarecord,
                date=self.min_date(date_subset) )
            yield from metabody
            date_set.update(date_subset)
            return

        metabody_generator = self.generate_matter_metabody(
            target, metarecord, matter=matter, matter_key=matter_key )
        for item in metabody_generator:
            if isinstance(item, self.MetabodyItem):
                yield item
            elif isinstance(item, Target):
                yield from self.generate_resolved_metabody(
                    item, date_set=date_set, seen_targets=seen_targets )
            else:
                raise RuntimeError(type(item))

    @processing_target_aspect(aspect='header metabody', wrap_generator=True)
    @classifying_items(aspect='resolved_metabody', default='verbatim')
    def generate_header_metabody( self, target, metarecord, *,
        date, resetproblem=True
    ):
        yield self.substitute_jeolmheader_begin()
        yield from self._generate_header_def_metabody( target, metarecord,
            date=date )
        yield self.substitute_jeolmheader_end()
        if resetproblem:
            yield self.substitute_resetproblem()

    def _generate_header_def_metabody(self, target, metarecord, *, date):
        if not target.flags.intersection({'multidate', 'no-date'}):
            if date is not None:
                yield self._constitute_date_def(date=date)

    def _find_date(self, target, metarecord):
        return metarecord.get('$date')

    @processing_target_aspect(aspect='matter metabody', wrap_generator=True)
    @classifying_items(aspect='metabody', default='verbatim')
    def generate_matter_metabody(self, target, metarecord,
        *, matter_key=None, matter=None
    ):
        if matter is None:
            matter_key, matter = self.select_flagged_item(
                metarecord, '$matter', target.flags )
        if matter is None:
            yield from self.generate_auto_metabody(target, metarecord)
            return
        with self.process_target_key(target, matter_key):
            if not isinstance(matter, list):
                raise DriverError(
                    "Matter must be a list, not {}"
                    .format(type(matter).__name__) )
            for item in matter:
                yield from self.generate_matter_item_metabody(
                    target, metarecord,
                    matter_key=matter_key, matter_item=item )

    def generate_matter_item_metabody(self, target, metarecord,
        *, matter_key, matter_item, recursed=False
    ):
        derive_target = partial( target.derive_from_string,
            origin='matter {target}, key {key}'
                .format(target=target, key=matter_key)
        )
        if isinstance(matter_item, str):
            yield derive_target(matter_item)
            return
        if isinstance(matter_item, list):
            if recursed:
                raise DriverError(
                    "Matter is allowed to have two folding levels at most" )
            if not matter_item:
                yield self.EmptyPageBodyItem()
            else:
                for item in matter_item:
                    yield from self.generate_matter_item_metabody(
                        target, metarecord,
                        matter_key=matter_key, matter_item=item,
                        recursed=True )
                yield self.ClearPageBodyItem()
            return
        if not isinstance(matter_item, dict):
            raise DriverError(
                "Matter item must be a string or a dictionary, not {}"
                .format(type(matter_item).__name__) )
        matter_item = matter_item.copy()
        condition = matter_item.pop('condition', True)
        if not target.flags.check_condition(condition):
            return
        if matter_item.keys() == {'delegate'}:
            yield derive_target(matter_item['delegate'])
        else:
            yield matter_item

    @processing_target_aspect(aspect='auto metabody', wrap_generator=True)
    @classifying_items(aspect='metabody', default='verbatim')
    def generate_auto_metabody(self, target, metarecord):
        if not metarecord.get('$source$able', False):
            raise DriverError( "Target {target} is not sourceable"
                .format(target=target) )
        yield from self.generate_source_metabody(
            target, metarecord )

    @processing_target_aspect(aspect='source metabody', wrap_generator=True)
    @classifying_items(aspect='metabody', default='verbatim')
    def generate_source_metabody(self, target, metarecord):
        assert metarecord.get('$source$able', False)
        if not target.flags.intersection(('header', 'no-header')):
            yield target.flags_union({'header'})
            return # recurse
        yield self.SourceBodyItem(metapath=target.path)
        if 'multidate' in target.flags:
            yield from self._generate_source_datestamp_metabody(
                target, metarecord )

    def _generate_source_datestamp_metabody(self, target, metarecord):
        if 'no-date' in target.flags:
            return
        date = self._find_date(target, metarecord)
        if date is None:
            return
        yield self.substitute_datestamp(date=date)

    @fetching_metarecord
    @processing_target_aspect(aspect='metapreamble', wrap_generator=True)
    @classifying_items(aspect='resolved_metapreamble', default=None)
    def generate_metapreamble(self, target, metarecord):
        style_key, style = self.select_flagged_item(
            metarecord, '$build$style', target.flags )
        with self.process_target_key(target, style_key):
            yield from self.generate_resolved_metapreamble(
                target, metarecord,
                style_key=style_key, style=style )

    @fetching_metarecord
    @checking_target_recursion
    @processing_target_aspect(aspect='resolved metapreamble',
        wrap_generator=True )
    @classifying_items(aspect='resolved_metapreamble', default=None)
    def generate_resolved_metapreamble(self, target, metarecord,
        *, style_key=None, style=None,
        seen_targets
    ):
        if style is not None:
            seen_targets -= {target}

        metapreamble_generator = self.generate_style_metapreamble(
            target, metarecord, style=style, style_key=style_key )
        for item in metapreamble_generator:
            if isinstance(item, self.MetapreambleItem):
                yield item
            elif isinstance(item, Target):
                yield from self.generate_resolved_metapreamble(
                    item, seen_targets=seen_targets )
            else:
                raise RuntimeError(type(item))

    @processing_target_aspect(aspect='style metapreamble', wrap_generator=True)
    @classifying_items(aspect='metapreamble', default=None)
    def generate_style_metapreamble(self, target, metarecord,
        *, style_key=None, style=None
    ):
        if style is None:
            style_key, style = self.select_flagged_item(
                metarecord, '$style', target.flags )
        if style is None:
            yield from self.generate_auto_metapreamble(target, metarecord)
            return
        with self.process_target_key(target, style_key):
            if not isinstance(style, list):
                raise DriverError(type(style))
            for item in style:
                yield from self.generate_style_item_metapreamble(
                    target, metarecord,
                    style_key=style_key, style_item=item )

    def generate_style_item_metapreamble(self, target, metarecord,
        *, style_key, style_item
    ):
        derive_target = partial( target.derive_from_string,
            origin='style {target}, key {key}'
                .format(target=target, key=style_key)
        )
        if isinstance(style_item, str):
            yield derive_target(style_item)
            return
        if not isinstance(style_item, dict):
            raise DriverError(
                "Style item must be a string or a dictionary, not {}"
                .format(type(style_item).__name__) )
        style_item = style_item.copy()
        condition = style_item.pop('condition', True)
        if not target.flags.check_condition(condition):
            return
        if style_item.keys() == {'delegate'}:
            yield derive_target(style_item['delegate'])
        else:
            yield style_item

    @processing_target_aspect(aspect='auto metapreamble', wrap_generator=True)
    @classifying_items(aspect='metapreamble', default='verbatim')
    def generate_auto_metapreamble(self, target, metarecord):
        if '$package$able' in metarecord:
            for package_type in self._package_types:
                package_type_key = self._get_package_type_key(package_type)
                if metarecord.get(package_type_key, False):
                    break
            else:
                raise DriverError("Failed to determine package type")
            yield self.LocalPackagePreambleItem(
                package_path=target.path,
                package_type=package_type )
        else:
            yield target.path_derive('..')

    def _digest_metabody(self, target, metabody, *,
        sources, figures, metapreamble
    ):
        """
        Yield metabody items. Extend sources, figures, metapreamble.
        """
        page_cleared = True
        for item in metabody:
            assert isinstance(item, self.MetabodyItem), type(item)
            if isinstance(item, self.ClearPageBodyItem):
                if not page_cleared:
                    page_cleared = True
                    yield item
            elif isinstance(item, self.EmptyPageBodyItem):
                if not page_cleared:
                    yield self.ClearPageBodyItem()
                    page_cleared = True
                yield item
            elif isinstance(item, self.VerbatimBodyItem):
                page_cleared = False
                yield item
            elif isinstance(item, self.SourceBodyItem):
                self._digest_metabody_source_item( target, item,
                    sources=sources, figures=figures )
                page_cleared = False
                yield item
            elif isinstance(item, self.RequirePreambleBodyItem):
                metapreamble.append(self.ProvidePreamblePreambleItem(
                    key=item.key, value=item.value ))
            elif isinstance(item, self.RequirePackageBodyItem):
                metapreamble.append(self.ProvidePackagePreambleItem(
                    package=item.package, options=item.options ))
            elif isinstance(item, self.ControlBodyItem):
                # should be handled by superclass
                yield item
            else:
                raise RuntimeError(type(item))

    def _digest_metabody_source_item(self, target, item,
        *, sources, figures
    ):
        assert isinstance(item, self.SourceBodyItem)
        metarecord = self.getitem(item.metapath)
        if not metarecord.get('$source$able', False):
            raise RuntimeError( "Path {path} is not sourceable"
                .format(path=item.metapath) )
        item.alias = self.select_alias(item.inpath, suffix='.tex')
        self.check_and_set(sources, item.alias, item.inpath)
        item.figure_map = OrderedDict()
        figure_refs = metarecord.get('$source$figures', ())
        for figure_ref in figure_refs:
            match = self._figure_ref_pattern.match(figure_ref)
            if match is None:
                raise RuntimeError(figure_ref)
            figure = match.group('figure')
            figure_type = match.group('figure_type')
            figure_path = RecordPath(item.metapath, figure)
            figure_alias = self.select_alias(figure_path.as_inpath())
            with self.process_target_aspect(item.metapath, 'figure_map'):
                self.check_and_set(item.figure_map, figure_ref, figure_alias)
            with self.process_target_aspect(target, 'figures'):
                self.check_and_set( figures,
                    figure_alias, (figure_path, figure_type) )

    _figure_ref_pattern = re.compile( r'^'
        r'(?P<figure>'
            r'/?'
            r'(?:(?:\w+-)\w+/|../)*'
            r'(?:\w+-)*\w+'
        r')'
        r'(?:\.(?P<figure_type>asy|svg|pdf|eps|png|jpg))?'
    r'$')

    def _digest_metapreamble(self, target, metapreamble,
        *, package_paths
    ):
        """
        Yield metapreamble items.
        Extend package_paths.
        """
        for item in metapreamble:
            assert isinstance(item, self.MetapreambleItem), type(item)
            if isinstance(item, self.LocalPackagePreambleItem):
                package_path = item.package_path
                package_type = item.package_type
                metarecord = self.getitem(package_path)
                package_name_key = self._get_package_name_key(package_type)
                try:
                    package_name = item.package_name = \
                        metarecord[package_name_key]
                except KeyError as error:
                    raise DriverError( "Package {} of type {} name not found"
                        .format(package_path, package_type) ) from error
                self.check_and_set(package_paths, package_name, package_path)
                yield item
            elif isinstance(item, self.ProvidePackagePreambleItem):
                key = 'usepackage:{}'.format(item.package)
                value = self.substitute_usepackage( package=item.package,
                    options=self.constitute_options(item.options) )
                yield self.ProvidePreamblePreambleItem(key=key, value=value)
            else:
                yield item


    ##########
    # Record-level functions (package_record)

    def _generate_package_records(self, package_path):
        try:
            metarecord = self.getitem(package_path)
        except RecordNotFoundError as error:
            raise DriverError('Package not found') from error
        if not metarecord.get('$package$able', False):
            raise DriverError("Package '{}' not found".format(package_path))

        for package_type in self._package_types:
            package_type_key = self._get_package_type_key(package_type)
            if not metarecord.get(package_type_key, False):
                continue
            suffix = self._get_package_suffix(package_type)
            inpath = package_path.as_inpath(suffix=suffix)
            name_key = self._get_package_name_key(package_type)
            try:
                package_name = metarecord[name_key]
            except KeyError as error:
                raise DriverError( "Package {} of type {} name not found"
                    .format(package_path, package_type) ) from error

            package_record = {
                'type' : package_type,
                'source' : inpath, 'name' : package_name }
            yield package_type, package_record

    _package_types = ('dtx', 'sty',)

    @staticmethod
    def _get_package_type_key(package_type):
        return '$package$type${}'.format(package_type)

    @staticmethod
    def _get_package_name_key(package_type):
        return '$package${}$name'.format(package_type)

    @staticmethod
    def _get_package_suffix(package_type):
        return '.{}'.format(package_type)


    ##########
    # Record-level functions (figure_record)

    def _generate_figure_records(self, figure_path):
        try:
            metarecord = self.getitem(figure_path)
        except RecordNotFoundError as error:
            raise DriverError('Figure not found') from error
        if not metarecord.get('$figure$able', False):
            raise DriverError("Figure '{}' not found".format(figure_path))

        for figure_type in self._figure_types:
            figure_type_key = self._get_figure_type_key(figure_type)
            if not metarecord.get(figure_type_key, False):
                continue
            suffix = self._get_figure_suffix(figure_type)
            inpath = figure_path.as_inpath(suffix=suffix)

            figure_record = {
                'type' : figure_type,
                'source' : inpath }
            if figure_type == 'asy':
                figure_record['accessed_sources'] = \
                    self._find_figure_asy_sources(figure_path, metarecord)
            yield figure_type, figure_record

    _figure_types = ('asy', 'svg', 'pdf', 'eps', 'png', 'jpg',)

    @staticmethod
    def _get_figure_type_key(figure_type):
        return '$figure$type${}'.format(figure_type)

    @staticmethod
    def _get_figure_suffix(figure_type):
        return '.{}'.format(figure_type)

    def _find_figure_asy_sources(self, figure_path, metarecord):
        accessed_sources = dict()
        for accessed_name, inpath in (
            self._trace_figure_asy_sources(figure_path, metarecord)
        ):
            self.check_and_set(accessed_sources, accessed_name, inpath)
        return accessed_sources

    def _trace_figure_asy_sources(self, figure_path, metarecord,
        *, seen_items=None
    ):
        """Yield (accessed_name, inpath) pairs."""
        if seen_items is None:
            seen_items = set()
        accessed_paths = metarecord.get('$figure$asy$accessed', {})
        for accessed_name, accessed_path_s in accessed_paths.items():
            accessed_path = RecordPath(figure_path, accessed_path_s)
            if (accessed_name, accessed_path) in seen_items:
                continue
            else:
                seen_items.add((accessed_name, accessed_path))
            inpath = accessed_path.as_inpath(suffix='.asy')
            yield accessed_name, inpath
            yield from self._trace_figure_asy_sources(
                figure_path, metarecord, seen_items=seen_items )


    ##########
    # LaTeX-level functions

    @classmethod
    def constitute_document(cls, outrecord, metapreamble, metabody):
        return cls.substitute_document(
            preamble=cls.constitute_preamble(outrecord, metapreamble),
            body=cls.constitute_body(outrecord, metabody)
        )

    document_template = (
        r'% Auto-generated by jeolm' '\n\n'
        r'$preamble' '\n\n'
        r'\begin{document}' '\n\n'
        r'$body' '\n\n'
        r'\end{document}' '\n'
    )

    @classmethod
    def constitute_preamble(cls, outrecord, metapreamble):
        preamble_lines = [None]
        provided_preamble = {}
        for item in metapreamble:
            if isinstance(item, cls.DocumentClassItem):
                if preamble_lines[0] is not None:
                    raise DriverError(
                        "Multiple definitions of document class" )
                preamble_lines[0] = cls.substitute_documentclass(
                    document_class=item.document_class,
                    options=cls.constitute_options(item.options) )
                continue
            if isinstance(item, cls.ProvidePreamblePreambleItem):
                if not cls.check_and_set( provided_preamble,
                        item.key, item.value ):
                    continue
            preamble_lines.append(cls.constitute_preamble_item(item))
        if preamble_lines[0] is None:
            raise DriverError("No document class provided")
        return '\n'.join(preamble_lines)

    documentclass_template = r'\documentclass$options{$document_class}'

    @classmethod
    def constitute_preamble_item(cls, item):
        assert isinstance(item, cls.MetapreambleItem), type(item)
        if isinstance(item, cls.VerbatimPreambleItem):
            return item.value
        elif isinstance(item, cls.LocalPackagePreambleItem):
            return cls.substitute_uselocalpackage(
                package=item.package_name, package_path=item.package_path )
        else:
            raise RuntimeError(type(item))

    uselocalpackage_template = r'\usepackage{$package}% $package_path'

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
            body_items.append(cls._constitute_body_item(item))
        return '\n'.join(body_items)

    @classmethod
    def _constitute_body_item(cls, item):
        assert isinstance(item, cls.MetabodyItem), item
        if isinstance(item, cls.VerbatimBodyItem):
            return item.value
        elif isinstance(item, cls.SourceBodyItem):
            return cls._constitute_body_input(
                alias=item.alias,
                figure_map=item.figure_map,
                inpath=item.inpath, metapath=item.metapath )
        elif isinstance(item, cls.ControlBodyItem):
            raise RuntimeError(
                "Control body items must be handled somewhere earlier: {}"
                .format(type(item)) )
        else:
            raise RuntimeError(type(item))

    @classmethod
    def _constitute_body_input( cls, *,
        alias, figure_map, metapath, inpath
    ):
        body = cls.substitute_input(
            filename=alias,
            metapath=metapath, inpath=inpath )
        if figure_map:
            body = cls.constitute_figure_map(figure_map) + '\n' + body
        return body

    input_template = r'\input{$filename}% $metapath'

    @classmethod
    def constitute_figure_map(cls, figure_map):
        assert isinstance(figure_map, OrderedDict), type(figure_map)
        return '\n'.join(
            cls.substitute_jeolmfiguremap(ref=figure_ref, alias=figure_alias)
            for figure_ref, figure_alias in figure_map.items() )

    jeolmfiguremap_template = r'\jeolmfiguremap{$ref}{$alias}'

    @classmethod
    def _constitute_date_def(cls, date):
        if date is None:
            raise RuntimeError
        return cls.substitute_date_def(date=cls.constitute_date(date))

    date_def_template = r'\def\jeolmdate{$date}'

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

    selectfont_template = (
        r'\AtBeginDocument{\fontsize{$size}{$skip}\selectfont}' )
    usepackage_template = r'\usepackage$options{$package}'
    resetproblem_template = r'\resetproblem'
    jeolmheader_begin_template = r'\jeolmheader{'
    jeolmheader_end_template = r'}'
    datestamp_template = (
        r'\begin{flushright}\small' '\n'
        r'    $date' '\n'
        r'\end{flushright}'
    )

    ##########
    # Supplementary finctions

    @staticmethod
    def select_alias(*parts, suffix=None):
        path = PurePosixPath(*parts)
        assert len(path.suffixes) <= 1, path
        if suffix is not None:
            path = path.with_suffix(suffix)
        assert not path.is_absolute(), path
        return '-'.join(path.parts)

    @staticmethod
    def min_date(date_set):
        datetime_date_set = { date
            for date in date_set
            if isinstance(date, datetime.date) }
        if datetime_date_set:
            return min(datetime_date_set)
        elif len(date_set) == 1:
            date, = date_set
            return date
        else:
            return None

    @staticmethod
    def check_and_set(mapping, key, value):
        """
        Set mapping[key] to value if key is not in mapping.

        Return True if key is not present in mapping.
        Return False if key is present and values was the same.
        Raise DriverError if key is present, but value is different.
        """
        return check_and_set(mapping, key, value, error_class=DriverError)

