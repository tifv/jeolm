"""
Keys recognized in metarecords:
  $authors
"""

from functools import partial
from string import Template

from jeolm.driver.regular import RegularDriver

from . import DriverError, ensure_type_items

class AuthorsDriver(RegularDriver):

    @ensure_type_items((RegularDriver.MetabodyItem))
    def _generate_header_def_metabody(self, target, metarecord, *, date):
        author_list = metarecord.get('$authors')
        if author_list is not None:
            yield self.VerbatimBodyItem(
                self._constitute_authors_def(author_list) )
        yield from super()._generate_header_def_metabody(
            target, metarecord, date=date )

    ##########
    # LaTeX-level functions

    @classmethod
    def _constitute_authors_def(cls, author_list):
        if isinstance(author_list, list):
            return cls.authors_def_template.substitute(
                authors=cls._constitute_authors(author_list))
        else:
            raise DriverError("Authors must be a list")

    @classmethod
    def _constitute_authors(cls, author_list, *, thin_space=r'\,'):
        assert isinstance(author_list, list), type(author_list)
        if len(author_list) == 1:
            author, = author_list
            return author
        abbreviate = partial(cls._abbreviate_author, thin_space=thin_space)
        return ', '.join(abbreviate(author) for author in author_list)

    @staticmethod
    def _abbreviate_author(author, thin_space=r'\,'):
        *names, last = author.split(' ')
        return thin_space.join([name[0] + '.' for name in names] + [last])

    authors_def_template = Template(
        r'\def\jeolmauthors{$authors}' )

