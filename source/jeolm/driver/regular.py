# Documentation {{{1
r"""
Keys recognized in metarecords:
  $target$able (boolean)
    - if false then raise error on delegate and outrecord stages
    - propagates to children, assumed true by default
  $build$able (boolean)
    - if false then raise error on outrecord stage
    - propagates to children, assumed true by default
  $source$able (boolean)
    - if false then raise error on auto metabody stage
      (hence, not checked if a suitable $matter key is found)
    - false by default
    - set to true by metadata grabber on .tex and .dtx files
  $source$type$tex, $source$type$dtx (boolean)
    - set to true by metadata grabber on respectively .tex and .dtx
      files
  $source$figures (ordered dict)
    { alias_name : accessed_path for all accessed paths }
    - set by metadata grabber
  $figure$able (boolean)
    - if false then raise error on figure_record stage
    - assumed false by default
    - set to true by metadata grabber on .asy, .svg, .pdf, .eps, .png
      and .jpg files
  $figure$type$* (boolean)
    - set to true by metadata grabber on respectively .asy, .svg, .pdf,
      .eps, .png and .jpg files
  $figure$asy$accessed (dict)
    - set by metadata grabber
  $package$able (boolean)
    - if false then raise error on package_record stage
    - assumed false by default
    - set to true by metadata grabber on .dtx and .sty files
  $package$type$dtx, $package$type$sty (boolean)
    - set to true by metadata grabber on respectively .dtx and .sty
      files
  $package$name
    - in build process, the package is symlinked with that very name
      (with .sty extension added)
    - extracted by metadata grabber from \ProvidesPackage command in
      .sty or .dtx file
    - in absence of \ProvidesPackage, borrowed by metadata grabber
      from the filename

  $delegate[*]
    Values:
    - <delegator (string)>
    - delegate: <delegator (string)>
    Dictionary values may be extended with 'condition' key.

  $build$outname[*]
    Provides stem for outname. Key flags will be subtracted from the
    target keys when outname is computed.

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
    - preamble package: <package name>
      options:
        required: [<package options>]
        suggested: [<package options>]
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
    - package: <package name>
      options:
        required: [<package options>]
        suggested: [<package options>]
    - resize font: [<size>, <skip>]
        # best used with anyfontsize package
        # only affects font size at the beginning of document
        # (like, any size command including \normalsize will undo this)
    Non-string values may be extended with conditions.

  $date

  $path:
    Used internally.

"""

# Imports and logging {{{1

from functools import partial
from contextlib import suppress
from collections import OrderedDict
from string import Template
import datetime
import re

from pathlib import PurePosixPath
from unidecode import unidecode

from jeolm.record_path import RecordPath
from jeolm.target import Target
from jeolm.records import MetaRecords

from jeolm.records import RecordNotFoundError
from jeolm.metadata import NAME_PATTERN, FIGURE_REF_PATTERN

from jeolm.utils import check_and_set, ClashingValueError

from . import ( DriverError, folding_driver_errors, checking_target_recursion,
    process_target_aspect, process_target_key,
    processing_target, processing_package_path, processing_figure_path,
    ensure_type_items, )

import logging
logger = logging.getLogger(__name__)


class RegularDriver(MetaRecords): # {{{1

    def __init__(self):
        super().__init__()
        self._cache.update(
            outrecords=dict(), package_records=dict(), figure_records=dict(),
            delegated_targets=dict() )

    ##########
    # Interface methods and attributes {{{2

    class NoDelegators(Exception):
        pass

    class StopDelegation(NoDelegators):
        pass

    @folding_driver_errors
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
                        delegators = list(self._generate_delegators(target))
                    except self.NoDelegators:
                        delegators = None
                else:
                    delegators = list(self._generate_delegated_targets(target))
                self._cache['delegated_targets'][target, recursively] = \
                    delegators
            if delegators is None:
                raise self.NoDelegators
            else:
                yield from delegators

    @folding_driver_errors
    def list_metapaths(self):
        # Caching is not necessary since no use-case involves calling this
        # method several times.
        yield from self._generate_metapaths()

    @folding_driver_errors
    def metapath_is_targetable(self, metapath):
        return self.get(metapath)['$target$able']

    @folding_driver_errors
    def list_targetable_children(self, metapath):
        for name in self.get(metapath):
            if name.startswith('$'):
                continue
            assert '/' not in name
            submetapath = metapath / name
            if self.get(submetapath)['$target$able']:
                yield submetapath

    @folding_driver_errors
    def produce_outrecord(self, target):
        """
        Return outrecord.

        Each outrecord must contain the following fields:
        'outname'
            string
        'type'
            must be 'regular'
        'compiler'
            one of 'latex', 'pdflatex', 'xelatex', 'lualatex'

        'regular' outrecord must also contain fields:
        'sources'
            {alias_name : inpath for each inpath}
            where alias_name is a filename with '.tex' extension, and inpath
            also has '.tex' extension.
        'figures'
            {alias_stem : (figure_path, figure_type) for each figure}
        'document'
            LaTeX document as a string
        'package_paths'
            {alias_name : package_path for each local package}
            (for latexdoc, this is the corresponding package)

        """
        with suppress(KeyError):
            return self._cache['outrecords'][target]
        outrecord = self._cache['outrecords'][target] = \
            self._generate_outrecord(target)
        keys = outrecord.keys()
        if not keys >= {'outname', 'type', 'compiler'}:
            raise RuntimeError(keys)
        if outrecord['type'] not in {'regular'}:
            raise RuntimeError
        if not keys >= {'sources', 'figures', 'document'}:
            raise RuntimeError
        for figure_path, figure_type in outrecord['figures'].values():
            if not isinstance(figure_path, RecordPath):
                raise RuntimeError(type(figure_path))
            if figure_type not in { None,
                    'asy', 'svg', 'eps', 'pdf', 'png', 'jpg'}:
                raise RuntimeError(figure_type)
        if 'package_paths' not in keys:
            raise RuntimeError
        if outrecord['compiler'] not in {
                'latex', 'pdflatex', 'xelatex', 'lualatex' }:
            raise RuntimeError
        return outrecord

    @folding_driver_errors
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

    @folding_driver_errors
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
        'other_sources'
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
            if figure_type not in {'asy', 'svg', 'pdf', 'eps', 'png', 'jpg'}:
                raise RuntimeError(figure_type)
            if figure_record['type'] != figure_type:
                raise RuntimeError
            if figure_record['type'] == 'asy':
                if 'other_sources' not in keys:
                    raise RuntimeError
                if not isinstance(figure_record['other_sources'], dict):
                    raise RuntimeError
        return figure_records

    @folding_driver_errors
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
    # Record extension {{{2

    def _derive_record(self, parent_record, child_record, path):
        super()._derive_record(parent_record, child_record, path)
        child_record.setdefault('$target$able',
            parent_record.get('$target$able', True) )
        child_record.setdefault('$build$able',
            parent_record.get('$build$able', True) )

    def _generate_metapaths(self, path=None):
        """Yield metapaths."""
        if path is None:
            path = RecordPath()
        record = self.get(path)
        if record.get('$target$able', True):
            yield path
        for key in record:
            if key.startswith('$'):
                continue
            assert '/' not in key
            yield from self._generate_metapaths(path=path/key)

    dropped_keys = dict()
    dropped_keys.update(MetaRecords.dropped_keys)
    dropped_keys.update({
        '$manner' : '$build$matter',
        '$rigid'  : '$build$matter',
        '$fluid'  : '$matter',
        '$manner$style'   : '$build$style',
        '$manner$options' : '$build$style',
        '$out$options'    : '$build$style',
        '$fluid$opt'      : '$build$style',
        '$rigid$opt'      : '$build$style',
        '$manner$opt'     : '$build$style',
        '$build$special'  : '$build$style',
        '$build$options'  : '$build$outname',
        '$required$packages' : '$matter: preamble package',
        '$latex$packages'    : '$matter: preamble package',
        '$tex$packages'      : '$matter: preamble package',
        '$target$delegate' : '$delegate',
        '$targetable' : '$target$able',
        '$delegate$stop' : '$delegate',
    })

    ##########
    # Record-level functions (delegate) {{{2

    @checking_target_recursion()
    @processing_target
    def _generate_delegated_targets( self, target, metarecord=None,
        *, _seen_targets=None
    ):
        if metarecord is None:
            metarecord = self.get(target.path)

        try:
            delegators = list(self._generate_delegators(target, metarecord))
        except self.NoDelegators:
            yield target
        else:
            for delegator in delegators:
                yield from self._generate_delegated_targets(
                    delegator, _seen_targets=_seen_targets )

    @processing_target
    def _generate_delegators(self, target, metarecord=None):
        """Yield targets."""
        if metarecord is None:
            metarecord = self.get(target.path)
        if not metarecord.get('$target$able', True):
            raise DriverError( "Target {target} is not targetable"
                .format(target=target) )

        delegate_key, delegators = self.select_flagged_item(
            metarecord, '$delegate', target.flags )
        if delegate_key is None:
            raise self.NoDelegators
        with process_target_key(target, delegate_key):
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
    # Metabody and metapreamble items {{{2

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
        include_command = r'\input'
        file_suffix = '.tex'

        def __init__(self, metapath):
            if not isinstance(metapath, RecordPath):
                raise RuntimeError(metapath)
            self.metapath = metapath
            super().__init__()

        @property
        def inpath(self):
            return self.metapath.as_inpath(suffix=self.file_suffix)

    class ClearPageBodyItem(VerbatimBodyItem):
        __slots__ = []
        _value = r'\clearpage' '\n'

        def __init__(self):
            super().__init__(value=self._value)

    class EmptyPageBodyItem(VerbatimBodyItem):
        __slots__ = []
        _value = r'\strut\clearpage' '\n'

        def __init__(self):
            super().__init__(value=self._value)

    class DocSourceBodyItem(SourceBodyItem):
        __slots__ = []
        include_command = r'\DocInput'
        file_suffix = '.dtx'

    class MetapreambleItem:
        __slots__ = []

        def __init__(self):
            super().__init__()

    class VerbatimPreambleItem(MetapreambleItem):
        __slots__ = ['value']

        def __init__(self, value):
            if value is None:
                self.value = None
            else:
                self.value = str(value)
            super().__init__()

    class CompilerItem(MetapreambleItem):
        __slots__ = ['compiler']

        def __init__(self, compiler):
            self.compiler = str(compiler)
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

    class RequirePreambleBodyItem(ProvidePreamblePreambleItem, ControlBodyItem):
        __slots__ = []

    class ProvidePackagePreambleItem(MetapreambleItem):
        __slots__ = ['package', 'options_required', 'options_suggested']

        def __init__(self, package, options=None):
            self.package = str(package)
            if options is None:
                self.options_required = []
                self.options_suggested = []
            elif isinstance(options, dict):
                options_required = options.get('required', ())
                self.options_required = [str(item) for item in options_required]
                options_suggested = options.get('suggested', ())
                self.options_suggested = [str(item) for item in options_suggested]
            elif isinstance(options, (list, tuple)):
                self.options_required = [str(item) for item in options]
                self.options_suggested = list(self.options_required)
            elif isinstance(options, str):
                self.options_required = [options]
                self.options_suggested = [options]
            else:
                raise DriverError(options)
            if not set(self.options_required).issuperset(self.options_suggested):
                raise DriverError(options)
            super().__init__()

    class RequirePackageBodyItem(ProvidePackagePreambleItem, ControlBodyItem):
        __slots__ = []

    class ProhibitPackagePreambleItem(MetapreambleItem):
        __slots__ = ['package']

        def __init__(self, package):
            self.package = str(package)
            super().__init__()

    class ProhibitPackageBodyItem(ProhibitPackagePreambleItem, ControlBodyItem):
        __slots__ = []

    @classmethod
    def _classify_matter_item(cls, item):
        if not isinstance(item, dict):
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
        elif item.keys() == {'preamble no package'}:
            return cls.ProhibitPackageBodyItem(
                package=item['preamble no package'] )
        elif item.keys() == {'error'}:
            raise DriverError(item['error'])
        else:
            raise DriverError(item)

    @classmethod
    def _classify_style_item(cls, item):
        if not isinstance(item, dict):
            raise RuntimeError(item)
        elif item.keys() & {'verbatim'}:
            return cls._classify_style_verbatim_item(item)
        elif item.keys() & {'package', 'no package'}:
            return cls._classify_style_package_item(item)
        elif item.keys() == {'resize font'}:
            size, skip = item['resize font']
            return cls.ProvidePreamblePreambleItem(
                value=cls.selectfont_template.substitute(
                    size=float(size), skip=float(skip)
                ), key='AtBeginDocument:fontsize' )
        elif item.keys() == {'compiler'}:
            return cls.CompilerItem(
                compiler=item['compiler'] )
        elif item.keys() == {'document class'}:
            return cls.DocumentClassItem(
                document_class=item['document class'] )
        elif item.keys() == {'document class', 'options'}:
            return cls.DocumentClassItem(
                document_class=item['document class'],
                options=item['options'] )
        elif item.keys() == {'error'}:
            raise DriverError(item['error'])
        else:
            raise DriverError(item)

    @classmethod
    def _classify_style_verbatim_item(cls, item):
        if item.keys() == {'verbatim'}:
            return cls.VerbatimPreambleItem(
                value=item['verbatim'] )
        elif item.keys() == {'verbatim', 'provide'}:
            return cls.ProvidePreamblePreambleItem(
                value=item['verbatim'], key=item['provide'] )
        else:
            raise DriverError(item)

    @classmethod
    def _classify_style_package_item(cls, item):
        if item.keys() == {'package'}:
            return cls.ProvidePackagePreambleItem(
                package=item['package'] )
        elif item.keys() == {'package', 'options'}:
            return cls.ProvidePackagePreambleItem(
                package=item['package'], options=item['options'] )
        elif item.keys() == {'no package'}:
            return cls.ProhibitPackagePreambleItem(
                package=item['no package'] )
        else:
            raise DriverError(item)

    ##########
    # Record-level functions (outrecord) {{{2

    @processing_target
    def _generate_outrecord(self, target, metarecord=None):
        if metarecord is None:
            metarecord = self.get(target.path)
        if not metarecord.get('$target$able', True) or \
                not metarecord.get('$build$able', True):
            raise DriverError( "Target {target} is not buildable"
                .format(target=target) )
        if target.path.is_root():
            raise DriverError("Direct building of '/' is prohibited." )

        return self._generate_regular_outrecord(target)

    @processing_target
    def _generate_regular_outrecord(self, target, metarecord=None):
        """
        Return outrecord.
        """
        if metarecord is None:
            metarecord = self.get(target.path)

        date_set = set()

        outrecord = {'type' : 'regular'}

        # We must exhaust _generate_metabody() to fill date_set
        metabody = list(self._generate_metabody(
            target, metarecord, date_set=date_set ))
        metapreamble = list(self._generate_metapreamble(
            target, metarecord ))

        sources = outrecord['sources'] = OrderedDict()
        figures = outrecord['figures'] = OrderedDict()
        package_paths = outrecord['package_paths'] = OrderedDict()
        outrecord.setdefault('date', self._min_date(date_set))
        compilers = list()

        metabody = list(self._digest_metabody(
            target, metabody,
            sources=sources, figures=figures,
            metapreamble=metapreamble ))
        metapreamble = list(self._digest_metapreamble(
            target, metapreamble,
            package_paths=package_paths,
            compilers=compilers ))

        target.check_unutilized_flags()
        target.abandon_children()

        assert 'outname' not in outrecord
        outrecord['outname'] = self._select_outname(
            target, metarecord, date=outrecord['date'] )
        if not compilers:
            raise DriverError("Compiler is not specified")
        if len(compilers) > 1:
            raise DriverError("Compiler is specified multiple times")
        # pylint: disable=unbalanced-tuple-unpacking
        outrecord['compiler'], = compilers
        # pylint: enable=unbalanced-tuple-unpacking

        with process_target_aspect(target, 'document'):
            outrecord['document'] = self._constitute_document(
                outrecord,
                metapreamble=metapreamble, metabody=metabody, )
        return outrecord

    def _select_outname(self, target, metarecord, date=None):
        """Return outname."""
        outname = self._select_outname_stem(target, metarecord)
        if isinstance(date, datetime.date):
            outname = date.isoformat() + '-' + outname
        assert '/' not in outname, repr(outname)
        return outname

    def _select_outname_stem(self, target, metarecord):
        """Return outname, except for date part."""
        outname_key, outname = self.select_flagged_item(
            metarecord, '$build$outname', target.flags )
        if outname_key is None:
            outname = '-'.join(target.path.parts)
            outname_flag_set = target.flags.as_frozenset
        else:
            if not isinstance(outname, str):
                raise DriverError("Outname must be a string.")
            omitted_flag_set = target.flags.split_flags_group(
                self.attribute_key_regex.fullmatch(outname_key).group('flags')
            )
            outname_flag_set = target.flags.as_frozenset - omitted_flag_set
        outname_flags = '{:optional}'.format(target.flags.__class__(
            outname_flag_set ))
        return outname + outname_flags

    @ensure_type_items(MetabodyItem)
    @processing_target
    def _generate_metabody(self, target, metarecord=None,
        *, date_set
    ):
        """
        Yield metabody items.
        Update date_set.
        """
        if metarecord is None:
            metarecord = self.get(target.path)

        matter_key, matter = self.select_flagged_item(
            metarecord, '$build$matter', target.flags )
        yield from self._generate_resolved_metabody( target, metarecord,
            matter_key=matter_key, matter=matter, date_set=date_set )

    # pylint: disable=no-self-use,unused-argument,invalid-name
    def _generate_resolved_metabody_skip_check( self, target, *args,
        matter_key=None, **kwargs
    ):
        return matter_key is not None
    # pylint: enable=no-self-use,unused-argument,invalid-name

    @checking_target_recursion(
        skip_check=_generate_resolved_metabody_skip_check )
    @ensure_type_items(MetabodyItem)
    @processing_target
    def _generate_resolved_metabody( self, target, metarecord=None,
        *, matter_key=None, matter=None, date_set,
        _seen_targets=None
    ):
        """
        Yield metabody items.
        Update date_set.
        """
        if metarecord is None:
            metarecord = self.get(target.path)

        date = self._find_date(target, metarecord)
        if date is not None:
            date_set.add(date)
            date_set = set()

        if 'header' in target.flags:
            date_subset = set()
            # exhaust iterator to find date_subset
            metabody = list(self._generate_resolved_metabody(
                target.flags_delta(
                    difference={'header'},
                    union={'no-header'} ),
                metarecord,
                matter_key=matter_key, matter=matter, date_set=date_subset,
                _seen_targets=_seen_targets ))
            yield from self._generate_header_metabody( target, metarecord,
                date=self._min_date(date_subset) )
            yield from metabody
            date_set.update(date_subset)
            return

        metabody_generator = self._generate_matter_metabody(
            target, metarecord,
            matter_key=matter_key, matter=matter, )
        for item in metabody_generator:
            if isinstance(item, self.MetabodyItem):
                yield item
            elif isinstance(item, Target):
                yield from self._generate_resolved_metabody(
                    item, date_set=date_set, _seen_targets=_seen_targets )
            else:
                raise RuntimeError(type(item))

    del _generate_resolved_metabody_skip_check

    @ensure_type_items(MetabodyItem)
    @processing_target
    def _generate_header_metabody( self, target, metarecord,
        *, date, resetproblem=True
    ):
        yield self.VerbatimBodyItem(
            self.jeolmheader_begin_template.substitute() )
        yield from self._generate_header_def_metabody(
            target, metarecord, date=date )
        yield self.VerbatimBodyItem(
            self.jeolmheader_end_template.substitute() )
        if resetproblem:
            yield self.VerbatimBodyItem(
                self.resetproblem_template.substitute() )

    # pylint: disable=no-self-use,unused-argument
    @ensure_type_items(MetabodyItem)
    def _generate_header_def_metabody(self, target, metarecord, *, date):
        if not target.flags.intersection({'multidate', 'no-date'}):
            if date is not None:
                yield self.VerbatimBodyItem(
                    self._constitute_date_def(date=date) )
    # pylint: enable=no-self-use,unused-argument

    # pylint: disable=no-self-use,unused-argument
    def _find_date(self, target, metarecord):
        return metarecord.get('$date')
    # pylint: enable=no-self-use,unused-argument

    @ensure_type_items((MetabodyItem, Target))
    @processing_target
    def _generate_matter_metabody(self, target, metarecord,
        *, matter_key=None, matter=None
    ):
        if matter_key is None:
            matter_key, matter = self.select_flagged_item(
                metarecord, '$matter', target.flags )
            if matter_key is None:
                yield from self._generate_auto_metabody(target, metarecord)
                return
        with process_target_key(target, matter_key):
            if not isinstance(matter, list):
                raise DriverError(
                    "Matter must be a list, not {}"
                    .format(type(matter).__name__) )
            for item in matter:
                if isinstance(item, list):
                    yield from self._generate_matter_long_item_metabody(
                        target, metarecord,
                        matter_key=matter_key, matter_item=item )
                else:
                    yield from self._generate_matter_item_metabody(
                        target, metarecord,
                        matter_key=matter_key, matter_item=item )

    @ensure_type_items((MetabodyItem, Target))
    def _generate_matter_long_item_metabody(self, target, metarecord,
        *, matter_key, matter_item
    ):
        assert isinstance(matter_item, list)
        if not matter_item:
            yield self.EmptyPageBodyItem()
        else:
            yield self.ClearPageBodyItem()
            for item in matter_item:
                yield from self._generate_matter_item_metabody(
                    target, metarecord,
                    matter_key=matter_key, matter_item=item, )
            yield self.ClearPageBodyItem()

    @ensure_type_items((MetabodyItem, Target))
    def _generate_matter_item_metabody(self, target, metarecord,
        *, matter_key, matter_item
    ):
        derive_target = partial( target.derive_from_string,
            origin='matter {target}, key {key}'
                .format(target=target, key=matter_key)
        )
        assert not isinstance(matter_item, list)
        if isinstance(matter_item, str):
            yield derive_target(matter_item)
            return
        if not isinstance(matter_item, dict):
            raise DriverError(
                "Matter item must be a string or a dictionary, not {}"
                .format(type(matter_item)) )
        matter_item = matter_item.copy()
        condition = matter_item.pop('condition', True)
        if not target.flags.check_condition(condition):
            return
        if matter_item.keys() == {'delegate'}:
            yield derive_target(matter_item['delegate'])
        else:
            yield self._classify_matter_item(matter_item)

    @ensure_type_items((MetabodyItem, Target))
    @processing_target
    def _generate_auto_metabody(self, target, metarecord):
        if not target.flags.intersection(('header', 'no-header')):
            yield target.flags_union({'header'})
            return
        if not metarecord.get('$source$able', False):
            raise DriverError( "Target {target} is not sourceable"
                .format(target=target) )
        yield from self._generate_source_metabody(
            target, metarecord )
        if 'multidate' in target.flags:
            yield from self._generate_source_datestamp_metabody(
                target, metarecord )

    @ensure_type_items((MetabodyItem, Target))
    @processing_target
    def _generate_source_metabody(self, target, metarecord):
        assert metarecord.get('$source$able', False)
        has_source_tex = metarecord.get(
            self._get_source_type_key('tex'), False )
        has_source_dtx = metarecord.get(
            self._get_source_type_key('dtx'), False )
        if has_source_tex:
            yield self.SourceBodyItem(metapath=target.path)
        elif has_source_dtx:
            yield self.DocSourceBodyItem(metapath=target.path)
        else:
            raise RuntimeError
        if has_source_tex and has_source_dtx:
            logger.warning(
                "File <MAGENTA>%(dtx_path)s<NOCOLOUR> is shadowed by "
                "<MAGENTA>%(tex_path)s<NOCOLOUR>",
                dict(
                    dtx_path=target.path.as_inpath(suffix='.dtx'),
                    tex_path=target.path.as_inpath(suffix='.tex') )
            )

    @staticmethod
    def _get_source_type_key(source_type):
        return '$source$type${}'.format(source_type)

    @ensure_type_items(MetabodyItem)
    @processing_target
    def _generate_source_datestamp_metabody(self, target, metarecord):
        if 'no-date' in target.flags:
            return
        date = self._find_date(target, metarecord)
        if date is None:
            return
        yield self.VerbatimBodyItem(
            self.datestamp_template.substitute(
                date=self._constitute_date(date) )
        )

    @ensure_type_items(MetapreambleItem)
    @processing_target
    def _generate_metapreamble(self, target, metarecord=None):
        if metarecord is None:
            metarecord = self.get(target.path)

        style_key, style = self.select_flagged_item(
            metarecord, '$build$style', target.flags )
        yield from self._generate_resolved_metapreamble(
            target, metarecord,
            style_key=style_key, style=style )

    # pylint: disable=no-self-use,unused-argument,invalid-name
    def _generate_resolved_metapreamble_skip_check( self, target, *args,
        style_key=None, **kwargs
    ):
        return style_key is not None
    # pylint: enable=no-self-use,unused-argument,invalid-name

    @checking_target_recursion(
        skip_check=_generate_resolved_metapreamble_skip_check )
    @ensure_type_items(MetapreambleItem)
    @processing_target
    def _generate_resolved_metapreamble(self, target, metarecord=None,
        *, style_key=None, style=None,
        _seen_targets=None
    ):
        if metarecord is None:
            metarecord = self.get(target.path)

        metapreamble_generator = self._generate_style_metapreamble(
            target, metarecord,
            style_key=style_key, style=style, )
        for item in metapreamble_generator:
            if isinstance(item, self.MetapreambleItem):
                yield item
            elif isinstance(item, Target):
                yield from self._generate_resolved_metapreamble(
                    item, _seen_targets=_seen_targets )
            else:
                raise RuntimeError(type(item))

    del _generate_resolved_metapreamble_skip_check

    @ensure_type_items((MetapreambleItem, Target))
    @processing_target
    def _generate_style_metapreamble(self, target, metarecord,
        *, style_key=None, style=None
    ):
        if style is None:
            style_key, style = self.select_flagged_item(
                metarecord, '$style', target.flags )
            if style is None:
                yield from self._generate_auto_metapreamble(target, metarecord)
                return
        with process_target_key(target, style_key):
            if not isinstance(style, list):
                raise DriverError(type(style))
            for item in style:
                yield from self._generate_style_item_metapreamble(
                    target, metarecord,
                    style_key=style_key, style_item=item )

    @ensure_type_items((MetapreambleItem, Target))
    def _generate_style_item_metapreamble(self, target, metarecord,
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
            yield self._classify_style_item(style_item)

    @ensure_type_items((MetapreambleItem, Target))
    @processing_target
    def _generate_auto_metapreamble(self, target, metarecord):
        if target.path.is_root():
            raise DriverError("Missing toplevel $style")
        if '$package$able' in metarecord:
            for package_type in self._package_types:
                package_type_key = self._get_package_type_key(package_type)
                if metarecord.get(package_type_key, False):
                    break
            else:
                raise DriverError("Failed to determine package type")
            # pylint: disable=undefined-loop-variable
            yield self.LocalPackagePreambleItem(
                package_path=target.path,
                package_type=package_type )
            # pylint: enable=undefined-loop-variable
        else:
            yield target.path_derive('..')

    def _digest_metabody(self, target, metabody,
        *, sources, figures, metapreamble
    ):
        """
        Yield metabody items. Extend sources, figures, metapreamble.
        """
        page_cleared = True
        for item in metabody:
            assert isinstance(item, self.MetabodyItem), type(item)
            if isinstance(item, self.ClearPageBodyItem):
                if not page_cleared:
                    yield item
                    page_cleared = True
            elif isinstance(item, self.EmptyPageBodyItem):
                if not page_cleared:
                    yield self.ClearPageBodyItem()
                    page_cleared = True
                yield item
            elif isinstance(item, self.VerbatimBodyItem):
                yield item
                page_cleared = False
            elif isinstance(item, self.SourceBodyItem):
                yield from self._digest_metabody_source_item( target, item,
                    sources=sources, figures=figures,
                    metapreamble=metapreamble )
                page_cleared = False
            elif isinstance(item, self.RequirePreambleBodyItem):
                metapreamble.append(self.ProvidePreamblePreambleItem(
                    key=item.key, value=item.value ))
            elif isinstance(item, self.RequirePackageBodyItem):
                metapreamble.append(self.ProvidePackagePreambleItem(
                    package=item.package, options={
                        'required' : item.options_required,
                        'suggested' : item.options_suggested }
                ))
            elif isinstance(item, self.ProhibitPackageBodyItem):
                metapreamble.append(self.ProhibitPackagePreambleItem(
                    package=item.package ))
            elif isinstance(item, self.ControlBodyItem):
                # should be handled by superclass
                yield item
            else:
                raise RuntimeError(type(item))

    def _digest_metabody_source_item(self, target, item,
        *, sources, figures, metapreamble
    ):
        """
        Yield metabody items. Extend sources, figures.
        """
        assert isinstance(item, self.SourceBodyItem)
        metarecord = self.get(item.metapath)
        if not metarecord.get('$source$able', False):
            raise RuntimeError( "Path {path} is not sourceable"
                .format(path=item.metapath) )
        item.alias = self._select_alias( item.inpath, suffix=item.file_suffix,
            ascii_only=True )
        self._check_and_set(sources, item.alias, item.inpath)
        item.figure_map = OrderedDict()
        figure_refs = metarecord.get('$source$figures', ())
        for figure_ref in figure_refs:
            match = self._figure_ref_regex.fullmatch(figure_ref)
            if match is None:
                raise RuntimeError(figure_ref)
            figure = match.group('figure')
            figure_type = match.group('figure_type')
            figure_path = RecordPath(item.metapath, figure)
            figure_alias_stem = self._select_alias( figure_path.as_inpath(),
                ascii_only=True )
            with process_target_aspect(item.metapath, 'figure_map'):
                self._check_and_set( item.figure_map,
                    figure_ref, figure_alias_stem )
            with process_target_aspect(target, 'figures'):
                self._check_and_set( figures,
                    figure_alias_stem, (figure_path, figure_type) )
        yield item

    _figure_ref_regex = re.compile(FIGURE_REF_PATTERN)

    def _digest_metapreamble(self, target, metapreamble,
        *, package_paths, compilers
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
                metarecord = self.get(package_path)
                package_name_key = self._get_package_name_key(package_type)
                try:
                    package_name = item.package_name = \
                        metarecord[package_name_key]
                except KeyError as error:
                    raise DriverError( "Package {} of type {} name not found"
                        .format(package_path, package_type) ) from error
                self._check_and_set(package_paths, package_name, package_path)
                yield item
            elif isinstance(item, self.CompilerItem):
                compilers.append(item.compiler)
            else:
                yield item


    ##########
    # Record-level functions (package_record) {{{2

    @processing_package_path
    def _generate_package_records(self, package_path):
        try:
            metarecord = self.get(package_path)
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
    # Record-level functions (figure_record) {{{2

    @processing_figure_path
    def _generate_figure_records(self, figure_path):
        try:
            metarecord = self.get(figure_path)
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
                figure_record['other_sources'] = \
                    self._find_figure_asy_other_sources(
                        figure_path, metarecord )
                assert isinstance(figure_record['other_sources'], dict)
            yield figure_type, figure_record

    _figure_types = ('asy', 'svg', 'pdf', 'eps', 'png', 'jpg',)

    @staticmethod
    def _get_figure_type_key(figure_type):
        return '$figure$type${}'.format(figure_type)

    @staticmethod
    def _get_figure_suffix(figure_type):
        return '.{}'.format(figure_type)

    @processing_figure_path
    def _find_figure_asy_other_sources(self, figure_path, metarecord):
        other_sources = dict()
        for accessed_name, inpath in (
            self._trace_figure_asy_other_sources(figure_path, metarecord)
        ):
            self._check_and_set(other_sources, accessed_name, inpath)
        return other_sources

    @processing_figure_path
    def _trace_figure_asy_other_sources(self, figure_path, metarecord=None,
        *, _seen_items=None
    ):
        """Yield (accessed_name, inpath) pairs."""
        if _seen_items is None:
            _seen_items = set()
        if metarecord is None:
            metarecord = self.get(figure_path)
        accessed_paths = metarecord.get('$figure$asy$accessed', {})
        for accessed_name, accessed_path_s in accessed_paths.items():
            accessed_path = RecordPath(figure_path, accessed_path_s)
            accessed_item = (accessed_name, accessed_path)
            if accessed_item in _seen_items:
                continue
            else:
                _seen_items.add(accessed_item)
            inpath = accessed_path.as_inpath(suffix='.asy')
            yield accessed_name, inpath
            yield from self._trace_figure_asy_other_sources(
                accessed_path, _seen_items=_seen_items )


    ##########
    # LaTeX-level functions {{{2

    @classmethod
    def _constitute_document(cls, outrecord, metapreamble, metabody):
        return cls.document_template.substitute(
            compiler=outrecord['compiler'],
            preamble=cls._constitute_preamble(outrecord, metapreamble),
            body=cls._constitute_body(outrecord, metabody)
        )

    document_template = Template(
        r'% Auto-generated by jeolm for compiling with $compiler' '\n\n'
        r'$preamble' '\n\n'
        r'\begin{document}' '\n\n'
        r'$body' '\n\n'
        r'\end{document}' '\n'
    )

    @classmethod
    def _constitute_preamble(cls, outrecord, metapreamble):
        assert isinstance(outrecord, dict)
        preamble_lines = [None] # first line is always documentclass
        provided_preamble = {}
        provided_packages = {}
        for item in metapreamble:
            if isinstance(item, cls.DocumentClassItem):
                if preamble_lines[0] is not None:
                    raise DriverError(
                        "Document class is specified multiple times" )
                preamble_lines[0] = cls.documentclass_template.substitute(
                    document_class=item.document_class,
                    options=cls._constitute_options(item.options) )
                continue
            if isinstance(item, cls.ProvidePreamblePreambleItem):
                if not cls._check_and_set( provided_preamble,
                        item.key, item.value ):
                    continue
            elif isinstance(item, cls.ProvidePackagePreambleItem):
                if item.package not in provided_packages:
                    provided_packages[item.package] = item.options_suggested
                else:
                    provided_options = provided_packages[item.package]
                    if provided_options is None:
                        raise DriverError(
                            "Package {} was prohibited, cannot provide it"
                            .format(item.package) )
                    elif not set(provided_options).issuperset(item.options_required):
                        raise DriverError(
                            "Package {} was already provided with options {}, "
                            "incompatible with options {}"
                            .format(
                                item.package,
                                cls._constitute_options(provided_options),
                                cls._constitute_options(item.options_required) )
                        )
                    continue
            elif isinstance(item, cls.ProhibitPackagePreambleItem):
                if item.package not in provided_packages:
                    provided_packages[item.package] = None
                else:
                    provided_options = provided_packages[item.package]
                    if provided_options is not None:
                        raise DriverError(
                            "Package {} was provided, cannot prohibit it"
                            .format(item.package) )
                    continue
            preamble_line = cls._constitute_preamble_item(item)
            if preamble_line is None:
                continue
            preamble_lines.append(preamble_line)
        if preamble_lines[0] is None:
            raise DriverError(
                "Document class is not specified")
        return '\n'.join(preamble_lines)

    documentclass_template = Template(
        r'\documentclass$options{$document_class}' )

    @classmethod
    def _constitute_preamble_item(cls, item):
        assert isinstance(item, cls.MetapreambleItem), type(item)
        if isinstance(item, cls.VerbatimPreambleItem):
            return item.value
        elif isinstance(item, cls.LocalPackagePreambleItem):
            return cls.uselocalpackage_template.substitute(
                package=item.package_name,
                package_path=item.package_path )
        elif isinstance(item, cls.ProvidePackagePreambleItem):
            return cls.usepackage_template.substitute(
                package=item.package,
                options=cls._constitute_options(item.options_suggested) )
        elif isinstance(item, cls.ProhibitPackagePreambleItem):
            return None
        else:
            raise RuntimeError(type(item))

    uselocalpackage_template = Template(
        r'\usepackage{$package}% $package_path' )

    @classmethod
    def _constitute_options(cls, options):
        if not options:
            return ''
        if not isinstance(options, str):
            options = ','.join(options)
        return '[' + options + ']'

    @classmethod
    def _constitute_body(cls, outrecord, metabody):
        assert isinstance(outrecord, dict)
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
                include_command=item.include_command,
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
    def _constitute_body_input( cls,
        *, include_command, alias, figure_map, metapath, inpath
    ):
        body = cls.input_template.substitute(
            command=include_command, filename=alias,
            metapath=metapath, inpath=inpath )
        if figure_map:
            body = cls._constitute_figure_map(figure_map) + '\n' + body
        return body

    input_template = Template(
        r'$command{$filename}% $metapath' )

    @classmethod
    def _constitute_figure_map(cls, figure_map):
        assert isinstance(figure_map, OrderedDict), type(figure_map)
        return '\n'.join(
            cls.jeolmfiguremap_template.substitute(
                ref=figure_ref, alias=figure_alias )
            for figure_ref, figure_alias in figure_map.items() )

    jeolmfiguremap_template = Template(
        r'\jeolmfiguremap{$ref}{$alias}%' )

    @classmethod
    def _constitute_date_def(cls, date):
        if date is None:
            raise RuntimeError
        date = cls._constitute_date(date)
        if '%' in date:
            raise DriverError(
                "'%' symbol is found in the date: {}"
                .format(date) )
        return cls.date_def_template.substitute(date=date)

    date_def_template = Template(
        r'\def\jeolmdate{$date}%' )

    @classmethod
    def _constitute_date(cls, date):
        if not isinstance(date, datetime.date):
            return str(date)
        return cls.date_template.substitute(
            year=date.year,
            month=cls.ru_monthes[date.month-1],
            day=date.day )

    date_template = Template(
        r'$day~$month~$year\,г.' )
    ru_monthes = [
        'января', 'февраля', 'марта', 'апреля',
        'мая', 'июня', 'июля', 'августа',
        'сентября', 'октября', 'ноября', 'декабря' ]

    selectfont_template = Template(
        r'\AtBeginDocument{\fontsize{$size}{$skip}\selectfont}' )
    usepackage_template = Template(
        r'\usepackage$options{$package}' )
    resetproblem_template = Template(
        r'\resetproblem' )
    jeolmheader_begin_template = Template(
        r'\begingroup % \jeolmheader' )
    jeolmheader_end_template = Template(
        r'\jeolmheader \endgroup' )
    datestamp_template = Template(
        r'\begin{flushright}\small' '\n'
        r'    $date' '\n'
        r'\end{flushright}%'
    )

    ##########
    # Supplementary finctions {{{2

    @classmethod
    def _select_alias(cls, *parts, suffix=None, ascii_only=False):
        path = PurePosixPath(*parts)
        assert len(path.suffixes) <= 1, path
        if suffix is not None:
            path = path.with_suffix(suffix)
        assert not path.is_absolute(), path
        alias = '-'.join(path.parts)
        if ascii_only and not cls._ascii_file_name_pattern.fullmatch(alias):
            alias = unidecode(alias).replace("'", "")
            assert cls._ascii_file_name_pattern.fullmatch(alias), alias
        else:
            assert cls._file_name_pattern.fullmatch(alias), alias
        return alias

    _ascii_file_name_pattern = re.compile(
        '(?:' + NAME_PATTERN + ')' + r'(?:\.\w+)?', re.ASCII)
    _file_name_pattern = re.compile(
        '(?:' + NAME_PATTERN + ')' + r'(?:\.\w+)?' )

    @staticmethod
    def _min_date(date_set):
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
    def _check_and_set(mapping, key, value):
        """
        Set mapping[key] to value if key is not in mapping.

        Return True if key is not present in mapping.
        Return False if key is present and values was the same.
        Raise DriverError if key is present, but value is different.
        """
        try:
            return check_and_set(mapping, key, value)
        except ClashingValueError as error:
            raise DriverError("unable to set different value") from error

# }}}1
# vim: set foldmethod=marker :
