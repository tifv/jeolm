This application aims at managing course-like projects, that consist of
many small pieces distributed to course listeners over time.

Application includes build system implemented in Python, and
complementary LaTeX package.

#### Required dependencies

* Python 3.4.2 or greater; the following non-standard packages are required:
  * [PyYAML](http://pyyaml.org/);
  * unidecode
* LaTeX.

#### Optional dependencies

* Python non-standard packages:
  * [pyinotify](http://github.com/seb-m/pyinotify) is required for `jeolm buildline` subcommand;
  * [pyenchant](http://pythonhosted.org/pyenchant/) is required for `jeolm spell` subcommand;
* [Asymptote](http://asymptote.sourceforge.net/) is required to compile `.asy` figures;
* [Inkscape](http://inkscape.org/) is required to convert `.svg` figures.
