"""
Keys recognized in metarecords:
  $source-root-link
"""

from string import Template

from jeolm.record_path import RecordPath
from jeolm.target import Target

from jeolm.driver.regular import RegularDriver

from . import DriverError, processing_target, ensure_type_items

import logging
logger = logging.getLogger(__name__)


class SourceLinkDriver(RegularDriver):

    def __init__(self):
        super().__init__()
        self._cache.update(source_link_root=list())

    @property
    def _source_link_root(self):
        if self._cache['source_link_root']:
            source_link_root, = self._cache['source_link_root']
        else:
            source_link_root = self.get(RecordPath())['$source-link$root']
            if not isinstance(source_link_root, str):
                raise DriverError
            if not source_link_root.endswith('/'):
                raise DriverError
            self._cache['source_link_root'].append(source_link_root)
        return source_link_root

    class SourceBodyItem(RegularDriver.SourceBodyItem):
        __slots__ = ['source_link']

        def __init__(self, metapath):
            super().__init__(metapath)
            self.source_link = False

    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_source_metabody(self, target, metarecord):
        if 'source-link' not in target.flags:
            yield from super()._generate_source_metabody(target, metarecord)
            return

        for item in super()._generate_source_metabody(target, metarecord):
            if isinstance(item, self.SourceBodyItem):
                item.source_link = True
            yield item

    class SourceLinkBodyItem(RegularDriver.VerbatimBodyItem):
        _template = Template(
            r'\begin{flushright}\ttfamily\small' '\n'
            r'  \href{${root}${inpath}}' '\n'
            r'    {source:${inpath}}' '\n'
            r'\end{flushright}' )

        def __init__(self, inpath, *, root):
            super().__init__(
                value=self._template.substitute(root=root, inpath=inpath) )

    def _digest_metabody_source_item(self, target, item,
        *, sources, figures, metapreamble
    ):
        """
        Yield metabody items. Extend sources, figures.
        """
        yield from super()._digest_metabody_source_item( target, item,
            sources=sources, figures=figures, metapreamble=metapreamble )
        if not item.source_link:
            return
        metapreamble.append(self.ProvidePackagePreambleItem(
            package='hyperref' ))
        yield self.SourceLinkBodyItem(
            inpath=item.inpath,
            root=self._source_link_root )
        for figure_alias_stem in item.figure_map.values():
            figure_path, figure_type = figures[figure_alias_stem]
            if figure_type is None:
                def figure_has_type( figure_type,
                        figure_metarecord=self.get(figure_path) ):
                    return figure_metarecord.get(
                        self._get_figure_type_key(figure_type), False )
                for figure_type in ('asy', 'svg'):
                    if figure_has_type(figure_type):
                        break
                else:
                    continue
                    #if figure_has_type('eps'):
                    #    continue
                    #for figure_type in ('pdf', 'png', 'jpg'):
                    #    if figure_has_type(figure_type):
                    #        break
                    #else:
                    #    continue
            assert figure_type is not None
            yield self.SourceLinkBodyItem(
                inpath=figure_path.as_inpath(
                    suffix=self._get_figure_suffix(figure_type) ),
                root=self._source_link_root )

