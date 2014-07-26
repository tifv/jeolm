from distutils.core import setup

setup(
    name='jeolm',
    packages=['jeolm', 'jeolm.driver'],
    package_dir={'jeolm' : 'python'},
    package_data={'jeolm' : ['resources/*']}
)

