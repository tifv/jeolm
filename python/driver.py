"""
Driver(inrecords, outrecords)
    Given a target, Driver can produce corresponding LaTeX code, along
    with dependency list. It is Driver which ultimately knows how to
    deal with inrecords and outrecords.

driver.produce_metarecords(targets)
    Return (metarecords, figrecords) where
    metarecords = ODict(metaname : metarecord for some metanames)
    figrecords = ODict(figname : figrecord for some fignames)

    Metanames and fignames are derived from targets, inrecords and
    outrecords. They must not contain any '/' slashes and should not
    contain any extensions.

driver.list_targets()
    Return a list of some valid targets, that may be used with
    produce_metarecords(). This list is not (actually, can not be)
    guaranteed to be complete.

Metarecords
    Each metarecord must contain the following fields:

    'metaname'
        string equal to the corresponding metaname

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
    Inpaths are relative PurePath objects. They should be based on
    inrecords, and supposed to be valid subpaths of the '<root>/source/'
    directory.

"""

import datetime
from itertools import chain
from collections import OrderedDict
from string import Template

from pathlib import PurePosixPath as PurePath

from jeolm.utils import pure_join

import logging
logger = logging.getLogger(__name__)

class RecordNotFoundError(ValueError):
    pass

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

class Driver(metaclass=Substitutioner):
    """
    Driver for course-like projects.
    """

    ##########
    # High-level functions

    def __init__(self, inrecords, outrecords):
        self.inrecords = self.InrecordAccessor(inrecords)
        self.outrecords = self.OutrecordAccessor(outrecords)

        self.metarecords = OrderedDict()
        self.figrecords = OrderedDict()
        self.formed_metarecords = dict()

    def produce_metarecords(self, targets):
        targets = list(chain.from_iterable(
            self.trace_delegators(self.pathify_target(target))
            for target in targets ))

        # Generate metarecords in self.metarecords
        metanames = [self.form_metarecord(target) for target in targets]

        # Extract requested metarecords
        metarecords = OrderedDict(
            (metaname, self.metarecords[metaname])
            for metaname in metanames )

        # Extract requested figrecords
        figrecords = OrderedDict(
            (figname, self.figrecords[figname])
            for metarecord in metarecords.values()
            for figname in metarecord['fignames'] )

        return metarecords, figrecords

    def list_targets(self):
        yield from self.inrecords.list_targets()
        yield from self.outrecords.list_targets()

    def list_inpaths(self, targets, *, source_type='tex'):
        metarecords, figrecords = self.produce_metarecords(targets)
        if 'tex' == source_type:
            for metarecord in metarecords.values():
                for inpath in metarecord['inpaths']:
                    if inpath.suffix == '.tex':
                        yield inpath
        elif 'asy' == source_type:
            for figrecord in figrecords.values():
                for inpath in figrecord['source']:
                    yield inpath

    def form_metarecord(self, target):
        """
        Return metaname.

        Update self.metarecords and self.figrecords.
        """
        if target in self.formed_metarecords:
            return self.formed_metarecords[target]

        metarecord = self.produce_protorecord(target)

        metaname = self.select_metaname(target, date=metarecord.get('date'))
        metarecord['metaname'] = metaname
        if metaname in self.metarecords:
            raise ValueError("Metaname '{}' duplicated.".format(metaname))
        self.metarecords[metaname] = metarecord

        self.select_aliases(metarecord)

        figname_maps = dict()
        fignames = set()
        for inpath, inrecord in metarecord['inrecords'].items():
            figname_maps[inpath] = figname_map = \
                self.produce_figname_map(inpath, inrecord)
            fignames.update(figname_map.values())
        metarecord['figname maps'] = figname_maps
        metarecord['fignames'] = sorted(fignames)

        metarecord['document'] = self.constitute_document(
            metarecord,
            metastyle=metarecord.pop('style'),
            metabody=metarecord.pop('body'), )
        self.formed_metarecords[target] = metaname
        return metaname

    def select_aliases(self, metarecord):
        metarecord['aliases'] = aliases = dict()

        inpaths = metarecord['inpaths']

        for inpath in inpaths:
            if inpath.suffix == '.tex':
                aliases[inpath] = self.sluggify_path(
                    inpath, suffix='.in.tex' )
            elif inpath.suffix == '.sty':
                aliases[inpath] = self.sluggify_path(
                    'local', inpath, suffix='.sty' )

        metarecord['sources'] = {
            alias : inpath
            for inpath, alias in metarecord['aliases'].items() }
        if len(metarecord['sources']) < len(metarecord['aliases']):
            clashed_inpaths = (
                set(metarecord['inpaths']) -
                set(metarecord['sources'].values()) )
            raise ValueError({
                metarecord['aliases'][inpath]
                for inpath in clashed_inpaths })
        metarecord['inrecords'] = {
            inpath : self.inrecords[inpath]
            for inpath in metarecord['inpaths'] }

    def produce_figname_map(self, inpath, inrecord):
        """
        Return {figalias : figname for each figname included in source}

        Update self.figrecords.
        """

        inrecord_figures = inrecord.get('$figures')
        if inrecord_figures is None:
            return {};
        if not isinstance(inrecord_figures, dict):
            raise TypeError(inrecord_figures)
        return OrderedDict(
            (figalias, self.form_figrecord(figpath))
            for figalias, figpath in inrecord_figures.items() )

    def form_figrecord(self, figpath):
        """
        Return figname.
        """
        figtype, inpath, inrecord = self.find_figure_inrecord(figpath)

        figname = '-'.join(figpath.parts)
        if figname in self.figrecords:
            alt_inpath = self.figrecords[figname]['source']
            if alt_inpath != inpath:
                raise ValueError(figname, inpath, alt_inpath)
            return figname;

        figrecord = self.figrecords[figname] = dict()
        figrecord['figname'] = figname
        figrecord['source'] = inpath
        figrecord['type'] = figtype

        if figtype == 'asy':
            used_items = list(self.trace_figure_used(inpath))
            used = figrecord['used'] = dict(used_items)
            if len(used) != len(used_items):
                raise ValueError(inpath, used_items)

        return figname;

    ##########
    # Record-level functions

    def trace_delegators(self, target, *, seen_targets=frozenset()):
        if target in seen_targets:
            raise ValueError(target)
        seen_targets = seen_targets.union((target,))
        resolved_path, record = self.outrecords.get_item(target)
        yield from self._trace_delegators(target, resolved_path, record,
            seen_targets=seen_targets )

    # This supplementary generator makes use of resolved_path and record
    # arguments, computed by trace_delegators.
    # Useful for overriding.
    def _trace_delegators(self, target, resolved_path, record,
        *, seen_targets
    ):
        if '$delegate' not in record:
            yield target
            return;

        delegators = record.get('$delegate')
        if not isinstance(delegators, list):
            raise TypeError(delegators)
        for delegator in delegators:
            yield from self.trace_delegators(
                pure_join(resolved_path, delegator),
                seen_targets=seen_targets )

    def list_protorecord_methods(self):
        yield self.produce_rigid_protorecord
        yield self.produce_fluid_protorecord

    def produce_protorecord(self, target):
        """
        Return protorecord.
        """
        date_set = set()
        resolved_path, record = self.outrecords.get_item(target)

        for method in self.list_protorecord_methods():
            try:
                protorecord = method(resolved_path, record, date_set=date_set)
                # Call is not over! We must fix 'body', 'date' and 'inpaths'
                break;
            except RecordNotFoundError as error:
                if error.args != (target,):
                    raise;
        else:
            raise RecordNotFoundError(target);

        inpaths = protorecord['inpaths'] = []
        protorecord.setdefault('date', self.min_date(date_set))

        body = protorecord.pop('body')
        protorecord['body'] = [
            self.digest_body_item(item)
            for item in body ]
        for item in body:
            if 'input' not in item:
                continue
            inpath = item['input']
            if inpath not in self.inrecords:
                raise RecordNotFoundError(inpath)
            inpaths.append(inpath)

        style = record['$style']
        style.extend(protorecord.pop('style', ()))
        protorecord['style'] = [
            self.digest_style_item(item)
            for item in style ]
        for item in style:
            if 'style' not in item:
                continue
            inpath = item['style']
            if inpath not in self.inrecords:
                raise RecordNotFoundError(inpath)
            inpaths.append(inpath)

        # old key..
        assert 'preamble' not in protorecord

        return protorecord

    def produce_rigid_protorecord(self, target, record,
        *, date_set
    ):
        """Return protorecord with 'body'."""
        if '$rigid' not in record:
            raise RecordNotFoundError(target);
        rigid = record['$rigid']
        rigid_opt = record.get('$rigid$opt', {})
        if '$date' in record:
            date_set.add(record['$date']); date_set = set()

        body = []; append = body.append
        for page in rigid:
            append({'verbatim' : self.substitute_clearpage()})
            if not page: # empty page
                append({'verbatim' : self.substitute_phantom()})
                continue
            for item in page:
                if isinstance(item, dict):
                    append(item)
                    continue
                if not isinstance(item, str):
                    raise TypeError(target, item)

                subpath = self.outrecords.resolve(pure_join(target, item))
                inpath, inrecord = self.inrecords.get_item(
                    subpath.with_suffix('.tex') )
                if inrecord is None:
                    raise RecordNotFoundError(inpath, target);
                date_set.add(inrecord.get('$date'))
                append({'input' : inpath, 'rigid' : True})

        protorecord = {'body' : body}
        protorecord.update(rigid_opt)
        return protorecord

    def produce_fluid_protorecord(self, target, record,
        *, date_set, fluid_opt=None
    ):
        """Return protorecord with 'body'."""
        fluid = record.get('$fluid', None)
        if fluid_opt is None:
            fluid_opt = record.get('$fluid$opt', {})
        if '$date' in record:
            date_set.add(record['$date']); date_set = set()

        body = []; append = body.append
        if fluid is None:
            # No outrecord fluid.
            # Try directory inrecord.
            fluid = self.generate_autofluid(target, fluid_opt)
        if fluid is None:
            # No outrecord fluid and no directory inrecord.
            # Try single file inrecord.
            inpath, inrecord = self.inrecords.get_item(
                target.with_suffix('.tex') )
            if inrecord is None:
                # We tried everything..
                raise RecordNotFoundError(target)
            date_set.add(inrecord.get('$date'))
            append({'input' : inpath})
        else:
            for item in fluid:
                if isinstance(item, dict):
                    append(item)
                    continue
                if not isinstance(item, str):
                    raise TypeError(target, item)

                subpath, subrecord = self.outrecords.get_item(
                    pure_join(target, item) )
                subprotorecord = self.produce_fluid_protorecord(
                    subpath, subrecord, fluid_opt=fluid_opt,
                    date_set=date_set )
                body.extend(subprotorecord['body'])

        protorecord = {'body' : body}
        protorecord.update(fluid_opt)
        return protorecord

    def generate_autofluid(self, target, fluid_opt):
        inrecord = self.inrecords[target]
        if inrecord is None:
            return None;
        subnames = []
        for subname, subrecord in inrecord.items():
            subnamepath = PurePath(subname)
            suffix = subnamepath.suffix
            if suffix == '.tex':
                subname = str(subnamepath.with_suffix(''))
            elif suffix == '':
                pass
            else:
                continue
            if not self.filter_autofluid(
                target/subname, subrecord, fluid_opt=fluid_opt
            ):
                continue
            subnames.append(subname)
        return subnames

    def filter_autofluid(self, inpath, inrecord, *, fluid_opt):
        return True

    def find_figure_inrecord(self, figpath):
        """
        Return (figtype, inpath, inrecord).

        figtype is one of 'asy', 'eps'.
        """
        for figtype, suffix in (('asy', '.asy'), ('eps', '.eps')):
            inpath, inrecord = self.inrecords.get_item(
                figpath.with_suffix(suffix) )
            if inrecord is None:
                continue;
            if not isinstance(inrecord, dict):
                raise TypeError(inpath, inrecord)
            return figtype, inpath, inrecord;
        raise RecordNotFoundError(figpath);

    def trace_figure_used(self, inpath, *, seen_paths=frozenset()):
        if inpath in seen_paths:
            raise ValueError(path)
        seen_paths = seen_paths.union((inpath,))
        assert inpath.suffix == '.asy', inpath
        inrecord = self.inrecords[inpath]
        if inrecord is None:
            raise RecordNotFoundError(inpath);
        used = inrecord.get('$used')
        if used is None:
            return;
        for used_name, original_path in used.items():
            yield used_name, original_path
            yield from self.trace_figure_used(original_path,
                seen_paths=seen_paths )

    ##########
    # Record accessors

    class RecordAccessor:
        def __init__(self, records):
            self.records = records

        def get_item(self, path, *, seen_aliases=frozenset()):
            assert isinstance(path, PurePath) and not path.is_absolute(), path
            try:
                the_path, the_record = self.cache[path]
            except KeyError:
                if path == PurePath():
                    the_path, the_record = self.get_child(
                        path, {'root' : self.records}, 'root',
                        seen_aliases=seen_aliases)
                    the_path = path
                else:
                    the_path, the_record = self.get_item(
                        path.parent(),
                        seen_aliases=seen_aliases)
                    the_path, the_record = self.get_child(
                        the_path, the_record, path.name,
                        seen_aliases=seen_aliases )
                self.cache[path] = the_path, the_record
            if the_record is not None:
                the_record = the_record.copy()
            return the_path, the_record

        def get_child(self, parent_path, parent_record, name,
            *, seen_aliases
        ):
            path = parent_path/name
            if parent_record is None:
                return path, None;
            assert isinstance(parent_record, dict), (
                parent_path, parent_record )
            record = parent_record.get(name)
            if record is None:
                return path, None;
            if not isinstance(record, dict):
                raise TypeError(path, record)
            return path, record.copy();

        def resolve(self, path):
            the_path, the_record = self.get_item(path)
            return the_path

        def __getitem__(self, path):
            the_path, the_record = self.get_item(path)
            return the_record

        def __contains__(self, path):
            the_path, the_record = self.get_item(path)
            return the_record is not None

    class InrecordAccessor(RecordAccessor):
        cache = dict()

        def list_targets(self):
            """List some targets based on inrecords."""
            target_iterator = self._list_targets(PurePath(), self.records)
            root = next(target_iterator)
            assert root == PurePath(), root
            yield from target_iterator

        def _list_targets(self, inpath, inrecord):
            if inpath.suffix == '.tex':
                yield inpath.with_suffix('')
            elif inpath.suffix == '':
                yield inpath
                for subname, subrecord in inrecord.items():
                    if '$' in subname:
                        continue
                    yield from self._list_targets(inpath/subname, subrecord)

    class OutrecordAccessor(RecordAccessor):
        cache = dict()

        # Extension
        def get_child(self, parent_path, parent_record, name,
            *, seen_aliases
        ):
            path, record = super().get_child(parent_path, parent_record, name,
                seen_aliases=seen_aliases )
            if record is None:
                record = {'$fake' : True}
            if '$alias' in record:
                if len(record) > 1:
                    raise ValueError(
                        '{}: $alias must be the only content of the record.'
                        .format(path) )
                if path in seen_aliases:
                    raise ValueError('{}: alias cycle detected.'.format(path))
                aliased_path = pure_join(path.parent(), record['$alias'])
                return self.get_item(aliased_path,
                    seen_aliases=seen_aliases.union((path,)) );
            self.derive_attributes(parent_record, record, path)
            return path, record;

        @classmethod
        def derive_attributes(cls, parent_record, record, path):
            record['$style'] = cls.derive_styles(
                parent_style=parent_record.get('$style'),
                style=record.get('$style'),
                path=path )

        def list_targets(self):
            """List some targets based on outrecords."""
            target_iterator = self._list_targets(PurePath(), self.records)
            root = next(target_iterator)
            assert root == PurePath(), root
            yield from target_iterator

        def _list_targets(self, outpath, outrecord):
            yield outpath
            assert isinstance(outrecord, dict), type(outrecord)
            if '$alias' in outrecord:
                return
            if '$delegate' in outrecord:
                for delegator in outrecord.get('$delegate'):
                    yield pure_join(outpath, delegator)
            for subname, subrecord in outrecord.items():
                if '$' in subname:
                    continue
                yield from self._list_targets(outpath/subname, subrecord)

        @classmethod
        def derive_styles(cls, parent_style, style, path):
            if parent_style is None:
                parent_style = []
            if style is None:
                return parent_style

            if not isinstance(style, dict):
                return cls.assimilate_style(style, path)

            for key, substyle in style.items():
                if key == 'extend':
                    return parent_style + cls.assimilate_style(substyle, path)
                else:
                    raise ValueError(key)
            return base_style

        @classmethod
        def assimilate_style(cls, style, path):
            assimilated = []
            append = assimilated.append
            for item in style:
                if isinstance(item, str):
                    inpath = pure_join(path, item).with_suffix('.sty')
                    append({'style' : inpath})
                elif isinstance(item, dict):
                    append(item)
                else:
                    raise TypeError(item)
            return assimilated


    ##########
    # LaTeX-level functions

    @classmethod
    def constitute_document(cls, metarecord, metastyle, metabody):
        documentclass = cls.select_documentclass(metarecord)
        classoptions = cls.generate_classoptions(metarecord)

        return cls.substitute_document(
            documentclass=documentclass,
            classoptions=cls.constitute_options(classoptions),
            preamble=cls.constitute_preamble(metarecord, metastyle),
            body=cls.constitute_body(metarecord, metabody)
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
    def select_documentclass(cls, metarecord):
        return metarecord.get('class', 'article')

    @classmethod
    def generate_classoptions(cls, metarecord):
        paper_option = metarecord.get('paper', 'a5paper')
        yield str(paper_option)
        font_option = metarecord.get('font', '10pt')
        yield str(font_option)
        yield from metarecord.get('class options', ())

        if paper_option not in {'a4paper', 'a5paper'}:
            logger.warning(
                "<BOLD><MAGENTA>{name}<NOCOLOUR> uses "
                "bad paper option '<YELLOW>{option}<NOCOLOUR>'<RESET>"
                .format(name=metarecord.metaname, option=paper_option) )
        if font_option not in {'10pt', '11pt', '12pt'}:
            logger.warning(
                "<BOLD><MAGENTA>{name}<NOCOLOUR> uses "
                "bad font option '<YELLOW>{option}<NOCOLOUR>'<RESET>"
                .format(name=metarecord.metaname, option=font_option) )

#    def generate_metapreamble(self, metarecord):
#        for item in metarecord['style']:
#            assert isinstance(item, dict), item
#            if 'verbatim' in item:
#                yield item
#            elif 'package' in item:
#                yield item
#            elif 'style' in item:
#                item['alias'] = metarecord['aliases'][item['style']]
#                yield item
#        if 'selectsize' in metarecord:
#            font, skip = metarecord['selectsize']
#            yield {'verbatim' :
#                self.substitute_selectsize(font=font, skip=skip) }
#        yield from metarecord.get('preamble', ())

    @classmethod
    def constitute_preamble(cls, metarecord, metastyle):
        aliases = metarecord['aliases']

        preamble_items = []
        for item in metastyle:
            assert isinstance(item, dict), item
            if 'style' in item:
                inpath = item['style']
                item['alias'] = aliases[inpath]
            preamble_items.append(cls.constitute_preamble_item(item))
        if 'selectsize' in metarecord:
            font, skip = metarecord['selectsize']
            preamble_items.append(
                cls.substitute_selectsize(font=font, skip=skip) )
        return '\n'.join(preamble_items)

    selectsize_template = (
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
        elif 'style' in item:
            alias = item['alias']
            assert alias.endswith('.sty')
            return cls.substitute_uselocalpackage(
                package=alias[:-len('.sty')], inpath=item['style'] )
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
        aliases = metarecord['aliases']
        inrecords = metarecord['inrecords']
        figname_maps = metarecord['figname maps']

        body_items = []
        for item in metabody:
            assert isinstance(item, dict), item
            if 'input' in item:
                inpath = item['input']
                item['alias'] = aliases[inpath]
                item['inrecord'] = inrecords[inpath]
                item['figname map'] = figname_maps[inpath]
            body_items.append(cls.constitute_body_item(item))

        return '\n\n'.join(body_items)

    @classmethod
    def constitute_body_item(cls, item):
        assert isinstance(item, dict), item
        if 'verbatim' in item:
            return item['verbatim']
        elif 'input' in item:
            kwargs = dict(item)
            kwargs['inpath'] = kwargs.pop('input')
            kwargs['figname_map'] = kwargs.pop('figname map')
            return cls.constitute_body_input(**kwargs)
        else:
            raise ValueError(item)

    @classmethod
    def constitute_body_input(cls, inpath, *,
        alias, inrecord, figname_map, rigid=False
    ):
        caption = cls.extract_inrecord_caption(inpath, inrecord)
        body = cls.substitute_input(
            caption=caption, filename=alias, inpath=inpath )
        date = inrecord.get('$date')
        if rigid:
            body = cls.substitute_jeolmheader() + '\n' + body
        if date is None:
            body = cls.substitute_datedef(date='(no date)') + '\n' + body
        else:
            date = cls.constitute_date(date)
            body = cls.substitute_datedef(date=date) + '\n' + body
            if not rigid:
                body = body + '\n' + cls.substitute_datestamp()
        if figname_map:
            body = cls.constitute_figname_map(figname_map) + '\n' + body
        return body

    input_template = (
        r'\section*{$caption%'
         '\n    }'
        r'\resetproblem' '\n'
        r'\input{$filename}% $inpath' )
    jeolmheader_template = r'\jeolmheader'
    datedef_template = r'\def\jeolmdate{$date}'
    datestamp_template = (
        r'    \begin{flushright}\small' '\n'
        r'    \jeolmdate' '\n'
        r'    \end{flushright}'
    )

    @classmethod
    def extract_inrecord_caption(cls, inpath, inrecord):
        caption = inrecord.get('$caption')
        if caption is None:
            caption = '{}'.format(inpath)
        return caption

    @classmethod
    def constitute_figname_map(cls, figname_map):
        return '\n'.join(
            cls.substitute_jeolmfiguremap(alias=figalias, name=figname)
            for figalias, figname in figname_map.items() )

    jeolmfiguremap_template = r'\jeolmfiguremap{$alias}{$name}'

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

    clearpage_template = r'\clearpage'
    phantom_template = r'\phantom{Ы}'

    ##########
    # Supplementary finctions

    @staticmethod
    def select_metaname(target, date=None):
        metaname = '-'.join(target.parts)
        if isinstance(date, datetime.date):
            date_prefix = '{0.year:04}-{0.month:02}-{0.day:02}'.format(date)
            metaname = date_prefix + '-' + metaname
        return metaname

    @staticmethod
    def pathify_target(target):
        assert isinstance(target, str), target
        if not target or ' ' in target:
            raise ValueError(target)
        path = PurePath(target)
        path = PurePath(*(part for part in path.parts if '.' not in part))
        if path.is_absolute():
            raise ValueError(target)
        return path

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
    def digest_style_item(cls, item):
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
        elif 'style' in item:
            if not item.keys() <= {'style'}:
                raise ValueError(item)
            inpath = PurePath(item['style'])
            if inpath.is_absolute():
                raise ValueError(item)
            digested = {'style' : inpath}
        else:
            raise ValueError(item)
        return digested

    @classmethod
    def digest_body_item(cls, item):
        assert isinstance(item, dict), item
        if 'verbatim' in item:
            if not item.keys() <= {'verbatim'}:
                raise ValueError(item)
            digested =  {
                'verbatim' : str(item['verbatim']) }
        elif 'input' in item:
            if not item.keys() <= {'input', 'rigid'}:
                raise ValueError(item)
            inpath = PurePath(item['input'])
            if inpath.is_absolute():
                raise ValueError(item)
            digested = {'input' : inpath}
            if 'rigid' in item:
                digested['rigid'] = bool(item['rigid'])
        else:
            raise ValueError(item)
        return digested

