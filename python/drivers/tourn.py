from pathlib import PurePosixPath as PurePath

from .course import CourseDriver, RecordNotFoundError
from jeolm.utils import pure_join

import logging
logger = logging.getLogger(__name__)

def produce_metarecords(targets, inrecords, outrecords):
    return TournDriver(inrecords, outrecords).produce_metarecords(targets)

def list_targets(inrecords, outrecords):
    return sorted(set(TournDriver(inrecords, outrecords).list_targets() ))

class TournDriver(CourseDriver):

    ##########
    # Record-level functions

    # Extension
    # Mimic non-delegations:
    # * some-contest/{problems,solutions,complete}
    # * some-contest-league/whatever
    # * some-regatta/{problems,solutions,complete}
    # Mimic delegations
    # * some-contest/whatever ->
    #       [some-contest-league/whatever for each league]
    # * some-regatta/whatever ->
    #       [some-regatta-league/whatever for each league]
    # * some-regatta-league/jury ->
    #       [some-regatta-league/subject/jury for each subject ]
    def _trace_delegators(self, target, resolved_path, record,
        *, seen_targets
    ):
        if not record.get('$mimic', False):
            yield from super()._trace_delegators(target, resolved_path, record,
                seen_targets=seen_targets )
            return;

        mimicroot = record['$mimic$root']
        mimicpath = record['$mimic$path']
        if '$contest' in record:
            contest = record['$contest']
            if mimicpath in self.tourn_fluid_targets:
                yield target
            else:
                for league in contest['leagues']:
                    yield from self.trace_delegators(
                        pure_join(mimicroot, league, mimicpath),
                        seen_targets=seen_targets )
        elif '$contest$league' in record:
            yield target
        elif '$regatta' in record:
            regatta = record['$regatta']
            if mimicpath in self.tourn_fluid_targets:
                yield target
            else:
                for league in regatta['leagues']:
                    yield from self.trace_delegators(
                        pure_join(mimicroot, league, mimicpath),
                        seen_targets=seen_targets )
        elif '$regatta$league' in record:
            league = record['$regatta$league']
            if mimicpath != PurePath('jury'):
                yield target
            else:
                for subjectkey in league['subjects']:
                    yield from self.trace_delegators(
                        pure_join(mimicroot, subjectkey, 'jury'),
                        seen_targets=seen_targets )
        else:
            raise AssertionError(record)

    tourn_fluid_targets = frozenset(PurePath(p) for p in
        ('problems', 'solutions', 'complete') )

    # Extension
    def list_protorecord_methods(self):
        yield self.produce_mimic_protorecord
        yield from super().list_protorecord_methods()

    def produce_mimic_protorecord(self, target, record,
        *, inpath_set, date_set ):
        if record is None or '$mimic' not in record:
            raise RecordNotFoundError(target);
        mimic = record['$mimic']


        kwargs = dict(
            subroot=record['$mimic$root'],
            subtarget=record['$mimic$path'],
            inpath_set=inpath_set, date_set=date_set )
        if mimic == '$contest':
            return self.produce_contest_protorecord(target, record=record,
                contest=record['$contest'], **kwargs );
        elif mimic == '$contest$league':
            return self.produce_contest_league_protorecord(target,
                record=record, contest=self.find_contest(record),
                league=record['$contest$league'], **kwargs );
        elif mimic == '$regatta':
            return self.produce_regatta_protorecord(target, record=record,
                regatta=record['$regatta'], **kwargs );
        elif mimic == '$regatta$league':
            return self.produce_regatta_league_protorecord(target,
                record=record, regatta=self.find_regatta(record),
                league=record['$regatta$league'], **kwargs );
        else:
            raise AssertionError(mimic)

    def produce_contest_protorecord(self, target, subroot, subtarget,
        record, contest,
        *, inpath_set, date_set
    ):
        if subtarget in self.tourn_fluid_targets:
            subtarget, = subtarget.parts
            return {'body' : self.generate_contest_body(
                subroot, subtarget, contest, inpath_set=inpath_set )};
        logger.debug('Tourn record not found: {!s}'.format(target))
        raise RecordNotFoundError(target);

    def produce_contest_league_protorecord(self, target, subroot, subtarget,
        record, contest, league, contained=False,
        *, inpath_set, date_set
    ):
        if subtarget in self.contest_league_fluid_targets:
            subtarget, = subtarget.parts
            return {'body' : self.generate_fluid_contest_league_body(
                subroot, subtarget,
                contest, league, contained, inpath_set=inpath_set )};
        assert not contained
        if subtarget == PurePath():
            rigid = record['$rigid']
            protorecord = {'body' : self.generate_rigid_contest_league_body(
                subroot, contest, league, rigid, inpath_set=inpath_set )}
            protorecord.update(record.get('$rigid$opt', ()))
            return protorecord;
        logger.debug('Tourn record not found: {!s}'.format(target))
        raise RecordNotFoundError(target);

    contest_league_fluid_targets = tourn_fluid_targets | {PurePath('jury')}

    def produce_regatta_protorecord(self, target, subroot, subtarget,
        record, regatta,
        *, inpath_set, date_set
    ):
        if subtarget in self.tourn_fluid_targets:
            subtarget, = subtarget.parts
            return {'body' : self.generate_regatta_body(
                subroot, subtarget, regatta, inpath_set=inpath_set )};
        logger.debug('Tourn record not found: {!s}'.format(target))
        raise RecordNotFoundError(target);

    def produce_regatta_league_protorecord(self, target, subroot, subtarget,
        record, regatta, league, contained=False,
        *, inpath_set, date_set
    ):
        if subtarget in self.regatta_league_fluid_targets:
            subtarget, = subtarget.parts
            return {'body' : self.generate_fluid_regatta_league_body(
                subroot, subtarget,
                regatta, league, contained, inpath_set=inpath_set )};
        if subtarget == PurePath():
            assert not contained
            protorecord = {'body' : self.generate_rigid_regatta_league_body(
                subroot, regatta, league, inpath_set=inpath_set )}
            protorecord.update(record.get('$rigid$opt', ()))
            return protorecord;
        subjectkey, subtarget = subtarget.parts[0], subtarget.parts[1:]
        if subjectkey in league['subjects']:
            if subtarget == PurePath('jury'):
                assert not contained
                return {'body' : self.generate_fluid_regatta_jury_body(
                    subroot, subjectkey,
                    regatta, league, inpath_set=inpath_set )};
            if subtarget in self.regatta_league_fluid_targets:
                assert contained
                subtarget, = subtarget.parts
                return {'body' : self.generate_fluid_regatta_subject_body(
                    subroot, subjectkey, subtarget,
                    regatta, league, inpath_set=inpath_set )};
        logger.debug('Tourn record not found: {!s}'.format(target))
        raise RecordNotFoundError(target);

    regatta_league_fluid_targets = tourn_fluid_targets

    def generate_contest_body(self, subroot, subtarget, contest,
        *, inpath_set
    ):
        yield self.constitute_section(contest['name'], select=subtarget)
        for leaguekey in contest['leagues']:
            leagueroot, leaguerecord = self.outrecords.get_item(
                pure_join(subroot, leaguekey) )
            league = leaguerecord['$contest$league']
            subprotorecord = self.produce_contest_league_protorecord(
                leagueroot/subtarget, leagueroot, PurePath(subtarget),
                {}, contest, league, contained=True,
                inpath_set=inpath_set, date_set=set() )
            yield from subprotorecord['body']

    def generate_fluid_contest_league_body(self, subroot, subtarget,
        contest, league, contained,
        *, inpath_set
    ):
        if contained:
            yield self.constitute_section(league['name'], level=1)
        else:
            yield self.constitute_section(
                contest['name'] + '. ' + league['name'], select=subtarget )
        select = {'problems' : 'problem', 'solutions' : 'solution',
            'complete' : 'both', 'jury' : 'both'} [subtarget]
        yield self.substitute_begin_problems()
        for i in range(1, 1 + league['problems']):
            inpath = subroot/(str(i)+'.tex')
            if inpath not in self.inrecords:
                raise RecordNotFoundError(inpath, subroot)
            inpath_set.add(inpath)
            yield { 'inpath' : inpath,
                'select' : select,
                'number' : str(i) }
        yield self.substitute_end_problems()

    def generate_rigid_contest_league_body(self, subroot,
        contest, league, rigid,
        *, inpath_set
    ):
        for page in rigid:
            yield self.substitute_clearpage()
            if not page: # empty page
                yield self.substitute_phantom()
                continue;
            for item in page:
                if isinstance(item, dict):
                    yield self.constitute_special(item)
                    continue;
                if item != '.':
                    raise ValueError(subroot, item)

                yield self.substitute_jeolmheader()
                yield self.constitute_section(contest['name'])
                yield self.substitute_begin_problems()
                for i in range(1, 1 + league['problems']):
                    inpath = subroot/(str(i)+'.tex')
                    if inpath not in self.inrecords:
                        raise RecordNotFoundError(inpath, subroot)
                    inpath_set.add(inpath)
                    yield { 'inpath' : inpath,
                        'select' : 'problem',
                        'number' : str(i) }
                yield self.substitute_end_problems()
                yield self.substitute_postword()

    def generate_regatta_body(self, subroot, subtarget, regatta,
        *, inpath_set
    ):
        yield self.constitute_section(regatta['name'], select=subtarget)
        for leaguekey in regatta['leagues']:
            leagueroot, leaguerecord = self.outrecords.get_item(
                pure_join(subroot, leaguekey) )
            league = leaguerecord['$regatta$league']
            subprotorecord = self.produce_regatta_league_protorecord(
                leagueroot/subtarget, leagueroot, PurePath(subtarget),
                {}, regatta, league, contained=True,
                inpath_set=inpath_set, date_set=set() )
            yield from subprotorecord['body']

    def generate_fluid_regatta_league_body(self, subroot, subtarget,
        regatta, league, contained,
        *, inpath_set
    ):
        if contained:
            yield self.constitute_section(league['name'], level=1)
        else:
            yield self.constitute_section(
                regatta['name'] + '. ' + league['name'], select=subtarget )
        for subjectkey in league['subjects']:
            subprotorecord = self.produce_regatta_league_protorecord(
                subroot/subjectkey/subtarget,
                subroot, PurePath(subjectkey, subtarget),
                {}, regatta, league, contained=True,
                inpath_set=inpath_set, date_set=set() )
            yield from subprotorecord['body']

    def generate_fluid_regatta_jury_body(self, subroot, subjectkey,
        regatta, league,
        *, inpath_set
    ):
        subject = league['subjects'][subjectkey]
        yield self.constitute_section(
            '. '.join((
                regatta['name'], league['name'],
                subject['name'] )),
            select='jury' )
        yield self.substitute_begin_problems()
        for tour in range(1, 1 + len(league['tours'])):
            inpath = subroot/subjectkey/(str(tour)+'.tex')
            if inpath not in self.inrecords:
                raise RecordNotFoundError(inpath, target)
            inpath_set.add(inpath)
            yield { 'inpath' : inpath,
                'select' : 'both',
                'number' : self.substitute_regatta_number(
                    subject_index=subject['index'], tour=tour )
            }
        yield self.substitute_end_problems()

    def generate_fluid_regatta_subject_body(self,
        subroot, subjectkey, subtarget, regatta, league,
        *, inpath_set
    ):
        subject = league['subjects'][subjectkey]
        yield self.constitute_section(subject['name'], level=2)
        select = {'problems' : 'problem', 'solutions' : 'solution',
            'complete' : 'both', 'jury' : 'both'} [subtarget]
        yield self.substitute_begin_problems()
        for tour in range(1, 1 + len(league['tours'])):
            inpath = subroot/subjectkey/(str(tour)+'.tex')
            if inpath not in self.inrecords:
                raise RecordNotFoundError(inpath, target)
            inpath_set.add(inpath)
            yield { 'inpath' : inpath,
                'select' : select,
                'number' : self.substitute_regatta_number(
                    subject_index=subject['index'], tour=tour )
            }
        yield self.substitute_end_problems()

    def generate_rigid_regatta_league_body(self, subroot, regatta, league,
        *, inpath_set
    ):
        for subjectkey, subject in league['subjects'].items():
            for tour, tourvalue in enumerate(league['tours'], 1):
                yield self.substitute_clearpage()
                yield self.substitute_jeolmheader_nospace()
                yield self.substitute_rigid_regatta_caption(
                    caption=regatta['name'], mark=tourvalue['mark'] )
                inpath = subroot/subjectkey/(str(tour)+'.tex')
                if inpath not in self.inrecords:
                    raise RecordNotFoundError(inpath, target)
                inpath_set.add(inpath)
                yield self.substitute_begin_problems()
                yield { 'inpath' : inpath,
                    'select' : 'problem',
                'number' : self.substitute_regatta_number(
                    subject_index=subject['index'], tour=tour )
                }
                yield self.substitute_end_problems()
                yield self.substitute_hrule()

    # Extension
    def produce_fluid_protorecord(self, target, record, **kwargs):
        if record is None or '$mimic' not in record:
            return super().produce_fluid_protorecord(target, record, **kwargs);
        try:
            return self.produce_mimic_protorecord(target, record, **kwargs);
        except RecordNotFoundError as error:
            if error.args != (target,):
                raise
        return super().produce_fluid_protorecord(target, record, **kwargs);

    def find_contest(self, record):
        return self.outrecords[pure_join(
            record['$mimic$root'], record['$contest$league']['contest']
        )]['$contest']

    def find_regatta(self, record):
        return self.outrecords[pure_join(
            record['$mimic$root'], record['$regatta$league']['regatta']
        )]['$regatta']

    ##########
    # Record accessors

    # Extension
    # If e.g 'a/the-contest/$contest' outrecord exists and accessor is
    # requested a path 'a/the-contest/b/c' which does not exist, than the
    # return value will contain the following keys:
    # * $contest = <mimicvalue> = <value of /a/the-contest/$contest>
    # * $mimic = "$contest"
    # * $mimic$root = a/the-contest
    # * $mimic$path = b/c
    class OutrecordAccessor(CourseDriver.OutrecordAccessor):
        mimickeys = frozenset((
            '$contest', '$contest$league', '$regatta', '$regatta$league' ))
        mimictargets = frozenset((
            'problems', 'solutions', 'complete', 'jury' ))

        def get_child(self, parent_path, parent_record, name, **kwargs):
            path, record = super().get_child(
                parent_path, parent_record, name, **kwargs )
            if record is not None:
                mimickeys = self.mimickeys & record.keys()
                if mimickeys:
                    mimickey, = mimickeys
                    record = record.copy()
                    record.update({ '$mimic' : mimickey,
                        '$mimic$root' : path, '$mimic$path' : PurePath() })
                return path, record;
            if (
                parent_record is None or
                name in parent_record or
                not (self.mimickeys & parent_record.keys())
            ):
                return path, record;

            mimickey, = self.mimickeys & parent_record.keys()
            mimicvalue = parent_record[mimickey]
            record = {}
            record[mimickey] = mimicvalue
            record['$mimic'] = mimickey
            record['$mimic$root'] = parent_record['$mimic$root']
            record['$mimic$path'] = parent_record['$mimic$path']/name
            return path, record;

        def list_targets(self, outpath=PurePath(), outrecord=None):
            if outrecord is None:
                outrecord = self.records
            yield from super().list_targets(outpath, outrecord)
            if '$contest' in outrecord:
                for key in self.mimictargets:
                    yield outpath/key
            elif '$contest$league' in outrecord:
                for key in self.mimictargets:
                    yield outpath/key
            elif '$regatta' in outrecord:
                for key in self.mimictargets:
                    yield outpath/key
            elif '$regatta$league' in outrecord:
                for key in self.mimictargets:
                    yield outpath/key
                for subject in outrecord['$regatta$league']['subjects']:
                    for key in self.mimictargets:
                        yield outpath/subject/key

    mimickeys = OutrecordAccessor.mimickeys

    ##########
    # LaTeX-level functions

    # Extension
    def constitute_input(self, inpath, alias, inrecord, figname_map, *,
        select=None, number=None
    ):
        if select is None:
            return super().constitute_input(
                inpath, alias, inrecord, figname_map );

        assert number is not None, (inpath, number)
        numeration = self.substitute_rigid_numeration(number=number)

        if select == 'problem':
            body = self.substitute_input_problem(
                filename=alias, numeration=numeration )
        elif select == 'solution':
            body = self.substitute_input_solution(
                filename=alias, numeration=numeration )
        elif select == 'both':
            body = self.substitute_input_both(
                filename=alias, numeration=numeration )
        else:
            raise AssertionError(inpath, select)

        if figname_map:
            body = self.constitute_figname_map(figname_map) + '\n' + body
        return body

    rigid_numeration_template = r'\itemy{$number}'

    input_template = r'\input{$filename}'
    input_problem_template = r'\probleminput{$numeration}{$filename}'
    input_solution_template = r'\solutioninput{$numeration}{$filename}'
    input_both_template = r'\problemsolutioninput{$numeration}{$filename}'

    @classmethod
    def constitute_section(cls, caption, *, level=0, select='problems'):
        if level == 0:
            substitute_section = cls.substitute_section
        elif level == 1:
            substitute_section = cls.substitute_subsection
        elif level == 2:
            substitute_section = cls.substitute_subsubsection
        else:
            raise AssertionError(level)
        caption += cls.caption_select_appendage[select]
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

    begin_problems_template = r'\begin{problems}'
    end_problems_template = r'\end{problems}'
    postword_template = r'\postword'

    jeolmheader_nospace_template = r'\jeolmheader*'
    rigid_regatta_caption_template = r'\regattacaption{$caption}{$mark}'
    hrule_template = r'\medskip\hrule'

    regatta_number_template = r'$tour$subject_index'

