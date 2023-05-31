from distutils.core import setup

setup(
    name='jeolm',
    packages=[
        'jeolm',
        'jeolm.utils', 'jeolm.driver', 'jeolm.node', 'jeolm.node_factory',
        'jeolm.commands', 'jeolm.scripts' ],
    package_dir={'jeolm' : 'source/jeolm'},
    package_data={'jeolm' : ['resources/*']},
    install_requires=[
        'typing_extensions',
        'pyyaml',
        'pyinotify',
    ],
)

