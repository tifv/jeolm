import argparse
import os

from contextlib import suppress
from functools import partial

from pathlib import Path

import jeolm
import jeolm.project
import jeolm.target
import jeolm.commands
import jeolm.logging

# use 'jeolm' logger instead of '__main__'
import logging
logger = logging.getLogger(jeolm.__name__)


def _get_base_arg_parser( prog='jeolm',
    description="Automated build system for course-like projects"
):
    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument( '-R', '--root',
        help="explicit root path of a jeolm project" )
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument( '-v', '--verbose',
        help="show debug messages",
        action='store_const', dest='log_level', const=logging.DEBUG )
    verbosity_group.add_argument( '-q', '--quiet',
        help="show only warnings and errors",
        action='store_const', dest='log_level', const=logging.WARNING )
    parser.add_argument( '-C', '--no-colour',
        help="disable colour output",
        action='store_false', dest='colour' )
    parser.add_argument( '--nice',
        help="increment niceness level by this amount (default 10)",
        type=int, default=10 )
    parser.set_defaults(log_level=logging.INFO)
    return parser

def _jobs_arg(arg):
    try:
        jobs = int(arg)
    except ValueError:
        jobs = 0
    if jobs < 1:
        raise argparse.ArgumentTypeError("positive integer expected")
    return jobs

def main(args):
    jeolm.logging.setup_logging(level=args.log_level, colour=args.colour)
    nice_level = os.nice(args.nice)
    logger.debug("Nice level: %s", nice_level)
    if args.command is None:
        logger.error("No command selected.")
        raise SystemExit(1)
    if args.command == 'init':
        # special case: no project expected
        return main_init(args)
    try:
        project = jeolm.project.Project(root=args.root)
    except jeolm.project.RootNotFoundError:
        jeolm.project.report_missing_root()
        raise SystemExit(1)
    return args.command_func(args, project=project)


# pylint: disable=unused-variable,unused-argument


####################
# build

def _add_build_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'build',
        help="build specified targets" )
    parser.add_argument( 'targets',
        nargs='*', metavar='TARGET', type=jeolm.target.Target.from_string)
    force_build_group = parser.add_mutually_exclusive_group()
    force_build_group.add_argument( '-f', '--force-latex',
        help="force recompilation on LaTeX stage",
        action='store_const', dest='force', const='latex' )
    force_build_group.add_argument( '-F', '--force-generate',
        help="force overwriting of generated LaTeX file",
        action='store_const', dest='force', const='generate' )
    parser.add_argument( '-D', '--no-delegate',
        help="ignore the possibility of delegating targets",
        action='store_false', dest='delegate' )
    archive_group = parser.add_mutually_exclusive_group()
    archive_group.add_argument( '-z', '--sources-zip',
        help="pack source files in a ZIP archive for each target built",
        action='store_const', dest='archive', const='zip' )
    archive_group.add_argument( '-s', '--sources-tar-gz',
        help="pack source files in a .tar.gz archive for each target built",
        action='store_const', dest='archive', const='tgz' )
    parser.add_argument( '-j', '--jobs',
        help="number of parallel jobs",
        type=_jobs_arg, default=1 )
    parser.set_defaults(command_func=main_build, force=None, archive=None)

def main_build(args, *, project):
    from jeolm.node import PathNode, NodeErrorReported
    from jeolm.node_factory.target import TargetNodeFactory

    if not args.targets:
        logger.warning("No-op: no targets for building")
    PathNode.root = project.root
    node_updater = _build_get_node_updater(args.jobs)
    driver = jeolm.commands.simple_load_driver(project)

    target_node_factory = TargetNodeFactory(project=project, driver=driver)
    target_node = target_node_factory( args.targets,
        delegate=args.delegate, archive=args.archive )
    if args.force is None:
        pass
    elif args.force == 'latex':
        _build_force_latex(target_node)
    elif args.force == 'generate':
        _build_force_generate(target_node)
    else:
        raise RuntimeError(args.force)
    with suppress(NodeErrorReported):
        node_updater.update(target_node)

def _build_force_latex(target_node):
    from jeolm.node.latex import LaTeXNode
    for node in target_node.iter_needs():
        if isinstance(node, LaTeXNode):
            node.force()

def _build_force_generate(target_node):
    from jeolm.node.latex import LaTeXNode
    from jeolm.node import FileNode
    for node in target_node.iter_needs():
        if (isinstance(node, LaTeXNode) and
            isinstance(node.source, FileNode)
        ):
            node.source.force()

def _build_get_node_updater(jobs):
    assert isinstance(jobs, int), type(jobs)
    assert jobs >= 1
    from jeolm.node.updater import NodeUpdater
    return NodeUpdater(jobs=jobs)


####################
# buildline

def _add_buildline_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'buildline',
        help="start an interactive build shell" )
    parser.add_argument( '-j', '--jobs',
        help="number of parallel jobs",
        type=_jobs_arg, default=1 )
    parser.set_defaults(command_func=main_buildline, force=None)

def main_buildline(args, *, project):
    from jeolm.node import PathNode
    from jeolm.buildline import BuildLine

    PathNode.root = project.root
    node_updater = _build_get_node_updater(args.jobs)

    buildline = BuildLine(project=project, node_updater=node_updater)
    with buildline.readline_setup():
        return buildline.main()


####################
# review

def _add_review_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'review',
        help="review given infiles" )
    parser.add_argument( 'inpaths',
        nargs='*', metavar='INPATH' )
    parser.set_defaults(command_func=main_review)

def main_review(args, *, project):
    from jeolm.commands.review import review
    from jeolm.commands.diffprint import log_metadata_diff
    if not args.inpaths:
        logger.warning("No-op: no inpaths for review")
    metadata = (project.metadata_class)(project=project)
    metadata.load_metadata_cache()
    with log_metadata_diff(metadata, logger=logger):
        review( args.inpaths,
            viewpoint=Path.cwd(), project=project, metadata=metadata )
    metadata.dump_metadata_cache()


####################
# init

def _add_init_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'init',
        help="create jeolm directory/file structure" )
    parser.add_argument( 'resources',
        nargs='*', metavar='RESOURCE' )
    # command_func default is intentionally not set

def main_init(args):
    if args.root is None:
        root = Path.cwd()
    else:
        root = Path(args.root)
    jeolm.project.InitProject(
        root=root, resources=args.resources )


####################
# list

def _add_list_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'list',
        help="list all infiles for given targets" )
    parser.add_argument( 'targets',
        nargs='*', metavar='TARGET', type=jeolm.target.Target.from_string )
    parser.add_argument( '--type',
        help="searched-for infiles type",
        choices=['tex', 'asy'], default='tex',
        dest='source_type', metavar='SOURCE_TYPE' )
    parser.set_defaults(command_func=main_list)

def main_list(args, *, project):
    from jeolm.commands.list_sources import print_source_list
    if not args.targets:
        logger.warning("No-op: no targets for source list")
    print_source_list( args.targets,
        viewpoint=Path.cwd(), project=project,
        driver=jeolm.commands.simple_load_driver(project),
        source_type=args.source_type )


####################
# spell

def _add_spell_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'spell',
        help="spell-check all infiles for given targets" )
    parser.add_argument( 'targets',
        nargs='*', metavar='TARGET', type=jeolm.target.Target.from_string )
    parser.set_defaults(command_func=main_spell)

def main_spell(args, *, project):
    from jeolm.commands.spell import check_spelling
    if not args.targets:
        logger.warning("No-op: no targets for spell check")
    check_spelling( args.targets,
        project=project,
        driver=jeolm.commands.simple_load_driver(project),
        colour=args.colour )


####################
# makefile

def _add_makefile_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'makefile',
        help="generate makefile for given targets" )
    parser.add_argument( 'targets',
        nargs='*', metavar='TARGET', type=jeolm.target.Target.from_string)
    parser.add_argument( '-o', '--output-makefile',
        help="where to write makefile; default is Makefile",
        default='Makefile' )
    parser.add_argument( '-O', '--output-unbuildable',
        help = "where to write list of files which makefile cannot rebuild "
            "(and depends on); default is stdout" )
    parser.set_defaults(command_func=main_makefile)

def main_makefile(args, *, project):
    from jeolm.commands.makefile import MakefileGenerator
    from jeolm.node import PathNode, NodeErrorReported
    from jeolm.node_factory.target import TargetNodeFactory

    if not args.targets:
        logger.warning("No-op: no targets for makefile generation")
    PathNode.root = project.root
    node_updater = _build_get_node_updater(jobs=1)
    driver = jeolm.commands.simple_load_driver(project)

    target_node_factory = TargetNodeFactory(project=project, driver=driver)
    makefile_string, unbuildable_nodes, unrepresentable_nodes = \
        MakefileGenerator.generate(
            target_node_factory(args.targets, name='first'),
            viewpoint=project.root )
    with suppress(NodeErrorReported):
        for node in unbuildable_nodes:
            node_updater.update(node)
    for node in unrepresentable_nodes:
        node.logger.warning(
            "Node has no possible representation in Makefile" )
    _open = partial(open, encoding='utf-8')
    with _open(args.output_makefile, 'w') as makefile:
        makefile.write(makefile_string)
    if args.output_unbuildable is None:
        _print_unbuildable_list(unbuildable_nodes, project=project)
    else:
        with _open(args.output_unbuildable, 'w') as unbuildable_list_file:
            _print_unbuildable_list( unbuildable_nodes, project=project,
                file=unbuildable_list_file )

def _print_unbuildable_list(unbuildable_nodes, *, project, **kwargs):
    for node in unbuildable_nodes:
        print(str(node.path.relative_to(project.root)), **kwargs)


####################
# clean

def _add_clean_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'clean',
        help="clean toplevel links to build/**.pdf" )
    parser.set_defaults(command_func=main_clean)

def main_clean(args, *, project):
    from jeolm.commands.clean import clean_build_links, clean_broken_links
    clean_build_links(project.root)
    clean_broken_links(project.build_dir, recursive=True)


# pylint: enable=unused-variable,unused-argument


def _get_arg_parser():
    parser = _get_base_arg_parser()
    subparsers = parser.add_subparsers(title='commands', dest='command')
    _add_build_arg_subparser(subparsers)
    _add_buildline_arg_subparser(subparsers)
    _add_review_arg_subparser(subparsers)
    _add_init_arg_subparser(subparsers)
    _add_list_arg_subparser(subparsers)
    _add_spell_arg_subparser(subparsers)
    _add_makefile_arg_subparser(subparsers)
    _add_clean_arg_subparser(subparsers)
    return parser

def _get_args():
    parser = _get_arg_parser()
    args = parser.parse_args()
    return args

if __name__ == '__main__':
    main(args=_get_args())

