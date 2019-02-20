# Documentation {{{1
r"""
Record keys recognized by the driver:
* $delegate$able:
    - boolean;
    - indicates that the target may be used as document target;
    - if false then raise error on delegate and document_recipe stages;
    - affects $delegate$child.
    * default:
        - inherited from parent;
        - otherwise true;
* $content$able:
    - boolean;
    - if false then raise error on content stage;
    - affects $content$child.
    * default:
        - inherited from parent;
        - otherwise true;

* $source$able:
    - boolean;
    - indicates that the path corresponds to a source file;
    - affects $delegate$auto and $content$auto behavior;
    - if not true then raise error on source stage.
    * set to true by metadata grabber on .tex and .dtx files.
* $source$type$tex, $source$type$dtx:
    - boolean;
    * set to true by metadata grabber on respectively
      .tex and .dtx files.
* $source$figures:
    - a list of items:
        - [<figure_ref (string)>, <figure_option_string>]
    * set by metadata grabber on .tex files.

* $figure$able:
    - boolean;
    - indicates that the path corresponds to a figure file;
    - if not true then raise error on figure_recipe stage.
    * set to true by metadata grabber on
      .asy, .svg, .pdf, .eps, .png and .jpg files
* $figure$type$asy, $figure$type$svg, $figure$type$pdf,
  $figure$type$eps, $figure$type$png, $figure$type$jpg:
    - boolean;
    * set to true by metadata grabber on respectively
      .asy, .svg, .pdf, .eps, .png and .jpg files.
* $figure$asy$accessed
    - a dictionary:
        <alias_name (string)> : <accessed_path (string)>
    * set by metadata grabber on .asy files.

* $package$able:
    - boolean;
    - indicates that the path corresponds to a package file;
    - if not true then raise error on package_recipe stage.
    * set to true by metadata grabber on .dtx and .sty files.
* $package$type$dtx, $package$type$sty:
    - boolean;
    * set to true by metadata grabber on respectively
      .dtx and .sty files
* $package$dtx$name, $package$sty$name
    - string;
    - indicates the package name; this is the filename the package is
      supposed to be symlinked with during the build process.
    * set by metadata grabber on .sty or .dtx files.

* $delegate[*]
    - either boolean false (implying no delegation),
    - or a list of items:
        - <delegator (string)>
        - delegate:
            - a list of items, same as in $delegate;
            - nested delegate items are not allowed.
        - children: null
          exclude: [<name (string)>, …] (optional)
        - error: <string>
            * raises error
        * dictionary items may also contain 'condition' key.
* $delegate$child:
    - boolean or condition;
    - if false then disable including this name in the list of children
      of its parent.
    * default:
        - false if $delegate$able is false;
        - otherwise true.
        * (Not inheritable.)
* key $delegate$auto:
    - boolean or condition;
    - if true then imply
        - (unless applicable $delegate key is found)
        - if $source$able is not true
            $delegate: [{children: {}}]
        - otherwise nothing.
    * default is:
        - inherited from parent;
        - otherwise false.

* $document$outname[*]:
    - string;
    - provides stem for outname;
    * key flags will be subtracted from the target flags when outname
      is computed;
    * outname may contain its own flags, which will be placed before
      remaining target flags (after subtraction).
* $document$flags[*]
    - a list of additional flags for the target
* $document$content[*]
    - a list of items, same as $content;
    - will be used as initial content for document.
* $document$style[*]
    - a list of items, same as $style;
    - will be used as initial style for document.

* $content[*]
    - a list of items:
        - <delegator (string)>
        - content:
            * a list of items, same as in $content;
            * nested content items are prohibited.
          header:
            * a dict or false, optional.
            date: <Date>
              * may be null to remove date from the header;
              * default is the minimal date of the items in content.
            caption: <string>
              * only affects toc;
              * may be null to disable toc line;
              * default is the captions of the content items,
                joined by "; ".
            authors: [<author_item>, …]
              * may be null to remove authors from the header;
              * items are same as in $authors;
              * abbreviation strategy is applied;
              * default is the union of authors of the items
                in content.
            * if header is present, content items are granted
              'contained' flag that blocks them from generating headers
              of their own by default.
            * header may also be false, which still grants 'contained'
              flag to content items, but generates no header.
          newpage:
            * boolean, optional;
            * if true, generates \clearpage around content;
            * if true and content is empty, empty page is generated;
            * default is true.
        - children: null
          exclude: [<name (string)>, …]
            * exclude is optional, deafult is [].
          order: 'record' or 'date'
            * order is optional, defaults to $content$order.
        - verbatim: <string>
        - source: <delegator (string)>
            * if the delegator appears to be not $source$able, this
              will cause an error
        - figure: <delegator (string)>
            * if the delegator appears to be not $figure$able, this
              will cause an error
          options: [<option (string)>, …] (optional)
            * \jeolmfigure options, like width etc.
        - error: <string>
            * raises error
        - style:
            * a list of items, same as in $style;
              * targets, 'style', 'compiler' and 'package'+'source'
                items are not allowed;
            * appended to the end of the preamble
        * dictionary items may also contain 'condition' key.
* $content$order
    - either 'record' or 'date'
    - defines default order of children items in $content.
    * default:
        - inherited from parent;
        - otherwise 'record'.
* $content$child:
    - boolean or condition;
    - if false then disable including this name in the list of children
      of its parent.
    * default:
        - false if $content$able is false;
        - otherwise true.
        * (Not inheritable.)
* $content$auto
    - boolean or condition;
    - if true then imply
        - (unless applicable $content key is found)
        - if $source$able is not true
            $content: [{children: {}}]
        - if $source$able is true and target has no 'contained' flag
            $content: [{header: {}, content: [.]}]
        - if $source$able is true and target has 'contained' flag
            $content: [{source: .}]
    * default is:
        - inherited from parent;
        - otherwise false.

* $style[*]:
    - a list of items:
        - <delegator (string)>
        - style:
            * a list of items, same as in $style;
            * nested style items are prohibited.
        - compiler: <string>
        - verbatim: <string>
        - verbatim: <string> or null
          provide: <key (string)>
        - package: <package_name>
          options:
            required: [<package_option>, …]
            suggested: [<package_option>, …]
            prohibited: [<package_option>, …]
            * options is optional
            * options may also be just a list, in which case
              required and suggested will default to it
            * otherwise required defaults to [];
            * suggested defaults to required;
            * prohibited defaults to [];
            * the ultimate set of options, after all package items are
              recollected, is union(suggested) - union(prohibited).
              If it is not a subset of union(required), an error is raised.
        - package: <package_name>
          prohibited: true
          * such package must not be included.
        - package-source: <delegator (string)>
          * if delegator appears to be not $package$able, this
            will cause an error.
        - error: <string>
            * raises error
        * dictionary items may also contain 'condition' key.
- $style$auto
    - boolean or condition;
    - if true then imply
        - (unless applicable $style key is found)
        - if $package$able is not true
            $content: [{style: ..}]
        - if $package$able is true
            $content: [{source_package: .}]
    * default is:
        - inherited from parent;
        - otherwise true.

* $date:
    - datetime.date or jeolm.utils.Date instance
* $authors:
    - a list of items:
        - <name (string)>
        - name: <name (string)>
        - name: <name (string)>
          abbr: <abbreviation (string)>
    * unless abbr is specified, abbreviation strategy will be applied
* $caption:
    - string.

* $path:
    * used internally.

"""

# Imports and logging {{{1

from functools import partial
from contextlib import suppress
from collections import OrderedDict
from string import Template
import re
from pathlib import PurePosixPath

from jeolm.records import RecordPath, RecordNotFoundError
from jeolm.target import Target, OUTNAME_PATTERN
from jeolm.metadata import NAME_PATTERN, FIGURE_REF_PATTERN

from jeolm.date import Date, Never
from jeolm.utils.check_and_set import check_and_set, ClashingValueError
from jeolm.utils.unique import unique

from . import ( DriverRecords, DocumentTemplate,
    DriverError, folding_driver_errors, checking_target_recursion,
    process_target_aspect, process_target_key,
    processing_target, processing_package_path, processing_figure_path,
    ensure_type_items,
)

import logging
logger = logging.getLogger(__name__)


class RegularDriver(DriverRecords): # {{{1

    def __init__(self):
        super().__init__()
        self._cache.update(
            document_recipes=dict(),
            package_recipes=dict(), figure_recipes=dict(),
            delegated_targets=dict() )


    ##########
    # Interface methods and attributes {{{2

    class NoDelegators(Exception):
        pass

    @folding_driver_errors
    def list_delegated_targets(self, *targets):
        for target in targets:
            try:
                delegated_targets = self._cache['delegated_targets'][target]
            except KeyError:
                delegated_targets = list(self._generate_targets(target))
                self._cache['delegated_targets'][target] = delegated_targets
            yield from delegated_targets

    @folding_driver_errors
    def list_targetable_paths(self):
        # Caching is not necessary since no use-case involves calling this
        # method several times.
        yield from self._generate_targetable_paths()

    @folding_driver_errors
    def path_is_targetable(self, record_path):
        return self.get(record_path)['$delegate$able']

    @folding_driver_errors
    def list_targetable_children(self, record_path):
        for name in self.get(record_path):
            if name.startswith('$'):
                continue
            assert '/' not in name
            child_path = record_path / name
            if self.get(child_path)['$delegate$able']:
                yield child_path

    @folding_driver_errors
    def produce_document_recipe(self, target):
        """
        Return document recipe.

        Recipe must contain the following fields:
        'outname'
            string
        'type'
            must be 'regular'
        'compiler'
            one of 'latex', 'pdflatex', 'xelatex', 'lualatex'

        'regular' recipe must also contain field:
        'document'
            LaTeX document as a driver.DocumentTemplate
            keys should include
            ('source', source_path) for each source,
            ('package', package_path) for each package,
            ('figure', figure_path, figure_index)
                for each figure.
        'asy_latex_compiler'
            one of 'latex', 'pdflatex', 'xelatex', 'lualatex'
        'asy_latex_preamble'
            a string
        """
        # XXX will also provide asy_preamble
        # (a version of preamble for asymptote figures)
        with suppress(KeyError):
            return self._cache['document_recipes'][target]
        document_recipe = self._cache['document_recipes'][target] = \
            self._generate_document_recipe(target)
        if not document_recipe.keys() >= {'outname', 'type', 'compiler'}:
            raise RuntimeError
        if '/' in document_recipe['outname']:
            raise RuntimeError
        if document_recipe['type'] not in {'regular'}:
            raise RuntimeError
        if document_recipe['compiler'] not in {
                'latex', 'pdflatex', 'xelatex', 'lualatex' }:
            raise RuntimeError
        if not document_recipe.keys() >= {'document'}:
            raise RuntimeError
        for key in document_recipe['document'].keys():
            if not isinstance(key, tuple):
                raise RuntimeError
            key_type, *key_value = key
            if key_type == 'source':
                source_path, = key_value
                if not isinstance(source_path, PurePosixPath):
                    raise RuntimeError
            elif key_type in {'figure', 'figure-size'}:
                figure_path, figure_index, = key_value
                if not isinstance(figure_path, RecordPath):
                    raise RuntimeError
                if not isinstance(figure_index, int):
                    raise RuntimeError
            elif key_type == 'package':
                package_path, = key_value
                if not isinstance(package_path, RecordPath):
                    raise RuntimeError
            else:
                raise RuntimeError
        return document_recipe

    @folding_driver_errors
    def produce_package_recipe(self, package_path):
        """
        Return package recipe.

        Recipe must contain the following fields:
        'source_type'
            one of 'dtx', 'sty'
        'source'
            source_path
        'name'
            package name, as in ProvidesPackage.
        """
        assert isinstance(package_path, RecordPath), type(package_path)
        with suppress(KeyError):
            return self._cache['package_recipes'][package_path]
        package_recipe = self._cache['package_recipes'][package_path] = \
            self._generate_package_recipe(package_path)
        # QA
        if not package_recipe.keys() >= {'source_type', 'source', 'name'}:
            raise RuntimeError
        if package_recipe['source_type'] not in {'dtx', 'sty'}:
            raise RuntimeError
        if not isinstance(package_recipe['source'], PurePosixPath):
            raise RuntimeError
        if not isinstance(package_recipe['name'], str):
            raise RuntimeError
        return package_recipe

    @folding_driver_errors
    def produce_figure_recipe( self, figure_path,
        figure_formats=frozenset(('pdf', 'png', 'jpg'))
    ):
        """
        Return figure recipe.

        Recipe must contain the following fields:
        'format'
            one of 'pdf', 'eps', 'png', 'jpg'
        'source_type'
            one of 'asy', 'svg', 'pdf', 'eps', 'png', 'jpg'
        'source'
            source_path

        In case of Asymptote file ('asy' source type), figure_record must
        also contain:
        'other_sources'
            {accessed_name : source_path for each accessed source_path}
            where accessed_name is a filename with '.asy' extension,
            and source_path has '.asy' extension
        """
        assert isinstance(figure_path, RecordPath), type(figure_path)
        if not isinstance(figure_formats, frozenset):
            figure_formats = frozenset(figure_formats)
        with suppress(KeyError):
            return self._cache['figure_recipes'][figure_path, figure_formats]
        figure_recipe = \
            self._cache['figure_recipes'][figure_path, figure_formats] = \
            self._generate_figure_recipe(figure_path, figure_formats)
        # QA
        if not figure_recipe.keys() >= {'format', 'source_type', 'source'}:
            raise RuntimeError
        if figure_recipe['format'] not in {'pdf', 'eps', 'png', 'jpg'}:
            raise RuntimeError
        if figure_recipe['format'] not in figure_formats:
            raise RuntimeError
        if figure_recipe['source_type'] not in \
                {'asy', 'svg', 'pdf', 'eps', 'png', 'jpg'}:
            raise RuntimeError
        if figure_recipe['source_type'] == 'asy':
            if 'other_sources' not in figure_recipe:
                raise RuntimeError
            other_sources = figure_recipe['other_sources']
            if not isinstance(other_sources, dict):
                raise RuntimeError
            for accessed_name, accessed_path in other_sources.items():
                if not isinstance(accessed_name, str):
                    raise RuntimeError
                if not isinstance(accessed_path, RecordPath):
                    raise RuntimeError
        return figure_recipe

#    # XXX this belongs to node_factory
#    # Driver has not much to do with inpaths
#    @folding_driver_errors
#    def list_inpaths(self, *targets, inpath_type='tex'):
#        if inpath_type not in {'tex', 'asy'}:
#            raise RuntimeError(inpath_type)
#        for target in targets:
#            outrecord = self.produce_outrecord(target)
#            if outrecord['type'] not in {'regular'}:
#                raise DriverError(
#                    "Can only list inpaths for regular documents: {target}"
#                    .format(target=target) )
#            if inpath_type == 'tex':
#                for inpath in outrecord['sources'].values():
#                    if inpath.suffix == '.tex':
#                        yield inpath
#            elif inpath_type == 'asy':
#                yield from self._list_inpaths_asy(target, outrecord)
#
#    # XXX this belongs to node_factory
#    def _list_inpaths_asy(self, target, outrecord):
#        for figure_path, figure_type in outrecord['figures'].values():
#            if figure_type != 'asy':
#                continue
#            for figure_record in self.produce_figure_records(figure_path):
#                if figure_record['type'] != 'asy':
#                    continue
#                yield figure_record['source']
#                break
#            else:
#                raise DriverError(
#                    "No 'asy' type figure found for {path} in {target}"
#                    .format(path=figure_path, target=target) )


    ##########
    # Record extension {{{2

    def _derive_record(self, parent_record, child_record, path):
        super()._derive_record(parent_record, child_record, path)

        child_record.setdefault( '$delegate$able',
            parent_record.get('$delegate$able', True) )
        child_record.setdefault( '$delegate$child',
            child_record.get('$delegate$able') )
        child_record.setdefault( '$delegate$auto',
            parent_record.get('$delegate$auto', False) )

        child_record.setdefault( '$content$able',
            parent_record.get('$content$able', True) )
        child_record.setdefault( '$content$child',
            child_record.get('$content$able') )
        child_record.setdefault( '$content$auto',
            parent_record.get('$content$auto', False) )
        child_record.setdefault( '$content$order',
            parent_record.get('$content$order', 'record') )

        child_record.setdefault('$style$auto',
            parent_record.get('$style$auto', True) )

    def _generate_targetable_paths(self, path=None):
        """Yield targetable paths."""
        if path is None:
            path = RecordPath()
        record = self.get(path)
        if record.get('$delegate$able', True):
            yield path
        for key in record:
            if key.startswith('$'):
                continue
            assert '/' not in key
            yield from self._generate_targetable_paths(path=path/key)

    dropped_keys = dict()
    dropped_keys.update(DriverRecords.dropped_keys)
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
        # XXX
    })


    ##########
    # Record-level functions (delegate) {{{2

    @checking_target_recursion()
    @ensure_type_items(Target)
    @processing_target
    def _generate_targets( self, target, record=None,
        *, _seen_targets=None
    ):
        if record is None:
            record = self.get(target.path)
        if not record.get('$delegate$able', True):
            raise DriverError( f"Target {target} is not targetable" )
        delegate_key, delegate = self.select_flagged_item(
            record, '$delegate', target.flags )
        if delegate_key is None:
            yield from self._generate_targets_auto( target, record,
                _seen_targets=_seen_targets )
            return
        yield from self._generate_targets_delegate( target, record,
            delegate_key=delegate_key, delegate=delegate,
            _seen_targets=_seen_targets )

    @ensure_type_items(Target)
    @processing_target
    def _generate_targets_delegate( self, target, record,
        *, delegate_key, delegate, _recursed=False,
        _seen_targets,
    ):
        with process_target_key(target, delegate_key):
            if not isinstance(delegate, list):
                raise DriverError(
                     "$delegate must be a list, "
                    f"not {type(delegate)}" )
            for item in delegate:
                yield from self._generate_targets_delegate_item(
                    target, record,
                    delegate_key=delegate_key, delegate_item=item,
                    _recursed=_recursed,
                    _seen_targets=_seen_targets )

    @ensure_type_items(Target)
    def _generate_targets_delegate_item( self, target, record,
        *, delegate_key, delegate_item, _recursed,
        _seen_targets,
    ):
        if isinstance(delegate_item, str):
            yield from self._generate_targets(
                target.derive_from_string( delegate_item,
                    origin=f'delegate {target}, key {delegate_key}' ),
                _seen_targets=_seen_targets )
            return
        if not isinstance(delegate_item, dict):
            raise DriverError( "Element of $delegate must be a dictionary, "
               f"not {type(delegate_item)}" )
        delegate_item = delegate_item.copy()
        condition = delegate_item.pop('condition', True)
        if not target.flags.check_condition(condition):
            return
        if 'delegate' in delegate_item.keys():
            if delegate_item.keys() != {'delegate'}:
                raise DriverError(delegate_item.keys())
            if _recursed:
                raise DriverError("Nested 'delegate' items are not allowed.")
            yield from self._generate_targets_delegate( target, record,
                delegate_key=delegate_key+"/delegate",
                delegate=delegate_item,
                _recursed=True,
                _seen_targets=_seen_targets )
        elif 'children' in delegate_item.keys():
            yield from self._generate_targets_delegate_children(
                target, record, delegate_item=delegate_item,
                _seen_targets=_seen_targets )
        elif 'error' in delegate_item.keys():
            if delegate_item.keys() == {'error'}:
                raise DriverError(delegate_item['error'])
            else:
                raise DriverError(delegate_item.keys())
        else:
            raise DriverError(delegate_item)

    @ensure_type_items(Target)
    def _generate_targets_delegate_children( self, target, record,
        *, delegate_item,
        _seen_targets,
    ):
        if not delegate_item.keys() <= {'children', 'exclude'}:
            raise DriverError(delegate_item.keys())
        if delegate_item['children'] is not None:
            raise DriverError( "In 'children' item, "
                "the value of 'children' must be None, "
               f"not {type(delegate_item['children'])}" )
        exclude = delegate_item.get('exclude', ())
        if not isinstance(delegate_item['exclude'], (tuple, list)):
            raise DriverError( "In 'children' item, "
                "the value of 'exclude' must be a list, "
               f"not {type(delegate_item['exclude'])}" )
        for child in exclude:
            if not isinstance(child, str):
                raise DriverError(type(child))
            if self._child_pattern.fullmatch(child) is None:
                raise DriverError(repr(child))
        yield from self._generate_targets_children( target, record,
            exclude=exclude,
            _seen_targets=_seen_targets )

    _child_pattern = re.compile(NAME_PATTERN)

    @ensure_type_items(Target)
    @processing_target
    def _generate_targets_children( self, target, record,
        *, exclude=frozenset(),
        _seen_targets,
    ):
        exclude = frozenset(exclude)
        for key in record:
            if key.startswith('$'):
                continue
            if key in exclude:
                continue
            child_target = target.path_derive(key)
            child_record = self.get(child_target.path)
            if not child_record.get('$delegate$child'):
                continue
            yield from self._generate_targets( child_target, child_record,
                _seen_targets=_seen_targets )

    @ensure_type_items(Target)
    @processing_target
    def _generate_targets_auto( self, target, record,
        *, _seen_targets,
    ):
        if not record.get('$delegate$auto', False):
            yield target
            return
        if record.get('$source$able', False):
            yield from self._generate_targets_auto_source( target, record,
                _seen_targets=_seen_targets )
            return
        yield from self._generate_targets_children( target, record,
            _seen_targets=_seen_targets )

    @ensure_type_items(Target)
    @processing_target
    def _generate_targets_auto_source( self, target, record,
        *, _seen_targets,
    ):
        yield target
        return


    ##########
    # Document body and preamble items {{{2

    class BodyItem:
        __slots__ = []

    class VerbatimBodyItem(BodyItem):
        """These items represent a piece of LaTeX code."""
        __slots__ = ['value']

        def __init__(self, value):
            super().__init__()
            self.value = str(value)

    class SourceBodyItem(BodyItem):
        """These items represent inclusion of a source file."""
        __slots__ = ['record_path']
        include_command = r'\input'
        file_suffix = '.tex'

        def __init__(self, record_path):
            super().__init__()
            if not isinstance(record_path, RecordPath):
                raise RuntimeError(type(record_path))
            self.record_path = record_path

        @property
        def source_path(self):
            return self.record_path.as_source_path(suffix=self.file_suffix)

    class DocSourceBodyItem(SourceBodyItem):
        __slots__ = []
        include_command = r'\DocInput'
        file_suffix = '.dtx'

    class FigureDefBodyItem(BodyItem):
        __slots__ = ['figure_ref', 'figure_path']

        def __init__(self, figure_ref, figure_path):
            if not isinstance(figure_ref, str):
                raise DriverError(type(figure_ref))
            self.figure_ref = figure_ref
            if not isinstance(figure_path, RecordPath):
                raise RuntimeError(type(figure_path))
            self.figure_path = figure_path

    class NewPageBodyItem(VerbatimBodyItem):
        __slots__ = []
        _value = r'\clearpage' '\n'

        def __init__(self):
            super().__init__(value=self._value)

    class PreambleItem:
        __slots__ = []

        def __init__(self):
            super().__init__()

    class VerbatimPreambleItem(PreambleItem):
        __slots__ = ['value']

        def __init__(self, value):
            super().__init__()
            if value is not None and not isinstance(value, str):
                raise DriverError(type(value))
            self.value = value

    class CompilerItem(PreambleItem):
        __slots__ = ['compiler']

        def __init__(self, compiler):
            super().__init__()
            self.compiler = str(compiler)

    class LocalPackagePreambleItem(PreambleItem):
        __slots__ = ['package_path']

        def __init__(self, package_path):
            super().__init__()
            if not isinstance(package_path, RecordPath):
                raise RuntimeError(type(package_path))
            self.package_path = package_path

    class ProvideVerbatimPreambleItem(VerbatimPreambleItem):
        __slots__ = ['key']

        def __init__(self, key, value):
            super().__init__(value=value)
            if not isinstance(key, str):
                raise DriverError(type(key))
            self.key = key

    class ProvidePackagePreambleItem(PreambleItem):
        __slots__ = [ 'package',
            'options_required', 'options_suggested', 'options_prohibited']

        def __init__(self, package, options=None):
            super().__init__()
            if not isinstance(package, str):
                raise DriverError(type(package))
            self.package = package
            if options is None:
                self.options_required = []
                self.options_suggested = []
                self.options_prohibited = []
                return
            if isinstance(options, (list, tuple)):
                options = {'required' : options}
            if not isinstance(options, dict):
                raise DriverError(type(options))
            self.options_required = self._list_of_strings(
                options.get('required', ()) )
            self.options_suggested = self._list_of_strings(
                options.get('suggested', self.options_required) )
            self.options_prohibited = self._list_of_strings(
                options.get('prohibited', ()) )

        @staticmethod
        def _list_of_strings(what):
            if not isinstance(what, (list, tuple)):
                raise DriverError(type(what))
            result = []
            for item in what:
                if not isinstance(item, str):
                    raise DriverError(type(item))
                result.append(str(item))
            return result

    class ProhibitPackagePreambleItem(PreambleItem):
        __slots__ = ['package']

        def __init__(self, package):
            self.package = str(package)
            super().__init__()

    class PackagePreambleItem(PreambleItem):
        # Only produced by reconciling package options.
        __slots__ = ['package', 'options']

        def __init__(self, package, options):
            super().__init__()
            assert isinstance(package, str)
            self.package = package
            assert isinstance(options, list)
            assert all(isinstance(option, str) for option in options)
            self.options = options

    class Author:
        __slots__ = ['name', 'abbr']

        def __init__(self, author_item):
            if isinstance(author_item, RegularDriver.Author):
                self.name = author_item.name
                self.abbr = author_item.abbr
            elif isinstance(author_item, dict):
                if not {'name'} <= author_item.keys() <= {'name', 'abbr'}:
                    raise DriverError(author_item.keys())
                if not isinstance(author_item['name'], str):
                    raise DriverError(type(author_item['name']))
                self.name = author_item['name']
                if 'abbr' in author_item and \
                        not isinstance(author_item['abbr'], str):
                    raise DriverError(type(author_item['abbr']))
                self.abbr = author_item.get('abbr', None)
            elif isinstance(author_item, str):
                self.name = author_item
                self.abbr = None
            else:
                raise DriverError(type(author_item))

        def __str__(self):
            return self.name

        def __repr__(self):
            if self.abbr is None:
                return f'Author({self.name})'
            else:
                return f'Author(name={self.name}, abbr={self.abbr})'

    ##########
    # Record-level functions (document_recipe) {{{2

    @processing_target
    def _generate_document_recipe(self, target, record=None):
        if record is None:
            record = self.get(target.path)
        if not record['$delegate$able'] or \
                not record['$content$able']:
            raise DriverError( "Target {target} is not buildable"
                .format(target=target) )
        if target.path.is_root():
            raise DriverError("Direct building of '/' is prohibited." )

        return self._generate_regular_document_recipe(target, record=record)

    @processing_target
    def _generate_regular_document_recipe(self, target, record=None):
        """
        Return document recipe.
        """
        if record is None:
            record = self.get(target.path)

        document_recipe = {'type' : 'regular'}

        compilers = []
        header_info = {'dates' : [], 'captions' : [], 'authors' : []}

        document_target = self._get_attuned_target(target, record)
        # We must exhaust _generate_body() to fill header_info
        preamble = list(self._generate_preamble_document(
            document_target, record,
            compilers=compilers ))
        body = list(self._generate_body_document(
            document_target, record,
            preamble=preamble, header_info=header_info ))

        target.check_unutilized_flags()
        target.abandon_children() # clear references

        document_recipe['outname'] = self._select_outname(
            target, record,
            date=self._min_date(header_info['dates']) )

        if not compilers:
            raise DriverError("Compiler is not specified")
        if len(compilers) > 1:
            raise DriverError("Compiler is specified multiple times")
        # pylint: disable=unbalanced-tuple-unpacking
        document_recipe['compiler'], = compilers
        # pylint: enable=unbalanced-tuple-unpacking

        preamble = list(self._reconcile_packages(preamble))
        with process_target_aspect(target, 'document'):
            document_recipe['document'] = \
                self._constitute_document(
                    document_recipe, preamble=preamble, body=body, )
            document_recipe['document'].freeze()

        asy_latex_compilers = []
        asy_latex_preamble = list(self._generate_preamble_document(
            document_target.flags_union({'asy'}), record,
            compilers=asy_latex_compilers ))
        asy_latex_preamble = list(self._reconcile_packages(
            asy_latex_preamble ))
        asy_latex_preamble = self._constitute_preamble(
            document_recipe,
            preamble=asy_latex_preamble )
        if len(asy_latex_compilers) != 1:
            raise DriverError
        # pylint: disable=unbalanced-tuple-unpacking
        document_recipe['asy_latex_compiler'], = asy_latex_compilers
        # pylint: enable=unbalanced-tuple-unpacking
        if asy_latex_preamble.keys() != ():
            raise DriverError
        document_recipe['asy_latex_preamble'] = asy_latex_preamble.substitute({})

        return document_recipe

    _outname_regex = re.compile(OUTNAME_PATTERN)

    def _select_outname(self, target, record, date=None):
        """Return outname, except for date part."""
        outname_key, outname = self.select_flagged_item(
            record, '$document$outname', target.flags )
        if outname_key is not None:
            if not isinstance(outname, str):
                raise DriverError("Outname must be a string.")
            key_match = self._attribute_key_regex.fullmatch(outname_key)
            outname_match = self._outname_regex.fullmatch(outname)
            omitted_flag_set = frozenset(target.flags.split_flags_string(
                key_match.group('flags'),
                relative_flags=False ))
            added_flags = target.flags.split_flags_string(
                outname_match.group('flags'),
                relative_flags=False )
            assert isinstance(added_flags, list), type(added_flags)
            outname_flags = target.flags.__format__( 'optional',
                sorted_flags=added_flags +
                    sorted(target.flags.as_frozenset - omitted_flag_set)
            )
            return outname + outname_flags
        else:
            return self._select_outname_auto(target, record, date)

    def _select_outname_auto(self, target, record, date=None):
        """Return outname."""
        outname_base = '-'.join(target.path.parts)
        outname_flags = target.flags.__format__('optional')
        outname = outname_base + outname_flags
        if isinstance(date, (Date, *Date.date_types)):
            outname = str(Date(date)) + '-' + outname
        return outname

    def _get_attuned_target(self, target, record):
        flags_key, flags = self.select_flagged_item(
            record, '$document$flags', target.flags )
        if flags_key is None:
            return target
        else:
            with process_target_key(target, flags_key):
                if not isinstance(flags, list):
                    raise DriverError(type(flags))
                return target.flags_delta_mixed( flags,
                    origin=f'attuned target {target}, key {flags_key}' )


    ##########
    # Record-level functions (document preamble) {{{2

    @ensure_type_items(PreambleItem)
    @processing_target
    def _generate_preamble_document( self, target, record=None,
        *, compilers,
    ):
        if record is None:
            record = self.get(target.path)
        style_key, style = self.select_flagged_item(
            record, '$document$style', target.flags,
            required_flags={'asy'}
                    if 'asy' in target.flags
                else (),
        )
        if style_key is None:
            yield from self._generate_preamble( target, record,
                compilers=compilers,
                _seen_targets=None )
        else:
            yield from self._generate_preamble_style( target, record,
                style_key=style_key, style=style,
                compilers=compilers,
                _seen_targets=None )

    @checking_target_recursion()
    @ensure_type_items(PreambleItem)
    @processing_target
    def _generate_preamble( self, target, record=None,
        *, compilers,
        _seen_targets,
    ):
        if record is None:
            record = self.get(target.path)
        style_key, style = self.select_flagged_item(
            record, '$style', target.flags,
            required_flags={'asy'}
                    if 'asy' in target.flags
                else (),
        )
        if style_key is None:
            yield from self._generate_preamble_auto( target, record,
                compilers=compilers,
                _seen_targets=_seen_targets )
        else:
            yield from self._generate_preamble_style( target, record,
                style_key=style_key, style=style,
                compilers=compilers,
                _seen_targets=_seen_targets )

    @ensure_type_items(PreambleItem)
    @processing_target
    def _generate_preamble_style( self, target, record,
        *, style_key, style, _recursed=False,
        compilers,
        _seen_targets,
    ):
        with process_target_key(target, style_key):
            if not isinstance(style, list):
                raise DriverError(
                     "$style must be a list, "
                    f"not {type(style)}" )
            for item in style:
                yield from self._generate_preamble_style_item(
                    target, record,
                    style_key=style_key, style_item=item,
                    _recursed=_recursed,
                    compilers=compilers,
                    _seen_targets=_seen_targets )

    @ensure_type_items(PreambleItem)
    def _generate_preamble_style_item( self, target, record,
        *, style_key, style_item, _recursed,
        compilers,
        _seen_targets,
    ):
        if isinstance(style_item, str):
            yield from self._generate_preamble(
                target.derive_from_string( style_item,
                    origin=f'style {target}, key {style_key}' ),
                compilers=compilers,
                _seen_targets=_seen_targets )
            return

        if not isinstance(style_item, dict):
            raise DriverError(
                 "$style item must be a string or a dictionary, "
                f"not {type(style_item)}" )
        style_item = style_item.copy()
        condition = style_item.pop('condition', True)
        if not target.flags.check_condition(condition):
            return
        if 'style' in style_item.keys():
            if style_item.keys() != {'style'}:
                raise DriverError(style_item.keys())
            if _recursed:
                raise DriverError("Nested 'style' items are not allowed.")
            yield from self._generate_preamble_style( target, record,
                style_key=style_key+"/style", style=style_item['style'],
                _recursed=True,
                compilers=compilers,
                _seen_targets=_seen_targets )
        elif 'compiler' in style_item.keys():
            if style_item.keys() != {'compiler'}:
                raise DriverError(style_item.keys())
            compiler = style_item['compiler']
            if not isinstance(compiler, str):
                raise DriverError(type(compiler))
            if compiler not in {'latex', 'pdflatex', 'xelatex', 'lualatex'}:
                raise DriverError(compiler)
            compilers.append(compiler)
        elif 'package-source' in style_item.keys():
            if style_item.keys() != {'package-source'}:
                raise DriverError(style_item.keys())
            if not isinstance(style_item['package-source'], str):
                raise DriverError(type(style_item['package-source']))
            package_path = \
                RecordPath(target.path, style_item['package-source'])
            if not self.get(package_path).get('$package$able', False):
                raise DriverError
            yield self.LocalPackagePreambleItem(
                package_path=package_path )
        else:
            yield from self._generate_preamble_style_simple(style_item)

    @ensure_type_items(PreambleItem)
    def _generate_preamble_style_simple(self, style_item):
        # coincides with the set of items that are allowed in 'style' items
        # in $content
        if 'verbatim' in style_item.keys():
            yield from self._generate_preamble_style_verbatim(style_item)
        elif 'package' in style_item.keys():
            yield from self._generate_preamble_style_package(style_item)
        elif 'error' in style_item.keys():
            if style_item.keys() == {'error'}:
                raise DriverError(style_item['error'])
            else:
                raise DriverError(style_item.keys())
        else:
            raise DriverError(style_item.keys())

    @ensure_type_items(PreambleItem)
    def _generate_preamble_style_verbatim(self, style_item):
        if style_item.keys() == {'verbatim'}:
            if not isinstance(style_item['verbatim'], str):
                raise DriverError(type(style_item['verbatim']))
            yield self.VerbatimPreambleItem(value=style_item['verbatim'])
        elif style_item.keys() == {'verbatim', 'provide'}:
            if style_item['verbatim'] is not None and \
                    not isinstance(style_item['verbatim'], str):
                raise DriverError(type(style_item['verbatim']))
            if not isinstance(style_item['provide'], str):
                raise DriverError(type(style_item['provide']))
            yield self.ProvideVerbatimPreambleItem(
                value=style_item['verbatim'], key=style_item['provide'] )
        else:
            raise DriverError(style_item.keys())

    @ensure_type_items(PreambleItem)
    def _generate_preamble_style_package(self, style_item):
        if style_item.keys() == {'package'}:
            yield self.ProvidePackagePreambleItem(
                package=style_item['package'] )
        elif style_item.keys() == {'package', 'options'}:
            yield self.ProvidePackagePreambleItem(
                package=style_item['package'], options=style_item['options'] )
        elif style_item.keys() == {'package', 'prohibited'}:
            if style_item['prohibited'] is not True:
                raise DriverError(style_item)
            yield self.ProhibitPackagePreambleItem(
                package=style_item['package'] )
        else:
            raise DriverError(style_item.keys())

    @ensure_type_items(PreambleItem)
    @processing_target
    def _generate_preamble_auto( self, target, record,
        compilers,
        _seen_targets,
    ):
        if not record.get('$style$auto', True):
            raise DriverError("$style is not defined")
        if '$package$able' not in record:
            if target.path.is_root():
                raise DriverError("Toplevel $style is not defined")
            yield from self._generate_preamble(
                target.path_derive('..'),
                compilers=compilers,
                _seen_targets=_seen_targets )
        else:
            yield self.LocalPackagePreambleItem(
                package_path=target.path )


    ##########
    # Record-level functions (document body) {{{2

    @processing_target
    @ensure_type_items(BodyItem)
    def _generate_body_document(self, target, record=None,
        *, preamble, header_info,
    ):
        if record is None:
            record = self.get(target.path)
        content_key, content = self.select_flagged_item(
            record, '$document$content', target.flags )
        if content_key is None:
            yield from self._generate_body( target, record,
                preamble=preamble,
                header_info=header_info,
                _seen_targets=None )
        else:
            yield from self._generate_body_content( target, record,
                content_key=content_key, content=content,
                preamble=preamble,
                header_info=header_info,
                _seen_targets=None )

    @checking_target_recursion()
    @processing_target
    @ensure_type_items(BodyItem)
    def _generate_body( self, target, record=None,
        *, preamble, header_info,
        _seen_targets,
    ):
        if record is None:
            record = self.get(target.path)
        content_key, content = self.select_flagged_item(
            record, '$content', target.flags )
        if content_key is None:
            yield from self._generate_body_auto( target, record,
                preamble=preamble, header_info=header_info,
                _seen_targets=_seen_targets )
        else:
            yield from self._generate_body_content( target, record,
                content_key=content_key, content=content,
                preamble=preamble, header_info=header_info,
                _seen_targets=_seen_targets )

    @processing_target
    @ensure_type_items(BodyItem)
    def _generate_body_content(self, target, record,
        *, content_key=None, content=None, _recursed=False,
        preamble, header_info,
        _seen_targets,
    ):
        with process_target_key(target, content_key):
            if not isinstance(content, list):
                raise DriverError(
                     "$content must be a list, "
                    f"not {type(content)}" )
            for item in content:
                yield from self._generate_body_content_item(
                    target, record,
                    content_key=content_key, content_item=item,
                    _recursed=_recursed,
                    preamble=preamble, header_info=header_info,
                    _seen_targets=_seen_targets )

    @ensure_type_items(BodyItem)
    def _generate_body_content_item( self, target, record,
        *, content_key, content_item, _recursed,
        preamble, header_info,
        _seen_targets,
    ):
        if isinstance(content_item, str):
            yield from self._generate_body(
                target.derive_from_string(content_item,
                    origin=f'content {target}, key {content_key}' ),
                preamble=preamble, header_info=header_info,
                _seen_targets=_seen_targets )
            return

        if not isinstance(content_item, dict):
            raise DriverError(
                 "$content item must be a string or a dictionary, "
                f"not {type(content_item)}" )
        content_item = content_item.copy()
        condition = content_item.pop('condition', True)
        if not target.flags.check_condition(condition):
            return
        if 'content' in content_item.keys():
            if _recursed:
                raise DriverError("Nested 'content' items are not allowed.")
            yield from self._generate_body_content_content( target, record,
                content_key=content_key, content_item=content_item,
                preamble=preamble, header_info=header_info,
                _seen_targets=_seen_targets )
        elif 'children' in content_item.keys():
            yield from self._generate_body_content_children( target, record,
                content_item=content_item,
                preamble=preamble, header_info=header_info,
                _seen_targets=_seen_targets )
        elif 'verbatim' in content_item.keys():
            if content_item.keys() != {'verbatim'}:
                raise DriverError(content_item.keys())
            yield self.VerbatimBodyItem(value=content_item['verbatim'])
        elif 'source' in content_item.keys():
            if content_item.keys() != {'source'}:
                raise DriverError(content_item.keys())
            if not isinstance(content_item['source'], str):
                raise DriverError(type(content_item['source']))
            yield from self._generate_body_source(
                target.derive_from_string(content_item['source'],
                    origin=f'content {target}, key {content_key}/source' ),
                preamble=preamble, header_info=header_info,
                _seen_targets=_seen_targets )
        elif 'figure' in content_item.keys():
            if not content_item.keys() <= {'figure', 'options'}:
                raise DriverError(content_item.keys())
            yield from self._generate_body_content_figure( target, record,
                content_item=content_item )
        elif 'style' in content_item.keys():
            if content_item.keys() != {'style'}:
                raise DriverError(content_item.keys())
            if not isinstance(content_item['style'], list):
                raise DriverError(type(content_item['style']))
            for style_item in content_item['style']:
                preamble.append(
                    self._generate_preamble_style_simple(style_item) )
        elif 'special' in content_item.keys():
            special_name = content_item.pop('special')
            special_method = getattr( self,
                f'_generate_body_special_{special_name}' )
            yield from special_method( target, record, content_item,
                preamble=preamble, header_info=header_info,
                _seen_targets=_seen_targets )
        elif 'error' in content_item.keys():
            if content_item.keys() == {'error'}:
                raise DriverError(content_item['error'])
            else:
                raise DriverError(content_item.keys())
        else:
            raise DriverError(content_item.keys())

    @ensure_type_items(BodyItem)
    def _generate_body_content_content( self, target, record,
        *, content_key, content_item,
        preamble, header_info,
        _seen_targets,
    ):
        if not content_item.keys() <= {'content', 'header', 'newpage'}:
            raise DriverError(content_item.keys())

        newpage = content_item.get('newpage', True)
        if not isinstance(newpage, bool):
            raise DriverError( "In 'content' item, "
                "the value of 'newpage' must be a boolean, "
               f"not {type(newpage)}" )

        content = content_item['content']
        if not isinstance(content, list):
            raise DriverError( "In 'content' item, "
                "the value of 'content' must be a list, "
               f"not {type(content)}" )

        header = None
        if 'header' in content_item:
            if content_item['header'] is False:
                header = False
            elif content_item['header'] is None:
                header = {}
            elif content_item['header'] is True:
                header = {}
            elif isinstance(content_item['header'], dict):
                header = content_item['header'].copy()
            else:
                raise DriverError( "In 'content' item, "
                    "the value of 'header' must be false or a list, "
                   f"not {type(newpage)}" )

        yield from self._generate_body_headered_content(
            target, record,
            content_key=content_key+'/content', content=content,
            header=header, newpage=newpage,
            preamble=preamble, header_info=header_info,
            _seen_targets=_seen_targets )

    @ensure_type_items(BodyItem)
    def _generate_body_content_figure(self, target, record,
        *, content_item,
    ):
        if not isinstance(content_item['figure'], str):
            raise DriverError(type(content_item['figure']))
        if 'options' in content_item:
            if not isinstance(content_item['options'], list):
                raise DriverError(type(content_item['options']))
            for option in content_item['options']:
                if not isinstance(option, str):
                    raise DriverError(type(option))
            options = content_item['options']
        else:
            options = None
        figure_path = RecordPath(target.path, content_item['figure'])
        figure_ref = '-'.join(figure_path.parts)
        yield self.FigureDefBodyItem(figure_ref, figure_path)
        yield self.VerbatimBodyItem(
            self.jeolmfigure_template.substitute(
                options=self._constitute_options(options),
                figure_ref=figure_ref )
        )

    @ensure_type_items(BodyItem)
    def _generate_body_headered_content( self, target, record,
        *, content_key, content=None, header, newpage=True,
        preamble, header_info,
        _seen_targets,
    ):
        def generate_body(*, header_info=header_info):
            yield from (
                self._generate_body_content( target, record,
                    content_key=content_key, content=content,
                    preamble=preamble, header_info=header_info,
                    _seen_targets=_seen_targets )
            )

        if newpage:
            yield self.NewPageBodyItem()

        if header is None:
            yield from generate_body()
        elif header is False:
            target = target.flags_union({'contained'})
            yield from generate_body()
        else:
            target = target.flags_union({'contained'})
            content_header_info = \
                {'dates' : [], 'captions' : [], 'authors' : []}
            body = list(generate_body(header_info=content_header_info))
            self._prepare_body_header( target, record, header,
                super_header_info=header_info,
                header_info=content_header_info )
            yield from self._generate_body_header( target, record,
                header=header )
            yield from body

        if newpage:
            if not content and header is None:
                yield self.VerbatimBodyItem(r'\null')
            yield self.NewPageBodyItem()

    def _prepare_body_header( self, target, record, header,
        *, super_header_info, header_info,
    ):
        if 'date' not in header:
            header['date'] = self._min_date(header_info['dates'])
        if header['date'] is not None and header['date'] is not Never:
            if not isinstance(header['date'], (Date, *Date.date_types, str)):
                raise DriverError(type(header['date']))
            super_header_info['dates'].append(header['date'])
        if 'caption' not in header:
            header['caption'] = \
                self._join_captions(header_info['captions'])
        if header['caption'] is not None:
            if not isinstance(header['caption'], str):
                raise DriverError(type(header['caption']))
            super_header_info['captions'].append(header['caption'])
        if 'authors' not in header:
            header['authors'] = self._unique_authors(header_info['authors'])
        if header['authors'] is not None:
            if not isinstance(header['authors'], list):
                raise DriverError(type(header['authors']))
            super_header_info['authors'].extend(header['authors'])

    @ensure_type_items(BodyItem)
    def _generate_body_header( self, target, record,
        *, header,
    ):
        yield self.VerbatimBodyItem(
            self.jeolmheader_begin_template.substitute() )
        yield from self._generate_body_header_def(
            target, record, header=header )
        yield self.VerbatimBodyItem(
            self.jeolmheader_end_template.substitute() )
        yield self.VerbatimBodyItem(
            self.resetproblem_template.substitute() )

    @ensure_type_items(BodyItem)
    def _generate_body_header_def( self, target, record,
        *, header,
    ):
        if header['date'] is not None and header['date'] is not Never:
            yield self.VerbatimBodyItem(
                self._constitute_date_def(date=header['date']) )
        if header['caption'] is not None:
            yield self.VerbatimBodyItem(
                self._constitute_caption_addtoc(caption=header['caption']) )
        if header['authors'] is not None:
            yield self.VerbatimBodyItem(
                self._constitute_authors_def(author_list=header['authors']) )

    @ensure_type_items(BodyItem)
    def _generate_body_content_children( self, target, record,
        *, content_item,
        preamble, header_info,
        _seen_targets,
    ):
        if not content_item.keys() <= {'children', 'exclude', 'order'}:
            raise DriverError(content_item.keys())
        if content_item['children'] is not None:
            raise DriverError( "In 'children' item, "
                "the value of 'children' must be None, "
               f"not {type(content_item['children'])}" )
        exclude = content_item.get('exclude', ())
        if not isinstance(content_item['exclude'], (tuple, list)):
            raise DriverError( "In 'children' item, "
                "the value of 'exclude' must be a list, "
               f"not {type(content_item['exclude'])}" )
        for child in exclude:
            if not isinstance(child, str):
                raise DriverError(type(child))
            if self._child_pattern.fullmatch(child) is None:
                raise DriverError(repr(child))
        order = content_item.get('order')
        if order is not None:
            if not isinstance(order, str):
                raise DriverError( "In 'children' item, "
                    "the value of 'order' must be a string, "
                   f"not {type(order)}" )
            if order not in {'record', 'date'}:
                raise DriverError( "In 'children' item, "
                    "the value of 'order' must be 'record' or 'date', "
                   f"not {order!r}" )
        yield from self._generate_body_children( target, record,
            exclude=exclude, order=order,
            preamble=preamble, header_info=header_info,
            _seen_targets=_seen_targets )

    @processing_target
    @ensure_type_items(BodyItem)
    def _generate_body_children( self, target, record,
        *, exclude=frozenset(), order=None,
        preamble, header_info,
        _seen_targets,
    ):
        exclude = frozenset(exclude)
        child_bodies = []
        for key in record:
            if key.startswith('$'):
                continue
            if key in exclude:
                continue
            child_target = target.path_derive(key)
            child_record = self.get(child_target.path)
            if not child_record.get('$content$child'):
                continue
            child_preamble = []
            child_header_info = \
                {'dates' : [], 'captions' : [], 'authors' : []}
            child_bodies.append((
                list(self._generate_body( child_target, child_record,
                    preamble=child_preamble, header_info=child_header_info,
                    _seen_targets=_seen_targets )),
                child_preamble,
                child_header_info,
            ))
        if order is None:
            order = record.get('$content$order', 'record')
            if not isinstance(order, str):
                raise DriverError( "$content$order must be a string, "
                   f"not {type(order)}" )
            if order not in {'record', 'date'}:
                raise DriverError(
                    "$content$order must be 'record' or 'date', "
                   f"not {order!r}" )
        if order == 'record':
            pass
        elif order == 'date':
            def date_key(item):
                body, preamble, header_info = item
                return self._min_date(header_info['dates'])
            child_bodies.sort(key=date_key)
        else:
            raise RuntimeError(order)
        for child_body, child_preamble, child_header_info in child_bodies:
            preamble.extend(child_preamble)
            for key in ('dates', 'captions', 'authors'):
                header_info[key].extend(child_header_info[key])
            yield from child_body

    @processing_target
    @ensure_type_items(BodyItem)
    def _generate_body_auto( self, target, record,
        *, preamble, header_info,
        _seen_targets,
    ):
        if not record.get('$content$auto', False):
            raise DriverError("$content is not defined")
        if record.get('$source$able', False):
            yield from self._generate_body_auto_source( target, record,
                preamble=preamble, header_info=header_info,
                _seen_targets=_seen_targets )
            return
        yield from self._generate_body_children( target, record,
            preamble=preamble, header_info=header_info,
            _seen_targets=_seen_targets )

    @processing_target
    @ensure_type_items(BodyItem)
    def _generate_body_auto_source( self, target, record,
        *, preamble, header_info,
        _seen_targets,
    ):
        if 'contained' in target.flags:
            yield from self._generate_body_source( target, record,
                preamble=preamble, header_info=header_info,
                _seen_targets=_seen_targets )
        else:
            yield from self._generate_body_headered_content( target, record,
                content_key='$content$auto',
                content=['.'],
                header={},
                preamble=preamble, header_info=header_info,
                _seen_targets=_seen_targets )

    @processing_target
    @ensure_type_items(BodyItem)
    def _generate_body_source( self, target, record=None,
        *, preamble, header_info,
        _seen_targets,
    ):
        if record is None:
            record = self.get(target.path)
        if not record.get('$source$able', False):
            raise DriverError
        has_source_tex = record.get(
            self._get_source_type_key('tex'), False )
        has_source_dtx = record.get(
            self._get_source_type_key('dtx'), False )
        if has_source_tex + has_source_dtx > 1:
            raise DriverError("Source type conflict")
        if has_source_tex + has_source_dtx < 1:
            raise DriverError
        if has_source_dtx:
            yield self.DocSourceBodyItem(record_path=target.path)
            return
        assert has_source_tex
        header_info['dates'].append(self._get_source_date(target, record))
        header_info['captions'].append(self._get_source_caption(target, record))
        header_info['authors'].extend(self._get_source_authors(target, record))
        yield from self._generate_body_source_figure_def(target, record)
        yield self.SourceBodyItem(record_path=target.path)

    @staticmethod
    def _get_source_type_key(source_type):
        return '$source$type${}'.format(source_type)

    def _get_source_date(self, target, record):
        date = record.get('$date', None)
        if date is None:
            return Never
        elif isinstance(date, (Date, *Date.date_types)):
            return Date(date)
        elif isinstance(date, str):
            return date
        else:
            raise DriverError(type(date))

    def _get_source_caption(self, target, record):
        if '$caption' in record:
            if not isinstance(record['$caption'], str):
                raise DriverError(type(record['$caption']))
            return str(record['$caption'])
        elif '$source$sections' in record:
            if not isinstance(record['$source$sections'], list):
                raise DriverError(type(record['$source$sections']))
            for section in record['$source$sections']:
                if not isinstance(section, str):
                    raise DriverError(type(section))
            return "; ".join(record['$source$sections'])
        else:
            return None

    def _get_source_authors(self, target, record):
        authors = record.get('$authors', ())
        if not isinstance(authors, (list, tuple)):
            raise DriverError(type(authors))
        return [self.Author(author) for author in authors]

    @ensure_type_items(BodyItem)
    @processing_target
    def _generate_body_source_figure_def(self, target, record):
        figure_refs = record.get('$source$figures', ())
        if not isinstance(figure_refs, (list, tuple)):
            raise DriverError(type(figure_refs))
        for figure_ref in figure_refs:
            if not isinstance(figure_ref, str):
                raise DriverError(type(figure_ref))
            match = self._figure_ref_regex.fullmatch(figure_ref)
            if match is None:
                raise DriverError( "Cannot parse figure ref "
                    f"{figure_ref!r}" )
            figure = match.group('figure')
            figure_path = RecordPath(target.path, figure)
            yield self.FigureDefBodyItem(figure_ref, figure_path)

    _figure_ref_regex = re.compile(FIGURE_REF_PATTERN)

    @classmethod
    def _reconcile_packages(cls, preamble):
        # Resolve all package prohibitions and option
        # suggestions/prohibitions.
        assert isinstance(preamble, list)
        prohibited_packages = set()
        package_options = {}
        for item in preamble:
            if isinstance(item, cls.ProvidePackagePreambleItem):
                options = package_options.setdefault(
                    item.package,
                    { 'required' : list(), 'suggested' : list(),
                        'prohibited' : list() }
                )
                options['required'].extend(item.options_required)
                options['suggested'].extend(item.options_suggested)
                options['prohibited'].extend(item.options_prohibited)
            elif isinstance(item, cls.ProhibitPackagePreambleItem):
                prohibited_packages.add(item.package)
        for item in preamble:
            if isinstance(item, cls.ProvidePackagePreambleItem):
                if item.package in prohibited_packages:
                    raise DriverError(
                       f"Package {item.package} "
                        "is prohibited and required at the same time" )
                options = package_options.get(item.package)
                if options is None:
                    # package is already processed
                    continue
                options_prohibited = set(options['prohibited'])
                option_list = [
                    option
                    for option in unique(options['suggested'])
                    if option not in options_prohibited ]
                if not set(option_list) >= set(options['required']):
                    bad_options = sorted(
                        set(options['required']) - set(option_list) )
                    raise DriverError(
                       f"Package {item.package} "
                       f"options {', '.join(repr(o) for o in bad_options)} "
                        "are prohibited and required at the same time" )
                yield cls.PackagePreambleItem(item.package, option_list)
            elif isinstance(item, cls.ProhibitPackagePreambleItem):
                pass
            else:
                yield item

    ##########
    # Record-level functions (package_record) {{{2

    @processing_package_path
    def _generate_package_recipe(self, package_path):
        try:
            record = self.get(package_path)
        except RecordNotFoundError as error:
            raise DriverError('Package not found') from error
        if not record.get('$package$able', False):
            raise DriverError("Package '{}' not found".format(package_path))

        package_types = [ package_type
            for package_type in self._package_types
            if record.get(self._get_package_type_key(package_type), False) ]
        if len(package_types) > 1:
            raise DriverError(package_types)
        package_type, = package_types
        suffix = self._get_package_suffix(package_type)
        source_path = package_path.as_source_path(suffix=suffix)
        name_key = self._get_package_name_key(package_type)
        if name_key in record:
            package_name = record[name_key]
            if not isinstance(package_name, str):
                raise DriverError(type(package_name))
        else:
            package_name = package_path.name

        return {
            'source_type' : package_type,
            'source' : source_path, 'name' : package_name }

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
    def _generate_figure_recipe(self, figure_path, figure_formats):
        try:
            record = self.get(figure_path)
        except RecordNotFoundError as error:
            raise DriverError('Figure not found') from error
        if not record.get('$figure$able', False):
            raise DriverError("Figure '{}' not found".format(figure_path))

        figure_types = [ figure_type
            for figure_type in self._figure_types
            if self._figure_formats[figure_type] & figure_formats
            if record.get(self._get_figure_type_key(figure_type), False) ]
        if len(figure_types) > 1:
            raise DriverError(figure_types)
        figure_type, = figure_types
        figure_formats = self._figure_formats[figure_type] & figure_formats
        if len(figure_formats) > 1:
            raise DriverError(figure_formats)
        figure_format, = figure_formats
        suffix = self._get_figure_suffix(figure_type)
        source_path = figure_path.as_source_path(suffix=suffix)

        figure_recipe = {
            'format' : figure_format,
            'source_type' : figure_type,
            'source' : source_path }
        if figure_type == 'asy':
            figure_recipe['other_sources'] = \
                self._find_figure_asy_other_sources(
                    figure_path, record )
            assert isinstance(figure_recipe['other_sources'], dict)
        return figure_recipe

    _figure_types = ('asy', 'svg', 'pdf', 'eps', 'png', 'jpg',)
    _figure_formats = {
        'asy' : {'pdf', 'eps'},
        'svg' : {'pdf', 'eps'},
        'pdf' : {'pdf'},
        'eps' : {'eps'},
        'png' : {'png'},
        'jpg' : {'jpg'},
    }

    @staticmethod
    def _get_figure_type_key(figure_type):
        return '$figure$type${}'.format(figure_type)

    @staticmethod
    def _get_figure_suffix(figure_type):
        return '.{}'.format(figure_type)

    @processing_figure_path
    def _find_figure_asy_other_sources(self, figure_path, record):
        other_sources = dict()
        for accessed_name, source_path in (
            self._trace_figure_asy_other_sources(figure_path, record)
        ):
            self._check_and_set(other_sources, accessed_name, source_path)
        return other_sources

    @processing_figure_path
    def _trace_figure_asy_other_sources(self, figure_path, record=None,
        *, _seen_items=None
    ):
        """Yield (accessed_name, source_path) pairs."""
        if _seen_items is None:
            _seen_items = set()
        if record is None:
            record = self.get(figure_path)
        accessed_paths = record.get('$figure$asy$accessed', {})
        for accessed_name, accessed_path_s in accessed_paths.items():
            accessed_path = RecordPath(figure_path, accessed_path_s)
            accessed_item = (accessed_name, accessed_path)
            if accessed_item in _seen_items:
                continue
            else:
                _seen_items.add(accessed_item)
            source_path = accessed_path.as_source_path(suffix='.asy')
            yield accessed_name, source_path
            yield from self._trace_figure_asy_other_sources(
                accessed_path, _seen_items=_seen_items )


    ##########
    # LaTeX-level functions {{{2

    @classmethod
    def _constitute_document(cls, document_recipe, preamble, body):
        document_template = DocumentTemplate()
        document_template.append_text(
            cls.document_compiler_template.substitute(
                compiler=document_recipe['compiler'] )
        )
        cls._fill_preamble(preamble, document_template)
        document_template.append_text(
            cls.document_begin_template.substitute() )
        cls._fill_body(body, document_template)
        document_template.append_text(
            cls.document_end_template.substitute() )
        return document_template

    document_compiler_template = Template(
        r'% Auto-generated by jeolm for compiling with $compiler' '\n\n'
    )
    document_begin_template = Template(
        '\n' r'\begin{document}' '\n\n' )
    document_end_template = Template(
        '\n' r'\end{document}' '\n\n' )

    @classmethod
    def _constitute_preamble(cls, document_recipe, preamble):
        preamble_template = DocumentTemplate()
        cls._fill_preamble(preamble, preamble_template)
        return preamble_template

    @classmethod
    def _fill_preamble(cls, preamble, document_template):
        provided_preamble = {}
        for item in preamble:
            assert isinstance(item, cls.PreambleItem), type(item)
            assert not isinstance(item, cls.ProvidePackagePreambleItem)
            assert not isinstance(item, cls.ProhibitPackagePreambleItem)
            if isinstance(item, cls.ProvideVerbatimPreambleItem):
                if not cls._check_and_set( provided_preamble,
                        item.key, item.value ):
                    continue
            cls._fill_preamble_item(item, document_template)
            document_template.append_text('\n')

    @classmethod
    def _fill_preamble_item(cls, item, document_template):
        if isinstance(item, cls.VerbatimPreambleItem):
            document_template.append_text(item.value)
        elif isinstance(item, cls.LocalPackagePreambleItem):
            document_template.append_text(
                cls.uselocalpackage_0_template.substitute() )
            document_template.append_key(('package', item.package_path))
            document_template.append_text(
                cls.uselocalpackage_1_template.substitute(
                    package_path=item.package_path)
            )
        elif isinstance(item, cls.PackagePreambleItem):
            document_template.append_text(
                cls.usepackage_template.substitute(
                    package=item.package,
                    options=cls._constitute_options(item.options) )
            )
        else:
            raise RuntimeError(type(item))

    uselocalpackage_0_template = Template(
        r'\usepackage{' )
    uselocalpackage_1_template = Template(
        r'}% $package_path' )

    @classmethod
    def _constitute_options(cls, options):
        if not options:
            return ''
        if not isinstance(options, str):
            options = ','.join(options)
        return '[' + options + ']'

    @classmethod
    def _fill_body(cls, body, document_template):
        for item in body:
            assert isinstance(item, cls.BodyItem), type(item)
            cls._fill_body_item(item, document_template)
            document_template.append_text('\n')

    @classmethod
    def _fill_body_item(cls, item, document_template):
        if isinstance(item, cls.VerbatimBodyItem):
            document_template.append_text(item.value)
        elif isinstance(item, cls.SourceBodyItem):
            document_template.append_text(
                cls.input_0_template.substitute(
                    include_command=item.include_command )
            )
            document_template.append_key(('source', item.source_path))
            document_template.append_text(
                cls.input_1_template.substitute(
                    source_path=item.source_path )
            )
        elif isinstance(item, cls.FigureDefBodyItem):
            figure_index = getattr(document_template, 'figure_index', 0)
            document_template.append_text(
                cls.jeolmfiguremap_0_template.substitute(
                    figure_ref=item.figure_ref )
            )
            document_template.append_key(
                ('figure', item.figure_path, figure_index) )
            document_template.append_text(
                cls.jeolmfiguremap_1_template.substitute(
                    figure_path=item.figure_path )
            )
            document_template.append_key(
                ('figure-size', item.figure_path, figure_index) )
            document_template.append_text(
                cls.jeolmfiguremap_2_template.substitute(
                    figure_path=item.figure_path )
            )
            document_template.figure_index = figure_index + 1
        else:
            raise RuntimeError(type(item))

    input_0_template = Template(
        r'$include_command{' )
    input_1_template = Template(
        r'}% $source_path' )

    jeolmfiguremap_0_template = Template(
        r'\jeolmfiguremap{$figure_ref}{' )
    jeolmfiguremap_1_template = Template(
        r'}{' )
    jeolmfiguremap_2_template = Template(
        r'}% $figure_path' )

    @classmethod
    def _constitute_date_def(cls, date):
        if date is None or date is Never:
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
        if not isinstance(date, (Date, *Date.date_types)):
            return str(date)
        if not isinstance(date, Date):
            date = Date(date)
        date_s = cls.date_template.substitute(dateiso=date.date.isoformat())
        if date.period is not None:
            date_s += cls.period_template.substitute(period=date.period)
        return date_s

    date_template = Template(
        r'\DTMDate{$dateiso}' )
    period_template = Template(
        r'\jeolmdisplayperiod{$period}')

    @classmethod
    def _constitute_caption_addtoc(cls, caption):
        return cls.addtoc_template.substitute(caption=caption)

    addtoc_template = Template(
        r'\phantomsection\addcontentsline{toc}{section}{$caption}' )

    @classmethod
    def _constitute_authors_def(cls, author_list):
        authors = cls._constitute_authors(author_list)
        if '%' in authors:
            raise DriverError(
                "'%' symbol is found in the list of authors: {}"
                .format(authors) )
        return cls.authors_def_template.substitute(authors=authors)

    @classmethod
    def _constitute_authors(cls, author_list, *, thin_space=r'\,'):
        assert isinstance(author_list, list), type(author_list)
        if not author_list:
            return ''
        elif len(author_list) == 1:
            author, = author_list
            return str(author)
        else:
            abbreviate = partial( cls._abbreviate_author,
                thin_space=thin_space )
        return ', '.join(abbreviate(author) for author in author_list)

    @classmethod
    def _abbreviate_author(cls, author, thin_space=r'\,'):
        if isinstance(author, cls.Author):
            if author.abbr is not None:
                return author.abbr
            author_name = author.name
        elif isinstance(author, str):
            author_name = author
        else:
            raise RuntimeError(type(author))
        *names, last = author_name.split(' ')
        return thin_space.join([name[0] + '.' for name in names] + [last])

    authors_def_template = Template(
        r'\def\jeolmauthors{$authors}%' )

    usepackage_template = Template(
        r'\usepackage$options{$package}' )
    resetproblem_template = Template(
        r'\resetproblem' )
    jeolmheader_begin_template = Template(
        r'\begingroup % \jeolmheader' )
    jeolmheader_end_template = Template(
        r'\jeolmheader \endgroup' )
    jeolmfigure_template = Template(
        r'\jeolmfigure$options{$figure_ref}' )

    ##########
    # Supplementary finctions {{{2

#    @classmethod
#    def _select_alias(cls, *parts, suffix=None, ascii_only=False):
#        path = PurePosixPath(*parts)
#        assert len(path.suffixes) <= 1, path
#        if suffix is not None:
#            path = path.with_suffix(suffix)
#        assert not path.is_absolute(), path
#        alias = '-'.join(path.parts)
#        if ascii_only and not cls._ascii_file_name_pattern.fullmatch(alias):
#            alias = unidecode(alias).replace("'", "")
#            assert cls._ascii_file_name_pattern.fullmatch(alias), alias
#        else:
#            assert cls._file_name_pattern.fullmatch(alias), alias
#        return alias
#
#    _ascii_file_name_pattern = re.compile(
#        '(?:' + NAME_PATTERN + ')' + r'(?:\.\w+)?', re.ASCII)
#    _file_name_pattern = re.compile(
#        '(?:' + NAME_PATTERN + ')' + r'(?:\.\w+)?' )

    @staticmethod
    def _min_date(dates, _date_types=(Date, *Date.date_types)):
        dates = [ date
            for date in dates
            if date is not None
            if date is not Never ]
        if not dates:
            return Never
        if len(dates) == 1:
            date, = dates
            return date
        if all(
            isinstance(date, _date_types)
            for date in dates
        ):
            return min(dates)
        return None

    @staticmethod
    def _join_captions(captions):
        captions = [caption for caption in captions if caption is not None]
        if not captions:
            return None
        if len(captions) == 1:
            caption, = captions
            return caption
        assert all(isinstance(caption, str) for caption in captions)
        return "; ".join(captions)

    @classmethod
    def _unique_authors(cls, authors):
        unique_authors = OrderedDict()
        for author in authors:
            assert isinstance(author, cls.Author), type(author)
            if author.name not in unique_authors:
                unique_authors[author.name] = author
                continue
            if author.abbr is None:
                continue
            old_abbr = unique_authors[author.name].abbr
            if old_abbr is None:
                unique_authors[author.name] = author
                continue
            if old_abbr != author.abbr:
                raise DriverError(unique_authors[author.name], author)
        if not unique_authors:
            return None
        return list(unique_authors.values())

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
            raise DriverError(*error.args) from error

# }}}1
# vim: set foldmethod=marker :
