"""
driver = Driver(metarecords)
    Given a target, driver can produce corresponding LaTeX code, along
    with dependency list. It is driver which ultimately knows what to
    do with metarecords.

driver.produce_outrecords(targets)
    Return (outrecords, figrecords) where
    outrecords = OrderedDict(outname : outrecord for some outnames)
    figrecords = OrderedDict(figname : figrecord for some fignames)

    outnames and fignames are derived from targets and metarecords.
    They must not contain any '/' and should contain only numbers,
    letters and '-'.

driver.list_targets()
    Return a list of some targets that may be used with
    produce_outrecords(). This list is not guaranteed to be complete.

outrecords
    Each outrecord must contain the following fields:

    'outname'
        string equal to the corresponding outname

    'sources'
        {alias_name : inpath for each inpath}
        where alias_name is a filename with '.tex' extension,
        and inpath also has '.tex' extension.

    'fignames'
        an iterable of strings; all of them must be contained
        in figrecords.keys()

    'document'
        LaTeX document as a string

figrecords
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

inpaths
    Inpaths are relative PurePosixPath objects. They are supposed to be
    valid subpaths of the <root>/source/ directory.

"""


