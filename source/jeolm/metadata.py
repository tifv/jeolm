import os
import io
import re
import pickle

from collections import OrderedDict

from pathlib import PurePosixPath

import jeolm.yaml

from .record_path import RecordPath
from .records import RecordsManager

import logging
logger = logging.getLogger(__name__)


class MetadataPath(RecordPath):
    @property
    def suffix(self):
        name = self.name
        return name[self._suffix_pos(name):]

    @property
    def basename(self):
        name = self.name
        return name[:self._suffix_pos(name)]

    @staticmethod
    def _suffix_pos(name):
        suffix_pos = name.find('.', 1)
        if suffix_pos <= 0:
            suffix_pos = len(name)
        return suffix_pos

    def with_suffix(self, suffix):
        if '/' in suffix:
            raise ValueError(suffix)
        if suffix and (not suffix.startswith('.') or suffix == '.'):
            raise ValueError(suffix)
        name = self.name
        return type(self)(
            self.parent,
            name[:self._suffix_pos(name)] + suffix )


class MetadataManager(RecordsManager):
    Dict = dict
    Path = MetadataPath
    name_pattern = re.compile(r'^(?:\w+-)*\w+(?:\.\w+)?$')

    source_types = {

        ''      : 'directory',
        '.yaml' : 'metadata in YAML',

        '.tex'  : 'LaTeX source',
        '.dtx'  : 'LaTeX documented style',
        '.sty'  : 'LaTeX style',

        '.asy'  : 'Asymptote image',
        '.svg'  : 'SVG image',
        '.pdf'  : 'PDF image',
        '.eps'  : 'EPS image',

        '.png'  : 'PNG image',
        '.jpg'  : 'JPEG image',

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
                self.check_dropped_metarecord_keys(metarecord, metapath)
        return metarecords

    def review(self, inpath):

        if not isinstance(inpath, PurePosixPath):
            raise RuntimeError(type(inpath))
        path = self.local.source_dir/inpath
        metainpath = MetadataPath.from_inpath(inpath)

        exists = path.exists()
        recorded = metainpath in self
        if not exists:
            assert not metainpath.is_root()
            if recorded:
                self.delete(metainpath)
            else:
                logger.warning(
                    "Reviewed path was not recorded and does not exist "
                    "as file: %(path)s",
                    dict(path='source'/inpath) )
            return
        # path exists

        suffix = inpath.suffix
        is_dir = path.is_dir()
        if any('.' in part for part in inpath.parts[:-1]):
            raise ValueError( "Reviewed path has dot in directory parts: {}"
                .format('source'/inpath) )
        if inpath.name.startswith('.'):
            raise ValueError( "Reviewed path name has leading dot: {}"
                .format('source'/inpath) )
        if len(inpath.suffixes) > 1:
            raise ValueError( "Reviewed path name has multiple suffixes: {}"
                .format('source'/inpath) )
        if not suffix in self.source_types:
            raise ValueError( "Reviewed path name has unrecognized suffix: {}"
                .format('source'/inpath) )
        if suffix == '' and not is_dir:
            raise ValueError( "Reviewed file name has no suffix: {}"
                .format('source'/inpath) )
        if suffix != '' and is_dir:
            raise ValueError( "Reviewed directory name has suffix: {}"
                .format('source'/inpath) )
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
            subpath_is_dir = subpath.is_dir()
            def warn(message, subname=subname):
                logger.warning( "<MAGENTA>%(path)s/<NOCOLOUR>: " +
                    message, dict(path='source'/inpath, name=subname) )
            if subname.startswith('.'):
                warn("name <YELLOW>%(name)s<NOCOLOUR> has leading dot")
                continue
            if len(subinpath.suffixes) > 1:
                warn("name <YELLOW>%(name)s<NOCOLOUR> has multiple suffixes")
                continue
            if subsuffix not in self.source_types:
                warn("name <YELLOW>%(name)s<NOCOLOUR> has unrecognized suffix")
                continue
            if subsuffix != '' and subpath_is_dir:
                warn("directory name <YELLOW>%(name)s<NOCOLOUR> has suffix")
                continue
            if subsuffix == '' and not subpath_is_dir:
                warn("file name <YELLOW>%(name)s<NOCOLOUR> has no suffix")
                continue
            self.review(subinpath)

    def _query_file(self, inpath):
        filetype = inpath.suffix
        if filetype == '':
            raise RuntimeError
        elif filetype == '.yaml':
            query_method = self._query_yaml_file
        elif filetype == '.tex':
            query_method = self._query_tex_file
        elif filetype == '.dtx':
            query_method = self._query_dtx_file
        elif filetype == '.sty':
            query_method = self._query_sty_file
        elif filetype == '.asy':
            query_method = self._query_asy_file
        elif filetype == '.svg':
            query_method = self._query_svg_file
        elif filetype == '.pdf':
            query_method = self._query_pdf_file
        elif filetype == '.eps':
            query_method = self._query_eps_file
        elif filetype == '.png':
            query_method = self._query_png_file
        elif filetype == '.jpg':
            query_method = self._query_jpg_file
        else:
            raise RuntimeError
        return query_method(inpath)

    def _query_yaml_file(self, inpath):
        with (self.local.source_dir/inpath).open('r') as yaml_file:
            metadata = jeolm.yaml.load(yaml_file)
        if not isinstance(metadata, dict):
            raise TypeError(
                "Metadata in {} is of type {}, expected dictionary"
                .format(inpath, type(metadata)) )
        return metadata

    def _query_tex_file(self, inpath):
        with (self.local.source_dir/inpath).open('r') as tex_file:
            tex_content = tex_file.read()
        metadata = OrderedDict((
            ('$source$able', True),
            ('$source$type$tex', True),
        ))
        metadata.update(self._query_tex_content(inpath, tex_content))
        return metadata

    def _query_tex_content(self, inpath, tex_content):
        metadata = OrderedDict()
        metadata.update(self._query_tex_figures(inpath, tex_content))
        metadata.update(self._query_tex_sections(inpath, tex_content))
        metadata.update(self._query_tex_metadata(inpath, tex_content))
        return metadata

    def _query_tex_figures(self, inpath, tex_content):
        if self._tex_includegraphics_pattern.search(tex_content) is not None:
            logger.warning( "<MAGENTA>%(path)s<NOCOLOUR>: "
                r"<YELLOW>\includegraphics<NOCOLOUR> command found",
                dict(path='source'/inpath) )
        figure_refs = list()
        figure_refs_set = set()
        for match in self._tex_figure_pattern.finditer(tex_content):
            figure_ref = match.group('figure_ref')
            if figure_ref in figure_refs_set:
                continue
            figure_refs_set.add(figure_ref)
            if figure_ref is None:
                continue
            figure_refs.append(figure_ref)
        if None in figure_refs_set:
            logger.warning( "<MAGENTA>%(path)s<NOCOLOUR>: "
                "unable to parse some of the "
                r"<YELLOW>\jeolmfigure<NOCOLOUR> commands",
                dict(path='source'/inpath) )
        if figure_refs:
            return {'$source$figures' : figure_refs}
        else:
            return {}

    _tex_figure_pattern = re.compile( r'(?m)'
        r'\\jeolmfigure(?:\s*'
            r'(?:\['
                r'[\w\s.,=\\]*?'
            r'\])?'
        r'\s*'
            r'\{'
                r'(?P<figure_ref>'
                    r'/?'
                    r'(?:(?:\w+-)*\w+/|../)*'
                    r'(?:\w+-)*\w+'
                    r'(?:\.(?P<figure_type>asy|svg|pdf|eps|png|jpg))?'
                r')'
            r'\}'
        r')?')
    _tex_includegraphics_pattern = re.compile(
        r'\\includegraphics')

    # pylint: disable=unused-argument

    def _query_tex_sections(self, inpath, tex_content):
        sections = [
            match.group('section')
            for match in self.tex_section_pattern.finditer(tex_content) ]
        return {'$source$sections' : sections} if sections else {}

    tex_section_pattern = re.compile(
        r'\\section\*?\s*'
            r'\{\s*'
                r'(?P<section>(?:[^\{\}%]|\{[^\{\}%]*\})*)'
            r'(?:\s|%.*$)*\}' )

    # pylint: enable=unused-argument

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
            piece = jeolm.yaml.load(piece_io)
            if not isinstance(piece, dict) or len(piece) != 1:
                logger.error( "<MAGENTA>%(path)s<NOCOLOUR>: "
                    "unrecognized metadata piece",
                    dict(path='source'/inpath) )
                raise ValueError(piece)
            (key, value), = piece.items()
            if extend:
                if isinstance(value, list):
                    metadata.setdefault(key, []).extend(value)
                elif isinstance(value, dict):
                    metadata.setdefault(key, {}).update(value)
                else:
                    logger.error( "<MAGENTA>%(path)s<NOCOLOUR>: "
                        "extending value may be only a list or a dict",
                        dict(path='source'/inpath) )
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
            '$package$type$dtx' : True,
            '$source$able' : True,
            '$source$type$dtx' : True }
        metadata.update(self._query_package_content(inpath, dtx_content,
            package_type='dtx' ))
        return metadata

    def _query_sty_file(self, inpath):
        with (self.local.source_dir/inpath).open('r') as sty_file:
            sty_content = sty_file.read()
        metadata = {
            '$package$able' : True,
            '$package$type$sty' : True }
        metadata.update(self._query_package_content(inpath, sty_content,
            package_type='sty' ))
        return metadata

    def _query_package_content( self, inpath, package_content,
        *, package_type
    ):
        match = self.package_name_pattern.search(package_content)
        if match is not None:
            package_name = match.group('package_name')
        else:
            package_name = inpath.with_suffix('').name
        return {'$package${}$name'.format(package_type) : package_name}

    package_name_pattern = re.compile(
        r'\\ProvidesPackage\{(?P<package_name>[\w-]+)\}'
    )

    def _query_asy_file(self, inpath):
        with (self.local.source_dir/inpath).open('r') as asy_file:
            asy_content = asy_file.read()
        metadata = {
            '$figure$able' : True,
            '$figure$type$asy' : True }
        metadata.update(self._query_asy_content(inpath, asy_content))
        return metadata

    def _query_asy_content(self, inpath, asy_content):
        metadata = self._query_asy_accessed(inpath, asy_content)
        return metadata or {}

    def _query_asy_accessed(self, inpath, asy_content):
        accessed = OrderedDict()
        for match in self._asy_access_pattern.finditer(asy_content):
            accessed[match.group('alias_name')] = match.group('accessed_path')
        for match in self._broken_asy_access_pattern.finditer(asy_content):
            if self._asy_access_pattern.match(match.group()) is not None:
                continue
            logger.warning( "<MAGENTA>%(path)s<NOCOLOUR>: "
                "invalid 'access path' line spotted",
                dict(path='source'/inpath) )
        if accessed:
            return {'$figure$asy$accessed' : accessed}
        else:
            return {}

    _asy_access_pattern = re.compile(
        r'(?m)^// access '
            r'(?P<accessed_path>'
                r'/?'
                r'(?:(?:\w+-)*\w+/|../)+'
            r') '
        r'as (?P<alias_name>[-a-zA-Z0-9]*?\.asy)$' )

    _broken_asy_access_pattern = re.compile(
        r'(?m)^// (?:access|use) (?:.*?) as (?:.*?)$' )

    # pylint: disable=no-self-use,unused-argument

    def _query_svg_file(self, inpath):
        metadata = {
            '$figure$able' : True,
            '$figure$type$svg' : True }
        return metadata

    def _query_pdf_file(self, inpath):
        metadata = {
            '$figure$able' : True,
            '$figure$type$pdf' : True }
        return metadata

    def _query_eps_file(self, inpath):
        metadata = {
            '$figure$able' : True,
            '$figure$type$eps' : True }
        return metadata

    def _query_png_file(self, inpath):
        metadata = {
            '$figure$able' : True,
            '$figure$type$png' : True }
        return metadata

    def _query_jpg_file(self, inpath):
        metadata = {
            '$figure$able' : True,
            '$figure$type$jpg' : True }
        return metadata

    # pylint: enable=no-self-use,unused-argument

    dropped_keys = {
        '$matter' : ('$fluid',),
        '$build$matter' : ('$manner', '$rigid',),
        '$build$style' : (
            '$manner$style', '$manner$options',
            '$out$options', '$fluid$opt', '$rigid$opt', '$manner$opt',
            '$build$special', ),
        '$delegate' : ('$target$delegate',),
        '$target$able' : ('$targetable',),
        '$matter: preamble package' : (
            '$required$packages', '$latex$packages', '$tex$packages', ),
    }

    @classmethod
    def check_dropped_metarecord_keys(cls, metarecord, metapath):
        for modern_key, dropped_keys in cls.dropped_keys.items():
            assert not isinstance(dropped_keys, str), dropped_keys
            for dropped_key in dropped_keys:
                for key in metarecord:
                    match = cls.flagged_pattern.match(key)
                    if match.group('key') != dropped_key:
                        continue
                    logger.warning(
                        "Dropped key <RED>%(key)s<NOCOLOUR> "
                        "detected in <YELLOW>%(metapath)s<NOCOLOUR> "
                        "(replace it with %(modern_key)s)",
                        dict(
                            key=dropped_key, metapath=metapath,
                            modern_key=modern_key, )
                    )

