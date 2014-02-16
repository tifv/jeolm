"""
Miscellaneous and relatively simple commands, not deserving their own
module.
"""
import os

from pathlib import Path, PurePosixPath as PurePath

import logging
logger = logging.getLogger(__name__)

def main():
    from . import filesystem, nodes
    from .argparser import parser
    from . import setup_logging

    args = parser.parse_args()
    setup_logging(args.verbose)
    try:
        fs = filesystem.FilesystemManager(
            root=Path(args.root) if args.root is not None else None )
    except filesystem.RootNotFoundError:
        raise SystemExit
    nodes.PathNode.root = fs.root
    fs.report_broken_links()
    if 'command' not in args:
        return parser.print_help()
    fs.load_local_module()
    main_function = globals()['main_' + args.command]
    return main_function(args, fs=fs)

def main_build(args, *, fs):

    from jeolm.builder import Builder
    if args.dump:
        from jeolm.builder import Dumper as Builder
    if not args.targets:
        logger.warn('No-op: no targets for building')

    if args.review:
        review(
            list_sources( args.targets,
                fs=fs, source_type='tex' ),
            viewpoint=Path.cwd(),
            fs=fs, recursive=False )

    builder = Builder(args.targets, fsmanager=fs,
        force=args.force, delegate=args.delegate )
    builder.update()

def main_review(args, *, fs):
    if not args.inpaths:
        logger.warn('No-op: no inpaths for review')
    review(args.inpaths, viewpoint=Path.cwd(),
            fs=fs, recursive=args.recursive )

def main_list(args, *, fs):
    if not args.targets:
        logger.warn('No-op: no targets for source list')
    print_source_list(args.targets,
        fs=fs, viewpoint=Path.cwd(),
        source_type=args.source_type, )

def main_expose(args, *, fs):
    from jeolm.builder import Builder
    if not args.targets:
        logger.warn('No-op: no targets for exposing source')
    builder = Builder(args.targets, fsmanager=fs, force=None)
    for node in builder.autosource_nodes.values():
        node.update()
        print(node.path)

def main_spell(args, *, fs):
    if not args.targets:
        logger.warn('No-op: no targets for spell check')
    check_spelling(args.targets, fs=fs,)

def main_clean(args, *, fs):
    clean(root=fs.root)
    fs.clean_broken_links(fs.build_dir, recursive=True)

def clean(root):
    """
    Remove all symbolic links to 'build/*whatever*' from the toplevel.
    """
    assert isinstance(root, Path), root
    for x in root.iterdir():
        if not x.is_symlink():
            continue
        target = os.readlink(str(x))
        if target.startswith('build/'):
            x.unlink()

def print_source_list(targets, *, fs, viewpoint, source_type):
    path_generator = list_sources(targets,
        fs=fs, source_type=source_type )
    for path in path_generator:
        print(path.relative_to(viewpoint))

def check_spelling(targets, *, fs, context=0):
    from . import spell
    from .spell import IncorrectWord
    from . import cleanlogger

    indicator_length = 0
    def indicator_clean():
        nonlocal indicator_length
        if indicator_length:
            print(' ' * indicator_length, end='\r')
        indicator_length = 0
    def indicator_show(s):
        nonlocal indicator_length
        print(s, end='\r')
        indicator_length = len(str(s))

    path_generator = list_sources(targets,
        fs=fs, source_type='tex' )
    for path in path_generator:
        indicator_clean()
        indicator_show(str(path))

        with path.open('r') as f:
            text = f.read()
        lines = ['']
        printed_line_numbers = set()
        try:
            for text_piece in spell.Speller(text, lang='ru_RU'):
                if isinstance(text_piece, IncorrectWord):
                    lineno = len(lines) - 1
                    printed_line_numbers.update(
                        range(lineno-context, lineno+context+1) )
                text_piece = str(text_piece).split('\n')
                lines[-1] += text_piece[0]
                for subpiece in text_piece[1:]:
                    lines.append(subpiece)
        except ValueError as error:
            raise ValueError(
                "Error while spell-checking {}"
                .format(path.relative_to(fs.root))
            ) from error
        if not printed_line_numbers:
            continue
        indicator_clean()
        cleanlogger.info(
            '<BOLD><YELLOW>{}<NOCOLOUR> possible misspellings<RESET>'
            .format(path.relative_to(fs.source_dir)) )
        line_range = range(len(lines))
        for lineno in sorted(printed_line_numbers):
            if lineno not in line_range:
                continue
            cleanlogger.info(
                '<MAGENTA>{}<NOCOLOUR>:{}'.format(lineno+1, lines[lineno]) )
    indicator_clean()

def review(paths, *, fs, viewpoint, recursive):
    import difflib
    from . import yaml, diffprint
    from . import cleanlogger

    inpaths = resolve_inpaths(paths,
        source_dir=fs.source_dir, viewpoint=viewpoint )
    metadata_manager = fs.load_metadata_manager()

    old_metarecords = metadata_manager.construct_metarecords()
    for inpath in inpaths:
        metadata_manager.review(inpath, recursive=recursive)
    new_metarecords = metadata_manager.construct_metarecords()
    Metarecords = type(old_metarecords)
    assert isinstance(new_metarecords, Metarecords)

    comparing_iterator = Metarecords.compare_items(
        old_metarecords, new_metarecords, wipe_subrecords=True )
    for inpath, old_record, new_record in comparing_iterator:
        assert old_record is not None or new_record is not None, inpath
        if old_record == new_record:
            continue
        old_dump = yaml.dump(old_record).splitlines()
        new_dump = yaml.dump(new_record).splitlines()
        if old_record is None:
            cleanlogger.info(
                '<BOLD><GREEN>{}<NOCOLOUR> metarecord added<RESET>'
                .format(inpath) )
            old_dump = []
        elif new_record is None:
            cleanlogger.info(
                '<BOLD><RED>{}<NOCOLOUR> metarecord removed<RESET>'
                .format(inpath) )
            new_dump = []
        else:
            cleanlogger.info(
                '<BOLD><YELLOW>{}<NOCOLOUR> metarecord changed<RESET>'
                .format(inpath) )
        delta = difflib.ndiff(a=old_dump, b=new_dump)
        diffprint.print_ndiff_delta(delta, fix_newlines=True)

    fs.dump_metadata(metadata_manager.records)

def list_sources(targets, *, fs, source_type):
    driver = fs.load_driver()
    source_dir = fs.source_dir
    for target in driver.list_delegators(*targets, recursively=True):
        inpath_generator = driver.list_inpaths(target, inpath_type=source_type)
        for inpath in inpath_generator:
            yield source_dir/inpath

def resolve_inpaths(inpaths, *, source_dir, viewpoint):
    assert isinstance(viewpoint, Path), viewpoint
    assert viewpoint.is_absolute(), viewpoint
    for inpath in inpaths:
        path = Path(viewpoint, inpath)
        try:
            path = path.resolve()
        except FileNotFoundError:
            pass
        yield PurePath(path).relative_to(source_dir)

