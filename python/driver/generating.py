import datetime
from functools import wraps, partial
from collections import OrderedDict
import abc

from pathlib import PurePosixPath

from ..records import RecordPath, RecordNotFoundError
from ..target import Target
from .base import BaseDriver, DriverError

import logging
logger = logging.getLogger(__name__)

class GeneratingDriver(BaseDriver):

    ##########
    # High-level functions
    # (not dealing with metarecords and LaTeX strings directly)

    @processing_target_aspect(aspect='outrecord')
    def generate_outrecord(self, target):
        if target.path == RecordPath():
            raise DriverError("Direct building of '/' is prohibited." )
        outrecord = self.generate_protorecord(target)
        target.check_unutilized_flags()
        assert outrecord.keys() >= {
            'date', 'inpaths', 'figpaths', 'metapreamble', 'metabody'
        }, outrecord.keys()

        outrecord['outname'] = self.select_outname(
            target, date=outrecord['date'] )
        outrecord['buildname'] = self.select_outname(
            target, date=None )

        with self.process_target_aspect(target, 'document'):
            outrecord['document'] = self.constitute_document(
                outrecord,
                metapreamble=outrecord.pop('metapreamble'),
                metabody=outrecord.pop('metabody'), )
        return outrecord

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

    def generate_figrecord(self, figpath):
        assert isinstance(figpath, RecordPath), type(figpath)
        figtype, inpath = self.find_figure_type(figpath)
        assert isinstance(inpath, PurePosixPath), type(inpath)
        assert not inpath.is_absolute(), inpath

        figrecord = dict()
        figrecord['buildname'] = figpath.__format__('join')
        figrecord['source'] = inpath
        figrecord['type'] = figtype

        if figtype == 'asy':
            used_items = list(self.trace_asy_used(figpath))
            used = figrecord['used'] = dict(used_items)
            if len(used) != len(used_items):
                raise DriverError(inpath, used_items)

        return figrecord


    ##########
    # Metabody and metapreamble items

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
        __slots__ = ['inpath', 'alias', 'figalias_map']

        def __init__(self, inpath):
            self.inpath = PurePosixPath(inpath)
            if self.inpath.is_absolute():
                raise RuntimeError(inpath)
            super().__init__()

    class LaTeXPackageBodyItem(MetabodyItem):
        __slots__ = ['latex_package']

        def __init__(self, latex_package):
            self.latex_package = str(latex_package)
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
        elif 'latex_package' in item:
            if not item.keys() == {'latex_package'}:
                raise DriverError(item)
            return cls.LaTeXPackageBodyItem(**item)
        else:
            raise DriverError(item)

    @classmethod
    def classify_matter_item(cls, item, *, default):
        if isinstance(item, Target):
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
        if isinstance(item, Target):
            return item
        return cls.classify_metapreamble_item(item, default=default)

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
    # Record-level functions

    @fetching_metarecord
    @processing_target_aspect(aspect='protorecord')
    def generate_protorecord(self, target, metarecord):
        """
        Return protorecord.
        """
        date_set = set()

        protorecord = {}
        options_key, options = self.select_flagged_item(
            metarecord, '$manner$options', target.flags )
        if options is not None:
            with self.process_target_key(target, options_key):
                if not isinstance(options, dict):
                    raise DriverError(type(options))
                protorecord.update(options)
        # We must exhaust generate_metabody() to fill date_set
        metabody = list(self.generate_metabody(
            target, metarecord, date_set=date_set ))
        metapreamble = list(self.generate_metapreamble(
            target, metarecord ))

        inpaths = protorecord['inpaths'] = OrderedDict()
        figpaths = protorecord['figpaths'] = OrderedDict()
        latex_packages = protorecord['latex_packages'] = list()
        protorecord.setdefault('date', self.min_date(date_set))

        protorecord['metabody'] = list(self.digest_metabody(
            metabody, inpaths=inpaths, figpaths=figpaths,
            latex_packages=latex_packages ))

        protorecord['metapreamble'] = list(self.digest_metapreamble(
            metapreamble, inpaths=inpaths ))

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

    @fetching_metarecord
    @processing_target_aspect(aspect='metabody', wrap_generator=True)
    @classifying_items(aspect='metabody', default=None)
    def generate_metabody(self, target, metarecord,
        *, date_set
    ):
        """
        Yield metabody items. Update date_set.
        """
        manner_key, manner = self.select_flagged_item(
            metarecord, '$manner', target.flags )
        with self.process_target_key(target, manner_key):
            yield from self.generate_matter_metabody( target, metarecord,
                pre_matter=manner, pre_matter_key=manner_key,
                date_set=date_set )

    @fetching_metarecord
    @checking_target_recursion
    @processing_target_aspect(aspect='matter metabody', wrap_generator=True)
    @classifying_items(aspect='metabody', default=None)
    def generate_matter_metabody(self, target, metarecord,
        *, date_set, seen_targets, pre_matter=None, pre_matter_key=None
    ):
        """
        Yield metabody items.

        Update date_set.
        """
        if pre_matter is not None:
            seen_targets -= {target}
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
            target, metarecord,
            pre_matter=pre_matter, pre_matter_key=pre_matter_key )
        for item in matter_generator:
            if isinstance(item, self.MetabodyItem):
                yield item
            elif isinstance(item, Target):
                yield from self.generate_matter_metabody(
                    item, date_set=date_set, seen_targets=seen_targets )
            else:
                raise RuntimeError(type(item))

    @processing_target_aspect(aspect='header metabody', wrap_generator=True)
    @classifying_items(aspect='metabody', default='verbatim')
    def generate_header_metabody(self, target, metarecord, *, date):
        if 'multidate' not in target.flags:
            yield self.constitute_datedef(date=date)
        else:
            yield self.constitute_datedef(date=None)
        yield self.substitute_jeolmheader()
        yield self.substitute_resetproblem()

    @processing_target_aspect(aspect='matter', wrap_generator=True)
    @classifying_items(aspect='matter', default='verbatim')
    def generate_matter(self, target, metarecord,
        pre_matter=None, pre_matter_key=None, recursed=False
    ):
        """Yield matter items."""
        if pre_matter is None:
            pre_matter_key, pre_matter = self.select_flagged_item(
                metarecord, '$matter', target.flags )
        if pre_matter is None:
            if not metarecord.get('$source', False):
                return
            if '$latex$source' in metarecord:
                yield from self.generate_tex_matter(
                    target, metarecord )
            for name in metarecord:
                if name.startswith('$'):
                    continue
                if metarecord[name].get('$source', False):
                    yield target.path_derive(name)
                    yield self.substitute_clearpage()
            return
        with self.process_target_key(target, pre_matter_key):
            if not isinstance(pre_matter, list):
                raise DriverError(type(pre_matter))
            derive_target = partial( target.derive_from_string,
                origin=lambda: ( 'matter {target:target}, key {key}'
                    .format(target=target, key=pre_matter_key)
                ))
            for item in pre_matter:
                if isinstance(item, str):
                    yield derive_target(item)
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
                            pre_matter=item, pre_matter_key=pre_matter_key,
                            recursed=True )
                        yield self.substitute_clearpage()
                    continue
                if not isinstance(item, dict):
                    raise DriverError(type(item))
                item = item.copy()
                condition = item.pop('condition', [])
                if not target.flags.check_condition(condition):
                    continue
                if item.keys() == {'delegate'}:
                    yield derive_target(item['delegate'])
                else:
                    yield item

    @processing_target_aspect(aspect='tex matter', wrap_generator=True)
    @classifying_items(aspect='matter', default='verbatim')
    def generate_tex_matter(self, target, metarecord):
        assert metarecord.get('$latex$source', False)
        if not target.flags.intersection(('header', 'no-header')):
            yield target.flags_union({'header'})
            return # recurse
        for tex_package in metarecord.get('$latex$packages', ()):
            yield {'latex_package' : tex_package}
        yield {'inpath' : target.path.as_inpath(suffix='.tex')}
        if '$date' in metarecord and 'multidate' in target.flags:
            date = metarecord['$date']
            yield self.constitute_datedef(date=date)
            yield self.substitute_datestamp()

    @fetching_metarecord
    @processing_target_aspect(aspect='metapreamble', wrap_generator=True)
    @classifying_items(aspect='metapreamble', default=None)
    def generate_metapreamble(self, target, metarecord):
        manner_style_key, manner_style = self.select_flagged_item(
            metarecord, '$manner$style', target.flags )
        with self.process_target_key(target, manner_style_key):
            yield from self.generate_style_metapreamble(
                target, metarecord,
                pre_style=manner_style, pre_style_key=manner_style_key )

    @fetching_metarecord
    @checking_target_recursion
    @processing_target_aspect(aspect='style', wrap_generator=True)
    @classifying_items(aspect='metapreamble', default=None)
    def generate_style_metapreamble(self, target, metarecord,
        *, seen_targets, pre_style=None, pre_style_key=None
    ):
        if pre_style is not None:
            seen_targets -= {target}

        style_generator = self.generate_style(
            target, metarecord, pre_style=pre_style, pre_style_key=pre_style_key )
        for item in style_generator:
            if isinstance(item, self.MetapreambleItem):
                yield item
            elif isinstance(item, Target):
                yield from self.generate_style_metapreamble(
                    item, seen_targets=seen_targets )
            else:
                raise RuntimeError(type(item))

    @classifying_items(aspect='style', default=None)
    def generate_style(self, target, metarecord, pre_style, pre_style_key=None):
        if pre_style is None:
            pre_style_key, pre_style = self.select_flagged_item(
                metarecord, '$style', target.flags )
        if pre_style is None:
            if '$sty$source' in metarecord:
                yield {'inpath' : target.path.as_inpath(suffix='.sty')}
            else:
                yield target.path_derive('..')
            return
        with self.process_target_key(target, pre_style_key):
            if not isinstance(pre_style, list):
                raise DriverError(type(pre_style))
            derive_target = partial( target.derive_from_string,
                origin=lambda: ( 'style {target:target}, key {key}'
                    .format(target=target, key=pre_style_key)
                ) )
            for item in pre_style:
                if isinstance(item, str):
                    yield derive_target(item)
                    continue
                if not isinstance(item, dict):
                    raise DriverError(type(item))
                item = item.copy()
                condition = item.pop('condition', [])
                if not target.flags.check_condition(condition):
                    continue
                if item.keys() == {'delegate'}:
                    yield derive_target(item['delegate'])
                else:
                    yield item

    def digest_metabody(self, metabody, *,
        inpaths, figpaths, latex_packages
    ):

        """
        Yield metabody items.

        Extend inpaths, aliases, fignames.
        """

        latex_package_set = set()
        for item in metabody:
            assert isinstance(item, self.MetabodyItem), type(item)
            if isinstance(item, self.VerbatimBodyItem):
                pass
            elif isinstance(item, self.InpathBodyItem):
                inpath = item.inpath
                metarecord = self.getitem(RecordPath(inpath.with_suffix('')))
                if not metarecord.get('$latex$source', False):
                    raise RecordNotFoundError(inpath)
                alias  = item.alias = self.select_alias(
                    inpath, suffix='.in.tex' )
                self.check_and_set(inpaths, alias, inpath)
                figalias_map = item.figalias_map = {}
                recorded_figures = metarecord.get('$latex$figures', {})
                for figref, figpath_s in recorded_figures.items():
                    figpath = RecordPath(figpath_s)
                    figalias = self.select_alias(
                        figpath.as_inpath(suffix='.eps'), suffix='')
                    figalias_map[figref] = figalias
                    self.check_and_set(figpaths, figalias, figpath)
            elif isinstance(item, self.LaTeXPackageBodyItem):
                if item.latex_package not in latex_package_set:
                    latex_packages.append(item.latex_package)
                    latex_package_set.add(item.latex_package)
                continue # skip yield
            else:
                raise RuntimeError(type(item))
            yield item

    def digest_metapreamble(self, metapreamble, *, inpaths):
        """
        Yield metapreamble items.

        Extend inpaths, aliases.
        """
        for item in metapreamble:
            assert isinstance(item, self.MetapreambleItem), type(item)
            if isinstance(item, self.VerbatimPreambleItem):
                pass
            elif isinstance(item, self.PackagePreambleItem):
                pass
            elif isinstance(item, self.InpathPreambleItem):
                inpath = item.inpath
                metarecord = self.getitem(RecordPath(inpath.with_suffix('')))
                if not metarecord.get('$sty$source', False):
                    raise RecordNotFoundError(inpath)
                alias = item.alias = self.select_alias(
                    'local', inpath, suffix='.sty' )
                assert alias.endswith('.sty'), alias
                self.check_and_set(inpaths, alias, inpath)
            else:
                raise RuntimeError(type(item))
            yield item

    # List of (figtype, figkey, figsuffix)
    figtypes = (
        ('asy', '$asy$source', '.asy'),
        ('eps', '$eps$source', '.eps'),
        ('svg', '$svg$source', '.svg'),
    )

    def find_figure_type(self, figpath):
        """
        Return (figtype, inpath).

        figtype is one of 'asy', 'eps', 'svg'.
        """
        try:
            metarecord = self.getitem(figpath)
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
        metarecord = self.getitem(figpath)
        for used_name, used_path in metarecord.get('$asy$used', {}).items():
            inpath = PurePosixPath(used_path)
            yield used_name, inpath
            yield from self.trace_asy_used(
                RecordPath(inpath.with_suffix('')),
                seen_paths=seen_paths )


    ##########
    # Record extension

    @classmethod
    def load_library(cls, library_name):
        if library_name == 'pgfpages':
            return cls.pgfpages_library
        else:
            super().load_library(library_name)

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
            ('$style[2on1,portrait]', [{'verbatim' :
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

        if paper_option not in { 'a4paper', 'a5paper',
            'a4paper,landscape', 'a5paper,landscape'
        }:
            logger.warning(
                "<BOLD><MAGENTA>{name}<NOCOLOUR> uses "
                "bad paper option '<YELLOW>{option}<NOCOLOUR>'<RESET>"
                .format(name=outrecord['outname'], option=paper_option) )
        if font_option not in {'10pt', '11pt', '12pt'}:
            logger.warning(
                "<BOLD><MAGENTA>{name}<NOCOLOUR> uses "
                "bad font option '<YELLOW>{option}<NOCOLOUR>'<RESET>"
                .format(name=outrecord['outname'], option=font_option) )

    @classmethod
    def constitute_preamble(cls, outrecord, metapreamble):
        preamble_items = []
        for item in metapreamble:
            preamble_items.append(cls.constitute_preamble_item(item))
        for tex_package in outrecord['latex_packages']:
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
            assert alias.endswith('.sty'), alias
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
                figalias_map=item.figalias_map )
        else:
            raise RuntimeError(type(item))

    @classmethod
    def constitute_body_input(cls, inpath,
        *, alias, figalias_map
    ):
        body = cls.substitute_input(filename=alias, inpath=inpath )
        if figalias_map:
            body = cls.constitute_figalias_map(figalias_map) + '\n' + body
        return body

    input_template = r'\input{$filename}% $inpath'

    @classmethod
    def constitute_figalias_map(cls, figalias_map):
        return '\n'.join(
            cls.substitute_jeolmfiguremap(ref=figref, alias=figalias)
            for figref, figalias in figalias_map.items() )

    jeolmfiguremap_template = r'\jeolmfiguremap{$ref}{$alias}'

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

    @staticmethod
    def check_and_set(mapping, key, value):
        other = mapping.get(key)
        if other is None:
            mapping[key] = value
        elif other == value:
            pass
        else:
            raise DriverError("{} clashed with {}".format(value, other))

