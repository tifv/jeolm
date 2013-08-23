import os
import re
import datetime
from collections import OrderedDict as ODict

from pathlib import Path, PurePath

from jeolm.utils import pure_join

import logging
logger = logging.getLogger(__name__)

def review(inpaths, *, fsmanager, viewpoint):
    """
    Review inrecords.

    root
        Path, jeolm root directory
    viewpoint
        Path, probably Path.cwd()
    """

    root = fsmanager.root
    inpaths = resolve_inpaths(inpaths,
        source_root=root/'source', viewpoint=viewpoint )

    reviewer = InrecordReviewer(fsmanager)
    reviewer.load_inrecords()
    for inpath in inpaths:
        reviewer.review(inpath)
    reviewer.dump_inrecords()

def print_inpaths(inroots, suffix, *, fsmanager, viewpoint):
    root = fsmanager.root
    source_root = root/'source'
    inroots = resolve_inpaths(inroots,
        source_root=source_root, viewpoint=viewpoint )

    reviewer = InrecordReviewer(root_manager)
    reviewer.load_inrecords()
    sourceroot = root/'source'
    for inroot in inroots:
        for inpath in reviewer.iter_inpaths(inroot, suffix=suffix):
            print(str((sourceroot/inpath).relative(viewpoint)))

def resolve_inpaths(inpaths, *, source_root, viewpoint):
    inpaths = [PurePath(inpath) for inpath in inpaths]
    if any('..' in inpath.parts for inpath in inpaths):
        raise ValueError("'..' parts are not allowed", inpaths)

    inpaths = [
        PurePath(viewpoint, inpath).relative(source_root)
        for inpath in inpaths ]
    if not inpaths:
        inpaths = [PurePath('')]
    return inpaths

class InrecordReviewer:
    recorded_suffixes = frozenset(('', '.tex', '.sty', '.asy', '.eps'))

    def __init__(self, fsmanager):
        self.fsmanager = fsmanager
        self.root = self.fsmanager.root

    def review(self, inpath):
        inrecord = self.get_inrecord(inpath)
        inrecord = self.review_inrecord(inpath, inrecord)
        if inrecord is not None:
            self.set_inrecord(inpath, inrecord)
        else:
            self.del_inrecord(inpath)

    def iter_inpaths(self, inroot, *, suffix, inrecord=None):
        if inrecord is None:
            inrecord = self.get_inrecord(inroot)
            if inrecord is None:
                return;
        assert isinstance(inrecord, dict), (inroot, inrecord)
        for subname, subrecord in inrecord.items():
            inpath = PurePath(inroot, subname)
            if inpath.suffix == suffix:
                yield inpath
            if inpath.suffix == '':
                yield from self.iter_inpaths(inpath,
                    suffix=suffix, inrecord=subrecord )

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
        path = self.root/'source'/inpath
        if not path.exists():
            if inrecord is not None:
                logger.info('<BOLD><RED>{}<NOCOLOUR>: inrecord removed<RESET>'
                    .format(inpath) )
            return None;
        if inpath.suffix != '':
            return self.review_file_inrecord(inpath, inrecord)
        if inrecord is None:
            inrecord = ODict()
            logger.info('<BOLD><GREEN>{}<NOCOLOUR>: inrecord added<RESET>'
                .format(inpath) )

        subnames = inrecord.keys() | set(os.listdir(str(path)))
        for subname in sorted(subnames):
            assert isinstance(subname, str), subname
            subpath = inpath/subname
            subsuffix = subpath.suffix
            if subsuffix not in self.recorded_suffixes:
                logger.warning('<BOLD><MAGENTA>{}<NOCOLOUR>: suffix of '
                    '<YELLOW>{}<NOCOLOUR> unrecognized<RESET>'
                    .format(inpath, subname) )
                continue;
            subrecord = inrecord.get(subname, None)
            subrecord = self.review_inrecord(subpath, subrecord)
            if subrecord is None:
                inrecord.pop(subname, None)
            else:
                inrecord[subname] = subrecord
        self.report_screened_names(inpath, inrecord)
        return inrecord;

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
        if inpath.suffix == '.sty':
            return self.review_sty_inrecord(inpath, inrecord)
        elif inpath.suffix == '.asy':
            return self.review_asy_inrecord(inpath, inrecord)
        elif inpath.suffix == '.eps':
            return self.review_eps_inrecord(inpath, inrecord)
        else:
            raise AssertionError(inpath)

    def review_tex_inrecord(self, inpath, inrecord):
        logger.debug("{}: reviewing LaTeX file".format(inpath))

        with (self.root/'source'/inpath).open('r') as f:
            s = f.read()

        self.review_tex_caption(inpath, inrecord, s)
        self.review_tex_date(inpath, inrecord, s)
        self.review_tex_figures(inpath, inrecord, s)

        return inrecord;

    def review_tex_caption(self, inpath, inrecord, s):
        if self.nocaption_pattern.search(s) is not None:
            logger.debug("{}: caption review skipped due to explicit "
                "'no caption' in the file".format(inpath) )
            return;
        caption_match = self.caption_pattern.search(s)
        if caption_match is None:
            if 'caption' in inrecord:
                logger.warning("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                    "file is missing any caption; "
                    "preserved the caption '{}' holded in the record<RESET>"
                    .format(inpath, inrecord['caption']) )
            return;
        caption = caption_match.group('caption')
        if 'caption' not in inrecord:
            logger.info("<BOLD><MAGENTA>{}<RESET>: "
                "added caption '<BOLD><GREEN>{}<RESET>'"
                .format(inpath, caption) )
        elif inrecord['caption'] != caption:
            logger.info("<BOLD><MAGENTA>{}<RESET>: "
                "caption changed from '<BOLD><RED>{}<RESET>' "
                "to '<BOLD><GREEN>{}<RESET>'"
                .format(inpath, inrecord['caption'], caption) )
        inrecord['caption'] = caption

    nocaption_pattern = re.compile(
        r'(?m)^% no caption$' )
    caption_pattern = re.compile(r'(?m)^'
        r'%+\n'
        r'%+ +(?! )(?P<caption>[^%]+)(?<! ) *(?:%.*)?\n'
        r'%+$')

    def review_tex_date(self, inpath, inrecord, s):
        if self.nodate_pattern.search(s) is not None:
            logger.debug("{}: date review skipped due to explicit "
                "'no date' in the file".format(inpath) )
            return;
        date_match = self.date_pattern.search(s)
        if date_match is None:
            if 'date' in inrecord:
                logger.warning("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                    "file is missing any date; "
                    "preserved the date '{}' holded in the record<RESET>"
                    .format(inpath, inrecord['date']) )
            return;
        date = datetime.date(**{
            key : int(value)
            for key, value in date_match.groupdict().items() })
        if 'date' not in inrecord:
            logger.info("<BOLD><MAGENTA>{}<RESET>: "
                "added date '<BOLD><GREEN>{}<RESET>'"
                .format(inpath, date) )
        elif inrecord['date'] != date:
            logger.info("<BOLD><MAGENTA>{}<RESET>: "
                "date changed from '<BOLD><RED>{}<RESET>' "
                "to '<BOLD><GREEN>{}<RESET>'"
                .format(inpath, inrecord['date'], date) )
        inrecord['date'] = date

    nodate_pattern = re.compile(
        r'(?m)^% no date$' )
    date_pattern = re.compile(
        r'(?m)^% (?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})$' )

    def review_tex_figures(self, inpath, inrecord, s):
        if self.nofigures_pattern.search(s) is not None:
            logger.debug("{}: figures review skipped due to explicit "
                "'no figures' in the file".format(inpath) )
            return;
        if self.includegraphics_pattern.search(s) is not None:
            logger.warning("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                "<YELLOW>\\includegraphics<NOCOLOUR> command found<RESET>"
                .format(inpath) )

        new_figures = self.unique(
            match.group('figure')
            for match in self.figure_pattern.finditer(s) )
        old_figures = inrecord.pop('figures', ())
        figures = [
            figure for figure in old_figures
            if figure in new_figures
        ] + [
            figure for figure in new_figures
            if figure not in old_figures
        ]
        for figure in set(old_figures).difference(new_figures):
            logger.info("<BOLD><MAGENTA>{}<RESET>: "
                "removed figure '<BOLD><RED>{}<RESET>'"
                .format(inpath, figure) )
        for figure in set(new_figures).difference(old_figures):
            logger.info("<BOLD><MAGENTA>{}<RESET>: "
                "added figure '<BOLD><GREEN>{}<RESET>'"
                .format(inpath, figure))

        parent = inpath.parent()
        if figures:
            inrecord['figures'] = ODict(
                (figure, pure_join(parent, figure))
                for figure in figures )

    nofigures_pattern = re.compile(
        r'(?m)^% no figures$' )
    figure_pattern = re.compile(
        r'\\jeolmfigure(?:\[.*?\])?\{(?P<figure>.*?)\}' )
    includegraphics_pattern = re.compile(
        r'\\includegraphics')

    def review_sty_inrecord(self, inpath, inrecord):
        logger.debug("{}: reviewing LaTeX style file".format(inpath))
        return inrecord

    def review_asy_inrecord(self, inpath, inrecord):
        logger.debug("{}: reviewing Asymptote file".format(inpath))
        with (self.root/'source'/inpath).open('r') as f:
            s = f.read()

        parent = inpath.parent()
        new_used = ODict(
            (
                match.group('used_name'),
                pure_join(parent, match.group('original_name'))
            )
            for match in self.asy_use_pattern.finditer(s) )
        old_used = inrecord.pop('used', ())
        used_names = [
            used_name for used_name in old_used
            if used_name in new_used
        ] + [
            used_name for used_name in new_used
            if used_name not in old_used
        ]
        for used_name in set(old_used).difference(new_used):
            logger.info("<BOLD><MAGENTA>{}<RESET>: "
                "removed used name '{}' for '<BOLD><RED>{}<RESET>'"
                .format(inpath, used_name, old_used[used_name]) )
        for used_name in set(new_used).difference(old_used):
            logger.info("<BOLD><MAGENTA>{}<RESET>: "
                "added used name '{}' for '<BOLD><GREEN>{}<RESET>'"
                .format(inpath, used_name, new_used[used_name]) )
        for used_name in set(new_used).intersection(old_used):
            if new_used[used_name] != old_used[used_name]:
                logger.info("<BOLD><MAGENTA>{}<RESET>: "
                    "used name '{}' changed from '<BOLD><RED>{}<RESET>' "
                    "to '<BOLD><GREEN>{}<RESET>'"
                    .format(
                        inpath, used_name,
                        old_used[used_name], new_used[used_name]
                    ) )
        used = ODict(
            (used_name, new_used[used_name])
            for used_name in used_names )
        if used:
            inrecord['used'] = used

        return inrecord

    asy_use_pattern = re.compile(
        r'(?m)^// use (?P<original_name>[-.a-zA-Z0-9/]*?\.asy) '
        r'as (?P<used_name>[-a-zA-Z0-9]*?\.asy)$' )

    def review_eps_inrecord(self, inpath, inrecord):
        logger.debug("{}: reviewing EPS file".format(inpath))
        return inrecord

    @staticmethod
    def unique(iterable):
        seen = set()
        unique = []
        for i in iterable:
            if i not in seen:
                unique.append(i)
                seen.add(i)
        return unique

