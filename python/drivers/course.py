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

class CourseDriver(metaclass=Substitutioner):
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
        fignames = { figname
            for metarecord in metarecords.values()
            for figname in metarecord['fignames'] }
        figrecords = {
            figname : self.figrecords[figname]
            for figname in fignames }

        return metarecords, figrecords

    def list_targets(self):
        yield from self.inrecords.list_targets()
        yield from self.outrecords.list_targets()

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

        inpath_set = metarecord['inpath set']
        metarecord['aliases'] = {
            inpath : '-'.join(inpath.parts).replace('.tex', '.in.tex')
            for inpath in inpath_set }
        metarecord['sources'] = {
            alias : inpath
            for inpath, alias in metarecord['aliases'].items() }
        if len(metarecord['sources']) < len(metarecord['aliases']):
            raise ValueError({
                metarecord['aliases'][inpath]
                for inpath in
                    inpath_set.difference(metarecord['sources'].values())
            })
        metarecord['inrecords'] = {
            inpath : self.inrecords[inpath] for inpath in inpath_set }

        figname_maps = metarecord['figname maps'] = {
            inpath : self.produce_figname_map(inpath)
            for inpath in inpath_set }

        metarecord['fignames'] = sorted(
            figname
            for figname_map in figname_maps.values()
            for figname in figname_map.values() )

        metarecord['document'] = self.constitute_document(
            metarecord, metabody=metarecord.pop('body'))
        self.formed_metarecords[target] = metaname
        return metaname

    def produce_figname_map(self, inpath):
        """
        Return {figalias : figname for each figname included in source}

        Update self.figrecords.
        """

        inrecord_figures = self.inrecords[inpath].get('figures')
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
        if record is None:
            yield target
            return;
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
        inpath_set = set()
        date_set = set()
        resolved_path, record = self.outrecords.get_item(target)

        for method in self.list_protorecord_methods():
            try:
                protorecord = method(resolved_path, record,
                    inpath_set=inpath_set, date_set=date_set )
                # Call is not over! We must fix 'body', 'date' and 'inpath set'
                break;
            except RecordNotFoundError as error:
                if error.args != (target,):
                    raise;
        else:
            raise RecordNotFoundError(target);

        if not isinstance(protorecord['body'], list):
            protorecord['body'] = list(protorecord['body'])
        protorecord.setdefault('date', self.min_date(date_set))
        protorecord['inpath set'] = inpath_set
        return protorecord

    def produce_rigid_protorecord(self, target, record,
        *, inpath_set, date_set
    ):
        """Return protorecord with 'body'."""
        if record is None or '$rigid' not in record:
            raise RecordNotFoundError(target);
        protorecord = dict()
        protorecord.update(record.get('$rigid$opt', ()))
        if 'date' in protorecord:
            date_set.add(protorecord['date']); date_set = set()
        rigid = record['$rigid']

        protorecord['body'] = list(self.generate_rigid_body(
            target, rigid, inpath_set=inpath_set, date_set=date_set ))
        return protorecord

    def produce_fluid_protorecord(self, target, record,
        *, inpath_set, date_set
    ):
        """Return protorecord with 'body'."""
        if record is None:
            record = {}
        protorecord = dict()
        protorecord.update(record.get('$fluid$opt', ()))
        if 'date' in protorecord:
            date_set.add(protorecord['date']); date_set = set()
        fluid = record.get('$fluid')

        protorecord['body'] = list(self.generate_fluid_body(
            target, fluid, inpath_set=inpath_set, date_set=date_set ))
        return protorecord

    def generate_rigid_body(self, target, rigid, *, inpath_set, date_set):
        for page in rigid:
            yield self.substitute_clearpage()
            if not page: # empty page
                yield self.substitute_phantom()
                continue;
            for item in page:
                if isinstance(item, dict):
                    yield self.constitute_special(item)
                    continue;
                if not isinstance(item, str):
                    raise TypeError(target, item)

                yield self.substitute_jeolmheader()
                subpath = self.outrecords.resolve(pure_join(target, item))
                inpath, inrecord = self.inrecords.get_item(
                    subpath.with_suffix('.tex') )
                if inrecord is None:
                    raise RecordNotFoundError(inpath, target);
                inpath_set.add(inpath)
                date_set.add(inrecords.get('date'))
                yield {'inpath' : inpath}

    def generate_fluid_body(self, target, fluid, *, inpath_set, date_set):
        if fluid is None:
            # No outrecords fluid - generate fluid from inrecords
            fluid = self.generate_autofluid(target)
        if fluid is None:
            # Try single file inrecord
            inpath, inrecord = self.inrecords.get_item(
                target.with_suffix('.tex') )
            if inrecord is None:
                # Fail
                raise RecordNotFoundError(target);
            inpath_set.add(inpath)
            date_set.add(inrecord.get('date'))
            yield {'inpath' : inpath}
            return;
        for item in fluid:
            if isinstance(item, dict):
                yield self.constitute_special(item)
                continue;
            if not isinstance(item, str):
                raise TypeError(target, item)

            subpath, subrecord = self.outrecords.get_item(
                pure_join(target, item) )
            subprotorecord = self.produce_fluid_protorecord(
                subpath, subrecord,
                inpath_set=inpath_set, date_set=date_set )
            yield from subprotorecord['body']

    def generate_autofluid(self, target):
        inrecord = self.inrecords[target]
        if inrecord is None:
            return None;
        subnames = []
        for subname in inrecord:
            subnamepath = PurePath(subname)
            suffix = subnamepath.suffix
            if suffix == '':
                subnames.append(subname)
            elif suffix == '.tex':
                subnames.append(str(subnamepath.with_suffix('')))
            else: pass
        return subnames

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
        raise RecordNotFoundError(figpath, 'figure');

    def trace_figure_used(self, inpath, *, seen_paths=frozenset()):
        if inpath in seen_paths:
            raise ValueError(path)
        seen_paths = seen_paths.union((inpath,))
        assert inpath.suffix == '.asy', inpath
        inrecord = self.inrecords[inpath]
        if inrecord is None:
            raise RecordNotFoundError(inpath);
        used = inrecord.get('used')
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

        def get_item(self, path):
            assert isinstance(path, PurePath) and not path.is_absolute(), path
            the_record = self.records
            the_path = PurePath()
            for part in path.parts:
                the_path, the_record = self.get_child(
                    the_path, the_record, part )
            return the_path, the_record

        def get_child(self, parent_path, parent_record, name):
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
            return path, record;

        def resolve(self, path):
            the_path, the_record = self.get_item(path)
            return the_path

        def __getitem__(self, path):
            the_path, the_record = self.get_item(path)
            return the_record

        def __contains__(self, path):
            return self[path] is not None

    class InrecordAccessor(RecordAccessor):
        def list_targets(self, inpath=PurePath(), inrecord=None):
            """List some targets based on inrecords."""
            if inrecord is None:
                inrecord = self.records
            for subname, subrecord in inrecord.items():
                subpath = inpath/subname
                if subpath.suffix == '.tex':
                    yield subpath.with_suffix('')
                    continue;
                elif subpath.suffix == '':
                    yield subpath
                    yield from self.list_targets(subpath, subrecord)

    class OutrecordAccessor(RecordAccessor):

        # Override
        def get_item(self, path, *, seen_aliases=frozenset()):
            assert isinstance(path, PurePath) and not path.is_absolute(), path
            the_record = self.records
            the_path = PurePath()
            for part in path.parts:
                the_path, the_record = self.get_child(
                    the_path, the_record, part, seen_aliases=seen_aliases )
            return the_path, the_record

        # Extension
        def get_child(self, parent_path, parent_record, name,
            *, seen_aliases
        ):
            path, record = super().get_child(parent_path, parent_record, name)
            if record is None:
                return path, None;
            if '$alias' not in record:
                return path, record;
            if len(record) > 1:
                raise ValueError(
                    '{!s}: $alias must be the only content of the record.'
                    .format(path) )
            if path in seen_aliases:
                raise ValueError('{!s}: alias cycle detected.')
            aliased_path = pure_join(path, record['$alias'])
            return self.get_item(aliased_path,
                seen_aliases=seen_aliases.union((path,)) );

        def list_targets(self, outpath=PurePath(), outrecord=None):
            """List some targets based on outrecords."""
            if outrecord is None:
                outrecord = self.records
            for subname, subrecord in outrecord.items():
                if '$' in subname:
                    continue;
                subpath = outpath/subname
                yield subpath
                if not isinstance(subrecord, dict):
                    continue;
                if '$alias' in subrecord:
                    continue;
                if '$delegate' in subrecord:
                    for delegator in subrecord.get('$delegate'):
                        yield pure_join(subpath, delegator)
                yield from self.list_targets(subpath, subrecord)

    ##########
    # LaTeX-level functions

    def constitute_document(self, metarecord, metabody):
        documentclass = self.select_documentclass(metarecord)
        classoptions = self.generate_classoptions(metarecord)
        metapreamble = self.generate_metapreamble(metarecord)

        return self.substitute_document(
            documentclass=documentclass,
            classoptions=self.constitute_options(classoptions),
            preamble=self.constitute_preamble(metapreamble),
            body=self.constitute_body(metarecord, metabody)
        )

    document_template = (
        r'% Auto-generated by jeolm' '\n'
        r'\documentclass$classoptions{$documentclass}' '\n\n'
        r'$preamble' '\n\n'
        r'\begin{document}' '\n\n'
        r'$body' '\n\n'
        r'\end{document}' '\n'
    )

    def select_documentclass(self, metarecord):
        return 'article'

    def generate_classoptions(self, metarecord):
        yield 'a5paper'
        font_option = metarecord.get('font')
        if font_option is None:
            yield '10pt'
        elif font_option in {'10pt', '11pt', '12pt'}:
            yield font_option
        else:
            raise ValueError(font_option)

    def generate_metapreamble(self, metarecord):
        yield {'package' : 'local'}
        yield {'package' : 'pgfpages'}
        yield {'verbatim' :
            self.substitute_pgfpages_resize(options='a4paper') }
#        yield { 'package' : 'hyperref', 'options' : [
#            'dvips', 'setpagesize=false',
#            'pdftitle={{{}}}'.format(metarecord['metaname'])
#        ]}
        if 'selectsize' in metarecord:
            font, skip = metarecord['selectsize']
            yield self.substitute_selectsize(font=font, skip=skip)
        yield from metarecord.get('preamble', ())

    pgfpages_resize_template = r'\pgfpagesuselayout{resize to}[$options]'
    selectsize_template = (
        r'\AtBeginDocument{\fontsize{$font}{$skip}\selectfont}' )

    @classmethod
    def constitute_preamble(cls, metapreamble):
        lines = []
        for metaline in metapreamble:
            if not isinstance(metaline, dict):
                raise TypeError(metaline)
            lines.append(cls.constitute_preamble_line(metaline))
        return '\n'.join(lines)

    @classmethod
    def constitute_preamble_line(cls, metaline):
        assert isinstance(metaline, dict)
        if 'verbatim' in metaline:
            return str(metaline['verbatim'])
        if 'package' in metaline:
            package = metaline['package']
            options = metaline.get('options', None)
            options = cls.constitute_options(options)
            return cls.substitute_usepackage(
                package=package,
                options=options )
        else:
            raise ValueError(metaline)

    usepackage_template = r'\usepackage$options{$package}'

    @classmethod
    def constitute_options(cls, options):
        if not options:
            return '';
        if not isinstance(options, str):
            options = ','.join(options)
        return '[' + options + ']'

    def constitute_body(self, metarecord, metabody):
        aliases, inrecords, figname_maps = ( metarecord[key]
            for key in ('aliases', 'inrecords', 'figname maps') )

        # Extension of self.consistute_input()
        def constitute_input(item):
            assert isinstance(item, dict), item
            assert 'inpath' in item, item
            inpath = item['inpath']
            item = item.copy()
            item.update(
                alias=aliases[inpath],
                inrecord=inrecords[inpath],
                figname_map=figname_maps[inpath])
            return self.constitute_input(**item)

        return '\n\n'.join(
            item if isinstance(item, str) else constitute_input(item)
            for item in metabody
        )

    def constitute_input(self, inpath, alias, inrecord, figname_map):
        caption = inrecord.get('caption', '(no caption)')
        date = inrecord.get('date', '(no date)')
        body = self.substitute_input(
            caption=caption, date=self.constitute_date(date),
            filename=alias )

        if figname_map:
            body = self.constitute_figname_map(figname_map) + '\n' + body
        return body

    input_template = (
        r'\section*{$caption%'
         '\n    }'
        r'\resetproblem' '\n'
        r'\input{$filename}' '\n'
        r'    \begin{flushright}\small' '\n'
        r'    $date' '\n'
        r'    \end{flushright}'
    )

    def constitute_figname_map(self, figname_map):
        return '\n'.join(
            self.substitute_jeolmfiguremap(alias=figalias, name=figname)
            for figalias, figname in figname_map.items() )

    jeolmfiguremap_template = r'\jeolmfiguremap{$alias}{$name}'

    @classmethod
    def constitute_date(cls, date):
        if not isinstance(date, datetime.date):
            return str(date);
        return cls.substitute_date(
            year=date.year,
            month=cls.ru_monthes[date.month-1],
            day=date.day )

    date_template = r'$day~$month~$year'
    ru_monthes = [
        'января', 'февраля', 'марта', 'апреля',
        'мая', 'июня', 'июля', 'августа',
        'сентября', 'октября', 'ноября', 'декабря' ]

    def constitute_special(self, special):
        assert isinstance(special, dict), special
        if len(special) != 1 or next(iter(special.keys())) != 'verbatim':
            raise ValueError(special)
        return str(next(iter(special.values())))

    jeolmheader_template = r'\jeolmheader'
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
            return min(datetime_date_set);
        elif len(date_set) == 1:
            date, = date_set
            return date;
        else:
            return None;

