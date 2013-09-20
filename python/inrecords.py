import os
import re
import datetime
from collections import OrderedDict as ODict
from difflib import ndiff as diff

from pathlib import Path, PurePath

from jeolm.utils import pure_join
from jeolm import yaml

import logging
logger = logging.getLogger(__name__)

def review(paths, *, fsmanager, viewpoint):
    inpaths = resolve_inpaths(paths,
        source_dir=fsmanager.source_dir, viewpoint=viewpoint )

    reviewer = fsmanager.get_reviewer()
    reviewer.load_inrecords()
    for inpath in inpaths:
        reviewer.review(inpath)
    reviewer.dump_inrecords()

def resolve_inpaths(inpaths, *, source_dir, viewpoint):
    inpaths = [
        Path(viewpoint, inpath).resolve()
        for inpath in inpaths ]
    inpaths = [
        PurePath(inpath).relative(source_dir)
        for inpath in inpaths ]
    if not inpaths:
        inpaths = [PurePath('')]
    return inpaths

class InrecordReviewer:
    recorded_suffixes = frozenset(('', '.tex', '.sty', '.asy', '.eps'))

    def __init__(self, fsmanager):
        self.fsmanager = fsmanager
        self.source_dir = self.fsmanager.source_dir

    def review(self, inpath):
        inrecord = self.get_inrecord(inpath)
        inrecord = self.review_inrecord(inpath, inrecord)
        if inrecord is not None:
            self.set_inrecord(inpath, inrecord)
        else:
            self.del_inrecord(inpath)

    def load_inrecords(self):
        inrecords = self.fsmanager.load_inrecords()
        if inrecords is None:
            inrecords = ODict()
        elif not isinstance(inrecords, ODict):
            inrecords = ODict(inrecords)
        self.inrecords = inrecords

    def dump_inrecords(self):
        self.fsmanager.dump_inrecords(self.inrecords)

    def get_inrecord(self, inpath, *, create_path=False):
        """
        Return inrecord for given inpath.

        Return None if there is no such inrecord.
        If create_path is set to True, None will never be returned -
        instead, empty directory inrecords will be created, if needed.
        """

        if inpath.suffix not in self.recorded_suffixes:
            raise ValueError("{}: unrecognized suffix".format(inpath))
        if inpath == PurePath(''):
            return self.inrecords

        parent_inpath = inpath.parent()
        if parent_inpath.suffix != '':
            raise ValueError("{}: directory must not have suffix"
                .format(parent_inpath) )
        parent_record = self.get_inrecord(inpath.parent(),
            create_path=create_path )
        if parent_record is None:
            assert not create_path
            return None

        if inpath.name not in parent_record:
            if not create_path:
                return None
            assert inpath.suffix == '', inpath
            inrecord = parent_record[inpath.name] = ODict()
        else:
            inrecord = parent_record[inpath.name]
            if not isinstance(inrecord, dict):
                raise TypeError("{}: dictionary expected, found {!r}"
                    .format(inpath, type(inrecord)) )
        return inrecord

    def set_inrecord(self, inpath, inrecord):
        """Fit given inrecord in the inrecords tree."""
        assert inrecord is not None
        if inpath == PurePath():
            self.inrecords = inrecord
            return
        parent_record = self.get_inrecord(inpath.parent(), create_path=True)
        assert isinstance(parent_record, dict), parent_record
        parent_record[inpath.name] = inrecord

    def del_inrecord(self, inpath):
        assert inpath != PurePath()
        parent_record = self.get_inrecord(inpath.parent())
        if parent_record is None:
            return
        assert isinstance(parent_record, dict), parent_record
        if inpath.name not in parent_record:
            return
        del parent_record[inpath.name]
        return

    def review_inrecord(self, inpath, inrecord):
        logger.debug('{}: inrecord reviewed'.format(inpath))
        path = self.source_dir/inpath
        if not path.exists():
            if inrecord is None:
                return None
            logger.info('<BOLD><RED>{}<NOCOLOUR>: inrecord removed<RESET>'
                .format(inpath) )
            return None
        if len(inpath.suffixes) > 1:
            raise ValueError(inpath)
        if inpath.suffix != '':
            return self.review_file_inrecord(inpath, inrecord)
        if inrecord is None:
            inrecord = ODict()
            logger.info('<BOLD><GREEN>{}<NOCOLOUR>: inrecord added<RESET>'
                .format(inpath) )

        subnames = set(inrecord.keys())
        subnames.update(
            name for name in os.listdir(str(path))
            if not name.startswith('.') )
        subnames = sorted(subnames)
        logger.debug('{} listing: {}'.format(inpath, subnames))
        for subname in subnames:
            assert isinstance(subname, str), subname
            subpath = inpath/subname
            subsuffix = subpath.suffix
            if subsuffix not in self.recorded_suffixes:
                logger.warning('<BOLD><MAGENTA>{}<NOCOLOUR>: suffix of '
                    '<YELLOW>{}<NOCOLOUR> unrecognized<RESET>'
                    .format(inpath, subname) )
                continue
            subrecord = inrecord.get(subname, None)
            subrecord = self.review_inrecord(subpath, subrecord)
            if subrecord is None:
                inrecord.pop(subname, None)
            else:
                inrecord[subname] = subrecord
        self.report_screened_names(inpath, inrecord)

        self.reorder_odict(inrecord, orderpath=path/'.order')
        return inrecord

    def report_screened_names(self, inpath, inrecord):
        """
        Show warnings if some inrecords are screened.

        'Screened' means that in some cases the file will get
        inaccessible. One of the reasons can be two files in the
        inrecords tree with clashing names.
        """
        subpaths = {inpath/subname for subname in inrecord}
        screened_suffixes = (
            ('.tex', ''), ('.eps', '.asy') )
        screened_paths = (
            (subpath, subpath.with_suffix(screening_suffix))
            for screened_suffix, screening_suffix in screened_suffixes
            for subpath in subpaths
            if subpath.suffix == screened_suffix
            if subpath.with_suffix(screening_suffix) in subpaths
        )
        for screened_path, screening_path in screened_paths:
            logger.warning("<BOLD>'<YELLOW>{screened_path}<NOCOLOUR>' "
                "got screened by '<MAGENTA>{screening_path}<NOCOLOUR>'<RESET>"
                .format(
                    screened_path=screened_path,
                    screening_path=screening_path ))

    def review_file_inrecord(self, inpath, inrecord):
        if inrecord is None:
            inrecord = {}
            logger.info('<BOLD><GREEN>{}<NOCOLOUR>: inrecord added<RESET>'
                .format(inpath) )
        if inpath.suffix == '.tex':
            return self.review_tex_inrecord(inpath, inrecord)
        elif inpath.suffix == '.sty':
            return self.review_sty_inrecord(inpath, inrecord)
        elif inpath.suffix == '.asy':
            return self.review_asy_inrecord(inpath, inrecord)
        elif inpath.suffix == '.eps':
            return self.review_eps_inrecord(inpath, inrecord)
        else:
            raise AssertionError(inpath)

    def review_tex_inrecord(self, inpath, inrecord):
        logger.debug("{}: reviewing LaTeX file".format(inpath))

        with (self.source_dir/inpath).open('r') as f:
            s = f.read()

        oldrecord = inrecord
        newrecord = {}
        self.review_tex_content(inpath, s, oldrecord, newrecord)
        olddump = yaml.dump(oldrecord, default_flow_style=False).splitlines()
        newdump = yaml.dump(newrecord, default_flow_style=False).splitlines()
        if olddump != newdump:
            logger.info('<BOLD><MAGENTA>{}<NOCOLOUR>: amendment<RESET>'
                .format(inpath) )
            for line in diff(olddump, newdump):
                if line.startswith('+'):
                    logger.info('<GREEN>{}<RESET>'.format(line))
                elif line.startswith('-'):
                    logger.info('<RED>{}<RESET>'.format(line))
                elif line.startswith('?'):
                    pass
                    logger.info('<YELLOW>{}<RESET>'.format(line))
                else:
                    logger.info(line)
        inrecord = newrecord

        return inrecord

    def review_tex_content(self, inpath, s, oldrecord, newrecord):
        self.review_tex_caption(inpath, s, oldrecord, newrecord)
        self.review_tex_date(inpath, s, oldrecord, newrecord)
        self.review_tex_figures(inpath, s, oldrecord, newrecord)
        self.review_tex_metadata(inpath, s, oldrecord, newrecord)

    def review_tex_caption(self, inpath, s, oldrecord, newrecord):
        if self.nocaption_pattern.search(s) is not None:
            logger.debug("{}: caption review skipped due to explicit "
                "'no caption' in the file".format(inpath) )
            return
        caption_match = self.caption_pattern.search(s)
        if caption_match is None:
            if '$caption' in oldrecord:
                logger.warning(
                    "<BOLD><MAGENTA>{}<NOCOLOUR>: "
                    "file is missing any caption; "
                    "preserved the caption '<YELLOW>{}<NOCOLOUR>' "
                    "holded in the record<RESET>"
                    .format(inpath, oldrecord['$caption']) )
                newrecord['$caption'] = oldrecord['$caption']
        else:
            newrecord['$caption'] = caption_match.group('caption')

    nocaption_pattern = re.compile(
        r'(?m)^% no caption$' )
    caption_pattern = re.compile(r'(?m)^'
        r'%+\n'
        r'%+ +(?! )(?P<caption>[^%]+)(?<! ) *(?:%.*)?\n'
        r'%+\n')

    def review_tex_date(self, inpath, s, oldrecord, newrecord):
        if self.nodate_pattern.search(s) is not None:
            logger.debug("{}: date review skipped due to explicit "
                "'no date' in the file".format(inpath) )
            return
        date_match = self.date_pattern.search(s)
        if date_match is None:
            if '$date' in oldrecord:
                logger.warning(
                    "<BOLD><MAGENTA>{}<NOCOLOUR>: "
                    "file is missing any date; "
                    "preserved the date '<YELLOW>{}<NOCOLOUR>' "
                    "holded in the record<RESET>"
                    .format(inpath, oldrecord['$date']) )
                newrecord['$date'] = oldrecord['$date']
        else:
            newrecord['$date'] = datetime.date(**{
                key : int(value)
                for key, value in date_match.groupdict().items() })

    nodate_pattern = re.compile(
        r'(?m)^% no date$' )
    date_pattern = re.compile(
        r'(?m)^% (?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})$' )

    def review_tex_figures(self, inpath, s, oldrecord, newrecord):
        if self.nofigures_pattern.search(s) is not None:
            logger.debug("{}: figures review skipped due to explicit "
                "'no figures' in the file".format(inpath) )
            return
        if self.includegraphics_pattern.search(s) is not None:
            logger.warning("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                "<YELLOW>\\includegraphics<NOCOLOUR> command found<RESET>"
                .format(inpath) )

        figures = self.unique(
            match.group('figure')
            for match in self.figure_pattern.finditer(s) )

        parent = inpath.parent()
        if figures:
            newrecord['$figures'] = ODict(
                (figure, pure_join(parent, figure))
                for figure in figures )

    nofigures_pattern = re.compile(
        r'(?m)^% no figures$' )
    figure_pattern = re.compile(
        r'\\jeolmfigure(?:\[.*?\])?\{(?P<figure>.*?)\}' )
    includegraphics_pattern = re.compile(
        r'\\includegraphics')

    def review_tex_metadata(self, inpath, s, oldrecord, newrecord):
        for match in self.metadata_pattern.finditer(s):
            piece = match.group(0).splitlines()
            assert all(line.startswith('% ') for line in piece)
            piece = '\n'.join(line[2:] for line in piece)
            piece = yaml.load(piece)
            if not isinstance(piece, dict):
                logger.warning("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                    "unrecognized metadata piece<RESET>"
                    .format(inpath) )
                logger.warning(piece)
            newrecord.update(piece)

    metadata_pattern = re.compile('(?m)^'
        r'% \$[a-z]+:.*'
        r'(\n%  .+)*')

    def review_sty_inrecord(self, inpath, inrecord):
        logger.debug("{}: reviewing LaTeX style file".format(inpath))
        return inrecord

    def review_asy_inrecord(self, inpath, inrecord):
        logger.debug("{}: reviewing Asymptote file".format(inpath))
        with (self.source_dir/inpath).open('r') as f:
            s = f.read()

        parent = inpath.parent()
        new_used = ODict(
            (
                match.group('used_name'),
                pure_join(parent, match.group('original_name'))
            )
            for match in self.asy_use_pattern.finditer(s) )
        old_used = inrecord.pop('$used', ())
        used_names = [
            used_name for used_name in old_used
            if used_name in new_used
        ] + [
            used_name for used_name in new_used
            if used_name not in old_used
        ]
        for used_name in set(old_used).difference(new_used):
            logger.info("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                "removed used name '{}' for '<RED>{}<NOCOLOUR>'<RESET>"
                .format(inpath, used_name, old_used[used_name]) )
        for used_name in set(new_used).difference(old_used):
            logger.info("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                "added used name '{}' for '<GREEN>{}<NOCOLOUR>'<RESET>"
                .format(inpath, used_name, new_used[used_name]) )
        for used_name in set(new_used).intersection(old_used):
            if new_used[used_name] != old_used[used_name]:
                logger.info("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                    "used name '{}' changed from '<RED>{}<NOCOLOUR>' "
                    "to '<GREEN>{}<NOCOLOUR>'<RESET>"
                    .format(
                        inpath, used_name,
                        old_used[used_name], new_used[used_name]
                    ) )
        used = ODict(
            (used_name, new_used[used_name])
            for used_name in used_names )
        if used:
            inrecord['$used'] = used

        return inrecord

    asy_use_pattern = re.compile(
        r'(?m)^// use (?P<original_name>[-.a-zA-Z0-9/]*?\.asy) '
        r'as (?P<used_name>[-a-zA-Z0-9]*?\.asy)$' )

    def review_eps_inrecord(self, inpath, inrecord):
        logger.debug("{}: reviewing EPS file".format(inpath))
        return inrecord

    @staticmethod
    def reorder_odict(odict, orderpath):
        if not orderpath.exists():
            return
        swap = ODict(odict)
        assert len(odict) == len(swap)
        odict.clear()
        with orderpath.open('r') as orderfile:
            order = [ key
                for key in orderfile.read().splitlines()
                if key if not key.startswith('#') ]
        if '*' not in order:
            order.append('*')
        star_i = order.index('*')
        first_order = order[:star_i]
        last_order = order[star_i+1:]
        middle_order = [key for key in swap if key not in order]

        for key in first_order + middle_order + last_order:
            try:
                odict[key] = swap[key]
            except KeyError:
                pass
        assert len(odict) == len(swap)

    @staticmethod
    def unique(iterable):
        seen = set()
        unique = []
        for i in iterable:
            if i not in seen:
                unique.append(i)
                seen.add(i)
        return unique

