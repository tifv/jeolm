from functools import partial
import os
import io
import re
import pickle

from collections import OrderedDict

from pathlib import PurePosixPath

import jeolm.yaml

from jeolm.utils.ordering import filename_keyfunc
from jeolm.records import ( RecordPath, Records,
    NAME_PATTERN, RELATIVE_NAME_PATTERN )
from jeolm.driver import ATTRIBUTE_KEY_PATTERN

import logging
logger = logging.getLogger(__name__)


DIR_NAME_PATTERN = NAME_PATTERN
FILE_NAME_PATTERN = '(?:' + NAME_PATTERN + ')' + r'\.\w+'

FIGURE_REF_PATTERN = (
    r'(?P<figure>'
        '/?'
        '(?:(?:' + RELATIVE_NAME_PATTERN + ')/)*'
        '(?:' + NAME_PATTERN + ')'
    r')'
    r'(?::(?P<figure_code>'
        + NAME_PATTERN +
    r'))?'
)

ASY_ACCESSED_PATH_PATTERN = (
    r'/?'
    r'(?:(?:' + RELATIVE_NAME_PATTERN + r')/)+'
)

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

    def sorting_key(self, keyfunc=filename_keyfunc):
        return super().sorting_key(keyfunc=keyfunc)


class Metadata(Records):
    _Dict = dict
    _Path = MetadataPath
    dir_name_regex = re.compile(DIR_NAME_PATTERN)
    file_name_regex = re.compile(FILE_NAME_PATTERN)
    name_regex = re.compile(DIR_NAME_PATTERN + '|' + FILE_NAME_PATTERN)
    ordering_keyfunc = partial(filename_keyfunc)

    source_types = {
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

    def __init__(self, *, project):
        self.project = project
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
        pickled_cache = pickle.dumps(self._records)
        new_path = self.project.build_dir / '.metadata.cache.pickle.new'
        with new_path.open('wb') as cache_file:
            cache_file.write(pickled_cache)
        new_path.rename(self._metadata_cache_path)

    @property
    def _metadata_cache_path(self):
        return self.project.build_dir / self._metadata_cache_name

    _metadata_cache_name = 'metadata.cache.pickle'

    def feed_metadata(self, records):
        for metadata_path, record in self.items():
            if metadata_path.is_root() or metadata_path.suffix == '':
                assert '$metadata' not in record
                continue
            elif metadata_path.suffix == '.yaml':
                record_path = metadata_path.parent
            else:
                record_path = metadata_path.with_suffix('')
            metadata = record.get('$metadata')
            records.absorb(metadata, record_path, overwrite=False)
        return records

    def review(self, source_path):
        if not isinstance(source_path, PurePosixPath):
            raise TypeError(type(source_path))
        if source_path.is_absolute():
            raise ValueError(source_path)
        if '..' in source_path.parts:
            raise ValueError(source_path)
        metadata_path = MetadataPath.from_source_path(source_path)
        #inpath = metadata_path.as_inpath()
        path = self.project.source_dir/source_path

        exists = path.exists()
        recorded = metadata_path in self
        if not exists:
            assert not metadata_path.is_root()
            if recorded:
                self.delete(metadata_path)
            else:
                logger.warning(
                    "Reviewed source path was not recorded and "
                    "does not exist as file: %(path)s",
                    dict(path=source_path) )
            return
        # path exists

        is_dir = path.is_dir()
        self._check_source_path(source_path, is_dir=is_dir)
        if is_dir and recorded:
            self.clear(metadata_path)
        if is_dir:
            self._review_subpaths(source_path)
            self.absorb(None, metadata_path)
            return
        metadata = self._query_file(source_path)
        self.absorb({'$metadata' : metadata}, metadata_path, overwrite=True)

    @classmethod
    def _check_source_path(cls, source_path, *, is_dir):
        dir_names = source_path.parts if is_dir else source_path.parts[:-1]
        for dir_name in dir_names:
            if not cls.dir_name_regex.fullmatch(dir_name):
                raise ValueError(
                    f"Nonconforming directory name {dir_name} in "
                    f"source path {source_path}" )
        if not is_dir:
            if not cls.file_name_regex.fullmatch(source_path.name):
                raise ValueError(
                    f"Nonconforming file name in source path "
                    f"{source_path}" )
            suffix = source_path.suffix
            if suffix not in cls.source_types:
                raise ValueError(
                    f"Unknown file suffix in source path "
                    f"{source_path}" )

    def _review_subpaths(self, source_path):
        # XXX symlinked directories and files
        for subname in os.listdir(str(self.project.source_dir/source_path)):
            if subname.startswith('.'):
                continue
            sub_source_path = source_path/subname
            subpath = self.project.source_dir/sub_source_path
            if subpath.is_dir():
                if not self.dir_name_regex.fullmatch(subname):
                    logger.warning(
                        "Nonconforming directory name "
                            "<YELLOW>%(path)s<NOCOLOUR>",
                        dict(path=sub_source_path) )
                    continue
            else:
                if not self.file_name_regex.fullmatch(subname):
                    logger.warning(
                        "Nonconforming file name "
                            "<YELLOW>%(path)s<NOCOLOUR>",
                        dict(path=sub_source_path) )
                    continue
                subsuffix = sub_source_path.suffix
                if subsuffix not in self.source_types:
                    logger.warning(
                        "Unknown suffix in file name "
                            "<YELLOW>%(path)s<NOCOLOUR>",
                        dict(path=sub_source_path) )
                    continue
            self.review(sub_source_path)

    def _query_file(self, source_path):
        filetype = source_path.suffix
        assert filetype in self.source_types
        query_method = getattr(self, f'_query_{filetype[1:]}_file')
        return query_method(source_path)

    def _open_source_path(self, source_path, mode='r'):
        return (self.project.source_dir/source_path).open(
            mode=mode, encoding='utf-8' )

    def _query_yaml_file(self, source_path):
        with self._open_source_path(source_path) as yaml_file:
            metadata = jeolm.yaml.load(yaml_file)
        if not isinstance(metadata, dict):
            raise TypeError(
                f"Metadata in {source_path} is of type {type(metadata)}, "
                f"expected dictionary" )
        return metadata

    def _query_tex_file(self, source_path):
        with self._open_source_path(source_path) as tex_file:
            tex_content = tex_file.read()
        metadata = OrderedDict((
            ('$source$able', True),
            ('$source$type$tex', True),
        ))
        metadata.update(self._query_tex_content(source_path, tex_content))
        return metadata

    def _query_tex_content(self, source_path, tex_content):
        metadata = OrderedDict()
        filtered_tex_content = self._filter_tex_comments(tex_content)
        metadata.update(
            self._query_tex_figures(source_path, filtered_tex_content) )
        metadata.update(
            self._query_tex_sections(source_path, filtered_tex_content) )
        metadata.update(
            self._query_tex_metadata(source_path, tex_content) )
        return metadata

    @classmethod
    def _filter_tex_comments(cls, tex_content):
        return cls._tex_comment_regex.sub('', tex_content)

    _tex_comment_regex = re.compile( r'(?m)'
        r'(?!<\\)%.*\n\s*'
    )

    def _query_tex_figures(self, source_path, tex_content):
        if self._tex_includegraphics_regex.search(tex_content) is not None:
            logger.warning(
                "Source file <MAGENTA>%(path)s<NOCOLOUR>: "
                r"<YELLOW>\includegraphics<NOCOLOUR> command found",
                dict(path=source_path) )
        figure_refs = list()
        figure_refs_set = set()
        for match in self._tex_figure_regex.finditer(tex_content):
            figure_ref = match.group('figure_ref')
            if figure_ref in figure_refs_set:
                continue
            figure_refs_set.add(figure_ref)
            if figure_ref is None:
                continue
            figure_refs.append(figure_ref)
        if None in figure_refs_set:
            logger.warning(
                "Source file <MAGENTA>%(path)s<NOCOLOUR>: "
                "unable to parse some of the "
                r"<YELLOW>\jeolmfigure<NOCOLOUR> commands",
                dict(path=source_path) )
        if figure_refs:
            return {'$source$figures' : figure_refs}
        else:
            return {}

    _tex_figure_regex = re.compile( r'(?m)'
        r'\\jeolmfigure(?:\s*'
            r'(?:\['
                r'[\w\s.,=\\]*?'
            r'\])?'
        r'\s*'
            r'\{'
                r'(?P<figure_ref>' + FIGURE_REF_PATTERN + r')'
            r'\}'
        r')?')
    _tex_includegraphics_regex = re.compile(
        r'\\includegraphics')

    # pylint: disable=unused-argument

    def _query_tex_sections(self, source_path, tex_content):
        sections = [
            match.group('section')
            for match in self._tex_section_regex.finditer(tex_content) ]
        return {'$source$sections' : sections} if sections else {}

    _tex_section_regex = re.compile( r'(?m)'
        r'\\(?:section|worksheet)\*?\s*'
            r'\{\s*'
                r'(?P<section>(?:[^\{\}%]|\{[^\{\}%]*\})*)'
            r'(?:\s|%.*$)*\}' )

    # pylint: enable=unused-argument

    def _query_tex_metadata(self, source_path, tex_content):
        metadata = OrderedDict()
        for match in self._tex_metadata_regex.finditer(tex_content):
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
            piece_io.name = source_path
            piece = jeolm.yaml.load(piece_io)
            if not isinstance(piece, dict) or len(piece) != 1:
                logger.error(
                    "Source file <MAGENTA>%(path)s<NOCOLOUR>: "
                    "unrecognized metadata piece",
                    dict(path=source_path) )
                raise ValueError(piece)
            (key, value), = piece.items()
            if extend:
                if isinstance(value, list):
                    metadata.setdefault(key, []).extend(value)
                elif isinstance(value, dict):
                    metadata.setdefault(key, {}).update(value)
                else:
                    logger.error(
                        "Source file <MAGENTA>%(path)s<NOCOLOUR>: "
                        "extending value may be only a list or a dict",
                        dict(path=source_path) )
                    raise TypeError(value)
            else:
                metadata[key] = value
        return metadata

    _tex_metadata_regex = re.compile( r'(?m)'
        r'^% (?P<extend>>> )?'
            '(?:' + ATTRIBUTE_KEY_PATTERN + ')'
            r':.*\n'
        r'(?:% [ \-#].+\n)*'
    )

    def _query_dtx_file(self, source_path):
        with self._open_source_path(source_path) as dtx_file:
            dtx_content = dtx_file.read()
        metadata = {
            '$package$able' : True,
            '$package$type$dtx' : True,
            '$source$able' : True,
            '$source$type$dtx' : True }
        metadata.update(self._query_package_content(source_path, dtx_content,
            package_type='dtx' ))
        return metadata

    def _query_sty_file(self, source_path):
        with self._open_source_path(source_path) as sty_file:
            sty_content = sty_file.read()
        metadata = {
            '$package$able' : True,
            '$package$type$sty' : True }
        metadata.update(self._query_package_content(source_path, sty_content,
            package_type='sty' ))
        return metadata

    def _query_package_content( self, source_path, package_content,
        *, package_type
    ):
        match = self._package_name_regex.search(package_content)
        if match is not None:
            package_name = match.group('package_name')
        else:
            package_name = source_path.with_suffix('').name
        return {'$package${}$name'.format(package_type) : package_name}

    _package_name_regex = re.compile(
        r'\\ProvidesPackage\{(?P<package_name>' + NAME_PATTERN + r')\}'
    )

    def _query_asy_file(self, source_path):
        with self._open_source_path(source_path) as asy_file:
            asy_content = asy_file.read()
        metadata = {
            '$figure$able' : True,
            '$figure$type$asy' : True }
        metadata.update(self._query_asy_content(source_path, asy_content))
        return metadata

    def _query_asy_content(self, source_path, asy_content):
        metadata = self._query_asy_accessed(source_path, asy_content)
        return metadata or {}

    def _query_asy_accessed(self, source_path, asy_content):
        accessed = OrderedDict()
        for match in self._asy_access_regex.finditer(asy_content):
            accessed[match.group('alias_name')] = match.group('accessed_path')
        for match in self._broken_asy_access_regex.finditer(asy_content):
            if self._asy_access_regex.fullmatch(match.group()) is not None:
                continue
            logger.warning(
                "Source file <MAGENTA>%(path)s<NOCOLOUR>: "
                "invalid 'access path' line spotted "
                "(correct form is '// access ../common/ as common.asy'",
                dict(path=source_path) )
        if accessed:
            return {'$figure$asy$accessed' : accessed}
        else:
            return {}

    _asy_access_regex = re.compile( r'(?m)'
        r'^// access '
            r'(?P<accessed_path>' + ASY_ACCESSED_PATH_PATTERN + r') '
        r'as (?P<alias_name>(?:' + NAME_PATTERN + r')\.asy)$' )

    _broken_asy_access_regex = re.compile( r'(?m)'
        r'^// (?:access|use) (?:.*?) as (?:.*?)$' )

    # pylint: disable=no-self-use,unused-argument

    def _query_svg_file(self, source_path):
        metadata = {
            '$figure$able' : True,
            '$figure$type$svg' : True }
        return metadata

    def _query_pdf_file(self, source_path):
        metadata = {
            '$figure$able' : True,
            '$figure$type$pdf' : True }
        return metadata

    def _query_eps_file(self, source_path):
        metadata = {
            '$figure$able' : True,
            '$figure$type$eps' : True }
        return metadata

    def _query_png_file(self, source_path):
        metadata = {
            '$figure$able' : True,
            '$figure$type$png' : True }
        return metadata

    def _query_jpg_file(self, source_path):
        metadata = {
            '$figure$able' : True,
            '$figure$type$jpg' : True }
        return metadata

    # pylint: enable=no-self-use,unused-argument

