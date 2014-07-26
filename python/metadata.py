import os
import io
import re
import pickle

from collections import OrderedDict

from pathlib import PurePosixPath

from .utils import unique

from . import yaml
from .records import RecordsManager, RecordPath

import logging
logger = logging.getLogger(__name__)

class MetadataManager(RecordsManager):
    Dict = dict

    source_types = {
        ''      : 'directory',
        '.tex'  : 'latex',
        '.dtx'  : 'latex documented style',
        '.sty'  : 'latex style',
        '.asy'  : 'asymptote image',
        '.svg'  : 'SVG image',
        '.eps'  : 'EPS image',
        '.yaml' : 'metadata in YAML',
    }

    def __init__(self, *, local):
        self.local = local
        super().__init__()

    def load_metadata_cache(self):
        try:
            with self._metadata_cache_path.open('rb') as cache_file:
                pickled_cache = cache_file.read()
        except FileNotFoundError:
            cache = {}
        else:
            cache = pickle.loads(pickled_cache)
        self.absorb(cache)

    def dump_metadata_cache(self):
        pickled_cache = pickle.dumps(self.records)
        new_path = self.local.build_dir / '.metadata.cache.pickle.new'
        with new_path.open('wb') as cache_file:
            cache_file.write(pickled_cache)
        new_path.rename(self._metadata_cache_path)
        from jeolm.completion import CachingCompleter
        completer = CachingCompleter(local=self.local)
        completer.invalidate_target_list_cache()

    @property
    def _metadata_cache_path(self):
        return self.local.build_dir / self._metadata_cache_name

    _metadata_cache_name = 'metadata.cache.pickle'

    def feed_metadata(self, metarecords):
        for metainpath, record in self.items():
            if metainpath.suffix == '':
                assert '$metadata' not in record
                continue
            elif metainpath.suffix == '.yaml':
                metapath = metainpath.parent
            else:
                if len(metainpath.suffixes) > 1:
                    raise ValueError(metainpath)
                metapath = metainpath.with_suffix('')
            metadata = record.get('$metadata')
            self.check_dropped_metarecord_keys(metadata, origin=metainpath)
            if metadata is not None:
                metarecords.absorb({metapath : metadata})
        return metarecords

    def review(self, inpath, *, recursive=False):

        if not isinstance(inpath, PurePosixPath):
            raise RuntimeError(type(inpath))
        path = self.local.source_dir/inpath
        metainpath = RecordPath(inpath)

        exists = path.exists()
        recorded = metainpath in self
        if not exists:
            assert metainpath.name # non-empty path
            if recorded:
                self.delete(metainpath)
            else:
                logger.warning(
                    '{} was not recorded and does not exist as file. No-op.'
                    .format(metainpath) )
            return
        # path exists

        suffix = inpath.suffix
        is_dir = path.is_dir()
        if not suffix in self.source_types:
            raise ValueError("Path suffix unrecognized: {}".format(inpath))
        if suffix == '' and not is_dir:
            raise ValueError("Reviewed file has no suffix: {}".format(inpath))
        if suffix != '' and is_dir:
            raise ValueError(
                "Reviewed directory has suffix: {}".format(inpath) )
        assert is_dir == (suffix == ''), (is_dir, suffix)
        if is_dir and recorded and recursive:
            if __debug__ and metainpath == RecordPath('/'):
                assert self.getitem(metainpath, original=True) is self.records
                logger.debug('All metadata cleared.')
            self.clear(metainpath)
        if is_dir:
            if recursive:
                self.review_subpaths(inpath)
            self.absorb({metainpath : None})
            return
        metadata = self.query_file(inpath)
        self.absorb({metainpath : {'$metadata' : metadata}}, overwrite=True)

    def review_subpaths(self, inpath):
        for subname in os.listdir(str(self.local.source_dir/inpath)):
            if subname.startswith('.'):
                continue
            subinpath = inpath/subname
            subpath = self.local.source_dir/subinpath
            subsuffix = subinpath.suffix
            if subsuffix not in self.source_types:
                logger.warning('<BOLD><MAGENTA>{}<NOCOLOUR>: '
                    'suffix of <YELLOW>{}<NOCOLOUR> unrecognized<RESET>'
                    .format(inpath, subname) )
                continue
            subpath_is_dir = subpath.is_dir()
            if subsuffix != '' and subpath_is_dir:
                logger.warning('<BOLD><MAGENTA>{}<NOCOLOUR>: '
                    'directory <YELLOW>{}<NOCOLOUR> has suffix<RESET>'
                    .format(inpath, subname) )
                continue
            if subsuffix == '' and not subpath_is_dir:
                logger.warning('<BOLD><MAGENTA>{}<NOCOLOUR>: '
                    'file <YELLOW>{}<NOCOLOUR> has no suffix<RESET>'
                    .format(inpath, subname) )
                continue
            self.review(subinpath, recursive=True)

    def query_file(self, inpath):
        filetype = inpath.suffix[1:]
        query_method = getattr(self, 'query_{}_file'.format(filetype))
        return query_method(inpath)

    def query_yaml_file(self, inpath):
        with (self.local.source_dir/inpath).open('r') as f:
            metadata = yaml.load(f)
        if not isinstance(metadata, dict):
            raise TypeError(
                "Metadata in {} is of type {}, expected dictionary"
                .format(inpath, type(metadata)) )
        return metadata

    def query_tex_file(self, inpath):
        with (self.local.source_dir/inpath).open('r') as f:
            s = f.read()
        metadata = {}
        metadata.update(self.query_tex_content(inpath, s))
        if '$build$special' not in metadata:
            metadata.setdefault('$source$able', True)
        elif metadata['$build$special'] == 'standalone':
            metadata.setdefault('$source$able', False)
        else:
            logger.warning("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                "<YELLOW>$build$special<NOCOLOUR> value unrecognized<RESET>"
                .format(inpath) )
        return metadata

    def query_tex_content(self, inpath, s):
        metadata = OrderedDict()
        metadata.update(self.query_tex_figures(inpath, s))
        metadata.update(self.query_tex_sections(inpath, s))
        metadata.update(self.query_tex_metadata(inpath, s))
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
            return {'$source$figures' : OrderedDict(
                (figure, str((metapath / figure).as_inpath()))
                for figure in figures
            )}
        else:
            return {}

    tex_figure_pattern = re.compile(
        r'\\jeolmfigure(?:\[.*?\])?\{(?P<figure>.*?)\}' )
    tex_includegraphics_pattern = re.compile(
        r'\\includegraphics')

    def query_tex_sections(self, inpath, s):
        sections = [
            match.group('section')
            for match in self.tex_section_pattern.finditer(s) ]
        return {'$source$sections' : sections} if sections else {}

    tex_section_pattern = re.compile(
        r'\\section\*?\{(?P<section>[^\{\}]*?)\}' )

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
        r'(?:\n% [ \-#].+)*')

    def query_dtx_file(self, inpath):
        with (self.local.source_dir/inpath).open('r') as f:
            s = f.read()
        metadata = {
            '$package$able' : True,
            '$package$type' : 'dtx',
            '$build$special' : 'latexdoc' }
        metadata.update(self.query_package_content(inpath, s))
        return metadata

    def query_sty_file(self, inpath):
        with (self.local.source_dir/inpath).open('r') as f:
            s = f.read()
        metadata = {
            '$package$able' : True,
            '$package$type' : 'sty' }
        metadata.update(self.query_package_content(inpath, s))
        return metadata

    def query_package_content(self, inpath, s):
        match = self.package_name_pattern.search(s)
        if match is not None:
            package_name = match.group('package_name')
        else:
            package_name = inpath.with_suffix('').name
        return {'$package$name' : package_name}

    package_name_pattern = re.compile(
        r'\\ProvidesPackage\{(?P<package_name>[\w-]+)\}'
    )

    def query_asy_file(self, inpath):
        with (self.local.source_dir/inpath).open('r') as f:
            s = f.read()
        metadata = {
            '$figure$able' : True,
            '$figure$type' : 'asy' }
        metadata.update(self.query_asy_content(inpath, s))
        return metadata

    def query_asy_content(self, inpath, s):
        metadata = self.query_asy_accessed(inpath, s)
        return metadata or {}

    def query_asy_accessed(self, inpath, s):
        metapath = RecordPath(inpath.with_suffix(''))
        accessed = OrderedDict()
        for match in self.asy_access_pattern.finditer(s):
            alias_name = match.group('alias_name')
            accessed_path_s = str((
                metapath / match.group('accessed_path')
            ).as_inpath())
            accessed[alias_name] = accessed_path_s
        if accessed:
            return {'$figure$asy$accessed' : accessed}
        else:
            return {}

    asy_access_pattern = re.compile(
        r'(?m)^// access (?P<accessed_path>[-._a-zA-Z0-9/]*?\.asy) '
        r'as (?P<alias_name>[-a-zA-Z0-9]*?\.asy)$' )

    def query_svg_file(self, inpath):
        metadata = {
            '$figure$able' : True,
            '$figure$type' : 'svg' }
        return metadata

    def query_eps_file(self, inpath):
        metadata = {
            '$figure$able' : True,
            '$figure$type' : 'eps' }
        return metadata

    dropped_keys = {
        '$required$packages' : ('$latex$packages',),
        '$matter' : ('$fluid',),
        '$build$matter' : ('$manner', '$rigid',),
        '$build$style' : ('$manner$style', '$manner$options',
            '$out$options', '$fluid$opt', '$rigid$opt', '$manner$opt' ),
        '$delegate' : ('$target$delegate'),
    }

    @classmethod
    def check_dropped_metarecord_keys(cls, metarecord, origin='somewhere'):
        for modern_key, dropped_keys in cls.dropped_keys.items():
            for dropped_key in dropped_keys:
                for key in metarecord:
                    match = cls.flagged_pattern.match(key)
                    if match.group('key') != dropped_key:
                        continue
                    logger.warning(
                        '<BOLD><RED>{key}<RESET> dropped key '
                        'detected in <BOLD><YELLOW>{origin}<RESET>'
                        .format(key=dropped_key, origin=origin) )

