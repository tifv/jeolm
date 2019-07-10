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
            date: <Period>
              * may be null to remove date from the header;
              * default is the minimal date of the items in content.
            caption: <string>
              * only affects toc;
              * may be null to disable toc line;
              * default is the captions of the content items,
                joined by "; ".
            authors: [<author_item>, …]
              * may be null or empty to remove authors from the header;
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
* $style$asy[*]:
    - a list of items:
        - <delegator (string)>
        - style-asy:
            * a list of items, same as in $style$asy;
            * nested style-asy items are prohibited.
        - style:
            * a list of items, same as in $style;
            * nested style items are prohibited.
        * all other items that can appear in $style are permitted,
          except for 'package-source'
        * dictionary items may also contain 'condition' key.
- $style$auto
    - boolean or condition;
    - if true then imply
        - (unless applicable $style key is found)
        - if $package$able is not true
            $style: [..]
        - if $package$able is true
            $style: [{source_package: .}]
    - if true then imply
        - (unless applicable $style$asy key is found)
        $style$asy: [..]
    * default is:
        - inherited from parent;
        - otherwise true.

* $date:
    - datetime.date or jeolm.date.Period instance
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

from jeolm.records import ( RecordPath, Record, RecordNotFoundError,
    NAME_PATTERN )
from jeolm.target import Flag, Target, OUTNAME_PATTERN

from jeolm.date import Period, DatePeriod, Never
from jeolm.utils.check_and_set import check_and_set, ClashingValueError
from jeolm.utils.unique import unique

from . import ( Driver,
    DocumentTemplate, Compiler, DocumentRecipe,
    PackageRecipe, FigureRecipe,
    DriverError, folding_driver_errors, SeenItems,
    process_target_aspect, process_target_key,
    processing_target, processing_package_path, processing_figure_path,
    FIGURE_REF_PATTERN,
)

import logging
logger = logging.getLogger(__name__)

import typing
from typing import ( TypeVar, ClassVar, Any, Union, Optional,
    Iterable, Collection, Sequence, Hashable, Mapping, MutableMapping,
    Tuple, List, Set, FrozenSet, Dict,
    Generator, Pattern )
K = TypeVar('K', bound=Hashable)
V = TypeVar('V')
if typing.TYPE_CHECKING:
    from mypy_extensions import TypedDict
    from typing_extensions import Literal
else:
    from typing_extensions import TypedDict, Literal


class RegularDriver(Driver): # {{{1

    ##########
    # Interface methods and attributes {{{2

    @folding_driver_errors
    def list_delegated_targets(self, *targets: Target) -> Iterable[Target]:
        for target in targets:
            yield from self._generate_targets(target)

    @folding_driver_errors
    def list_targetable_paths(self) -> Iterable[RecordPath]:
        # Caching is not necessary since no use-case involves calling this
        # method several times.
        yield from self._generate_targetable_paths()

    @folding_driver_errors
    def path_is_targetable(self, record_path: RecordPath) -> bool:
        return self.get(record_path)['$delegate$able']

    @folding_driver_errors
    def list_targetable_children( self, record_path: RecordPath,
    ) -> Iterable[RecordPath]:
        for name in self.get(record_path):
            if name.startswith('$'):
                continue
            assert '/' not in name
            child_path = record_path / name
            if self.get(child_path)['$delegate$able']:
                yield child_path

    @folding_driver_errors
    def produce_document_recipe( self, target: Target,
    ) -> DocumentRecipe:
        return self._generate_document_recipe(target)

    @folding_driver_errors
    def produce_document_asy_context( self, target: Target,
    ) -> Tuple[Compiler, str]:
        """Return (latex_compiler, latex_preamble)."""
        record = self.get(target.path)
        document_target = self._get_attuned_target(target, record)
        asy_latex_compilers: List[Compiler] = []
        asy_latex_preamble = list(self._generate_asy_preamble_document(
            document_target, record,
            compilers=asy_latex_compilers ))
        asy_latex_preamble = list(self._reconcile_packages(
            asy_latex_preamble ))
        asy_latex_preamble_dt: DocumentTemplate = self._constitute_preamble(
            preamble=asy_latex_preamble )
        if len(asy_latex_compilers) != 1:
            raise DriverError(str(asy_latex_compilers))
        # pylint: disable=unbalanced-tuple-unpacking
        asy_latex_compiler, = asy_latex_compilers
        # pylint: enable=unbalanced-tuple-unpacking
        if asy_latex_preamble_dt.keys():
            raise DriverError(str(asy_latex_preamble_dt.keys()))
        asy_latex_preamble_s = asy_latex_preamble_dt.substitute({})
        return asy_latex_compiler, asy_latex_preamble_s

    @folding_driver_errors
    def produce_package_recipe( self, package_path: RecordPath,
    ) -> PackageRecipe:
        assert isinstance(package_path, RecordPath), type(package_path)
        return self._generate_package_recipe(package_path)

    @folding_driver_errors
    def produce_figure_recipe( self, figure_path: RecordPath,
        *, figure_types: FrozenSet[str] = frozenset(('pdf', 'png', 'jpg')),
    ) -> FigureRecipe:
        assert isinstance(figure_path, RecordPath), type(figure_path)
        assert isinstance(figure_types, frozenset), type(figure_types)
        return self._generate_figure_recipe(figure_path, figure_types)


    ##########
    # Record extension {{{2

    def _derive_record( self,
        parent_record: Record, child_record: Record, path: RecordPath,
    ) -> None:
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

    def _generate_targetable_paths( self, path: RecordPath = None,
    ) -> Iterable[RecordPath]:
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

    @classmethod
    def get_dropped_keys(cls) -> Dict[str, str]:
        dropped_keys = super().get_dropped_keys()
        dropped_keys.update({
            '$manner' : '$document$content',
            '$rigid'  : '$document$content',
            '$fluid'  : '$content',
            '$manner$style'   : '$document$style',
            '$manner$options' : '$document$style',
            '$out$options'    : '$document$style',
            '$fluid$opt'      : '$document$style',
            '$rigid$opt'      : '$document$style',
            '$manner$opt'     : '$document$style',
            '$build$special'  : '$document$style',
            '$build$options'  : '$document$outname',
            '$required$packages' : '$content: [{style: [{package: …}]}]',
            '$latex$packages'    : '$content: [{style: [{package: …}]}]',
            '$tex$packages'      : '$content: [{style: [{package: …}]}]',
            '$target$delegate' : '$delegate',
            '$targetable' : '$delegate$able',
            '$delegate$stop' : '$delegate',
            '$target$able' : '$delegate$able',
            '$build$able' : '$content$able',
            '$build$outname' : '$document$outname',
            '$build$matter' : '$document$content',
            '$build$style' : '$document$style',
            '$matter' : '$content',
            '$training$matter$combine' : '$content',
            '$training$matter$chapter' : '$content: [{special: …}]',
        })
        return dropped_keys


    ##########
    # Record-level functions (delegate) {{{2

    @processing_target
    def _generate_targets( self,
        target: Target, record: Optional[Record] = None,
        *, _seen_targets: Optional[SeenItems[Target]] = None,
    ) -> Iterable[Target]:
        if record is None:
            record = self.get(target.path)
        if not record.get('$delegate$able', True):
            raise DriverError( f"Target {target} is not targetable" )
        delegate_key, delegate = self.select_flagged_item(
            record, '$delegate', target.flags )
        if _seen_targets is None:
            _seen_targets = SeenItems[Target]()
        with _seen_targets.look(target):
            if delegate_key is None:
                yield from self._generate_targets_auto( target, record,
                    _seen_targets=_seen_targets )
                return
            yield from self._generate_targets_delegate( target, record,
                delegate_key=delegate_key, delegate=delegate,
                _seen_targets=_seen_targets )

    @processing_target
    def _generate_targets_delegate( self,
        target: Target, record: Record,
        *, delegate_key: str, delegate: Any, _recursed: bool = False,
        _seen_targets: SeenItems[Target],
    ) -> Iterable[Target]:
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

    def _generate_targets_delegate_item( self,
        target: Target, record: Record,
        *, delegate_key: str, delegate_item: Any, _recursed: bool,
        _seen_targets: SeenItems[Target],
    ) -> Iterable[Target]:
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

    def _generate_targets_delegate_children( self,
        target: Target, record: Record,
        *, delegate_item: Dict,
        _seen_targets: SeenItems[Target],
    ) -> Iterable[Target]:
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

    @processing_target
    def _generate_targets_children( self,
        target: Target, record: Record,
        *, exclude: Collection[str] = frozenset(),
        _seen_targets: SeenItems[Target],
    ) -> Iterable[Target]:
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

    @processing_target
    def _generate_targets_auto( self,
        target: Target, record: Record,
        *, _seen_targets: SeenItems[Target],
    ) -> Iterable[Target]:
        if not record.get('$delegate$auto', False):
            yield target
            return
        if record.get('$source$able', False):
            yield from self._generate_targets_auto_source( target, record,
                _seen_targets=_seen_targets )
            return
        yield from self._generate_targets_children( target, record,
            _seen_targets=_seen_targets )

    @processing_target
    def _generate_targets_auto_source( self,
        target: Target, record: Record,
        *, _seen_targets: SeenItems[Target],
    ) -> Iterable[Target]:
        yield target
        return


    ##########
    # Document body and preamble items {{{2

    class BodyItem:
        __slots__ = ()

    class VerbatimBodyItem(BodyItem):
        """These items represent a piece of LaTeX code."""
        __slots__ = ['value']
        value: str

        def __init__(self, value: str) -> None:
            super().__init__()
            if not isinstance(value, str):
                raise RuntimeError(type(value))
            self.value = value

    class SourceBodyItem(BodyItem):
        """These items represent inclusion of a source file."""
        __slots__ = ['record_path']
        record_path: RecordPath
        include_command: ClassVar[str] = r'\input'
        file_suffix: ClassVar[str] = '.tex'

        def __init__(self, record_path: RecordPath) -> None:
            super().__init__()
            if not isinstance(record_path, RecordPath):
                raise RuntimeError(type(record_path))
            self.record_path = record_path

        @property
        def source_path(self) -> PurePosixPath:
            return self.record_path.as_source_path(suffix=self.file_suffix)

    class DocSourceBodyItem(SourceBodyItem):
        __slots__ = ()
        include_command = r'\DocInput'
        file_suffix = '.dtx'

    class FigureDefBodyItem(BodyItem):
        __slots__ = ['figure_ref', 'figure_path']
        figure_ref: str
        figure_path: RecordPath

        def __init__(self, figure_ref: str, figure_path: RecordPath) -> None:
            if not isinstance(figure_ref, str):
                raise DriverError(type(figure_ref))
            self.figure_ref = figure_ref
            if not isinstance(figure_path, RecordPath):
                raise RuntimeError(type(figure_path))
            self.figure_path = figure_path

    class NewPageBodyItem(VerbatimBodyItem):
        __slots__ = ()
        _value: ClassVar[str] = r'\clearpage' '\n'

        def __init__(self) -> None:
            super().__init__(value=self._value)

    class PreambleItem:
        __slots__ = ()

    class VerbatimPreambleItem(PreambleItem):
        __slots__ = ['value']
        value: str

        def __init__(self, value: str) -> None:
            super().__init__()
            if not isinstance(value, str):
                raise DriverError(type(value))
            self.value = value

    class LocalPackagePreambleItem(PreambleItem):
        __slots__ = ['package_path']
        package_path: RecordPath

        def __init__(self, package_path: RecordPath):
            super().__init__()
            if not isinstance(package_path, RecordPath):
                raise RuntimeError(type(package_path))
            self.package_path = package_path

    class ProvideVerbatimPreambleItem(PreambleItem):
        __slots__ = ['key', 'value']
        key: str
        value: Optional[str]

        def __init__(self, key: str, value: Optional[str]):
            super().__init__()
            if not isinstance(key, str):
                raise DriverError(type(key))
            if value is not None and not isinstance(value, str):
                raise DriverError(type(value))
            self.key = key
            self.value = value

    class ProvidePackagePreambleItem(PreambleItem):
        __slots__ = [ 'package',
            'options_required', 'options_suggested', 'options_prohibited']
        package: str
        options_required: Sequence[str]
        options_suggested: Sequence[str]
        options_prohibited: Sequence[str]

        def __init__(self,
            package: str,
            options: Any = None,
        ) -> None:
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
        def _list_of_strings(what: Any) -> Sequence[str]:
            if not isinstance(what, (list, tuple)):
                raise DriverError(type(what))
            result: List[str] = []
            for item in what:
                if not isinstance(item, str):
                    raise DriverError(type(item))
                result.append(str(item))
            return result

    class ProhibitPackagePreambleItem(PreambleItem):
        __slots__ = ['package']

        def __init__(self, package: str):
            if not isinstance(package, str):
                raise DriverError(type(package))
            self.package = package
            super().__init__()

    class PackagePreambleItem(PreambleItem):
        # Only produced by reconciling package options.
        __slots__ = ['package', 'options']
        package: str
        options: Sequence[str]

        def __init__(self, package: str, options: Sequence[str]):
            super().__init__()
            assert isinstance(package, str)
            self.package = package
            assert isinstance(options, list)
            assert all(isinstance(option, str) for option in options)
            self.options = options

    class Author:
        __slots__ = ['name', 'abbr']
        name: str
        abbr: str

        def __init__(self, author_item: Any) -> None:
            if isinstance(author_item, RegularDriver.Author):
                self.name = author_item.name
                self.abbr = author_item.abbr
            elif isinstance(author_item, dict):
                if not {'name'} <= author_item.keys() <= {'name', 'abbr'}:
                    raise DriverError(author_item.keys())
                if not isinstance(author_item['name'], str):
                    raise DriverError(type(author_item['name']))
                self.name = author_item['name']
                if 'abbr' in author_item:
                    if not isinstance(author_item['abbr'], str):
                        raise DriverError(type(author_item['abbr']))
                    self.abbr = author_item['abbr']
                else:
                    self.abbr = self._abbreviate(self.name)
            elif isinstance(author_item, str):
                self.name = author_item
                self.abbr = self._abbreviate(self.name)
            else:
                raise DriverError(type(author_item))

        def __str__(self) -> str:
            return self.name

        def __repr__(self) -> str:
            if self.abbr is None:
                return f'Author({self.name})'
            else:
                return f'Author(name={self.name}, abbr={self.abbr})'

        _thin_space: ClassVar[str] = r'\,'

        @classmethod
        def _abbreviate(cls, name: str) -> str:
            *names, last = name.split(' ')
            return cls._thin_space.join(
                [name[0] + '.' for name in names] + [last] )

    ##########
    # Record-level functions (document_recipe) {{{2

    class _HeaderInfo(TypedDict):
        dates: List[Union[None, DatePeriod, str]]
        captions: List[Optional[str]]
        authors: List['RegularDriver.Author']

    @processing_target
    def _generate_document_recipe( self,
        target: Target, record: Optional[Record] = None,
    ) -> DocumentRecipe:
        if record is None:
            record = self.get(target.path)
        if not record['$delegate$able'] or \
                not record['$content$able']:
            raise DriverError( "Target {target} is not buildable"
                .format(target=target) )
        if target.path.is_root():
            raise DriverError("Direct building of '/' is prohibited." )

        document_recipe = DocumentRecipe()

        compilers: List[Compiler] = []
        header_info: 'RegularDriver._HeaderInfo' = \
            {'dates' : [], 'captions' : [], 'authors' : []}

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

        document_recipe.outname = self._select_outname(
            target, record,
            date=self._min_date(header_info['dates']) )

        if not compilers:
            raise DriverError("Compiler is not specified")
        if len(compilers) > 1:
            raise DriverError("Compiler is specified multiple times")
        # pylint: disable=unbalanced-tuple-unpacking
        document_recipe.compiler, = compilers
        # pylint: enable=unbalanced-tuple-unpacking

        preamble = list(self._reconcile_packages(preamble))
        with process_target_aspect(target, 'document'):
            document_recipe.document = \
                self._constitute_document(
                    document_recipe, preamble=preamble, body=body, )

        return document_recipe

    _outname_regex = re.compile(OUTNAME_PATTERN)

    def _select_outname( self,
        target: Target, record: Record,
        date: Union[None, DatePeriod, str] = None,
    ) -> str:
        """Return outname, except for date part."""
        outname_key, outname = self.select_flagged_item(
            record, '$document$outname', target.flags )
        if outname_key is not None:
            if not isinstance(outname, str):
                raise DriverError("Outname must be a string.")
            key_match = self._attribute_key_regex.fullmatch(outname_key)
            if key_match is None:
                raise DriverError(repr(outname_key))
            outname_match = self._outname_regex.fullmatch(outname)
            if outname_match is None:
                raise DriverError(repr(outname))
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

    def _select_outname_auto( self,
        target: Target, record: Record,
        date: Union[None, DatePeriod, str] = None,
    ) -> str:
        """Return outname."""
        outname_base = '-'.join(target.path.parts)
        outname_flags = target.flags.__format__('optional')
        outname = outname_base + outname_flags
        if isinstance(date, DatePeriod):
            outname = str(Period(date)) + '-' + outname
        return outname

    def _get_attuned_target( self,
        target: Target, record: Record,
    ) -> Target:
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

    @processing_target
    def _generate_preamble_document( self,
        target: Target,
        record: Optional[Record] = None,
     *, compilers: List[Compiler],
    ) -> Iterable[PreambleItem]:
        if record is None:
            record = self.get(target.path)
        style_key, style = self.select_flagged_item(
            record, '$document$style', target.flags,
        )
        if style_key is None:
            yield from self._generate_preamble( target, record,
                compilers=compilers,
                _seen_targets=SeenItems[Target]() )
        else:
            yield from self._generate_preamble_style( target, record,
                style_key=style_key, style=style,
                compilers=compilers,
                _seen_targets=SeenItems[Target]() )

    @processing_target
    def _generate_preamble( self,
        target: Target, record: Optional[Record] = None,
     *, compilers: List[Compiler],
        _seen_targets: SeenItems[Target],
    ) -> Iterable[PreambleItem]:
        if record is None:
            record = self.get(target.path)
        style_key, style = self.select_flagged_item(
            record, '$style', target.flags,
        )
        with _seen_targets.look(target):
            if style_key is None:
                yield from self._generate_preamble_auto( target, record,
                    compilers=compilers,
                    _seen_targets=_seen_targets )
            else:
                yield from self._generate_preamble_style( target, record,
                    style_key=style_key, style=style,
                    compilers=compilers,
                    _seen_targets=_seen_targets )

    @processing_target
    def _generate_preamble_style( self,
        target: Target, record: Record,
     *, style_key: str, style: Any,
        _recursed: bool = False,
        compilers: List[Compiler],
        _seen_targets: SeenItems[Target],
    ) -> Iterable[PreambleItem]:
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

    def _generate_preamble_style_item( self,
        target: Target, record: Record,
     *, style_key: str, style_item: Any, _recursed: bool,
        compilers: List[Compiler],
        _seen_targets: SeenItems[Target],
    ) -> Iterable[PreambleItem]:
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
            compiler = Compiler(style_item['compiler'])
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

    def _generate_preamble_style_simple( self,
        style_item: Dict,
    ) -> Iterable[PreambleItem]:
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

    def _generate_preamble_style_verbatim( self,
        style_item: Dict,
    ) -> Iterable[PreambleItem]:
        if style_item.keys() == {'verbatim'}:
            if not isinstance(style_item['verbatim'], str):
                raise DriverError(type(style_item['verbatim']))
            yield self.VerbatimPreambleItem(style_item['verbatim'])
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

    def _generate_preamble_style_package( self,
        style_item: Dict,
    ) -> Iterable[PreambleItem]:
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

    @processing_target
    def _generate_preamble_auto( self,
        target: Target, record: Record,
        *, compilers: List[Compiler],
        _seen_targets: SeenItems[Target],
    ) -> Iterable[PreambleItem]:
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
    # Record-level functions (asy context preamble) {{{2

    @processing_target
    def _generate_asy_preamble_document( self,
        target: Target, record: Optional[Record] = None,
        *, compilers: List[Compiler],
    ) -> Iterable[PreambleItem]:
        if record is None:
            record = self.get(target.path)
        style_asy_key, style_asy = self.select_flagged_item(
            record, '$document$style$asy', target.flags,
        )
        if style_asy_key is None:
            yield from self._generate_asy_preamble( target, record,
                compilers=compilers,
                _seen_targets=SeenItems[Target]() )
        else:
            yield from self._generate_asy_preamble_style_asy( target, record,
                style_asy_key=style_asy_key, style_asy=style_asy,
                compilers=compilers,
                _seen_targets=SeenItems[Target]() )

    @processing_target
    def _generate_asy_preamble( self,
        target: Target, record: Optional[Record] = None,
        *, compilers: List[Compiler],
        _seen_targets: SeenItems[Target],
    ) -> Iterable[PreambleItem]:
        if record is None:
            record = self.get(target.path)
        style_asy_key, style_asy = self.select_flagged_item(
            record, '$style$asy', target.flags,
        )
        with _seen_targets.look(target):
            if style_asy_key is None:
                yield from self._generate_asy_preamble_auto(
                    target, record,
                    compilers=compilers,
                    _seen_targets=_seen_targets )
            else:
                yield from self._generate_asy_preamble_style_asy(
                    target, record,
                    style_asy_key=style_asy_key, style_asy=style_asy,
                    compilers=compilers,
                    _seen_targets=_seen_targets )

    @processing_target
    def _generate_asy_preamble_style_asy( self,
        target: Target, record: Record,
        *, style_asy_key: str, style_asy: Any, _recursed: bool = False,
        compilers: List[Compiler],
        _seen_targets: SeenItems[Target],
    ) -> Iterable[PreambleItem]:
        with process_target_key(target, style_asy_key):
            if not isinstance(style_asy, list):
                raise DriverError(
                     "$style$asy must be a list, "
                    f"not {type(style_asy)}" )
            for item in style_asy:
                yield from self._generate_asy_preamble_style_asy_item(
                    target, record,
                    style_asy_key=style_asy_key, style_asy_item=item,
                    _recursed=_recursed,
                    compilers=compilers,
                    _seen_targets=_seen_targets )

    def _generate_asy_preamble_style_asy_item( self,
        target: Target, record: Record,
        *, style_asy_key: str, style_asy_item: Any, _recursed: bool,
        compilers: List[Compiler],
        _seen_targets: SeenItems[Target],
    ) -> Iterable[PreambleItem]:
        if isinstance(style_asy_item, str):
            yield from self._generate_asy_preamble(
                target.derive_from_string( style_asy_item,
                    origin=f'asy-style {target}, key {style_asy_key}' ),
                compilers=compilers,
                _seen_targets=_seen_targets )
            return

        if not isinstance(style_asy_item, dict):
            raise DriverError(
                 "$style item must be a string or a dictionary, "
                f"not {type(style_asy_item)}" )
        style_asy_item = style_asy_item.copy()
        condition = style_asy_item.pop('condition', True)
        if not target.flags.check_condition(condition):
            return
        if 'style-asy' in style_asy_item.keys():
            if style_asy_item.keys() != {'style-asy'}:
                raise DriverError(style_asy_item.keys())
            if _recursed:
                raise DriverError("Nested 'style-asy' items are not allowed.")
            yield from self._generate_asy_preamble_style_asy( target, record,
                style_asy_key=style_asy_key+"/style-asy",
                style_asy=style_asy_item['style-asy'],
                _recursed=True,
                compilers=compilers,
                _seen_targets=_seen_targets )
        if 'style' in style_asy_item.keys():
            if style_asy_item.keys() != {'style'}:
                raise DriverError(style_asy_item.keys())
            yield from self._generate_preamble_style( target, record,
                style_key=style_asy_key+"/style",
                style=style_asy_item['style'],
                _recursed=True,
                compilers=compilers,
                _seen_targets=_seen_targets )
        elif 'compiler' in style_asy_item.keys():
            if style_asy_item.keys() != {'compiler'}:
                raise DriverError(style_asy_item.keys())
            compiler = Compiler(style_asy_item['compiler'])
            if not isinstance(compiler, str):
                raise DriverError(type(compiler))
            if compiler not in {'latex', 'pdflatex', 'xelatex', 'lualatex'}:
                raise DriverError(compiler)
            compilers.append(compiler)
        else:
            yield from self._generate_preamble_style_simple(style_asy_item)

    @processing_target
    def _generate_asy_preamble_auto( self,
        target: Target, record: Record,
        *, compilers: List[Compiler],
        _seen_targets: SeenItems[Target],
    ) -> Iterable[PreambleItem]:
        if not record.get('$style$auto', True):
            raise DriverError("$style is not defined")
        if target.path.is_root():
            raise DriverError("Toplevel $style$asy is not defined")
        yield from self._generate_asy_preamble(
            target.path_derive('..'),
            compilers=compilers,
            _seen_targets=_seen_targets )


    ##########
    # Record-level functions (document body) {{{2

    @processing_target
    def _generate_body_document( self,
        target: Target, record: Optional[Record] = None,
        *, preamble: List[PreambleItem], header_info: _HeaderInfo,
    ) -> Iterable[BodyItem]:
        if record is None:
            record = self.get(target.path)
        content_key, content = self.select_flagged_item(
            record, '$document$content', target.flags )
        if content_key is None:
            yield from self._generate_body( target, record,
                preamble=preamble,
                header_info=header_info,
                _seen_targets=SeenItems[Target]() )
        else:
            yield from self._generate_body_content( target, record,
                content_key=content_key, content=content,
                preamble=preamble,
                header_info=header_info,
                _seen_targets=SeenItems[Target]() )

    @processing_target
    def _generate_body( self,
        target: Target, record: Optional[Record] = None,
        *, preamble: List[PreambleItem], header_info: _HeaderInfo,
        _seen_targets: SeenItems[Target],
    ) -> Iterable[BodyItem]:
        if record is None:
            record = self.get(target.path)
        content_key, content = self.select_flagged_item(
            record, '$content', target.flags )
        with _seen_targets.look(target):
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
    def _generate_body_content(self,
        target: Target, record: Record,
        *, content_key: str, content: Any, _recursed: bool = False,
        preamble: List[PreambleItem], header_info: _HeaderInfo,
        _seen_targets: SeenItems[Target],
    ) -> Iterable[BodyItem]:
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

    def _generate_body_content_item( self,
        target: Target, record: Record,
        *, content_key: str, content_item: Any, _recursed: bool,
        preamble: List[PreambleItem], header_info: _HeaderInfo,
        _seen_targets: SeenItems[Target],
    ) -> Iterable[BodyItem]:
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
            yield self.VerbatimBodyItem(content_item['verbatim'])
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
                preamble.extend(
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

    _PreHeader = Union[None, Literal[False], Dict[Any, Any]]

    class _Header(TypedDict):
        date: Union[None, DatePeriod, str]
        caption: Optional[str]
        authors: Optional[Sequence['RegularDriver.Author']]

    def _generate_body_content_content( self,
        target: Target, record: Record,
        *, content_key: str, content_item: Any,
        preamble: List[PreambleItem], header_info: _HeaderInfo,
        _seen_targets: SeenItems[Target],
    ) -> Iterable[BodyItem]:
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

        pre_header: 'RegularDriver._PreHeader' = None
        if 'header' in content_item:
            if content_item['header'] is False:
                pre_header = False
            elif content_item['header'] is None:
                pre_header = {}
            elif content_item['header'] is True:
                pre_header = {}
            elif isinstance(content_item['header'], dict):
                pre_header = content_item['header'].copy()
            else:
                raise DriverError( "In 'content' item, "
                    "the value of 'header' must be false or a list, "
                   f"not {type(newpage)}" )

        yield from self._generate_body_headered_content(
            target, record,
            content_key=content_key+'/content', content=content,
            pre_header=pre_header, newpage=newpage,
            preamble=preamble, header_info=header_info,
            _seen_targets=_seen_targets )

    def _generate_body_content_figure( self,
        target: Target, record: Record,
        *, content_item: Any,
    ) -> Iterable[BodyItem]:
        if not isinstance(content_item['figure'], str):
            raise DriverError(type(content_item['figure']))
        if 'options' in content_item:
            if not isinstance(content_item['options'], list):
                raise DriverError(type(content_item['options']))
            for option in content_item['options']:
                if not isinstance(option, str):
                    raise DriverError(type(option))
            options: Optional[List[str]] = content_item['options']
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

    def _generate_body_headered_content( self,
        target: Target, record: Record,
        *, content_key: str, content: Any,
        pre_header: _PreHeader,
        newpage: bool = True,
        preamble: List[PreambleItem], header_info: _HeaderInfo,
        _seen_targets: SeenItems[Target],
    ) -> Iterable[BodyItem]:

        def generate_body(*,
            header_info: 'RegularDriver._HeaderInfo' = header_info
        ) -> Iterable['RegularDriver.BodyItem']:
            yield from (
                self._generate_body_content( target, record,
                    content_key=content_key, content=content,
                    preamble=preamble, header_info=header_info,
                    _seen_targets=_seen_targets )
            )

        if newpage:
            yield self.NewPageBodyItem()

        if pre_header is None:
            yield from generate_body()
        elif pre_header is False:
            target = target.flags_union({Flag('contained')})
            yield from generate_body()
        else:
            assert isinstance(pre_header, dict)
            target = target.flags_union({Flag('contained')})
            content_header_info: 'RegularDriver._HeaderInfo' = \
                {'dates' : [], 'captions' : [], 'authors' : []}
            body = list(generate_body(header_info=content_header_info))
            header: 'RegularDriver._Header' = \
                self._prepare_body_header( target, record,
                    pre_header,
                    super_header_info=header_info,
                    header_info=content_header_info )
            yield from self._generate_body_header( target, record,
                header=header )
            yield from body

        if newpage:
            if not content and header is None:
                yield self.VerbatimBodyItem(r'\null')
            yield self.NewPageBodyItem()

    def _prepare_body_header( self,
        target: Target, record: Record, pre_header: Dict[Any, Any],
        *, super_header_info: _HeaderInfo, header_info: _HeaderInfo,
    ) -> _Header:

        # date
        if 'date' not in pre_header:
            date = self._min_date(header_info['dates'])
        else:
            if pre_header['date'] is None:
                date = None
            elif not isinstance(pre_header['date'], (DatePeriod, str)):
                raise DriverError(type(pre_header['date']))
            else:
                date = pre_header['date']
        if date is not None:
            super_header_info['dates'].append(date)

        # caption
        if 'caption' not in pre_header:
            caption = self._join_captions(header_info['captions'])
        else:
            if pre_header['caption'] is None:
                caption = None
            elif not isinstance(pre_header['caption'], str):
                raise DriverError(type(pre_header['caption']))
            else:
                caption = pre_header['caption']
        if caption is not None:
            super_header_info['captions'].append(caption)

        # authors
        if 'authors' not in pre_header:
            authors = self._unique_authors(header_info['authors'])
        else:
            if pre_header['authors'] is None:
                authors = None
            elif not isinstance(pre_header['authors'], list):
                raise DriverError(type(pre_header['authors']))
            else:
                authors = [ self.Author(author)
                    for author in pre_header['authors'] ]
        if authors is not None:
            super_header_info['authors'].extend(authors)

        return {'date' : date, 'caption' : caption, 'authors' : authors}

    def _generate_body_header( self,
        target: Target, record: Record,
        *, header: _Header,
    ) -> Iterable[BodyItem]:
        yield self.VerbatimBodyItem(
            self.jeolmheader_begin_template.substitute() )
        yield from self._generate_body_header_def(
            target, record, header=header )
        yield self.VerbatimBodyItem(
            self.jeolmheader_end_template.substitute() )
        yield self.VerbatimBodyItem(
            self.resetproblem_template.substitute() )

    def _generate_body_header_def( self,
        target: Target, record: Record,
        *, header: _Header,
    ) -> Iterable[BodyItem]:
        if header['date'] is not None:
            yield self.VerbatimBodyItem(
                self._constitute_date_def(date=header['date']) )
        if header['caption'] is not None:
            yield self.VerbatimBodyItem(
                self._constitute_caption_addtoc(caption=header['caption']) )
        if header['authors'] is not None:
            yield self.VerbatimBodyItem(
                self._constitute_authors_def(author_list=header['authors']) )

    def _generate_body_content_children( self,
        target: Target, record: Record,
        *, content_item: Dict,
        preamble: List[PreambleItem], header_info: _HeaderInfo,
        _seen_targets: SeenItems[Target],
    ) -> Iterable[BodyItem]:
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
        order: Literal[None, 'record', 'date'] = content_item.get('order')
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

    _ChildItem = Tuple[List[BodyItem], List[PreambleItem], _HeaderInfo]

    @processing_target
    def _generate_body_children( self,
        target: Target, record: Record,
        *, exclude: Collection[str] = frozenset(),
        order: Literal[None, 'record', 'date'] = None,
        preamble: List[PreambleItem], header_info: _HeaderInfo,
        _seen_targets: SeenItems[Target],
    ) -> Iterable[BodyItem]:
        exclude = frozenset(exclude)
        child_bodies: List['RegularDriver._ChildItem'] = []
        for key in record:
            if key.startswith('$'):
                continue
            if key in exclude:
                continue
            child_target = target.path_derive(key)
            child_record = self.get(child_target.path)
            if not child_record.get('$content$child'):
                continue
            child_preamble: List['RegularDriver.PreambleItem'] = []
            child_header_info: 'RegularDriver._HeaderInfo' = \
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
            def date_key(item: 'RegularDriver._ChildItem') -> Any:
                body, preamble, header_info = item
                key = self._min_date(header_info['dates'])
                if key is not None:
                    return key
                else:
                    return Never
            child_bodies.sort(key=date_key)
        else:
            raise RuntimeError(order)
        for child_body, child_preamble, child_header_info in child_bodies:
            preamble.extend(child_preamble)
            header_info['dates'].extend(child_header_info['dates'])
            header_info['captions'].extend(child_header_info['captions'])
            header_info['authors'].extend(child_header_info['authors'])
            yield from child_body

    @processing_target
    def _generate_body_auto( self,
        target: Target, record: Record,
        *, preamble: List[PreambleItem], header_info: _HeaderInfo,
        _seen_targets: SeenItems[Target],
    ) -> Iterable[BodyItem]:
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
    def _generate_body_auto_source( self,
        target: Target, record: Record,
        *, preamble: List[PreambleItem], header_info: _HeaderInfo,
        _seen_targets: SeenItems[Target],
    ) -> Iterable[BodyItem]:
        if 'contained' in target.flags:
            yield from self._generate_body_source( target, record,
                preamble=preamble, header_info=header_info,
                _seen_targets=_seen_targets )
        else:
            yield from self._generate_body_headered_content( target, record,
                content_key='$content$auto',
                content=['.'],
                pre_header={},
                preamble=preamble, header_info=header_info,
                _seen_targets=_seen_targets )

    @processing_target
    def _generate_body_source( self,
        target: Target, record: Optional[Record] = None,
        *, preamble: List[PreambleItem], header_info: _HeaderInfo,
        _seen_targets: SeenItems[Target],
    ) -> Iterable[BodyItem]:
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
    def _get_source_type_key(source_type: str) -> str:
        return '$source$type${}'.format(source_type)

    def _get_source_date( self,
        target: Target, record: Record,
    ) -> Union[None, DatePeriod, str]:
        date = record.get('$date', None)
        if date is None:
            return None
        elif isinstance(date, DatePeriod):
            return Period(date) # type: ignore
        elif isinstance(date, str):
            return date
        else:
            raise DriverError(type(date))

    def _get_source_caption( self,
        target: Target, record: Record,
    ) -> Optional[str]:
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

    def _get_source_authors( self,
        target: Target, record: Record,
    ) -> Sequence[Author]:
        authors = record.get('$authors', ())
        if not isinstance(authors, (list, tuple)):
            raise DriverError(type(authors))
        return [self.Author(author) for author in authors]

    @processing_target
    def _generate_body_source_figure_def( self,
        target: Target, record: Record,
    ) -> Iterable[BodyItem]:
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

    class _PackageOptions(TypedDict):
        required: List[str]
        suggested: List[str]
        prohibited: List[str]

    @classmethod
    def _reconcile_packages( cls,
        preamble: Sequence[PreambleItem],
    ) -> Iterable[PreambleItem]:
        # Resolve all package prohibitions and option
        # suggestions/prohibitions.
        prohibited_packages: Set[str] = set()
        package_options: Dict[str, 'RegularDriver._PackageOptions'] = {}
        provided_preamble: Dict[str, Optional[str]] = {}
        for item in preamble:
            if isinstance(item, cls.ProvidePackagePreambleItem):
                options = package_options.setdefault(
                    item.package,
                    { 'required' : [], 'suggested' : [], 'prohibited' : [] }
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
                if item.package not in package_options:
                    # package is already processed
                    continue
                options = package_options[item.package]
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
            elif isinstance(item, cls.ProvideVerbatimPreambleItem):
                if not cls._check_and_set( provided_preamble,
                        item.key, item.value ):
                    continue
                if item.value is None:
                    continue
                else:
                    yield cls.VerbatimPreambleItem(item.value)
            else:
                yield item

    ##########
    # Record-level functions (package_record) {{{2

    @processing_package_path
    def _generate_package_recipe( self, package_path: RecordPath
    ) -> PackageRecipe:
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

        return PackageRecipe(package_type, source_path, package_name)

    _package_types = ('dtx', 'sty',)

    @staticmethod
    def _get_package_type_key(package_type: str) -> str:
        return '$package$type${}'.format(package_type)

    @staticmethod
    def _get_package_name_key(package_type: str) -> str:
        return '$package${}$name'.format(package_type)

    @staticmethod
    def _get_package_suffix(package_type: str) -> str:
        return '.{}'.format(package_type)


    ##########
    # Record-level functions (figure_record) {{{2

    @processing_figure_path
    def _generate_figure_recipe( self,
        figure_path: RecordPath, figure_types: FrozenSet[str],
    ) -> FigureRecipe:
        try:
            record = self.get(figure_path)
        except RecordNotFoundError as error:
            raise DriverError('Figure not found') from error
        if not record.get('$figure$able', False):
            raise DriverError("Figure '{}' not found".format(figure_path))

        source_types = [ source_type
            for source_type in self._figure_source_types
            if self._figure_types[source_type] & figure_types
            if record.get(self._get_figure_type_key(source_type), False) ]
        if len(source_types) > 1:
            raise DriverError(source_types)
        source_type, = source_types
        figure_types = self._figure_types[source_type] & figure_types
        if len(figure_types) > 1:
            raise DriverError(figure_types)
        figure_type, = figure_types
        suffix = self._get_figure_suffix(source_type)
        source_path = figure_path.as_source_path(suffix=suffix)

        figure_recipe = FigureRecipe(figure_type, source_type, source_path)
        if source_type == 'asy':
            figure_recipe.other_sources = \
                self._find_figure_asy_other_sources(
                    figure_path, record )
            assert isinstance(figure_recipe.other_sources, dict)
        return figure_recipe

    _figure_source_types = ('asy', 'svg', 'pdf', 'eps', 'png', 'jpg',)
    _figure_types = {
        'asy' : {'pdf', 'eps'},
        'svg' : {'pdf', 'eps'},
        'pdf' : {'pdf'},
        'eps' : {'eps'},
        'png' : {'png'},
        'jpg' : {'jpg'},
    }

    @staticmethod
    def _get_figure_type_key(figure_type: str) -> str:
        return '$figure$type${}'.format(figure_type)

    @staticmethod
    def _get_figure_suffix(source_type: str) -> str:
        return '.{}'.format(source_type)

    @processing_figure_path
    def _find_figure_asy_other_sources( self,
        figure_path: RecordPath, record: Record,
    ) -> Dict[str, PurePosixPath]:
        other_sources: Dict[str, PurePosixPath] = dict()
        for accessed_name, source_path in (
            self._trace_figure_asy_other_sources(figure_path, record)
        ):
            self._check_and_set(other_sources, accessed_name, source_path)
        return other_sources

    @processing_figure_path
    def _trace_figure_asy_other_sources( self,
        figure_path: RecordPath, record: Optional[Record] = None,
        *, _seen_items: Set[Tuple[str, RecordPath]] = None
    ) -> Iterable[Tuple[str, PurePosixPath]]:
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
    def _constitute_document( cls,
        document_recipe: DocumentRecipe,
        preamble: List[PreambleItem],
        body: List[BodyItem],
    ) -> DocumentTemplate:
        document_template = DocumentTemplate()
        document_template.append_text(
            cls.document_compiler_template.substitute(
                compiler=document_recipe.compiler )
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
    def _constitute_preamble( cls,
        preamble: List[PreambleItem],
    ) -> DocumentTemplate:
        preamble_template = DocumentTemplate()
        cls._fill_preamble(preamble, preamble_template)
        return preamble_template

    @classmethod
    def _fill_preamble( cls,
        preamble: List[PreambleItem],
        document_template: DocumentTemplate,
    ) -> None:
        for item in preamble:
            assert isinstance(item, cls.PreambleItem), type(item)
            assert not isinstance(item, cls.ProvidePackagePreambleItem)
            assert not isinstance(item, cls.ProhibitPackagePreambleItem)
            assert not isinstance(item, cls.ProvideVerbatimPreambleItem)
            cls._fill_preamble_item(item, document_template)
            document_template.append_text('\n')

    @classmethod
    def _fill_preamble_item( cls, item: PreambleItem,
        document_template: DocumentTemplate
    ) -> None:
        if isinstance(item, cls.VerbatimPreambleItem):
            document_template.append_text(item.value)
        elif isinstance(item, cls.LocalPackagePreambleItem):
            document_template.append_text(
                cls.uselocalpackage_0_template.substitute() )
            document_template.append_key(
                DocumentRecipe.PackageKey(item.package_path) )
            document_template.append_text(
                cls.uselocalpackage_1_template.substitute(
                    package_path=str(item.package_path))
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
    def _constitute_options( cls,
        options: Union[None, str, Sequence[str]],
    ) -> str:
        if not options:
            return ''
        if not isinstance(options, str):
            options = ','.join(options)
        return '[' + options + ']'

    @classmethod
    def _fill_body( cls,
        body: List[BodyItem],
        document_template: DocumentTemplate,
    ) -> None:
        figure_counter: Dict[RecordPath, int] = {}
        for item in body:
            assert isinstance(item, cls.BodyItem), type(item)
            cls._fill_body_item( item, document_template,
                figure_counter=figure_counter )
            document_template.append_text('\n')

    @classmethod
    def _fill_body_item( cls, item: BodyItem,
        document_template: DocumentTemplate,
        *, figure_counter: Dict[RecordPath, int],
    ) -> None:
        if isinstance(item, cls.VerbatimBodyItem):
            document_template.append_text(item.value)
        elif isinstance(item, cls.SourceBodyItem):
            document_template.append_text(
                cls.input_0_template.substitute(
                    include_command=item.include_command )
            )
            document_template.append_key(
                DocumentRecipe.SourceKey(item.source_path) )
            document_template.append_text(
                cls.input_1_template.substitute(
                    source_path=str(item.source_path) )
            )
        elif isinstance(item, cls.FigureDefBodyItem):
            figure_index = figure_counter.setdefault(item.figure_path, 0)
            document_template.append_text(
                cls.jeolmfiguremap_0_template.substitute(
                    figure_ref=item.figure_ref )
            )
            document_template.append_key(
                DocumentRecipe.FigureKey(item.figure_path, figure_index) )
            document_template.append_text(
                cls.jeolmfiguremap_1_template.substitute()
            )
            document_template.append_key(
                DocumentRecipe.FigureSizeKey(item.figure_path, figure_index) )
            document_template.append_text(
                cls.jeolmfiguremap_2_template.substitute(
                    figure_path=str(item.figure_path) )
            )
            figure_counter[item.figure_path] = figure_index + 1;
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
    def _constitute_date_def(cls, date: Union[str, DatePeriod]) -> str:
        assert date is not None
        date_s = cls._constitute_date(date)
        if '%' in date_s:
            raise DriverError(
                "'%' symbol is found in the date: {}"
                .format(date_s) )
        return cls.date_def_template.substitute(date=date_s)

    date_def_template = Template(
        r'\def\jeolmdate{$date}%' )

    @classmethod
    def _constitute_date(cls, date: Union[str, DatePeriod]) -> str:
        if not isinstance(date, DatePeriod):
            return date
        if not isinstance(date, Period):
            date_p = Period(date)
        else:
            date_p = date
        date_s = cls.date_template.substitute(dateiso=date_p.date.isoformat())
        if date_p.period is not None:
            date_s += cls.period_template.substitute(period=str(date_p.period))
        return date_s

    date_template = Template(
        r'\DTMDate{$dateiso}' )
    period_template = Template(
        r'\jeolmdisplayperiod{$period}')

    @classmethod
    def _constitute_caption_addtoc(cls, caption: str) -> str:
        return cls.addtoc_template.substitute(caption=caption)

    addtoc_template = Template(
        r'\phantomsection\addcontentsline{toc}{section}{$caption}' )

    @classmethod
    def _constitute_authors_def(cls, author_list: Sequence[Author]) -> str:
        authors = cls._constitute_authors(author_list)
        if '%' in authors:
            raise DriverError(
                "'%' symbol is found in the list of authors: {}"
                .format(authors) )
        return cls.authors_def_template.substitute(authors=authors)

    @classmethod
    def _constitute_authors( cls, author_list: Sequence[Author],
        *, thin_space: str = r'\,',
    ) -> str:
        if not author_list:
            return ''
        elif len(author_list) == 1:
            author, = author_list
            return str(author)
        else:
            return ', '.join(author.abbr for author in author_list)

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

    @staticmethod
    def _min_date( dates: Sequence[Union[None, DatePeriod, str]]
    ) -> Union[None, DatePeriod, str]:
        dates = [ date
            for date in dates
            if date is not None ]
        if not dates:
            return None
        if len(dates) == 1:
            date, = dates
            return date
        if all(
            isinstance(date, DatePeriod)
            for date in dates
        ):
            return min(dates)
        return None

    @staticmethod
    def _join_captions(captions: List[Optional[str]]) -> Optional[str]:
        real_captions: List[str] = [ caption
            for caption in captions if caption is not None ]
        if not real_captions:
            return None
        if len(real_captions) == 1:
            caption, = real_captions
            return caption
        assert all(isinstance(caption, str) for caption in real_captions)
        return "; ".join(real_captions)

    @classmethod
    def _unique_authors( cls, authors: Sequence[Author],
    ) -> Optional[Sequence[Author]]:
        unique_authors: Dict[str, 'RegularDriver.Author'] = OrderedDict()
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
    def _check_and_set( mapping: MutableMapping[K, V],
        key: K, value: V,
    ) -> bool:
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
