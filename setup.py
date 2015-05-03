from distutils.core import setup

setup(
    name='jeolm',
    packages=[
        'jeolm', 'jeolm.driver', 'jeolm.node',
        'jeolm.commands', 'jeolm.scripts' ],
    package_dir={'jeolm' : 'source/jeolm'},
    package_data={'jeolm' : ['resources/*']}
)

