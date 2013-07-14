"""
Driver(inrecords, outrecords)
    Given a target, Driver can produce corresponding LaTeX code, along
    with dependency list. It is Driver which ultimately knows how to
    deal with inrecords and outrecords.

driver.produce_metarecords(targets)
    Return (metarecords, figrecords) where
    metarecords = ODict(metaname : metarecord for some metanames)
    figrecords = ODict(figname : figrecord for some fignames)

    Metanames and fignames are derived from targets, inrecords and
    outrecords. They must not contain any '/' slashes and should not
    contain any extensions.

driver.list_targets()
    Return a list of some valid targets, that may be used with
    produce_metarecords(). This list is not (actually, can not be)
    guaranteed to be complete.

Metarecords
    Each metarecord must contain the following fields:

    'metaname'
        string equal to the corresponding metaname

    'sources'
        {alias_name : inpath for each inpath}
        where alias_name is a filename with '.tex' extension,
        and inpath has '.tex' extension.

    'fignames'
        an iterable of strings; all of them must be contained
        in figrecords.keys()

    'document'
        LaTeX document as a string

Figrecords
    Each figrecord must contain the following fields:

    'figname'
        string equal to the corresponding figname

    'source'
        inpath with '.asy' or '.eps' extension

    'type'
        string, either 'asy' or 'eps'

    In case of Asymptote file ('asy' type), figrecord must also
    contain:
    'used'
        {used_name : inpath for each used inpath}
        where used_name is a filename with '.asy' extension,
        and inpath has '.asy' extension

Inpaths
    Inpaths are relative PurePath objects. They should be based on
    inrecords, and supposed to be valid subpaths of the '<root>/source/'
    directory.

"""

from .course import CourseDriver as Driver

