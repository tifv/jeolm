import os
import io
import re
import pickle

from collections import OrderedDict

from pathlib import PurePosixPath

from .utils import unique

from . import yaml
from .record_path import RecordPath
from .records import RecordsManager

import logging
logger = logging.getLogger(__name__)


class MetadataManager(RecordsManager):
    Dict = dict

    source_types = {
        ''      : 'directory',
        '.tex'  : 'LaTeX source',
        '.dtx'  : 'LaTeX documented style',
        '.sty'  : 'LaTeX style',
        '.asy'  : 'Asymptote image',
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

    @property
    def _metadata_cache_path(self):
        return self.local.build_dir / self._metadata_cache_name

    _metadata_cache_name = 'metadata.cache.pickle'

    def feed_metadata(self, metarecords, *, warn_dropped_keys=True):
        for metainpath, record in self.items():
            if metainpath.is_root() or metainpath.suffix == '':
                assert '$metadata' not in record
                continue
            elif metainpath.suffix == '.yaml':
                metapath = metainpath.parent
            else:
                metapath = metainpath.with_suffix('')
            metadata = record.get('$metadata')
            metarecords.absorb(metadata, metapath, overwrite=False)
        if warn_dropped_keys:
            for metapath, metarecord in metarecords.items():
                self.check_dropped_metarecord_keys(
                    metarecord, origin=metapath )
        return metarecords

    def review(self, inpath):

        if not isinstance(inpath, PurePosixPath):
            raise RuntimeError(type(inpath))
        path = self.local.source_dir/inpath
        metainpath = RecordPath.from_inpath(inpath)

        exists = path.exists()
        recorded = metainpath in self
        if not exists:
            assert not metainpath.is_root()
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
        if is_dir and recorded:
            self.clear(metainpath)
        if is_dir:
            self._review_subpaths(inpath)
            self.absorb(None, metainpath)
            return
        metadata = self._query_file(inpath)
        self.absorb({'$metadata' : metadata}, metainpath, overwrite=True)

    def _review_subpaths(self, inpath):
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
            self.review(subinpath)

    def _query_file(self, inpath):
        filetype = inpath.suffix[1:]
        query_method = getattr(self, '_query_{}_file'.format(filetype))
        return query_method(inpath)

    def _query_yaml_file(self, inpath):
        with (self.local.source_dir/inpath).open('r') as yaml_file:
            metadata = yaml.load(yaml_file)
        if not isinstance(metadata, dict):
            raise TypeError(
                "Metadata in {} is of type {}, expected dictionary"
                .format(inpath, type(metadata)) )
        return metadata

    def _query_tex_file(self, inpath):
        with (self.local.source_dir/inpath).open('r') as tex_file:
            tex_content = tex_file.read()
        metadata = OrderedDict()
        metadata.update(self._query_tex_content(inpath, tex_content))
        if '$build$special' not in metadata:
            metadata.setdefault('$source$able', True)
        elif metadata['$build$special'] == 'standalone':
            metadata.setdefault('$source$able', False)
        else:
            logger.warning("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                "<YELLOW>$build$special<NOCOLOUR> value unrecognized<RESET>"
                .format(inpath) )
        return metadata

    def _query_tex_content(self, inpath, tex_content):
        metadata = OrderedDict()
        metadata.update(self._query_tex_figures(inpath, tex_content))
        metadata.update(self._query_tex_sections(inpath, tex_content))
        metadata.update(self._query_tex_metadata(inpath, tex_content))
        return metadata

    def _query_tex_figures(self, inpath, tex_content):
        if self.tex_includegraphics_pattern.search(tex_content) is not None:
            logger.warning("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                "<YELLOW>\\includegraphics<NOCOLOUR> command found<RESET>"
                .format(inpath) )
        figures = unique(
            match.group('figure')
            for match in self.tex_figure_pattern.finditer(tex_content) )
        metapath = RecordPath.from_inpath(inpath.with_suffix(''))
        if figures:
            return {'$source$figures' : OrderedDict(
                (figure, str(RecordPath(metapath, figure).as_inpath()))
                for figure in figures
            )}
        else:
            return {}

    tex_figure_pattern = re.compile(
        r'\\jeolmfigure(?:\[.*?\])?\{(?P<figure>.*?)\}' )
    tex_includegraphics_pattern = re.compile(
        r'\\includegraphics')

    def _query_tex_sections(self, inpath, tex_content):
        sections = [
            match.group('section')
            for match in self.tex_section_pattern.finditer(tex_content) ]
        return {'$source$sections' : sections} if sections else {}

    tex_section_pattern = re.compile(
        r'\\section\*?\{(?P<section>[^\{\}]*?)\}' )

    def _query_tex_metadata(self, inpath, tex_content):
        metadata = OrderedDict()
        for match in self.tex_metadata_pattern.finditer(tex_content):
            piece_lines = match.group(0).splitlines(keepends=True)
            assert all(line.startswith('% ') for line in piece_lines)
            piece_lines = [line[2:] for line in piece_lines]
            if match.group('extend') is not None:
                assert len(match.group('extend')) == 3
                piece_lines[0] = piece_lines[0][3:]
                extend = True
            else:
                extend = False
            piece = ''.join(piece_lines)
            piece_io = io.StringIO(piece)
            piece_io.name = inpath
            piece = yaml.load(piece_io)
            if not isinstance(piece, dict) or len(piece) != 1:
                logger.error("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                    "unrecognized metadata piece<RESET>"
                    .format(inpath) )
                raise ValueError(piece)
            (key, value), = piece.items()
            if extend:
                if isinstance(value, list):
                    metadata.setdefault(key, []).extend(value)
                elif isinstance(value, dict):
                    metadata.setdefault(key, {}).update(value)
                else:
                    logger.error("<BOLD><MAGENTA>{}<NOCOLOUR>: "
                        "extending value may be only a list or a dict.<RESET>"
                        .format(inpath) )
                    raise TypeError(value)
            else:
                metadata[key] = value
        return metadata

    tex_metadata_pattern = re.compile('(?m)^'
        r'% (?P<extend>>> )?\$[\w\$\-_\[\],\{\}]+:.*\n'
        r'(?:% [ \-#].+\n)*')

    def _query_dtx_file(self, inpath):
        with (self.local.source_dir/inpath).open('r') as dtx_file:
            dtx_content = dtx_file.read()
        metadata = {
            '$package$able' : True,
            '$package$format$dtx' : True,
            '$build$special' : 'latexdoc' }
        metadata.update(self._query_package_content(inpath, dtx_content))
        return metadata

    def _query_sty_file(self, inpath):
        with (self.local.source_dir/inpath).open('r') as sty_file:
            sty_content = sty_file.read()
        metadata = {
            '$package$able' : True,
            '$package$format$sty' : True }
        metadata.update(self._query_package_content(inpath, sty_content))
        return metadata

    def _query_package_content(self, inpath, package_content):
        match = self.package_name_pattern.search(package_content)
        if match is not None:
            package_name = match.group('package_name')
        else:
            package_name = inpath.with_suffix('').name
        return {'$package$name' : package_name}

    package_name_pattern = re.compile(
        r'\\ProvidesPackage\{(?P<package_name>[\w-]+)\}'
    )

    def _query_asy_file(self, inpath):
        with (self.local.source_dir/inpath).open('r') as asy_file:
            asy_content = asy_file.read()
        metadata = {
            '$figure$able' : True,
            '$figure$format$asy' : True }
        metadata.update(self._query_asy_content(inpath, asy_content))
        return metadata

    def _query_asy_content(self, inpath, asy_content):
        metadata = self._query_asy_accessed(inpath, asy_content)
        return metadata or {}

    def _query_asy_accessed(self, inpath, asy_content):
        metapath = RecordPath.from_inpath(inpath.with_suffix(''))
        accessed = OrderedDict()
        for match in self.asy_access_pattern.finditer(asy_content):
            alias_name = match.group('alias_name')
            accessed_path_s = str(RecordPath(
                metapath, match.group('accessed_path')
            ).as_inpath())
            accessed[alias_name] = accessed_path_s
        if accessed:
            return {'$figure$asy$accessed' : accessed}
        else:
            return {}

    asy_access_pattern = re.compile(
        r'(?m)^// access (?P<accessed_path>[-._a-zA-Z0-9/]*?\.asy) '
        r'as (?P<alias_name>[-a-zA-Z0-9]*?\.asy)$' )

    # pylint: disable=no-self-use,unused-argument

    def _query_svg_file(self, inpath):
        metadata = {
            '$figure$able' : True,
            '$figure$format$svg' : True }
        return metadata

    def _query_eps_file(self, inpath):
        metadata = {
            '$figure$able' : True,
            '$figure$format$eps' : True }
        return metadata

    # pylint: enable=no-self-use,unused-argument

    dropped_keys = {
        '$matter' : ('$fluid',),
        '$build$matter' : ('$manner', '$rigid', ),
        '$build$style' : ('$manner$style', '$manner$options',
            '$out$options', '$fluid$opt', '$rigid$opt', '$manner$opt', ),
        '$delegate' : ('$target$delegate', ),
        '$target$able' : ('$targetable', ),
        '$required$packages' : ('$latex$packages', '$tex$packages')
    }

    @classmethod
    def check_dropped_metarecord_keys(cls, metarecord, origin):
        for modern_key, dropped_keys in cls.dropped_keys.items():
            assert not isinstance(dropped_keys, str), dropped_keys
            for dropped_key in dropped_keys:
                for key in metarecord:
                    match = cls.flagged_pattern.match(key)
                    if match.group('key') != dropped_key:
                        continue
                    logger.warning(
                        'Dropped key <BOLD><RED>{key}<RESET> '
                        'detected in <BOLD><YELLOW>{origin}<RESET> '
                        '(replace it with {modern_key})'
                        .format(
                            key=dropped_key, origin=origin,
                            modern_key=modern_key )
                    )

