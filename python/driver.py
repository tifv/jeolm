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

import re
import datetime
from itertools import chain
from functools import wraps
from collections import OrderedDict
from string import Template

from pathlib import PurePosixPath as PurePath

from .utils import pure_join
from .records import Records, RecordNotFoundError
from .flags import FlagSet, UnutilizedFlagsError

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
    def wrapper(self, metapath, flags, metarecord=None, **kwargs):
        if metarecord is None:
            metarecord = self.metarecords[metapath]
        return method(self, metapath, flags, metarecord=metarecord, **kwargs)
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
        """
        Target flags (some of):
            'no-delegate'
                ignore delegation mechanics
            'multidate'
                place date after each file instead of in header
        """
        targets = self.split_produced_targets(targets)
        targets = list(chain.from_iterable(
            self.trace_delegators(metapath, flags)
            for metapath, flags in targets ))

        # Generate outrecords and store them in self.outrecords
        outnames = [
            self.form_outrecord(metapath, flags)
            for metapath, flags in targets ]

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
                yield figrecord['source']

    def form_outrecord(self, metapath, flags):
        """
        Return outname.

        Update self.outrecords and self.figrecords.
        """
        assert isinstance(flags, FlagSet), type(flags)
        target = (metapath, flags.as_frozenset())
        try:
            return self.outnames_by_target[target]
        except KeyError:
            pass

        flags = flags.clean_copy()
        outrecord = self.produce_protorecord(metapath, flags)
        try:
            flags.check_unutilized_flags(recursive=__debug__)
        except UnutilizedFlagsError as error:
            errorflags = ', '.join( "'{}'".format(flag)
                for flag in sorted(error.args[0]) )
            if error.origin_tb is not None:
                import traceback
                stack = ''.join(traceback.format_list(error.origin_tb))
                raise RuntimeError(
                    "Unutilised flags {flags} detected "
                    "while processing target {target}, "
                    "originated from:\n{stack}".format(
                        target=self.format_target(metapath, flags),
                        stack=stack, flags=errorflags )
                ) from error
            raise UnutilizedFlagsError(
                "Unutilized flags {flags} in target {target}".format(
                    target=self.format_target(metapath, flags),
                    flags=errorflags )
                ) from error

        assert outrecord.keys() >= {
            'date', 'inpaths', 'fignames', 'metastyle', 'metabody'
        }, outrecord.keys()

        outname = self.select_outname(metapath, flags,
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
        self.outnames_by_target[target] = outname
        return outname

    def revert_aliases(self, outrecord):
        """
        Based on outrecord['aliases'], define 'sources'.
        """
        outrecord['sources'] = {
            alias : inpath
            for inpath, alias in outrecord['aliases'].items() }
        if len(outrecord['sources']) < len(outrecord['aliases']):
            screened_inpaths = frozenset(outrecord['inpaths']).difference(
                outrecord['sources'].values() )
            clashed_aliases = {
                outrecord['aliases'][inpath]
                for inpath in clashed_inpaths }
            clashed_inpaths = {
                inpath
                for inpath, alias in outrecord['aliases'].items()
                if alias in clashed_aliases }
            raise ValueError(
                "Clashed inpaths: {}"
                .format(', '.join(
                    "'{}'".format(inpath)
                    for inpath in sorted(clashed_inpaths)
                )) )

    def produce_figname_map(self, figures):
        """
        Return { figalias : figname
            for each figname included in source as figalias }

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
    def trace_delegators(self, metapath, flags, metarecord,
        *, seen_targets=frozenset()
    ):
        """Generate (metapath, flags) pairs."""
        assert isinstance(flags, FlagSet), type(flags)
        assert not metapath.is_absolute(), metapath
        target = (metapath, flags.as_frozenset())
        if target in seen_targets:
            raise ValueError(
                "Delegation cycle detected from {target}"
                .format(target=self.format_target(metapath, flags)) )
        seen_targets |= {target}

        if 'no-delegate' in flags:
            yield metapath, flags.difference(('no-delegate',))
            return

        delegators = list(self.find_delegators(metapath, flags, metarecord))
        if not delegators:
            yield metapath, flags
            return
        for submetapath, subflags in delegators:
            yield from self.trace_delegators(submetapath, subflags,
                seen_targets=seen_targets )

    def find_delegators(self, metapath, flags, metarecord):
        """Yield (metapath, flags) pairs."""
        delegators = self.get_flagged_value(metarecord, '$delegate',
            flags=flags )
        if delegators is None:
            return
        if not isinstance(delegators, list):
            raise TypeError(
                "{target} delegators must be a list, not "
                "'{delegators.__class__}'"
                .format(
                    target=self.format_target(metapath, flags),
                    delegators=delegators ) )
        for item in delegators:
            if isinstance(item, str):
                subpath, add_flags, remove_flags = self.split_target(item)
                item = {
                    'delegate' : subpath,
                    'add flags' : add_flags, 'remove flags' : remove_flags }
            if not isinstance(item, dict): raise TypeError(item)
            item, subflags = self.derive_item_flags(item, flags)
            if 'condition' in item:
                item = item.copy()
                if not self.check_condition(item.pop('condition'), flags):
                    continue
            if item.keys() != {'delegate'}: raise ValueError(item)
            submetapath = item['delegate']
            assert isinstance(subflags, FlagSet), type(subflags)
            yield pure_join(metapath, submetapath), subflags

    @fetch_metarecord
    def produce_protorecord(self, metapath, flags, metarecord):
        """
        Return protorecord.
        """
        date_set = set()

        protorecord = {}
        protorecord.update(self.get_flagged_value(
            metarecord, '$manner$options',
            flags=flags, default={} ))
        protorecord['metabody'] = list(self.generate_metabody(
            metapath, flags, metarecord, date_set=date_set ))
        protorecord['metastyle'] = list(self.generate_metastyle(
            metapath, flags, metarecord ))

        inpaths = protorecord['inpaths'] = list()
        aliases = protorecord['aliases'] = dict()
        fignames = protorecord['fignames'] = list()
        tex_packages = protorecord['tex packages'] = list()
        protorecord.setdefault('date', self.min_date(date_set))

        protorecord['metabody'] = list(self.digest_metabody(
            protorecord.pop('metabody'),
            inpaths=inpaths, aliases=aliases, fignames=fignames,
            tex_packages=tex_packages ))

        protorecord['metastyle'] = list(self.digest_metastyle(
            protorecord.pop('metastyle'),
            inpaths=inpaths, aliases=aliases ))

        # dropped keys
        assert 'preamble' not in protorecord, 'style'
        assert 'style' not in protorecord, '$manner$style'
        assert '$out$options' not in metarecord, '$manner$options'
        assert '$rigid' not in metarecord, '$manner'
        assert '$rigid$opt' not in metarecord, '$manner$options'
        assert '$fluid' not in metarecord, '$matter'
        assert '$fluid$opt' not in metarecord
        assert '$manner$opt' not in metarecord, '$manner$options'

        return protorecord

    @fetch_metarecord
    def generate_metabody(self, metapath, flags, metarecord,
        *, date_set
    ):
        """
        Yield metabody items. Update date_set.
        """
        yield from self.generate_manner_metabody(metapath, flags, metarecord,
            date_set=date_set )

    @fetch_metarecord
    def generate_manner_metabody(self, metapath, flags, metarecord,
        *, date_set, seen_targets=frozenset()
    ):
        """
        Yield metabody items. Update date_set.
        """
        assert isinstance(flags, FlagSet), type(flags)
        target = (metapath, flags.as_frozenset())
        if target in seen_targets:
            raise ValueError(
                "Manner cycle detected from {target}"
                .format(target=self.format_target(metapath, flags)) )
        seen_targets |= {target}

        try:
            manner = self.get_flagged_value(metarecord, '$manner', flags=flags)
        except ValueError as error:
            raise ValueError(
                "Error detected while generating {target} matter"
                .format(target=self.format_target(metapath, flags))
            ) from error
        if manner is None:
            manner = [['.']]

        for item in manner:
            if isinstance(item, list):
                if not item:
                    yield {'verbatim' : self.substitute_emptypage()}
                    continue
                yield from self.generate_matter_metabody(
                    metapath, flags.union(('every-header',)), metarecord,
                    date_set=date_set, matter=item )
                yield {'verbatim' : self.substitute_clearpage()}
                continue
            if isinstance(item, str):
                subpath, add_flags, remove_flags = self.split_target(item)
                item = {
                    'manner' : subpath,
                    'add flags' : add_flags, 'remove flags' : remove_flags }
            if not isinstance(item, dict):
                raise TypeError(
                    "Expected dict or str, found {the_type} in manner {target}"
                    .format( the_type=type(item),
                        target=self.format_target(metapath, flags) )
                )
            if 'condition' in item:
                item = item.copy()
                condition = item.pop('condition')
                if not self.check_condition(condition, flags):
                    continue
            if 'manner' not in item:
                matter.append(item)
                continue
            item, subflags = self.derive_item_flags(item, flags)
            if item.keys() != {'manner'}:
                raise ValueError(
                    "Unrecognized item {item} in manner {target}"
                    .format(item=item,
                        target=self.format_target(metapath, flags) )
                )
            submetapath = item['manner']
            yield from self.generate_manner_metabody(
                pure_join(metapath, submetapath), subflags,
                date_set=date_set, seen_targets=seen_targets )

    @fetch_metarecord
    def generate_matter_metabody(self, metapath, flags, metarecord,
        *, date_set, seen_targets=frozenset(), matter=None
    ):
        """
        Yield metabody items.

        Update date_set.
        """
        assert isinstance(flags, FlagSet), type(flags)
        if matter is None:
            target = (metapath, flags.as_frozenset())
            if target in seen_targets:
                raise ValueError(
                    "Matter cycle detected from {target}"
                    .format(target=self.format_target(metapath, flags)) )
            seen_targets |= {target}

        if '$date' in metarecord:
            date_set.add(metarecord['$date']); date_set = set()

        if not flags.intersection(('no-header', 'every-header')):
            date_subset = set()
            # exhaust iterator to find date_subset
            metabody = list(self.generate_matter_metabody(
                metapath, flags.union(('no-header',)), metarecord,
                date_set=date_subset,
                seen_targets=seen_targets, matter=matter ))
            yield from self.generate_header_metabody(
                metapath, flags, metarecord,
                date=self.min_date(date_subset) )
            yield from metabody
            date_set.update(date_subset)
            return # recurse
        if 'every-header' in flags:
            flags = flags.difference(('every-header',))

        if matter is None:
            try:
                matter = self.get_flagged_value(
                    metarecord, '$matter', flags=flags )
            except ValueError as error:
                raise ValueError(
                    "Error detected while generating {target} matter"
                    .format(target=self.format_target(metapath, flags))
                ) from error
            if matter is None:
                matter = self.generate_matter(metapath, flags, metarecord)
        for item in matter:
            if isinstance(item, str):
                subpath, add_flags, remove_flags = self.split_target(item)
                item = {
                    'matter' : subpath,
                    'add flags' : add_flags, 'remove flags' : remove_flags }
            if not isinstance(item, dict):
                raise TypeError(
                    "Expected dict or str, found {the_type} in matter {target}"
                    .format( the_type=type(item),
                        target=self.format_target(metapath, flags) )
                )
            if 'condition' in item:
                item = item.copy()
                condition = item.pop('condition')
                if not self.check_condition(condition, flags):
                    continue
            if 'matter' not in item:
                yield item
                continue
            item, subflags = self.derive_item_flags(item, flags)
            if item.keys() != {'matter'}:
                raise ValueError(
                    "Unrecognized item {item} in matter {target}"
                    .format(item=item,
                        target=self.format_target(metapath, flags) )
                )
            submetapath = item['matter']

            yield from self.generate_matter_metabody(
                pure_join(metapath, submetapath), subflags,
                date_set=date_set,
                seen_targets=seen_targets )

    def generate_header_metabody(self, metapath, flags, metarecord, *, date):
        if 'multidate' not in flags:
            yield {'verbatim' : self.constitute_datedef(date=date)}
        else:
            yield {'verbatim' : self.constitute_datedef(date=None)}
        yield {'verbatim' : self.substitute_jeolmheader()}
        yield {'verbatim' : self.substitute_resetproblem()}

    def generate_matter(self, metapath, flags, metarecord):
        """Yield matter items."""
        if not metarecord.get('$source', False):
            return
        if '$tex$source' in metarecord:
            yield from self.generate_tex_matter(
                metapath, flags, metarecord )
        for name in metarecord:
            if name.startswith('$'):
                continue
            if metarecord[name].get('$source', False):
                yield name

    def generate_tex_matter(self, metapath, flags, metarecord):
        assert metarecord.get('$tex$source', False)
        item = {'inpath' : metapath.with_suffix('.tex')}
        has_date = '$date' in metarecord
        if has_date:
            date = metarecord['$date']
        yield item
        if has_date and 'multidate' in flags:
            yield {'verbatim' : self.constitute_datedef(date=date)}
            yield {'verbatim' : self.substitute_datestamp()}

    @fetch_metarecord
    def generate_metastyle(self, metapath, flags, metarecord):
        manner_style = self.get_flagged_value(
            metarecord, '$manner$style',
            flags=flags, default=['.'] )
        pseudorecord = metarecord.copy()
        self.clear_flagged_keys(pseudorecord, '$style')
        pseudorecord['$style'] = manner_style
        pseudorecord['$pseudo'] = True
        yield from self.generate_matter_metastyle(
            metapath, flags, pseudorecord )

    @fetch_metarecord
    def generate_matter_metastyle(self, metapath, flags, metarecord,
        *, seen_targets=frozenset()
    ):
        assert isinstance(flags, FlagSet), type(flags)
        if not metarecord.get('$pseudo', False):
            target = (metapath, flags.as_frozenset())
            if target in seen_targets:
                raise ValueError(
                    "Style cycle detected from {target}"
                    .format(target=self.format_target(metapath, flags)) )
            seen_targets |= {target}

        try:
            style = self.get_flagged_value(metarecord, '$style', flags=flags)
        except ValueError as error:
            raise ValueError(
                "Error detected while generating {target} style"
                .format(target=self.format_target(metapath, flags))
            ) from error
        if style is not None:
            pass
        elif '$sty$source' in metarecord:
            style = [{'inpath' : metapath.with_suffix('.sty')}]
        else:
            style = ['..']

        for item in style:
            if isinstance(item, str):
                subpath, add_flags, remove_flags = self.split_target(item)
                item = {
                    'style' : subpath,
                    'add flags' : add_flags, 'remove flags' : remove_flags }
            if not isinstance(item, dict): raise TypeError(item)
            if 'condition' in item:
                item = item.copy()
                condition = item.pop('condition')
                if not self.check_condition(condition, flags):
                    continue
            if 'style' not in item:
                yield item
                continue
            item, subflags = self.derive_item_flags(item, flags)
            if not item.keys() == {'style'}: raise ValueError(item)
            submetapath = item['style']

            yield from self.generate_matter_metastyle(
                pure_join(metapath, submetapath), subflags,
                seen_targets=seen_targets )

    def digest_metabody(self, metabody, *,
        inpaths, aliases, fignames, tex_packages
    ):
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
                for figname in figname_map.values():
                    if figname not in fignames:
                        fignames.append(figname)
                for tex_package in metarecord.get('$tex$packages', ()):
                    if tex_package not in tex_packages:
                        tex_packages.append(tex_package)
            yield item

    def digest_metastyle(self, metastyle, *,
        inpaths, aliases
    ):
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
        try:
            metarecord = self.metarecords[figpath]
        except RecordNotFoundError:
            pass
        else:
            for figtype in self.figtypes:
                figkey = self.figkeys[figtype]
                if not metarecord.get(figkey, False):
                    continue
                return figtype, figpath.with_suffix(self.figsuffixes[figtype])
        raise RecordNotFoundError("Figure {} not found.".format(figpath))

    def trace_asy_used(self, figpath, *, seen_paths=frozenset()):
        if figpath in seen_paths: raise ValueError(figpath)
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

        def list_targets(self, path=None):
            if path is None:
                path = PurePath()
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
                path = PurePath()
            else:
                path = parent_path/name
            child_record['$path'] = path
            super().derive_attributes(parent_record, child_record, name)

        def _get_child(self, record, name, *, original, **kwargs):
            child_record = super()._get_child(
                record, name, original=original, **kwargs )
            if '$library' not in child_record or original:
                return child_record
            return self.load_library_metadata(child_record['$library'])

        def load_library_metadata(self, library_name):
            if library_name == 'pgfpages':
                return pgfpages_library
            else:
                raise ValueError("Unknown library '{}'".format(library_name))

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
            preamble_items.append(cls.constitute_preamble_item(item))
        for tex_package in outrecord['tex packages']:
            preamble_items.append(cls.constitute_preamble_item(
                {'package' : tex_package} ))
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
    def select_outname(metapath, flags, date=None):
        outname = '-'.join(metapath.parts) + flags.as_flags()
        if isinstance(date, datetime.date):
            date_prefix = '{0.year:04}-{0.month:02}-{0.day:02}'.format(date)
            outname = date_prefix + '-' + outname
        return outname

    @staticmethod
    def format_target(metapath, flags):
        return str(metapath) + flags.as_flags()

    @classmethod
    def split_produced_targets(cls, targets, absolute=False):
        """Yield (metapath, flags) pairs."""
        for target in targets:
            if '.' in target: raise ValueError(target)
            metapath, flags, antiflags = cls.split_target(target)
            if metapath.is_absolute():
                raise ValueError("Absolute path in target {}".format(target))
            if antiflags:
                raise ValueError("Antiflag in target {}".format(target))
            yield metapath, FlagSet(flags, user=True)

    @classmethod
    def split_target(cls, target,
        target_pattern=re.compile(
            r'(?P<path>[^\[\] ]+)'
            r'(?:\[(?P<flags>[^\[\] ]+)\])?$' )
    ):
        """Return (metapath, flags, no_options)."""
        assert isinstance(target, str), target
        match = target_pattern.match(target)
        if match is None:
            raise ValueError("Failed to parse target '{}'".format(target))
        flags_string = match.group('flags')
        if flags_string is not None:
            raw_flags = frozenset(flags_string.split(','))
        else:
            raw_flags = frozenset()
        flags = set(); antiflags = set()
        for flag in raw_flags:
            if flag.startswith('-'):
                antiflags.add(flag[1:])
            else:
                flags.add(flag)
        path_string = match.group('path')
        assert path_string is not None, match.group(0)
        metapath = PurePath(path_string)
        return metapath, frozenset(flags), frozenset(antiflags)

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
    def check_condition(cls, condition, flags):
        if isinstance(condition, str):
            return condition in flags
        elif not isinstance(condition, dict):
            raise ValueError(condition)
        elif len(condition) != 1:
            raise ValueError(condition)
        (key, value), = condition.items()
        try:
            if key == 'not':
                return not cls.check_condition(value, flags)
            elif key == 'or':
                return any(cls.check_condition(item, flags)
                    for item in value )
            elif key == 'and':
                return all(cls.check_condition(item, flags)
                    for item in value )
            else:
                raise ValueError(condition)
        except ValueError as error:
            error.args += (condition,)

    @classmethod
    def get_flagged_value(cls, mapping, key, *, flags, default=None,
        flag_pattern=re.compile(
            r'(?:'
                r'(?:(?P<braket>\[)|(?P<brace>\{))'
                r'(?P<flags>.+)'
                r'(?(braket)\])(?(brace)\})'
            r')?$' )
    ):
        the_key = key
        assert isinstance(the_key, str), type(the_key)
        assert the_key.startswith('$')
        the_flags = flags
        assert isinstance(the_flags, (frozenset, FlagSet)), type(the_flags)
        if isinstance(the_flags, FlagSet):
            the_flags_set = None
        else:
            the_flags_set = the_flags

        matched_flagsets = set()
        matched_values = {}
        for key, value in mapping.items():
            if not key.startswith(the_key):
                continue
            flag_match = flag_pattern.match(key[len(the_key):])
            if flag_match is None:
                continue
            flags = flag_match.group('flags')
            if flags is None:
                flags = frozenset()
            else:
                flags = frozenset(flags.split(','))
                if not the_flags.issuperset(flags):
                    continue
                if flag_match.group('braket') is not None:
                    if the_flags_set is None:
                        the_flags_set = the_flags.as_set()
                    if flags != the_flags_set:
                        continue
                    matched_value = value
                    break
                assert flag_match.group('brace') is not None, match.group(0)
            if any(flags < flagset for flagset in matched_flagsets):
                # we are overmatched
                continue
            elif any(flags == flagset for flagset in matched_flagsets):
                raise ValueError('Flag set {!r} duplicated'.format(flags))
            else:
                overmatched_flagsets = frozenset(filter(
                    flags.__gt__, matched_flagsets ))
                matched_flagsets.difference_update(overmatched_flagsets)
                matched_flagsets.add(flags)
                matched_values[flags] = value
        else:
            if not matched_flagsets:
                return default
            if len(matched_flagsets) > 1:
                raise ValueError(
                    'Multiple flag sets matched, ambiguity unresolved',
                    *matched_flagsets )
            matched_flagset, = matched_flagsets
            matched_value = matched_values[matched_flagset]
        return matched_value

    @classmethod
    def clear_flagged_keys(cls, mapping, key):
        the_key = key
        flagged_keys = set()
        for key in mapping:
            if not key.startswith(the_key):
                continue
            flags = key[len(the_key):]
            if flags:
                if not flags.startswith('[') or not flags.endswith(']'):
                    continue
            flagged_keys.add(key)
        for key in flagged_keys:
            del mapping[key]

    @classmethod
    def derive_item_flags(cls, item, flags):
        the_flags = flags
        assert isinstance(the_flags, (frozenset, FlagSet)), type(the_flags)
        item = item.copy()
        if 'flags' in item:
            if 'add flags' in item or 'remove flags' in item:
                raise ValueError(item)
            flags = item.pop('flags')
            if not isinstance(flags, FlagSet):
                flags = frozenset(flags)
                if isinstance(the_flags, FlagSet):
                    flags = the_flags.bastard(frozenset(flags), user=True)
            return item, flags
        add_flags = frozenset(item.pop('add flags', ()))
        remove_flags = frozenset(item.pop('remove flags', ()))
        if add_flags & remove_flags:
            raise ValueError(item)
        flags = ( the_flags
            .union(add_flags, user=True)
            .difference(remove_flags, user=True) )
        return item, flags

class TestFilteringDriver(Driver):
    def generate_tex_matter(self, metapath, flags, metarecord):
        super_matter = list(super().generate_tex_matter(
            metapath, flags, metarecord ))
        if metarecord.get('$test', False):
            if not super_matter or 'exclude-test' in flags:
                return
            yield {'verbatim' : self.substitute_begingroup()}
            yield {'verbatim' : self.substitute_interrobang_section()}
            yield from super_matter
            yield from self.generate_scorebox_matter(
                metapath, flags, metarecord )
            yield {'verbatim' : self.substitute_endgroup()}
        else:
            yield from super_matter

    def generate_scorebox_matter(self, metapath, flags, metarecord):
        if 'with-problem-scores' not in flags:
            return
        problem_scores = metarecord.get('$test$problemscores')
        mark_limits = metarecord.get('$test$marklimits')
        if problem_scores is None:
            return
        try:
            scores_formula = self.constitute_problem_scores(problem_scores)
        except TypeError as error:
            error.args += (self.format_target(metapath, flags),)
            raise

        if mark_limits is not None and 'with-mark-limits' in flags:
            scores_formula += r';\quad'
            scores_formula += self.constitute_mark_limits(mark_limits)
        yield {'verbatim' : self.substitute_scorebox(scores=scores_formula)}

    @classmethod
    def constitute_problem_scores(cls, problem_scores):
        flatten_scores = []
        formula = ''.join(
            cls._constitute_problem_scores(problem_scores, flatten_scores)
        )
        return r'\(' + formula + r' = {}'.format(sum(flatten_scores)) + r'\)'

    @classmethod
    def _constitute_problem_scores(cls, problem_scores, flatten_scores):
        first = True
        if not isinstance(problem_scores, list):
            raise TypeError(
                "Problem scores must be a list of integers, found {}"
                .format(type(problem_scores)) )
        for i in problem_scores:
            if not first:
                yield '+'
            first = False
            if isinstance(i, int):
                yield str(i)
                flatten_scores.append(i)
            else:
                yield '('
                yield from cls._constitute_problem_scores(i, flatten_scores)
                yield ')'

    @classmethod
    def constitute_mark_limits(cls, mark_limits):
        return r'\(' + ',\ '.join(
            r'{score} \mapsto \mathbf{{{mark}}}'.format(mark=mark, score=score)
            for mark, score in sorted(mark_limits.items())
        ) + r'\)'

    interrobang_section_template = (
            r'\let\oldsection\section'
            r'\def\section#1#2{\oldsection#1{\textinterrobang\ #2}}' )
    begingroup_template = r'\begingroup'
    endgroup_template = r'\endgroup'

    scorebox_template = (
        r'\begin{flushright}\footnotesize\fbox{$scores}\end{flushright}' )

pgfpages_library = OrderedDict([
    ('$targetable', False),
    ('$style', [
        {'package' : 'pgfpages'},
        {'style' : 'uselayout'},
    ]),
    ('uselayout', OrderedDict([
        ('$style', [{'verbatim' :
            '\\pgfpagesuselayout{resize to}[a4paper]'
        }]),
        ('$style{2on1}', [{'verbatim' :
            '\\pgfpagesuselayout{2 on 1}[a4paper,landscape]'
        }]),
        ('$style{2on1-portrait}', [{'verbatim' :
            '\\pgfpagesuselayout{2 on 1}[a4paper]'
        }]),
        ('$style{4on1}', [{'verbatim' :
            '\\pgfpagesuselayout{4 on 1}[a4paper,landscape]'
        }]),
    ]))
])

