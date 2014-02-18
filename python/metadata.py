import os
import io
import re
from collections import OrderedDict

from pathlib import PurePosixPath as PurePath

from .utils import unique

from . import yaml
from .records import RecordsManager, RecordPath, RecordNotFoundError

import logging
logger = logging.getLogger(__name__)

class MetadataManager(RecordsManager):
    Dict = dict

    source_types = {
        ''      : 'directory',
        '.tex'  : 'latex',
        '.sty'  : 'latex style',
        '.asy'  : 'asymptote image',
        '.eps'  : 'eps image',
        '.yaml' : 'metadata',
    }

    def __init__(self, *, fs):
        self.fs = fs
        super().__init__()

    def load_metadata(self):
        self.merge(self.fs.load_metadata())

    def dump_metadata(self):
        self.fs.dump_metadata(self.records)

    def feed_metadata(self, metarecords):
        for inpath, record in self.items():
            if inpath.suffix == '':
                metapath = inpath
            elif inpath.suffix == '.yaml':
                metapath = inpath.parent
            else:
                if len(inpath.suffixes) > 1:
                    raise ValueError(path)
                metapath = inpath.with_suffix('')
            metadata = record.get('$metadata')
            if metadata is not None:
                metarecords.merge({metapath : metadata})
        return metarecords

    def review(self, inpath, *, recursive=False):
        path = self.fs.source_dir/inpath
        metapath = RecordPath(inpath)
        exists = path.exists()
        recorded = metapath in self
        is_dir = (metapath.suffix == '')
        if not inpath.suffix in self.source_types:
            raise ValueError("Path suffix unrecognized: {}".format(inpath))
        if is_dir and not path.is_dir() or not is_dir and path.is_dir():
            # We refuse to see this
            exists = False
        if not exists:
            assert metapath.name # non-empty path
            if recorded:
                self.unmerge(metapath)
            else:
                logger.warning(
                    '{} was not recorded and does not exist as file. No-op.'
                    .format(metapath) )
            return
        if is_dir and recorded and recursive:
            if __debug__ and metapath == RecordPath('/'):
                assert self.getitem(metapath, original=True) is self.records
                logger.debug('All metadata cleared.')
            self.clear(metapath)
        if is_dir:
            metadata = {'$source' : True}
            if recursive:
                self.review_subpaths(inpath)
        else:
            metadata = self.query_file(inpath)
        self.merge({metapath : {'$metadata' : metadata}}, overwrite=True)

    def review_subpaths(self, inpath):
        for subname in os.listdir(str(self.fs.source_dir/inpath)):
            if subname.startswith('.'):
                continue
            subpath = inpath/subname
            if subpath.suffix not in self.source_types:
                logger.warning('<BOLD><MAGENTA>{}<NOCOLOUR>: suffix of '
                    '<YELLOW>{}<NOCOLOUR> unrecognized<RESET>'
                    .format(inpath, subname) )
                continue
            self.review(subpath, recursive=True)

    def query_file(self, inpath):
        if inpath.suffix == '.yaml':
            metadata = self.query_yaml_file(inpath)
        elif inpath.suffix == '.tex':
            metadata = self.query_tex_file(inpath)
            metadata.setdefault('$source', True)
            metadata.setdefault('$latex$source', True)
        elif inpath.suffix == '.asy':
            metadata = self.query_asy_file(inpath)
            metadata.setdefault('$asy$source', True)
        elif inpath.suffix == '.sty':
            metadata = {'$sty$source' : True}
        elif inpath.suffix == '.eps':
            metadata = {'$eps$source' : True}
        else:
            raise RuntimeError(inpath)
        return metadata

    def query_yaml_file(self, inpath):
        with (self.fs.source_dir/inpath).open('r') as f:
            metadata = yaml.load(f)
        if not isinstance(metadata, dict):
            raise TypeError(inpath, type(metadata))
        return metadata

    def query_tex_file(self, inpath):
        with (self.fs.source_dir/inpath).open('r') as f:
            s = f.read()
        return self.query_tex_content(inpath, s)

    def query_tex_content(self, inpath, s):
        metadata = OrderedDict()
        metadata.update(self.query_tex_metadata(inpath, s))
        if not metadata:
            metadata = {}
        metadata.update(self.query_tex_figures(inpath, s))
        return metadata

    def query_tex_figures(self, inpath, s):
        if self.tex_includegraphics_pattern.search(s) is not None:
            logger.warning("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                "<YELLOW>\\includegraphics<NOCOLOUR> command found<RESET>"
                .format(inpath) )
        figures = unique(
            match.group('figure')
            for match in self.tex_figure_pattern.finditer(s) )
        metapath = RecordPath(inpath.with_suffix(''))
        if figures:
            return {'$latex$figures' : OrderedDict(
                (figure, str((metapath / figure).as_inpath()))
                for figure in figures
            )}
        else:
            return {}

    tex_figure_pattern = re.compile(
        r'\\jeolmfigure(?:\[.*?\])?\{(?P<figure>.*?)\}' )
    tex_includegraphics_pattern = re.compile(
        r'\\includegraphics')

    def query_tex_metadata(self, inpath, s):
        metadata = OrderedDict()
        for match in self.tex_metadata_pattern.finditer(s):
            piece = match.group(0).splitlines()
            assert all(line.startswith('% ') for line in piece)
            piece = '\n'.join(line[2:] for line in piece)
            piece_io = io.StringIO(piece)
            piece_io.name = inpath
            piece = yaml.load(piece_io)
            if not isinstance(piece, dict):
                logger.warning("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                    "unrecognized metadata piece<RESET>"
                    .format(inpath) )
                logger.warning(piece)
            metadata.update(piece)
        return metadata

    tex_metadata_pattern = re.compile('(?m)^'
        r'% \$[\w\$\-\[\],\{\}]+:.*'
        r'(?:\n% [ -].+)*')

    def query_asy_file(self, inpath):
        with (self.fs.source_dir/inpath).open('r') as f:
            s = f.read()
        return self.query_asy_content(inpath, s)

    def query_asy_content(self, inpath, s):
        metadata = self.query_asy_used(inpath, s)
        return metadata or {}

    def query_asy_used(self, inpath, s):
        metapath = RecordPath(inpath.with_suffix(''))
        used = OrderedDict()
        for match in self.asy_use_pattern.finditer(s):
            used_name = match.group('used_name')
            used_path = str((
                metapath / match.group('original_name')
            ).as_inpath())
            used[used_name] = used_path
        if used:
            return {'$asy$used' : used}
        else:
            return {}

    asy_use_pattern = re.compile(
        r'(?m)^// use (?P<original_name>[-.a-zA-Z0-9/]*?\.asy) '
        r'as (?P<used_name>[-a-zA-Z0-9]*?\.asy)$' )

