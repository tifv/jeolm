"""
Driver(metarecords)
    Given a target, Driver can produce corresponding LaTeX code, along
    with dependency list. It is Driver which ultimately knows how to
    deal with metarecords.

driver.produce_outrecords(targets)
    Return (outrecords, figrecords) where
    outrecords = ODict(outname : outrecord for some outnames)
    figrecords = ODict(figname : figrecord for some fignames)

    outnames and fignames are derived from targets and metarecords.
    They must not contain any '/' slashes and should contain only
    letters and '-'.

driver.list_targets()
    Return a list of some valid targets that may be used with
    produce_outrecords(). This list is not (actually, can not be)
    guaranteed to be complete.

Metarecords
    Each outrecord must contain the following fields:

    'outname'
        string equal to the corresponding outname

    'sources'
        {alias_name : inpath for each inpath}
        where alias_name is a filename with '.tex' extension,
        and inpath has '.tex' extension.

    'fignames'
        an iterable of strings; all of them must be contained
        in figrecords.keys()

    'document'
        LaTeX document as a string

Figrecords
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

Inpaths
    Inpaths are relative PurePath objects. They are supposed to be
    valid subpaths of the '<root>/source/' directory.

"""

import datetime
from itertools import chain
from functools import wraps
from collections import OrderedDict
from string import Template

from pathlib import PurePosixPath as PurePath

from .utils import pure_join
from .records import Records, RecordNotFoundError

import logging
logger = logging.getLogger(__name__)

class Substitutioner(type):
    """
    Metaclass for a driver.

    For any *_template attribute create substitute_* attribute, like
    cls.substitute_* = Template(cls.*_template).substitute
    """
    def __new__(cls, cls_name, cls_bases, namespace, **kwds):
        namespace_upd = {}
        for key, value in namespace.items():
            if key.endswith('_template'):
                substitute_key = 'substitute_' + key[:-len('_template')]
                namespace_upd[substitute_key] = Template(value).substitute
        namespace.update(namespace_upd)
        return super().__new__(cls, cls_name, cls_bases, namespace, **kwds)

def fetch_metarecord(method):
    @wraps(method)
    def wrapper(self, metapath, options, metarecord=None, **kwargs):
        if metarecord is None:
            metarecord = self.metarecords[metapath]
        return method(self, metapath, options, metarecord=metarecord, **kwargs )
    return wrapper

class Driver(metaclass=Substitutioner):
    """
    Driver for course-like projects.
    """


    ##########
    # High-level functions

    def __init__(self, metarecords):
        self.metarecords = metarecords
        assert isinstance(metarecords, self.Metarecords)

        self.outrecords = OrderedDict()
        self.figrecords = OrderedDict()
        self.outnames_by_target = dict()

    def produce_outrecords(self, targets):
        # Target options: 'no-delegate', 'matter', 'multidate', 'contained
        targets = self.split_produced_targets(targets)
        targets = list(chain.from_iterable(
            self.trace_delegators(metapath, options)
            for metapath, options in targets ))

        # Generate outrecords and store them in self.outrecords
        outnames = [
            self.form_outrecord(metapath, options)
            for metapath, options in targets ]

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

    def list_targets(self):
        """
        List some (usually most of) probably-working targets.
        """
        yield from self.metarecords.list_targets()

    def list_inpaths(self, targets, *, source_type='tex'):
        outrecords, figrecords = self.produce_outrecords(targets)
        if 'tex' == source_type:
            for outrecord in outrecords.values():
                for inpath in outrecord['inpaths']:
                    if inpath.suffix == '.tex':
                        yield inpath
        elif 'asy' == source_type:
            for figrecord in figrecords.values():
                for inpath in figrecord['source']:
                    yield inpath

    def form_outrecord(self, metapath, options):
        """
        Return outname.

        Update self.outrecords and self.figrecords.
        """
        try:
            return self.outnames_by_target[metapath, options]
        except KeyError:
            pass

        outrecord = self.produce_protorecord(metapath, options)
        assert outrecord.keys() >= {
            'date', 'inpaths', 'fignames', 'metastyle', 'metabody'
        }, outrecord.keys()

        outname = self.select_outname(metapath, options,
            date=outrecord['date'] )
        outrecord['outname'] = outname
        if outname in self.outrecords:
            raise ValueError("Metaname '{}' duplicated.".format(outname))
        self.outrecords[outname] = outrecord

        self.revert_aliases(outrecord)

        outrecord['document'] = self.constitute_document(
            outrecord,
            metastyle=outrecord.pop('metastyle'),
            metabody=outrecord.pop('metabody'), )
        self.outnames_by_target[metapath, options] = outname
        return outname

    def revert_aliases(self, outrecord):
        """
        Based on outrecord['aliases'], define 'sources'.
        """
        outrecord['sources'] = {
            alias : inpath
            for inpath, alias in outrecord['aliases'].items() }
        if len(outrecord['sources']) < len(outrecord['aliases']):
            clashed_inpaths = (
                set(outrecord['inpaths']) -
                set(outrecord['sources'].values()) )
            raise ValueError(*sorted({
                outrecord['aliases'][inpath]
                for inpath in clashed_inpaths }))

    def produce_figname_map(self, figures):
        """
        Return { figalias : figname
            for each figname included in source as figalias }

        Update self.figrecords.
        """
        if not figures:
            return {}
        if not isinstance(figures, dict):
            raise TypeError(figures)
        return OrderedDict(
            (figalias, self.form_figrecord(figpath))
            for figalias, figpath in figures.items() )

    def form_figrecord(self, figpath):
        """
        Return figname.

        Update self.figrecords.
        """
        figtype, inpath = self.find_figure_type(figpath)

        figname = '-'.join(figpath.parts)
        if figname in self.figrecords:
            alt_inpath = self.figrecords[figname]['source']
            if alt_inpath != inpath:
                raise ValueError(figname, inpath, alt_inpath)
            return figname

        figrecord = self.figrecords[figname] = dict()
        figrecord['figname'] = figname
        figrecord['source'] = inpath
        figrecord['type'] = figtype

        if figtype == 'asy':
            used_items = list(self.trace_asy_used(figpath))
            used = figrecord['used'] = dict(used_items)
            if len(used) != len(used_items):
                raise ValueError(inpath, used_items)

        return figname


    ##########
    # Record-level functions

    @fetch_metarecord
    def trace_delegators(self, metapath, options, metarecord,
        *, seen_targets=frozenset()
    ):
        """Generate (metapath, options) pairs."""
        target = (metapath, options)
        if target in seen_targets:
            raise ValueError(target)
        assert not metapath.is_absolute(), metapath
        seen_targets |= {target}

        if 'no-delegate' in options:
            yield metapath, options.difference(('no-delegate',))
            return

        delegators = list(self.find_delegators(metapath, options, metarecord))
        if not delegators:
            yield metapath, options
            return
        for d_metapath, d_options in delegators:
            yield from self.trace_delegators(d_metapath, d_options,
                seen_targets=seen_targets )

    def find_delegators(self, metapath, options, metarecord):
        """Yield (metapath, options) pairs."""
        if '$delegate' not in metarecord:
            return
        delegators = metarecord['$delegate']
        if not isinstance(delegators, list):
            raise TypeError(delegators)
        for delegator in delegators:
            if isinstance(delegator, str):
                delegator = {'delegate' : delegator}
            if not isinstance(delegator, dict):
                raise TypeError(delegator)
            if 'delegate' not in delegator:
                raise ValueError(delegator)
            if 'condition' in delegator:
                if not self.check_condition(delegator['condition'], options):
                    continue
            delegator = delegator['delegate']
            if not isinstance(delegator, str):
                raise TypeError(delegator)
            subpath, suboptions, antioptions = self.split_target(delegator)
            yield ( pure_join(metapath, subpath),
                (options | suboptions) - antioptions )

    @fetch_metarecord
    def produce_protorecord(self, metapath, options, metarecord):
        """
        Return protorecord.
        """
        date_set = set()

        protorecord = {}
        if 'matter' not in options:
            protorecord.update(metarecord.get('$manner$opt', ()))
        protorecord['metabody'] = list(self.generate_manner(
            metapath, options, metarecord, date_set=date_set ))

        inpaths = protorecord['inpaths'] = list()
        aliases = protorecord['aliases'] = dict()
        fignames = protorecord['fignames'] = list()
        protorecord.setdefault('date', self.min_date(date_set))

        protorecord['metabody'] = list(self.digest_metabody(
            protorecord.pop('metabody'), inpaths, aliases, fignames ))

        protorecord['metastyle'] = list(self.digest_metastyle(
            self.Metarecords.derive_styles(
                metarecord['$style'], protorecord.pop('style', None),
                path=metapath ),
            inpaths, aliases ))

        # dropped keys
        assert 'preamble' not in protorecord, 'style'
        assert '$out$options' not in metarecord, '$manner$opt'
        assert '$rigid' not in metarecord, '$manner'
        assert '$rigid$opt' not in metarecord, '$manner$opt'
        assert '$fluid' not in metarecord, '$matter'
        assert '$fluid$opt' not in metarecord, '$matter$opt'

        return protorecord

    @fetch_metarecord
    def generate_manner(self, metapath, options, metarecord,
        *, date_set
    ):
        """
        Yield metabody items.

        Update date_set.
        """
        if 'matter' in options:
            yield from self.generate_matter(
                metapath, options - {'matter'}, metarecord,
                date_set=date_set )
            return
        if '$manner' in metarecord:
            manner = metarecord['$manner']
        else:
            manner = [['.']]
        if '$date' in metarecord:
            date_set.add(metarecord['$date']); date_set = set()

        matter = []
        for page in manner:
            if not page:
                matter.append({'verbatim' : self.substitute_emptypage()})
                continue
            matter.extend(page)
#            for item in page:
#                matter.appennd
#                if isinstance(item, str)
#                if isinstance(item, dict):
#                    if 'condition' in item:
#                        condition = self.check_condition(
#                            item['condition'], options)
#                        if not condition:
#                            continue
#                    yield item
#                    continue
#                if not isinstance(item, str):
#                    raise TypeError(metapath, options, item)
#
#                subpath, suboptions, antioptions = self.split_target(item)
#                yield from self.generate_matter(
#                    pure_join(metapath, subpath),
#                    (options | suboptions) - antioptions,
#                    date_set=date_set )
            matter.append({'verbatim' : self.substitute_clearpage()})
        metarecord = metarecord.copy()
        metarecord['$matter'] = matter
        yield from self.generate_matter(
            metapath, options | {'every-header'}, metarecord,
            date_set=date_set )

    @fetch_metarecord
    def generate_matter(self, metapath, options, metarecord,
        *, date_set
    ):
        """
        Yield metabody items.

        Update date_set.
        """
        if '$matter' in metarecord:
            matter = metarecord['$matter']
        else:
            matter = self.auto_generate_matter(metapath, options, metarecord)
        if '$date' in metarecord:
            date_set.add(metarecord['$date']); date_set = set()

        if 'no-header' not in options and 'every-header' not in options:
            date_subset = set()
            metabody = list(self.generate_matter(
                metapath, options | {'no-header'}, metarecord,
                date_set=date_subset ))
            yield from self.generate_matter_header(
                metapath, options, metarecord,
                date=self.min_date(date_subset) )
            yield from metabody
            date_set.update(date_subset)
            return # recurse
        options -= {'every-header'}

        for item in matter:
            if isinstance(item, str):
                item = {'matter' : item}
            if not isinstance(item, dict):
                raise TypeError(item)
            if 'condition' in item:
                item = item.copy()
                condition = item.pop('condition')
                if not self.check_condition(condition, options):
                    continue
            if 'matter' not in item:
                yield item
                continue
            if not item.keys() <= {'matter', 'condition'}:
                raise ValueError(item)
            submatter = item['matter']

            subpath, suboptions, antioptions = self.split_target(submatter)
            yield from list(self.generate_matter(
                pure_join(metapath, subpath),
                (options | suboptions) - antioptions,
                date_set=date_set ))

    def generate_matter_header(self, metapath, options, metarecord, *, date):
        if 'multidate' not in options:
            yield {'verbatim' : self.constitute_datedef(date=date)}
        else:
            yield {'verbatim' : self.constitute_datedef(date=None)}
        yield {'verbatim' : self.substitute_jeolmheader()}
        yield {'verbatim' : self.substitute_resetproblem()}

    def auto_generate_matter(self, metapath, options, metarecord):
        """Yield matter items."""
        if not metarecord.get('$source', False):
            return
        if '$tex$source' in metarecord:
            yield from self.auto_generate_tex_matter(
                metapath, options, metarecord )
        for name in metarecord:
            if name.startswith('$'):
                continue
            if metarecord[name].get('$source', False):
                yield name

    def auto_generate_tex_matter(self, metapath, options, metarecord):
        assert metarecord.get('$tex$source', False)
        item = {'inpath' : metapath.with_suffix('.tex')}
        has_date = '$date' in metarecord
        if has_date:
            date = metarecord['$date']
        yield item
        if has_date and 'multidate' in options:
            yield {'verbatim' : self.constitute_datedef(date=date)}
            yield {'verbatim' : self.substitute_datestamp()}

    def digest_metabody(self, metabody, inpaths, aliases, fignames):
        """
        Yield metabody items.

        Extend inpaths, aliases, fignames.
        """
        for item in metabody:
            item = self.digest_metabody_item(item)
            if 'inpath' in item:
                inpath = item['inpath']
                assert isinstance(inpath, PurePath), inpath
                metarecord = self.metarecords[inpath.with_suffix('')]
                if not metarecord.get('$tex$source', False):
                    raise RecordNotFoundError(inpath)
                inpaths.append(inpath)
                aliases[inpath] = item['alias'] = self.sluggify_path(
                    inpath, suffix='.in.tex' )
                figures = OrderedDict(
                    (figalias, PurePath(figpath))
                    for figalias, figpath
                    in metarecord.get('$tex$figures', {}).items() )
                figname_map = self.produce_figname_map(figures)
                item['figname map'] = figname_map
                fignames.extend(figname_map.values())
            yield item

    def digest_metastyle(self, metastyle, inpaths, aliases):
        """
        Yield metastyle items.

        Extend inpaths, aliases.
        """
        for item in metastyle:
            item = self.digest_metastyle_item(item)
            if 'inpath' in item:
                inpath = item['inpath']
                metarecord = self.metarecords[inpath.with_suffix('')]
                if not metarecord.get('$sty$source', False):
                    raise RecordNotFoundError(inpath)
                inpaths.append(inpath)
                aliases[inpath] = item['alias'] = self.sluggify_path(
                    'local', inpath, suffix='.sty' )
            yield item

    figtypes = ('asy', 'eps')
    figkeys = {'asy' : '$asy$source', 'eps' : '$eps$source'}
    figsuffixes = {'asy' : '.asy', 'eps' : '.eps'}

    def find_figure_type(self, figpath):
        """
        Return (figtype, inpath).

        figtype is one of 'asy', 'eps'.
        """
        metarecord = self.metarecords[figpath]
        for figtype in self.figtypes:
            figkey = self.figkeys[figtype]
            if not metarecord.get(figkey, False):
                continue
            return figtype, figpath.with_suffix(self.figsuffixes[figtype])
        raise RecordNotFoundError(figpath)

    def trace_asy_used(self, figpath, *, seen_paths=frozenset()):
        if figpath in seen_paths:
            raise ValueError(figpath)
        seen_paths |= {figpath}
        metarecord = self.metarecords[figpath]
        used = OrderedDict(
            (used_name, PurePath(inpath))
            for used_name, inpath
            in metarecord.get('$asy$used', {}).items() )
        for used_name, inpath in used.items():
            yield used_name, inpath
            yield from self.trace_asy_used(
                inpath.with_suffix(''),
                seen_paths=seen_paths )


    ##########
    # Record accessor

    class Metarecords(Records):
        def list_targets(self, path=PurePath(), root=True):
            record = self.get(path)
            if not record.get('$targetable', True):
                return
            if not root:
                yield str(path)
            for key in record:
                if key.startswith('$'):
                    continue
                yield from self.list_targets(path=path/key, root=False)

        def derive_attributes(self, parent_record, child_record, name):
            parent_path = parent_record.get('$path')
            if parent_path is None:
                path = PurePath()
            else:
                path = parent_path/name
            child_record['$path'] = path
            child_record['$style'] = self.derive_styles(
                parent_record.get('$style'), child_record.get('$style'),
                path )
            super().derive_attributes(parent_record, child_record, name)

        @classmethod
        def derive_styles(cls, parent_style, child_style, path):
            if parent_style is None:
                parent_style = []
            else:
                parent_style = parent_style.copy()
            if child_style is None:
                return parent_style

            if not isinstance(child_style, dict):
                return cls.assimilate_style(child_style, path)

            for key, substyle in child_style.items():
                if key == 'extend':
                    parent_style += cls.assimilate_style(substyle, path)
                else:
                    raise ValueError(key)
            return parent_style

        @classmethod
        def assimilate_style(cls, style, path):
            assimilated = []
            append = assimilated.append
            for item in style:
                if isinstance(item, str):
                    inpath = pure_join(path, item).with_suffix('.sty')
                    append({'inpath' : inpath})
                elif isinstance(item, dict):
                    append(item)
                else:
                    raise TypeError(item)
            return assimilated


    ##########
    # LaTeX-level functions

    @classmethod
    def constitute_document(cls, outrecord, metastyle, metabody):
        documentclass = cls.select_documentclass(outrecord)
        classoptions = cls.generate_classoptions(outrecord)

        return cls.substitute_document(
            documentclass=documentclass,
            classoptions=cls.constitute_options(classoptions),
            preamble=cls.constitute_preamble(outrecord, metastyle),
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
        yield from outrecord.get('class options', ())

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
    def constitute_preamble(cls, outrecord, metastyle):

        preamble_items = []
        for item in metastyle:
            assert isinstance(item, dict), item
            if 'style' in item:
                inpath = item['style']
            preamble_items.append(cls.constitute_preamble_item(item))
        if 'scale font' in outrecord:
            font, skip = outrecord['scale font']
            preamble_items.append(
                cls.substitute_selectfont(font=font, skip=skip) )
        assert 'selectsize' not in outrecord, 'scale font'
        assert 'selectfont' not in outrecord, 'scale font'
        return '\n'.join(preamble_items)

    selectfont_template = (
        r'\AtBeginDocument{\fontsize{$font}{$skip}\selectfont}' )

    @classmethod
    def constitute_preamble_item(cls, item):
        assert isinstance(item, dict), item
        if 'verbatim' in item:
            return item['verbatim']
        elif 'package' in item:
            package = item['package']
            options = item.get('options', None)
            options = cls.constitute_options(options)
            return cls.substitute_usepackage(
                package=package,
                options=options )
        elif 'inpath' in item:
            alias = item['alias']
            assert alias.endswith('.sty')
            return cls.substitute_uselocalpackage(
                package=alias[:-len('.sty')], inpath=item['inpath'] )
        else:
            raise ValueError(item)

    usepackage_template = r'\usepackage$options{$package}'
    uselocalpackage_template = r'\usepackage{$package}% $inpath'

    @classmethod
    def constitute_options(cls, options):
        if not options:
            return '';
        if not isinstance(options, str):
            options = ','.join(options)
        return '[' + options + ']'

    @classmethod
    def constitute_body(cls, metarecord, metabody):
        body_items = []
        for item in metabody:
            assert isinstance(item, dict), item
            if 'inpath' in item:
                inpath = item['inpath']
            body_items.append(cls.constitute_body_item(item))

        return '\n'.join(body_items)

    @classmethod
    def constitute_body_item(cls, item):
        assert isinstance(item, dict), item
        if 'verbatim' in item:
            return item['verbatim']
        elif 'inpath' in item:
            kwargs = dict(item)
            kwargs['figname_map'] = kwargs.pop('figname map')
            return cls.constitute_body_input(**kwargs)
        else:
            raise ValueError(item)

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
    emptypage_template = r'\phantom{S}\clearpage'
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
    def select_outname(metapath, options, date=None):
        outname = '-'.join(metapath.parts)
        if options:
            outname += '[' + ','.join(sorted(options)) + ']'
        if isinstance(date, datetime.date):
            date_prefix = '{0.year:04}-{0.month:02}-{0.day:02}'.format(date)
            outname = date_prefix + '-' + outname
        return outname

    @classmethod
    def split_produced_targets(cls, targets, absolute=False):
        """Yield (metapath, options) pairs."""
        for target in targets:
            if '.' in target:
                raise ValueError(target)
            metapath, options, antioptions = cls.split_target(target)
            if metapath.is_absolute():
                raise ValueError(target)
            if antioptions:
                raise ValueError("Antioption in produced target", target)
            yield metapath, options

    @classmethod
    def split_target(cls, target):
        """Return (metapath, options, no_options)."""
        assert isinstance(target, str), target
        basetarget, braket, options_string = target.partition('[')
        if braket == '[':
            if not options_string.endswith(']'):
                raise ValueError(target)
            raw_options = frozenset(options_string[:-1].split(','))
        else:
            raw_options = frozenset()
        options = set(); antioptions = set()
        for option in raw_options:
            if option.startswith('-'):
                antioptions.add(option[1:])
            else:
                options.add(option)
        if not basetarget or ' ' in basetarget:
            raise ValueError(target)
        metapath = PurePath(basetarget)
        return metapath, frozenset(options), frozenset(antioptions)

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
    def sluggify_path(*parts, suffix=''):
        path = PurePath(*parts)
        assert not path.is_absolute() and len(path.suffixes) == 1, path
        return '-'.join(path.with_suffix('').parts) + suffix

    @classmethod
    def digest_metabody_item(cls, item):
        assert isinstance(item, dict), item
        if 'verbatim' in item:
            if not item.keys() <= {'verbatim'}:
                raise ValueError(item)
            digested =  {
                'verbatim' : str(item['verbatim']) }
        elif 'inpath' in item:
            if not item.keys() <= {'inpath'}:
                raise ValueError(item)
            inpath = PurePath(item['inpath'])
            if inpath.is_absolute():
                raise ValueError(item)
            digested = {'inpath' : inpath}
        else:
            raise ValueError(item)
        return digested

    @classmethod
    def digest_metastyle_item(cls, item):
        assert isinstance(item, dict), item
        if 'verbatim' in item:
            if not item.keys() <= {'verbatim'}:
                raise ValueError(item)
            digested = {'verbatim' : str(item['verbatim'])}
        elif 'package' in item:
            if not item.keys() <= {'package', 'options'}:
                raise ValueError(item)
            digested = {'package' : str(item['package'])}
            if 'options' in item:
                digested['options'] = [
                    str(option) for option in item['options'] ]
        elif 'inpath' in item:
            if not item.keys() <= {'inpath'}:
                raise ValueError(item)
            inpath = PurePath(item['inpath'])
            if inpath.is_absolute():
                raise ValueError(item)
            digested = {'inpath' : inpath}
        else:
            raise ValueError(item)
        return digested

    @classmethod
    def check_condition(cls, condition, options):
        if isinstance(condition, str):
            return condition in options
        elif not isinstance(condition, dict):
            raise ValueError(condition)
        elif len(condition) != 1:
            raise ValueError(condition)
        (key, subcondition), = condition.items()
        if key == 'not':
            return not cls.check_condition(subcondition, options)
        elif key == 'or':
            return any(cls.check_condition(item, options)
                for item in subcondition )
        elif key == 'and':
            return all(cls.check_condition(item, options)
                for item in subcondition )

class TestFilteringDriver(Driver):
    def auto_generate_tex_matter(self, metapath, options, metarecord):
        super_matter = list(super().auto_generate_tex_matter(
            metapath, options, metarecord ))
        if metarecord.get('$test', False):
            if not super_matter or 'exclude-test' in options:
                return
            yield {'verbatim' : self.substitute_begingroup()}
            yield {'verbatim' : self.substitute_interrobang_section()}
            yield from super_matter
            yield {'verbatim' : self.substitute_endgroup()}
        else:
            yield from super_matter

    interrobang_section_template = (
            r'\let\oldsection\section'
            r'\def\section#1#2{\oldsection#1{\textinterrobang\ #2}}'
    )
    begingroup_template = r'\begingroup'
    endgroup_template = r'\endgroup'

