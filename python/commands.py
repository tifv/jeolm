import os
import logging

from pathlib import Path

logger = logging.getLogger(__name__)

def cleanview(root):
    """
    Remove all <root>/build/** symbolic links from the toplevel.
    """
    assert isinstance(root, Path), root
    for x in root:
        if not x.is_symlink():
            continue
        target = os.readlink(str(x))
        if target.startswith((str(root['build']) + '/', 'build/')):
            x.unlink()

def unbuild(root):
    """
    Run cleanview() plus remove all generated build/**.tex files
    """
    cleanview(root)
    _unbuild_recursive(root['build'])

def _unbuild_recursive(builddir):
    for x in builddir:
        if x.is_symlink():
            continue
        if x.is_dir():
            _unbuild_recursive(x)
            continue
        if x.ext != '.tex':
            continue
        x.unlink()

def archive(root, target='archive', archive_name='archive.tar.gz'):
    import tarfile

    from pathlib import PurePath

    from jeolm.builder import Builder
    builder = Builder([target], root=root)
    builder.prebuild(); builder.update()

    def join(*args): return str(PurePath(*args))

    with tarfile.open(str(root[archive_name]), 'w:gz') as af:
        for name, node in builder.source_nodes.items():
            af.add(str(node.path), join('source', name))
        for metaname, node in builder.pdf_nodes.items():
            af.add(str(node.path), join('pdf', metaname + '.pdf'))
        for metaname, node in builder.autosource_nodes.items():
            af.add(str(node.path), join('autosource', metaname + '.tex'))
        for figname, node in builder.eps_nodes.items():
            af.add(str(node.path), join('eps', figname + '.eps'))

        af.add(str(root['meta/in.yaml']), 'meta/in.yaml')
        af.add(str(root['meta/out.yaml']), 'meta/out.yaml')
        af.add(str(root['meta/local.sty']), 'meta/local.sty')
        if root['meta/local.py'].exists():
            af.add(str(root['meta/local.py']), 'meta/local.py')

def shell(root):
    import readline
    from . import completion
    completer = completion.Completer(root)
    readline.set_completer(completer.readline_completer)
    readline.set_completer_delims('')
    readline.parse_and_bind('tab: complete')

    targets = []
    clear = 0
    try:
        while True:
            target = input('> ')
            if target == '':
                clear += 1
                if clear >= 2:
                    targets = []
            else:
                clear = 0
                targets.append(target)
            print(targets)
    except EOFError:
        print()
    except KeyboardInterrupt:
        raise SystemExit

    from . import builder
    builder.build(targets, root=root)

