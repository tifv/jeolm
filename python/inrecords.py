import os
import re
import datetime
from collections import OrderedDict

from pathlib import Path, PurePath

from jeolm import yaml
from jeolm.utils import pure_join

import logging
logger = logging.getLogger(__name__)

def review(inroots, *, root, viewpoint):
    """
    Review inrecords.

    root
        Path, jeolm root directory
    viewpoint
        Path, probably Path.cwd()
    """

    inroots = resolve_inpaths(inroots, root=root, viewpoint=viewpoint)

    reviewer = InrecordReviewer(root)
    reviewer.load_inrecords()
    for inroot in inroots:
        reviewer.review(inroot)
    reviewer.dump_inrecords()

def print_inpaths(inroots, ext, *, root, viewpoint):
    inroots = resolve_inpaths(inroots, root=root, viewpoint=viewpoint)

    reviewer = InrecordReviewer(root)
    reviewer.load_inrecords()
    for inroot in inroots:
        for inpath in reviewer.iter_inpaths(inroot, ext=ext):
            print(str(inpath))

def resolve_inpaths(inpaths, *, root, viewpoint):
    inpaths = [PurePath(inpath) for inpath in inpaths]
    if any('..' in inpath.parts for inpath in inpaths):
        raise ValueError("'..' parts are not allowed", inpaths)

    sourceroot = root['source']
    inpaths = [
        PurePath(viewpoint, inpath).relative_to(sourceroot)
        for inpath in inpaths ]
    if not inpaths:
        inpaths = [PurePath('')]
    return inpaths

class InrecordReviewer:
    __slots__ = ['root', 'inrecords']

    def __init__(self, root):
        self.root = root

    @property
    def metapath(self):
        return self.root['meta/in.yaml']

    def review(self, inroot):
        inrecord = self.get_inrecord(inroot)
        inrecord = self.review_inrecord(inroot, inrecord)
        self.set_inrecord(inroot, inrecord)

    def iter_inpaths(self, inroot, *, ext, inrecord=None):
        if inrecord is None:
            inrecord = self.get_inrecord(inroot)
            if inrecord is None:
                return
        assert isinstance(inrecord, dict), (inroot, inrecord)
        for subname, subrecord in inrecord.items():
            inpath = PurePath(inroot, subname)
            if inpath.ext == ext:
                yield inpath
            if inpath.ext == '':
                yield from self.iter_inpaths(inpath, ext=ext, inrecord=subrecord)

    def load_inrecords(self):
        with self.metapath.open('r') as f:
            s = f.read()
        inrecords = yaml.load(s)
        if inrecords is None:
            inrecords = OrderedDict()
        elif not isinstance(inrecords, OrderedDict):
            inrecords = OrderedDict(inrecords)
        self.inrecords = inrecords

    def dump_inrecords(self):
        s = yaml.dump(self.inrecords, default_flow_style=False)
        metapath_new = Path('.in.yaml.new')
        with metapath_new.open('w') as f:
            f.write(s)
        metapath_new.rename(self.metapath)

    def get_inrecord(self, inname, full_inname=None, create_path=False):
        """
        Return inrecord for given inname.

        Return None if there is not such inrecord.
        If create_path is set to True, None will never be returned -
        instead, empty directory inrecords will be created.
        """
        if full_inname is None:
            full_inname = inname
            if inname.ext not in {'', '.tex', '.asy', '.eps'}:
                raise ValueError("{!s}: unrecognized extension"
                    .format(full_inname) )
            if any(parent.ext != '' for parent in inname.parents()):
                raise ValueError("{!s}: directory has an extension"
                    .format(full_inname) )
        if inname == PurePath('.'):
            return self.inrecords
        inrecords = self.get_inrecord(inname.parent(),
            full_inname, create_path )
        if inrecords is None:
            assert not create_path
            return None
        assert isinstance(inrecords, dict), inrecords
        if inrecords.get('no review', False):
            logger.warning("<BOLD><YELLOW>{!s}<BLACK>: "
                "overpassing 'no review' tag<RESET>"
                .format(full_inname) )
        if inname.name not in inrecords:
            if not create_path:
                return None
            logger.info('<BOLD><GREEN>{!s}<RESET>: inrecord added'
                .format(inname) )
            if inname.ext == '':
                inrecords[inname.name] = OrderedDict()
            else:
                inrecords[inname.name] = dict()
        inrecord = inrecords[inname.name]
        if not isinstance(inrecord, dict):
            raise TypeError("{!s}: dictionary expected, found {!r}"
                .format(full_inname, type(inrecord)) )
        return inrecord

    def set_inrecord(self, inname, inrecord):
        """Fit given inrecord in the inrecords tree."""
        assert inname != PurePath('.') or inrecord is not None
        if inrecord is None:
            inrecords = self.get_inrecord(inname.parent())
            if inrecords is None:
                return
            assert isinstance(inrecords, dict)
            if inname.name not in inrecords:
                return
            del inrecords[inname.name]
            return
        inrecords = self.get_inrecord(inname, create_path=True)
        assert inrecords is not None
        if inrecord is inrecords:
            inrecord = inrecord.copy()
        inrecords.clear()
        inrecords.update(inrecord)

    def review_inrecord(self, inname, inrecord):
        if inrecord is not None and inrecord.get('no review', False):
            logger.debug(
                "{!s}: skipped due to explicit 'no review' in the record"
                .format(inname) )
            return inrecord
        inpath = self.root['source'][inname]
        if not inpath.exists():
            return None
        if inname.ext == '.tex':
            return self.review_tex_inrecord(inname, inrecord)
        elif inname.ext == '.asy':
            return self.review_asy_inrecord(inname, inrecord)
        elif inname.ext == '.eps':
            return self.review_eps_inrecord(inname, inrecord)
        assert inname.ext == '', inname
        if inrecord is None:
            inrecord = OrderedDict()
        subreviewed = inrecord.keys() | set(os.listdir(str(inpath)))
        assert all(isinstance(subname, str)
            for subname in subreviewed ), subreviewed
        for subname in sorted(subreviewed):
            subext = PurePath(subname).ext
            if subext not in {'', '.tex', '.asy', '.eps'}:
                if subname in inrecord:
                    raise ValueError("{!s}: unrecognized extension"
                        .format(inname[subname]) )
                logger.warning('<BOLD><MAGENTA>{!s}<BLACK>: extension of '
                    '<YELLOW>{}<BLACK> unrecognized<RESET>'
                    .format(inname, subname) )
                continue
            subrecord = inrecord.get(subname, None)
            subrecord = self.review_inrecord(inname[subname], subrecord)
            if subrecord is None and subname in inrecord:
                inrecord.pop(subname)
                logger.info('<BOLD><RED>{!s}<RESET>: inrecord removed<RESET>'
                    .format(inname[subname]) )
            elif subname in inrecord:
                inrecord[subname] = subrecord
            elif subrecord is not None:
                assert isinstance(subname, str)
                inrecord[subname] = subrecord
                logger.info('<BOLD><GREEN>{!s}<BLACK>: inrecord added<RESET>'
                    .format(inname[subname]) )
            else:
                pass
        self.report_screened_names(inname, inrecord)
        return inrecord

    def report_screened_names(self, inname, inrecord):
        """
        Show warnings if some inrecords are screened by other.

        'Screened' means that there are two files in the inrecords
        tree, but their names are clashing so in some cases one of them
        will be inaccessible.
        """
        tex_basenames, asy_basenames, eps_basenames = (
            {
                s[:s.index(ext)]
                for s in inrecord if s.endswith(ext) }
            for ext in ('.tex', '.asy', '.eps') )
        dirnames = {
            s for s in inrecord
            if not s.endswith(('.tex', '.asy', '.eps')) }

        for name in tex_basenames & dirnames:
            logger.warning("<BOLD>'<YELLOW>{texpath!s}<BLACK>' "
                "got screened by '{dirpath}'<RESET>"
                .format(texpath=inname[name + '.tex'], dirpath=inname[name]) )
        for name in asy_basenames & dirnames:
            logger.warning("<BOLD>'<YELLOW>{asypath!s}<BLACK>' "
                "got screened by '{dirpath}'<RESET>"
                .format(asypath=inname[name + '.asy'], dirpath=inname[name]) )
        for name in eps_basenames & dirnames:
            logger.warning("<BOLD>'<YELLOW>{epspath!s}<BLACK>' "
                "got screened by '{dirpath}'<RESET>"
                .format(epspath=inname[name + '.eps'], dirpath=inname[name]) )
        for name in eps_basenames & asy_basenames:
            logger.warning("<BOLD>'<YELLOW>{epspath!s}<BLACK>' "
                "got screened by '{asypath}'<RESET>"
                .format(
                    epspath=inname[name + '.eps'],
                    asypath=inname[name + '.asy'] ) )

    def review_tex_inrecord(self, inname, inrecord):
        assert inrecord is None or 'no review' not in inrecord
        logger.debug("{!s}: reviewing LaTeX file".format(inname))

        with self.root['source'][inname].open('r') as f:
            s = f.read()

        if self.noreview_pattern.search(s) is not None:
            logger.debug("{!s}: review skipped due to explicit "
                "'no review' in the file".format(inname) )
            return inrecord
        if inrecord is None:
            inrecord = {}

        self.review_tex_caption(inname, inrecord, s)
        self.review_tex_date   (inname, inrecord, s)
        self.review_tex_figures(inname, inrecord, s)

        return inrecord

    noreview_pattern = re.compile(
        r'(?m)^% no review$' )

    def review_tex_caption(self, inname, inrecord, s):
        if self.nocaption_pattern.search(s) is not None:
            logger.debug("{!s}: caption review skipped due to explicit "
                "'no caption' in the file".format(inname) )
            return
        caption_match = self.caption_pattern.search(s)
        if caption_match is None:
            if 'caption' in inrecord:
                logger.warning("<BOLD><MAGENTA>{!s}<BLACK>: "
                    "file is missing any caption; "
                    "preserved the caption '{}' holded in the record<RESET>"
                    .format(inname, inrecord['caption']) )
            return
        caption = caption_match.group('caption')
        if 'caption' not in inrecord:
            logger.info("<BOLD><MAGENTA>{!s}<RESET>: "
                "added caption '<BOLD><GREEN>{}<RESET>'"
                .format(inname, caption) )
        elif inrecord['caption'] != caption:
            logger.info("<BOLD><MAGENTA>{!s}<RESET>: "
                "caption changed from '<BOLD><RED>{}<BLACK>' "
                "to '<BOLD><GREEN>{}<BLACK>'"
                .format(inname, inrecord['caption'], caption) )
        inrecord['caption'] = caption

    nocaption_pattern = re.compile(
        r'(?m)^% no caption$' )
    caption_pattern = re.compile(
        r'(?m)^% (?! )(?P<caption>.+)$' )

    def review_tex_date(self, inname, inrecord, s):
        if self.nodate_pattern.search(s) is not None:
            logger.debug("{!s}: date review skipped due to explicit "
                "'no date' in the file".format(inname) )
        date_match = self.date_pattern.search(s)
        if date_match is None:
            if 'date' in inrecord:
                logger.warning("<BOLD><MAGENTA>{!s}<BLACK>: "
                    "file is missing any date; "
                    "preserved the date '{}' holded in the record<RESET>"
                    .format(inname, inrecord['date']) )
            return
        date = datetime.date(**{
            key : int(value)
            for key, value in date_match.groupdict().items() })
        if 'date' not in inrecord:
            logger.info("<BOLD><MAGENTA>{!s}<RESET>: "
                "added date '<BOLD><GREEN>{}<RESET>'"
                .format(inname, date) )
        elif inrecord['date'] != date:
            logger.info("<BOLD><MAGENTA>{!s}<RESET>: "
                "date changed from '<BOLD><RED>{}<RESET>' "
                "to '<BOLD><GREEN>{}<RESET>'"
                .format(inname, inrecord['date'], date) )
        inrecord['date'] = date

    nodate_pattern = re.compile(
        r'(?m)^% no date$' )
    date_pattern = re.compile(
        r'(?m)^% (?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})$' )

    def review_tex_figures(self, inname, inrecord, s):
        if self.nofigures_pattern.search(s) is not None:
            logger.debug("{!s}: figures review skipped due to explicit "
                "'no figures' in the file".format(inname) )
            return
        if self.includegraphics_pattern.search(s) is not None:
            logger.warning("<BOLD><MAGENTA>{!s}<BALCK>: "
                "<YELLOW>\\includegraphics<BLACK> command found<RESET>")

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
            logger.info("<BOLD><MAGENTA>{!s}<RESET>: "
                "removed figure '<BOLD><RED>{}<RESET>'"
                .format(inname, figure) )
        for figure in set(new_figures).difference(old_figures):
            logger.info("<BOLD><MAGENTA>{!s}<RESET>: "
                "added figure '<BOLD><GREEN>{}<RESET>'"
                .format(inname, figure))

        parent = inname.parent()
        if figures:
            inrecord['figures'] = OrderedDict(
                (figure, pure_join(parent, figure))
                for figure in figures )

    nofigures_pattern = re.compile(
        r'(?m)^% no figures$' )
    figure_pattern = re.compile(
        r'\\jeolmfigure(?:\[.*?\])?\{(?P<figure>.*?)\}' )
    includegraphics_pattern = re.compile(
        r'\\includegraphics')

    def review_asy_inrecord(self, inname, inrecord):
        assert inrecord is None or 'no review' not in inrecord
        logger.debug("{!s}: reviewing Asymptote file".format(inname))

        with self.root['source'][inname].open('r') as f:
            s = f.read()
        if inrecord is None:
            inrecord = {}

        parent = inname.parent()
        new_used = OrderedDict(
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
            logger.info("<BOLD><MAGENTA>{!s}<RESET>: "
                "removed used name '{}' for '<BOLD><RED>{}<RESET>'"
                .format(inname, used_name, old_used[used_name]) )
        for used_name in set(new_used).difference(old_used):
            logger.info("<BOLD><MAGENTA>{!s}<RESET>: "
                "added used name '{}' for '<BOLD><GREEN>{}<RESET>'"
                .format(inname, used_name, new_used[used_name]) )
        for used_name in set(new_used).intersection(old_used):
            if new_used[used_name] != old_used[used_name]:
                logger.info("<BOLD><MAGENTA>{!s}<RESET>: "
                    "used name '{}' changed from '<BOLD><RED>{}<RESET>' "
                    "to '<BOLD><GREEN>{}<RESET>'"
                    .format(
                        inname, used_name,
                        old_used[used_name], new_used[used_name]
                    ) )

        used = OrderedDict(
            (used_name, new_used[used_name])
            for used_name in used_names )
        if used:
            inrecord['used'] = used

        return inrecord

    asy_use_pattern = re.compile(
        r'(?m)^// use (?P<original_name>[-.a-zA-Z0-9/]*?\.asy) '
        r'as (?P<used_name>[-a-zA-Z0-9]*?\.asy)$' )

    def review_eps_inrecord(self, inname, inrecord):
        assert inrecord is None or 'no review' not in inrecord
        logger.debug("{!s}: reviewing EPS file".format(inname))

        if inrecord is None:
            inrecord = {}
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

