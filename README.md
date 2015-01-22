This application aims at managing course-like projects, that consist of
many small pieces distributed to course listeners over time.

Application includes build system implemented in Python, and
complementary LaTeX package.

#### Dependencies

* Python 3.3 or greater; the following non-standard packages must be installed:
  * [PyYAML](http://pyyaml.org/)
  * [pyinotify](http://github.com/seb-m/pyinotify) (used only by jeolm.buildline shell)
  * [pathlib](http://docs.python.org/3/library/pathlib.html) of some specific versions:
    - version included in Python 3.4.2 will work
    - [recent version](http://hg.python.org/cpython/file/4a55b98314cd/Lib/pathlib.py) will work too
    - unfortunately, version included in Python 3.4.1 won't work due to a [bug](http://bugs.python.org/issue20639)
* LaTeX

Following programs will be invoked occasionally:

* [Asymptote](http://asymptote.sourceforge.net/) (on .asy to .eps compilation)
* [Inkscape](http://inkscape.org/) (on .svg to .eps conversion)

#### Invocation

    $ python3 -m jeolm --help
    $ python3 -m jeolm init gitignore style
    $ cat <<EOF > source/_style.yaml
    \$style:
    - /_style
    - verbatim: \def\jeolmheader\jeolmheadertemplate{institution}{date range}{group name}
    EOF
    $ python3 -m jeolm review source/
    $ python3 -m jeolm build /_style/jeolm # build documentation of LaTeX package
    $ python3 -m jeolm.buildline
    jeolm>
