"""
Keys recognized in metarecords:
  $git-source-root
"""

from jeolm.driver.regular import Driver as RegularDriver

from jeolm.record_path import RecordPath

import logging
logger = logging.getLogger(__name__)


class Driver(RegularDriver):

    def __init__(self):
        super().__init__()
        self._cache.update(git_source_root=list())

    @property
    def git_source_root(self):
        cache = self._cache['git_source_root']
        if cache:
            git_link, = cache
        else:
            git_link = self.getitem(RecordPath())['$git-source-root']
            cache.append(git_link)
        assert isinstance(git_link, str), type(git_link)
        return git_link

    @processing_target_aspect( aspect='source metabody [git_link]',
        wrap_generator=True )
    @classifying_items(aspect='metabody', default='verbatim')
    def generate_source_metabody(self, target, metarecord):
        if target.flags.issuperset({'git-link', 'no-header'}):
            yield target.flags_difference({'git-link'})
            yield {'required_package' : 'hyperref'}
            yield self.substitute_source_link(
                target=( str(self.git_source_root) +
                    str(target.path.as_inpath(suffix='.tex')) ),
                text=str(target.path)
            )
        else:
            yield from super().generate_source_metabody(target, metarecord)

    source_link_template = (
        r'\begin{flushright}\ttfamily\small' '\n'
        r'\href{$target}{$text}' '\n'
        r'\end{flushright}' )

