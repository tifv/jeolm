from functools import wraps

from jeolm.driver.regular import RegularDriver, DriverError

from jeolm.record_path import RecordPath
from jeolm.flags import FlagContainer

import logging
logger = logging.getLogger(__name__)

class TournDriver(RegularDriver):

    @property
    def translations(self, _root=RecordPath()):
        translations = self.getitem(_root)['$translations']
        assert isinstance(translations, dict)
        assert all(isinstance(value, dict) for value in translations.values())
        return translations

    tourn_problem_flags = frozenset(('problems', 'solutions', 'complete',))

    all_tourn_flags = frozenset((
        'problems', 'solutions', 'complete',
        'contest', 'jury', 'blank' ))

    contest_keys = frozenset((
        '$contest', '$contest$league', '$contest$problem' ))
    regatta_keys = frozenset((
        '$regatta', '$regatta$league',
        '$regatta$subject', '$regatta$round',
        '$regatta$problem' ))
    subleague_keys = frozenset((
        '$contest$league', '$regatta$league',
        '$regatta$subject', '$regatta$round',
        '$contest$problem', '$regatta$problem', ))

    @staticmethod
    def target_flags_contest_to_blank(target):
        return target.flags_delta(
            difference={'contest'},
            union={'blank', 'without-problem-sources'} )

    @staticmethod
    def target_flags_jury_to_complete(target):
        return target.flags_delta(
            difference={'jury'},
            union={'complete', 'with-criteria'} )


    ##########
    # Record-level functions

    @classmethod
    def get_tourn_flags(cls, tourn_key):
        setlist = [cls.tourn_problem_flags]
        if tourn_key not in \
                {'$contest', '$contest$problem', '$regatta$problem'}:
            setlist.append(('contest', 'jury',))
        else:
            if tourn_key == '$regatta$problem':
                setlist.append(('blank',))
        return frozenset().union(*setlist)

    @inclass_decorator
    def ensure_tourn_flags(method):
        """Decorator."""
        @wraps(method)
        def wrapper(self, target, metarecord, **kwargs):
            tourn_key = metarecord.get('$tourn$key')
            if tourn_key is None:
                raise RuntimeError(target)
            tourn_flags = self.get_tourn_flags(tourn_key)
            all_tourn_flags = self.all_tourn_flags
            misused_flags = target.flags.intersection(
                all_tourn_flags - tourn_flags )
            if misused_flags:
                raise DriverError(
                    "Misused tourn flags {flags} in {target}"
                    .format(flags=misused_flags, target=target) )
            if not target.flags.intersection(tourn_flags):
                logger.error(
                    "<BOLD>One of tourn flags is required: {}<RESET>"
                    .format(', '.join(sorted(self.all_tourn_flags)))
                )
                raise DriverError(
                    "No tourn flags in {target}"
                    .format(target=target) )
            return method(self, target, metarecord, **kwargs)
        return wrapper

    # Extension
    @processing_target_aspect(aspect='matter metabody [tourn]', wrap_generator=True)
    @classifying_items(aspect='metabody', default='verbatim')
    def generate_matter_metabody(self, target, metarecord,
        *, matter_key=None, matter=None
    ):
        no_tourn = ( '$tourn$key' not in metarecord or
            matter_key is not None or
            matter is not None)
        if no_tourn:
            yield from super().generate_matter_metabody(
                target, metarecord,
                matter_key=matter_key, matter=matter )
            return

        tourn_key = metarecord['$tourn$key']
        no_league = tourn_key not in self.subleague_keys
        is_regatta = tourn_key in self.regatta_keys
        is_contest = tourn_key in self.contest_keys
        assert is_regatta or is_contest
        single_problem = tourn_key in {'$contest$problem', '$regatta$problem'}
        is_regatta_blank = is_regatta and (
            not single_problem and 'contest' in target.flags or
            single_problem and 'blank' in target.flags )
        if 'no-header' not in target.flags and not is_regatta_blank:
            if no_league:
                yield self._constitute_league_def(None)
            else:
                league = self._find_league(metarecord)
                yield self._constitute_league_def(
                    self._find_name(league, metarecord['$language']) )
                if not single_problem:
                    target = target.flags_union({'league-contained'})
            if single_problem:
                yield self.substitute_jeolmtournheader_nospace()
            else:
                # Create a negative offset in anticipation of \section
                yield self.substitute_jeolmtournheader()
                target = target.flags_union({'no-header'})

        yield from self._generate_tourn_metabody(target, metarecord)

    @processing_target_aspect(aspect='tourn metabody', wrap_generator=True)
    @classifying_items(aspect='metabody', default=None)
    def _generate_tourn_metabody(self, target, metarecord):
        tourn_key = metarecord['$tourn$key']
        tourn_flags = target.flags.intersection(
            self.get_tourn_flags(tourn_key) )
        if len(tourn_flags) > 1:
            raise ValueError(sorted(tourn_flags))

        args = [target, metarecord]
        kwargs = dict()
        if tourn_key in self.contest_keys:
            kwargs.update(contest=self._find_contest(metarecord))
        elif tourn_key in self.regatta_keys:
            kwargs.update(regatta=self._find_regatta(metarecord))
        else:
            raise RuntimeError(tourn_key)
        if tourn_key in self.subleague_keys:
            kwargs.update(league=self._find_league(metarecord))

        method = getattr(self,
            '_generate' + tourn_key.replace('$', '_') + '_matter' )

        yield from method(*args, **kwargs)

    @classifying_items(aspect='metabody', default='verbatim')
    @ensure_tourn_flags
    def _generate_contest_matter(self, target, metarecord,
        *, contest
    ):
        yield self.constitute_section(
            self._find_name( contest, metarecord['$language']),
            flags=target.flags )
        target = target.flags_union({'contained'}, overadd=False)
        target = target.flags_union(self.increase_containment(target.flags))

        for leaguekey in contest['leagues']:
            yield target.path_derive(leaguekey)

    @classifying_items(aspect='metabody', default='verbatim')
    @ensure_tourn_flags
    def _generate_regatta_matter(self, target, metarecord,
        *, regatta
    ):
        if 'contest' not in target.flags:
            yield self.constitute_section(
                self._find_name(regatta, metarecord['$language']),
                flags=target.flags )
            target = target.flags_union({'contained'}, overadd=False)
            target = target.flags_union(self.increase_containment(target.flags))

        for leaguekey in regatta['leagues']:
            yield target.path_derive(leaguekey)

    @classifying_items(aspect='metabody', default='verbatim')
    @ensure_tourn_flags
    def _generate_contest_league_matter(self, target, metarecord,
        *, contest, league
    ):
        if 'contest' in target.flags:
            target = target.flags_delta(
                difference={'contest'},
                union={'problems', 'without-problem-sources'} )
            has_postword = True
        else:
            has_postword = False
        if 'league-contained' in target.flags:
            yield self.constitute_section(
                self._find_name(contest, metarecord['$language']),
                #league_name,
                flags=target.flags )
        else:
            league_name = self._find_name(league, metarecord['$language'])
            yield self.constitute_section(
                self._find_name(contest, metarecord['$language']),
                league_name,
                flags=target.flags )

        if 'jury' in target.flags:
            target = self.target_flags_jury_to_complete(target)
        yield self.constitute_begin_tourn_problems(
            target.flags.intersection(self.tourn_problem_flags) )
        target = target.flags_union({'itemized'})
        for i in range(1, 1 + league['problems']):
            yield target.path_derive(str(i))
        yield self.substitute_end_tourn_problems()
        if has_postword:
            yield self.substitute_postword()

    @classifying_items(aspect='metabody', default='verbatim')
    @ensure_tourn_flags
    def _generate_regatta_league_matter(self, target, metarecord,
        *, regatta, league
    ):
        if 'contest' not in target.flags:
            if 'league-contained' in target.flags:
                yield self.constitute_section(
                    self._find_name(regatta, metarecord['$language']),
                    #league_name,
                    flags=target.flags )
            else:
                league_name = self._find_name(league, metarecord['$language'])
                yield self.constitute_section(
                    self._find_name(regatta, metarecord['$language']),
                    league_name,
                    flags=target.flags )
                target = target.flags_union(('league-contained',))
            target = target.flags_union(('contained',), overadd=False)
            target = target.flags_union(self.increase_containment(target.flags))
        by_round = ( 'by-round' in target.flags or
            'by-subject' not in target.flags )

        if by_round:
            for roundnum in range(1, 1 + league['rounds']):
                yield target.path_derive(str(roundnum))
        else:
            for subjectkey in league['subjects']:
                yield target.path_derive(subjectkey)

    @classifying_items(aspect='metabody', default='verbatim')
    @ensure_tourn_flags
    def _generate_regatta_subject_matter(self, target, metarecord,
        *, regatta, league
    ):
        subject = self._find_regatta_subject(metarecord)
        if 'contest' not in target.flags:
            if 'league-contained' in target.flags:
                yield self.constitute_section(
                    self._find_name(regatta, metarecord['$language']),
                    #league_name,
                    self._find_name(subject, metarecord['$language']),
                    flags=target.flags )
            else:
                league_name = self._find_name(league, metarecord['$language'])
                yield self.constitute_section(
                    self._find_name(regatta, metarecord['$language']),
                    league_name,
                    self._find_name(subject, metarecord['$language']),
                    flags=target.flags )
        else:
            target = self.target_flags_contest_to_blank(target)
        if 'jury' in target.flags:
            target = self.target_flags_jury_to_complete(target)

        if 'blank' not in target.flags:
            yield self.constitute_begin_tourn_problems(
                target.flags.intersection(self.tourn_problem_flags) )
            target = target.flags_union(('itemized',))
        for roundnum in range(1, 1 + league['rounds']):
            yield target.path_derive(str(roundnum))
        if 'blank' not in target.flags:
            yield self.substitute_end_tourn_problems()

    @classifying_items(aspect='metabody', default='verbatim')
    @ensure_tourn_flags
    def _generate_regatta_round_matter(self, target, metarecord,
        *, regatta, league
    ):
        regatta_round = self._find_regatta_round(metarecord)
        if 'contest' not in target.flags:
            if 'league-contained' in target.flags:
                yield self.constitute_section(
                    self._find_name(regatta, metarecord['$language']),
                    #league_name,
                    self._find_name(regatta_round, metarecord['$language']),
                    flags=target.flags )
            else:
                league_name = self._find_name(league, metarecord['$language'])
                yield self.constitute_section(
                    self._find_name(regatta, metarecord['$language']),
                    league_name,
                    self._find_name(regatta_round, metarecord['$language']),
                    flags=target.flags )
        else:
            target = self.target_flags_contest_to_blank(target)
        if 'jury' in target.flags:
            target = self.target_flags_jury_to_complete(target)

        if 'blank' not in target.flags:
            yield self.constitute_begin_tourn_problems(
                target.flags.intersection(self.tourn_problem_flags) )
            target = target.flags_union(('itemized',))
        for subjectkey in league['subjects']:
            yield target.path_derive('..', subjectkey, target.path.name)
        if 'blank' not in target.flags:
            yield self.substitute_end_tourn_problems()

    @classifying_items(aspect='metabody', default='verbatim')
    @ensure_tourn_flags
    def _generate_contest_problem_matter(self, target, metarecord,
        *, contest, league
    ):
        yield from self._generate_tourn_problem_matter(
            target, metarecord,
            number=target.path.name )

    @classifying_items(aspect='metabody', default='verbatim')
    @ensure_tourn_flags
    def _generate_regatta_problem_matter(self, target, metarecord,
        *, regatta, league
    ):
        subject = self._find_regatta_subject(metarecord)
        regatta_round = self._find_regatta_round(metarecord)
        if 'blank' in target.flags:
            assert 'itemized' not in target.flags, target
            assert 'league-contained' not in target.flags, target
            yield self._constitute_league_def(
                self._find_name(league, metarecord['$language']) )
            yield self.substitute_jeolmtournheader_nospace()
            yield self.substitute_regatta_blank_caption(
                caption=self._find_name(regatta, metarecord['$language']),
                mark=regatta_round['mark'] )
        if 'blank' in target.flags:
            subtarget = target.flags_union({'problems'})
        else:
            subtarget = target
        assert subtarget.flags.intersection(self.tourn_problem_flags), subtarget
        yield from self._generate_tourn_problem_matter(
            subtarget, metarecord,
            number=self.substitute_regatta_number(
                subject_index=subject['index'],
                round_index=regatta_round['index'] )
        )
        if 'blank' in target.flags:
            yield self.substitute_hrule()
            yield self.ClearPageBodyItem()

    class ProblemBodyItem(RegularDriver.SourceBodyItem):
        __slots__ = ['number']

        def __init__(self, metapath, number):
            super().__init__(metapath=metapath)
            self.number = number

    @classifying_items(aspect='metabody', default='verbatim')
    def _generate_tourn_problem_matter(self, target, metarecord,
        *, number
    ):
        has_criteria = ( 'with-criteria' in target.flags and
            '$criteria' in metarecord )
        has_problem_source = (
            'without-problem-sources' not in target.flags and
            '$problem-source' in metarecord )
        has_problem_source_www = (
            'without-problem-sources' not in target.flags and
            '$problem-source$www' in metarecord )
        if 'itemized' not in target.flags:
            yield self.constitute_begin_tourn_problems(
                target.flags.intersection(self.tourn_problem_flags) )
        yield self.ProblemBodyItem(metapath=target.path, number=number)
        if has_criteria:
            yield self.substitute_criteria(criteria=metarecord['$criteria'])
        if has_problem_source:
            yield self.substitute_problem_source(
                source=metarecord['$problem-source'] )
        if has_problem_source and has_problem_source_www:
            yield {'verbatim' : r'\par'}
        if has_problem_source_www:
            yield self.substitute_problem_source_www(
                source=metarecord['$problem-source$www'] )
        if 'itemized' not in target.flags:
            yield self.substitute_end_tourn_problems()

    def _find_contest(self, metarecord):
        contest_key = metarecord['$contest$key']
        if contest_key == '$contest':
            return metarecord[contest_key]
        elif contest_key in {'$contest$league', '$contest$problem'}:
            return self._find_contest(self[metarecord['$path'].parent])
        else:
            raise AssertionError(contest_key, metarecord)

    def _find_regatta(self, metarecord):
        regatta_key = metarecord['$regatta$key']
        if regatta_key == '$regatta':
            return metarecord[regatta_key]
        elif regatta_key in { '$regatta$league',
            '$regatta$subject', '$regatta$round', '$regatta$problem'
        }:
            return self._find_regatta(self[metarecord['$path'].parent])
        else:
            raise AssertionError(regatta_key, metarecord)

    def _find_league(self, metarecord):
        tourn_key = metarecord['$tourn$key']
        if tourn_key in {'$contest$league', '$regatta$league'}:
            return metarecord[tourn_key]
        elif tourn_key in { '$contest$problem',
            '$regatta$subject', '$regatta$round', '$regatta$problem'
        }:
            return self._find_league(self[metarecord['$path'].parent])
        else:
            raise AssertionError(tourn_key, metarecord)

    def _find_regatta_subject(self, metarecord):
        regatta_key = metarecord['$regatta$key']
        if regatta_key == '$regatta$subject':
            return metarecord['$regatta$subject']
        elif regatta_key == '$regatta$problem':
            return self._find_regatta_subject(self[metarecord['$path'].parent])
        else:
            raise AssertionError(regatta_key, metarecord)

    def _find_regatta_round(self, metarecord):
        regatta_key = metarecord['$regatta$key']
        if regatta_key == '$regatta$round':
            return metarecord['$regatta$round']
        elif regatta_key == '$regatta$problem':
            metapath = metarecord['$path']
            return self._find_regatta_round(
                self[metapath.parent.parent/metapath.name] )
        else:
            raise AssertionError(regatta_key, metarecord)

    def _find_name(self, entity, language):
        name = entity['name']
        if isinstance(name, str):
            return name
        elif isinstance(name, dict):
            (key, value), = name.items()
            if key == 'translate':
                return self.translations[value][language]
            else:
                raise ValueError(name)
        else:
            raise TypeError(name)

    ##########
    # Record extension

    def _derive_attributes(self, parent_record, child_record, name):
        super()._derive_attributes(parent_record, child_record, name)
        path = child_record['$path']
        child_record.setdefault('$language', parent_record.get('$language'))
        if '$contest$league' in parent_record:
            child_record['$contest$problem'] = {}
        if '$regatta$subject' in parent_record:
            child_record['$regatta$problem'] = {}

        contest_keys = self.contest_keys.intersection(child_record.keys())
        if contest_keys:
            contest_key, = contest_keys
            child_record['$contest$key'] = contest_key
        else:
            contest_key = None

        regatta_keys = self.regatta_keys.intersection(child_record.keys())
        if regatta_keys:
            regatta_key, = regatta_keys
            child_record['$regatta$key'] = regatta_key
        else:
            regatta_key = None

        if contest_key and regatta_key:
            raise ValueError(child_record.keys())

        tourn_key = contest_key or regatta_key
        if not tourn_key:
            return
        child_record['$tourn$key'] = tourn_key
        tourn_entity = child_record[tourn_key] = \
            child_record[tourn_key].copy()
        tourn_entity['metaname'] = path.name


    ##########
    # LaTeX-level functions

    # Extenstion
    @classmethod
    def _constitute_body_item(cls, item):
        if isinstance(item, cls.ProblemBodyItem):
            return cls._constitute_body_problem(
                alias=item.alias, number=item.number,
                figure_map=item.figure_map,
                metapath=item.metapath, inpath=item.inpath, )
        return super()._constitute_body_item(item)

    # Extension
    @classmethod
    def _constitute_body_problem( cls, *,
        alias, number, figure_map, metapath, inpath
    ):
        assert number is not None
        body = cls.substitute_tourn_problem(
            number=number, filename=alias,
            inpath=inpath, metapath=metapath )
        if figure_map:
            body = cls.constitute_figure_map(figure_map) + '\n' + body
        return body

    tourn_problem_template = (
        r'\tournproblem{$number}%' '\n'
        r'\input{$filename}% $metapath' )

    @classmethod
    def constitute_section(cls, *names, flags):
        try:
            select, = flags.intersection(
                ('problems', 'solutions', 'complete', 'jury',) )
        except ValueError as exc:
            assert isinstance(flags, FlagContainer), type(flags)
            exc.args += (flags.as_set(),)
            raise
        caption = names[-1]
        if 'subsubcontained' in flags:
            substitute_section = cls.substitute_subsubsection
        elif 'subcontained' in flags:
            substitute_section = cls.substitute_subsection
        else:
            substitute_section = cls.substitute_section
        if 'contained' not in flags:
            caption = '. '.join(names) + cls.caption_select_appendage[select]
        return substitute_section(caption=caption)

    section_template = r'\section*{$caption}'
    subsection_template = r'\subsection*{$caption}'
    subsubsection_template = r'\subsubsection*{$caption}'
    caption_select_appendage = {
        'problems' : '',
        'solutions' : ' (решения)',
        'complete' : ' (с решениями)',
        'jury' : ' (версия для жюри)',
    }

    @classmethod
    def constitute_begin_tourn_problems(cls, tourn_flags):
        select, = tourn_flags
        assert select in {'problems', 'solutions', 'complete'}
        return cls.substitute_begin_tourn_problems(select=select)

    @classmethod
    def _constitute_league_def(cls, league_name):
        if league_name is None:
            return cls.substitute_league_undef()
        return cls.substitute_league_def(league=league_name)

    league_undef_template = r'\let\jeolmleague\relax'
    league_def_template = r'\def\jeolmleague{$league}'

    begin_tourn_problems_template = r'\begin{tourn-problems}{$select}'
    end_tourn_problems_template = r'\end{tourn-problems}'
    postword_template = r'\postword'

    jeolmtournheader_template = r'\jeolmtournheader'
    jeolmtournheader_nospace_template = r'\jeolmtournheader*'
    regatta_blank_caption_template = r'\regattablankcaption{$caption}{$mark}'
    hrule_template = r'\medskip\hrule'

    regatta_number_template = r'$round_index$subject_index'

    criteria_template = r'\emph{Критерии: $criteria}\par'
    problem_source_template = ( r''
        r'\nopagebreak'
        r'\vspace{-1ex}\begingroup'
            r'\hfill\itshape\small($source' '%\n'
        r')\endgroup'
    )
    problem_source_www_template = ( r''
        r'\nopagebreak'
        r'\vspace{-1ex}\begingroup'
            r'\hfill\itshape\small $source' '%\n'
        r'\endgroup'
    )

    ##########
    # Supplementary finctions

    @staticmethod
    def increase_containment(flags):
        if 'subcontained' not in flags:
            yield 'subcontained'
        elif 'subsubcontained' not in flags:
            yield 'subsubcontained'
        else:
            raise ValueError(flags)


