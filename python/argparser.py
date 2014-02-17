from argparse import ArgumentParser

from .target import Target

parser = ArgumentParser(prog='jeolm',
    description='Automated build system for course-like projects' )
parser.add_argument('-R', '--root',
    help='explicit root path of a jeolm project', )
parser.add_argument('-v', '--verbose',
    help='make debug messages to stdout',
    action='store_true', )

subparsers = parser.add_subparsers()

build_parser = subparsers.add_parser('build',
    help='build specified targets', )
build_parser.add_argument('targets',
    nargs='*', metavar='TARGET', type=Target.from_string)
force_build_group = build_parser.add_mutually_exclusive_group()
force_build_group.add_argument('-f', '--force-latex',
    help='force recompilation on LaTeX stage',
    action='store_const', dest='force', const='latex')
force_build_group.add_argument('-F', '--force-generate',
    help='force overwriting of generated LaTeX file',
    action='store_const', dest='force', const='generate')
build_parser.add_argument('-D', '--no-delegate',
    help='ignore the possibility of delegating targets',
    action='store_false', dest='delegate' )
build_parser.add_argument('-r', '--review',
    help='review included infiles prior to build',
    action='store_true', )
build_parser.add_argument('--dump',
    help='instead of building create standalone version of document',
    action='store_true', )
build_parser.set_defaults(command='build', force=None)

list_parser = subparsers.add_parser('list',
    help='list all infiles for given targets' )
list_parser.add_argument('targets',
    nargs='*', metavar='TARGET', type=Target.from_string, )
list_parser.add_argument('--type',
    help='searched-for infiles type',
    choices=['tex', 'asy'], default='tex',
    dest='source_type', metavar='SOURCE_TYPE', )
list_parser.set_defaults(command='list')

#expose_parser = subparsers.add_parser('expose',
#    help='list generated main.tex files for given targets' )
#expose_parser.add_argument('targets',
#    nargs='*', metavar='TARGET', type=Target.from_string, )
#expose_parser.set_defaults(command='expose')

spell_parser = subparsers.add_parser('spell',
    help='spell-check all infiles for given targets' )
spell_parser.add_argument('targets',
    nargs='*', metavar='TARGET', type=Target.from_string, )
spell_parser.set_defaults(command='spell')

review_parser = subparsers.add_parser('review',
    help='review given infiles' )
review_parser.add_argument('inpaths',
    nargs='*', metavar='INPATH', )
review_parser.add_argument('-r', '--recursive',
    action='store_true', )
review_parser.set_defaults(command='review')

clean_parser = subparsers.add_parser('clean',
    help='clean toplevel links to build/**.pdf', )
clean_parser.set_defaults(command='clean')

