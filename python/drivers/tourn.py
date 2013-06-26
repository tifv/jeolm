from collections import OrderedDict as ODict

from pathlib import PurePosixPath as PurePath

from .course import CourseDriver, RecordNotFoundError
from jeolm.utils import pure_join

import logging
logger = logging.getLogger(__name__)

def produce_metarecords(targets, inrecords, outrecords):
    return TournDriver(inrecords, outrecords).produce_metarecords(targets)

def list_targets(inrecords, outrecords):
    return sorted(set(TournDriver(inrecords, outrecords).list_targets() ))

def pathset(*strings):
    return frozenset(map(PurePath, strings))

class TournDriver(CourseDriver):

    # contest DELEGATE
    #     contest/league for each league
    # contest/problems FLUID
    #     contest/league/problems for each league
    # contest/solutions FLUID
    #     contest/league/solutions for each league
    # contest/complete FLUID
    #     contest/league/complete for each league
    # contest/jury DELEGATE
    #     contest/league/jury for each league
    # contest/jury FLUID
    #     contest/league/jury for each league

    # contest/league RIGID
    # contest/league/problems FLUID
    # contest/league/solutions FLUID
    # contest/league/complete FLUID
    # contest/league/jury FLUID

    # contest/league/problem FLUID

    # regatta DELEGATE
    #     regatta/league for each league
    # regatta/problems FLUID
    #     regatta/league/problems for each league
    # regatta/solutions FLUID
    #     regatta/league/solutions for each league
    # regatta/complete FLUID
    #     regatta/league/complete for each league
    # regatta/jury DELEGATE
    #     regatta/league/jury for each league
    # regatta/jury FLUID
    #     regatta/league/jury for each league

    # regatta/league DELEGATE
    #     regatta/league/subject for each subject
    # regatta/league/problems FLUID
    #     regatta/league/tour/problems for each tour
    # regatta/league/solutions FLUID
    #     regatta/league/tour/solutions for each tour
    # regatta/league/complete FLUID
    #     regatta/league/tour/complete for each tour
    # regatta/league/jury DELEGATE
    #     regatta/league/subject/jury for each subject
    # regatta/league/jury FLUID
    #     regatta/league/tour/jury for each subject

    # regatta/league/subject RIGID
    # regatta/league/subject/problems FLUID
    # regatta/league/subject/solutions FLUID
    # regatta/league/subject/complete FLUID
    # regatta/league/subject/jury FLUID

    # regatta/league/tour DELEGATE
    #     regatta/league/tour/complete
    # regatta/league/tour/problems FLUID
    # regatta/league/tour/solutions FLUID
    # regatta/league/tour/complete FLUID

    # regatta/league/subject/problem FLUID

    ##########
    # Record-level functions

    # Extension
    def _trace_delegators(self, target, resolved_path, record,
        *, seen_targets
    ):
        if not '$mimic$key' in record:
            yield from super()._trace_delegators(target, resolved_path, record,
                seen_targets=seen_targets )
            return;

        mimickey = record['$mimic$key']
        mimicroot = record['$mimic$root']
        mimicpath = record['$mimic$path']

        if mimickey == '$contest':
            contest = record['$contest']
            if mimicpath == PurePath(''):
                for league in contest['leagues']:
                    yield from self.trace_delegators(
                        pure_join(mimicroot, league),
                        seen_targets=seen_targets )
            elif mimicpath == PurePath('jury'):
                for league in contest['leagues']:
                    yield from self.trace_delegators(
                        pure_join(mimicroot, league, 'jury'),
                        seen_targets=seen_targets )
            else:
                yield target
        elif mimickey == '$contest$league':
            yield target
        elif mimickey == '$regatta':
            regatta = record['$regatta']
            if mimicpath == PurePath(''):
                for league in regatta['leagues']:
                    yield from self.trace_delegators(
                        pure_join(mimicroot, league),
                        seen_targets=seen_targets )
            elif mimicpath == PurePath('jury'):
                for league in regatta['leagues']:
                    yield from self.trace_delegators(
                        pure_join(mimicroot, league, 'jury'),
                        seen_targets=seen_targets )
            else:
                yield target
        elif mimickey == '$regatta$league':
            league = record['$regatta$league']
            if mimicpath == PurePath(''):
                for subjectkey in league['subjects']:
                    yield from self.trace_delegators(
                        pure_join(mimicroot, subjectkey),
                        seen_targets=seen_targets )
            elif mimicpath == PurePath('jury'):
                for subjectkey in league['subjects']:
                    yield from self.trace_delegators(
                        pure_join(mimicroot, subjectkey, 'jury'),
                        seen_targets=seen_targets )
            else:
                yield target
        elif mimickey == '$regatta$subject':
            yield target
        elif mimickey == '$regatta$tour':
            tour = record['$regatta$tour']
            if mimicpath == PurePath(''):
                yield from self.trace_delegators(
                    mimicroot/'complete',
                    seen_targets=seen_targets )
            else:
                yield target
        else:
            raise AssertionError(mimickey, target)

    # Extension
    def produce_rigid_protorecord(self, target, record,
        *, inpath_set, date_set
    ):
        kwargs = dict(inpath_set=inpath_set, date_set=date_set)
        if record is None or '$mimic$key' not in record:
            return super().produce_rigid_protorecord(target, record, **kwargs)

        mimickey = record['$mimic$key']
        subroot = kwargs['subroot'] = record['$mimic$root']
        subtarget = kwargs['subtarget'] = record['$mimic$path']

        if mimickey == '$contest':
            raise RecordNotFoundError(target);
        elif mimickey == '$contest$league':
            if subtarget == PurePath(''):
                return self.produce_rigid_contest_league_protorecord(
                    target, record, rigid=record['$rigid'],
                    contest=self.find_contest(record),
                    league=self.find_contest_league(record),
                    **kwargs );
            raise RecordNotFoundError(target);
        elif mimickey == '$regatta':
            raise RecordNotFoundError(target);
        elif mimickey == '$regatta$league':
            raise RecordNotFoundError(target);
        elif mimickey == '$regatta$subject':
            if subtarget == PurePath(''):
                return self.produce_rigid_regatta_subject_protorecord(
                    target, record,
                    regatta=self.find_regatta(record),
                    league=self.find_regatta_league(record),
                    subject=self.find_regatta_subject(record),
                    **kwargs );
            raise RecordNotFoundError(target);
        elif mimickey == '$regatta$tour':
            raise RecordNotFoundError(target);
        else:
            raise AssertionError(mimickey, target)

    # Extension
    def produce_fluid_protorecord(self, target, record,
        *, inpath_set, date_set
    ):
        kwargs = dict(inpath_set=inpath_set, date_set=date_set)
        if record is None or '$mimic$key' not in record:
            return super().produce_fluid_protorecord(target, record, **kwargs)

        mimickey = record['$mimic$key']
        subroot = kwargs['subroot'] = record['$mimic$root']
        subtarget = kwargs['subtarget'] = record['$mimic$path']

        if mimickey == '$contest':
            # contest/{problems,solutions,complete,jury}
            if subtarget in self.outrecords.contest_fluid_targets:
                return self.produce_fluid_contest_protorecord(target, record,
                    contest=self.find_contest(record), **kwargs )
            raise RecordNotFoundError(target)
        elif mimickey == '$contest$league':
            # contest/league/{problems,solutions,complete,jury}
            if subtarget in self.outrecords.contest_league_fluid_targets:
                return self.produce_fluid_contest_league_protorecord(
                    target, record,
                    contest=self.find_contest(record),
                    league=self.find_contest_league(record), **kwargs )
            # contest/league/<problem number>
            elif str(subtarget).isnumeric():
                return self.produce_fluid_contest_problem_protorecord(
                    target, record,
                    contest=self.find_contest(record),
                    league=self.find_contest_league(record),
                    problem=int(str(subtarget)), **kwargs )
            raise RecordNotFoundError(target)
        elif mimickey == '$regatta':
            # regatta/{problems,solutions,complete,jury}
            if subtarget in self.outrecords.regatta_fluid_targets:
                return self.produce_fluid_regatta_protorecord(target, record,
                    regatta=self.find_regatta(record), **kwargs )
            raise RecordNotFoundError(target)
        elif mimickey == '$regatta$league':
            # regatta/league/{problems,solutions,complete,jury}
            if subtarget in self.outrecords.regatta_league_fluid_targets:
                return self.produce_fluid_regatta_league_protorecord(
                    target, record,
                    regatta=self.find_regatta(record),
                    league=self.find_regatta_league(record), **kwargs )
            raise RecordNotFoundError(target)
        elif mimickey == '$regatta$subject':
            # regatta/league/subject/{problems,solutions,complete,jury}
            if subtarget in self.outrecords.regatta_subject_fluid_targets:
                return self.produce_fluid_regatta_subject_protorecord(
                    target, record,
                    regatta=self.find_regatta(record),
                    league=self.find_regatta_league(record),
                    subject=self.find_regatta_subject(record), **kwargs )
            # regatta/league/subject/<tour number>
            elif str(subtarget).isnumeric():
                return self.produce_fluid_regatta_problem_protorecord(
                    target, record,
                    regatta=self.find_regatta(record),
                    league=self.find_regatta_league(record),
                    subject=self.find_regatta_subject(record),
                    tournum=int(str(subtarget)), **kwargs )
            raise RecordNotFoundError(target)
        elif mimickey == '$regatta$tour':
            if subtarget in self.outrecords.regatta_tour_fluid_targets:
                return self.produce_fluid_regatta_tour_protorecord(
                    target, record,
                    regatta=self.find_regatta(record),
                    league=self.find_regatta_league(record),
                    tour=self.find_regatta_tour(record), **kwargs )
            raise RecordNotFoundError(target)

    def produce_rigid_contest_league_protorecord(self,
        target, record,
        subroot, subtarget, rigid,
        contest, league,
        *, inpath_set, date_set
    ):
        body = []; append = body.append
        contest_record = self.outrecords[subroot.parent()]
        for page in rigid:
            append(self.substitute_clearpage())
            if not page: # empty page
                append(self.substitute_phantom())
                continue;
            for item in page:
                if isinstance(item, dict):
                    append(self.constitute_special(item))
                    continue;
                if item != '.':
                    raise ValueError(item, target)

                append(self.substitute_jeolmheader())
                append(self.constitute_section(contest['name']))
                append(self.substitute_begin_problems())
                for i in range(1, 1 + league['problems']):
                    inpath = subroot/(str(i)+'.tex')
                    if inpath not in self.inrecords:
                        raise RecordNotFoundError(inpath, target)
                    inpath_set.add(inpath)
                    append({ 'inpath' : inpath,
                        'select' : 'problem', 'number' : str(i) })
                append(self.substitute_end_problems())
                append(self.substitute_postword())
        protorecord = {'body' : body}
        protorecord.update(contest_record.get('$rigid$opt', ()))
        protorecord.update(record.get('$rigid$opt', ()))
        protorecord['preamble'] = preamble = list(
            protorecord.get('preamble', ()) )
        preamble.append({'league' : league['name']})
        return protorecord

    def produce_rigid_regatta_subject_protorecord(self,
        target, record,
        subroot, subtarget,
        regatta, league, subject,
        *, inpath_set, date_set
    ):
        body = []; append = body.append
        league_record = self.outrecords[subroot.parent()]
        regatta_record = self.outrecords[subroot.parent(2)]
        tourrecords = self.find_regatta_tour_records(league_record)
        for tournum, tourrecord in enumerate(tourrecords, 1):
            tour = tourrecord['$regatta$tour']
            append(self.substitute_clearpage())
            append(self.substitute_jeolmheader_nospace())
            append(self.substitute_rigid_regatta_caption(
                caption=regatta['name'], mark=tour['mark'] ))
            inpath = subroot/(str(tournum)+'.tex')
            if inpath not in self.inrecords:
                raise RecordNotFoundError(inpath, target)
            inpath_set.add(inpath)
            append(self.substitute_begin_problems())
            append({ 'inpath' : inpath,
                'select' : 'problem',
                'number' : self.substitute_regatta_number(
                    subject_index=subject['index'],
                    tour_index=tour['index'] )
            })
            append(self.substitute_end_problems())
            append(self.substitute_hrule())
        protorecord = {'body' : body}
        protorecord.update(regatta_record.get('$rigid$opt', ()))
        protorecord.update(league_record.get('$rigid$opt', ()))
        protorecord.update(record.get('$rigid$opt', ()))
        preamble = protorecord.setdefault('preamble', [])
        preamble.append({'league' : league['name']})
        return protorecord

    def produce_fluid_contest_protorecord(self,
        target, record,
        subroot, subtarget, contest,
        *, inpath_set, date_set
    ):
        body = []
        body.append(self.constitute_section(contest['name'],
            select=str(subtarget) ))
        league_records = self.find_contest_league_records(record)
        for leaguekey, leaguerecord in league_records.items():
            subprotorecord = self.produce_fluid_contest_league_protorecord(
                subroot/leaguekey/subtarget, leaguerecord,
                subroot/leaguekey, subtarget,
                contest, leaguerecord['$contest$league'],
                contained=1,
                inpath_set=inpath_set, date_set=date_set
            )
            body.extend(subprotorecord['body'])
        protorecord = {'body' : body}
        return protorecord

    def produce_fluid_contest_league_protorecord(self,
        target, record,
        subroot, subtarget,
        contest, league,
        *, contained=False, inpath_set, date_set
    ):
        body = []; append = body.append
        select = str(subtarget)
        if contained:
            append(self.constitute_section(league['name'], level=contained))
        else:
            append(self.constitute_section(
                contest['name'] + '. ' + league['name'],
                select=select ))
        append(self.substitute_begin_problems())
        for i in range(1, 1 + league['problems']):
            inpath = subroot/(str(i)+'.tex')
            if inpath not in self.inrecords:
                raise RecordNotFoundError(inpath, subroot)
            inpath_set.add(inpath)
            append({ 'inpath' : inpath,
                'select' : select, 'number' : str(i) })
        append(self.substitute_end_problems())
        protorecord = {'body' : body}
        return protorecord

    def produce_fluid_contest_problem_protorecord(self,
        target, record,
        subroot, subtarget,
        contest, league, problem,
        *, inpath_set, date_set
    ):
        body = []; append = body.append
        if not 1 <= problem <= league['problems']:
            return super().produce_fluid_protorecord(target, record,
                inpath_set=inpath_set, date_set=date_set )
        inpath = subroot/(str(problem)+'.tex')
        if inpath not in self.inrecords:
            raise RecordNotFoundError(inpath, subroot)
        inpath_set.add(inpath)
        append(self.substitute_begin_problems())
        append({ 'inpath' : inpath,
            'select' : 'complete', 'number' : str(problem) })
        append(self.substitute_end_problems())
        protorecord = {'body' : body}
        return protorecord

    def produce_fluid_regatta_protorecord(self,
        target, record,
        subroot, subtarget, regatta,
        *, inpath_set, date_set
    ):
        body = []
        body.append(self.constitute_section(regatta['name'],
            select=str(subtarget) ))
        league_records = self.find_regatta_league_records(record)
        for leaguekey, leaguerecord in league_records.items():
            subprotorecord = self.produce_fluid_regatta_league_protorecord(
                subroot/leaguekey/subtarget, leaguerecord,
                subroot/leaguekey, subtarget,
                regatta, leaguerecord['$regatta$league'],
                contained=1,
                inpath_set=inpath_set, date_set=date_set
            )
            body.extend(subprotorecord['body'])
        protorecord = {'body' : body}
        return protorecord

    def produce_fluid_regatta_league_protorecord(self,
        target, record,
        subroot, subtarget,
        regatta, league,
        *, contained=False, inpath_set, date_set
    ):
        body = []; append = body.append
        if contained:
            append(self.constitute_section(league['name'], level=contained))
        else:
            append(self.constitute_section(
                regatta['name'] + '. ' + league['name'],
                select=str(subtarget) ))
        tour_records = self.find_regatta_tour_records(record)
        for tournum, tourrecord in enumerate(tour_records, 1):
            subprotorecord = self.produce_fluid_regatta_tour_protorecord(
                subroot/str(tournum)/subtarget, tourrecord,
                subroot/str(tournum), subtarget,
                regatta, league, tourrecord['$regatta$tour'],
                contained=contained+1,
                inpath_set=inpath_set, date_set=date_set
            )
            body.extend(subprotorecord['body'])
        protorecord = {'body' : body}
        return protorecord

    def produce_fluid_regatta_subject_protorecord(self,
        target, record,
        subroot, subtarget,
        regatta, league, subject,
        *, contained=False, inpath_set, date_set
    ):
        body = []; append = body.append
        select = str(subtarget)
        if contained:
            append(self.constitute_section(subject['name'], level=contained))
        else:
            append(self.constitute_section(
                '{}. {}. {}'.format(
                    regatta['name'], league['name'], subject['name'] ),
                select=select ))
        tour_records = self.find_regatta_tour_records(record)
        append(self.substitute_begin_problems())
        for tournum, tourrecord in enumerate(tour_records, 1):
            inpath = subroot/(str(tournum)+'.tex')
            if inpath not in self.inrecords:
                raise RecordNotFoundError(inpath, subroot)
            inpath_set.add(inpath)
            append({ 'inpath' : inpath,
                'select' : select,
                'number' : self.substitute_regatta_number(
                    subject_index=subject['index'],
                    tour_index=tourrecord['$regatta$tour']['index'] )
            })
        append(self.substitute_end_problems())
        protorecord = {'body' : body}
        return protorecord

    def produce_fluid_regatta_tour_protorecord(self,
        target, record,
        subroot, subtarget,
        regatta, league, tour,
        *, contained=False, inpath_set, date_set
    ):
        body = []; append = body.append
        select = str(subtarget)
        if contained:
            append(self.constitute_section(tour['name'], level=contained))
        else:
            append(self.constitute_section(
                '{}. {}. {}'.format(
                    regatta['name'], league['name'], tour['name'] ),
                select=str(subtarget) ))
        subject_records = self.find_regatta_subject_records(record)
        leagueroot = subroot.parent()
        tournum = int(subroot.name)
        append(self.substitute_begin_problems())
        for subjectkey, subjectrecord in subject_records.items():
            inpath = leagueroot/subjectkey/(str(tournum)+'.tex')
            if inpath not in self.inrecords:
                raise RecordNotFoundError(inpath, subroot)
            inpath_set.add(inpath)
            append({ 'inpath' : inpath,
                'select' : select,
                'number' : self.substitute_regatta_number(
                    subject_index=subjectrecord['$regatta$subject']['index'],
                    tour_index=tour['index'] )
            })
        append(self.substitute_end_problems())
        protorecord = {'body' : body}
        return protorecord

    def produce_fluid_regatta_problem_protorecord(self,
        target, record,
        subroot, subtarget,
        regatta, league, subject, tournum,
        *, inpath_set, date_set
    ):
        body = []; append = body.append
        if not 1 <= tournum <= league['tours']:
            return super().produce_fluid_protorecord(target, record,
                inpath_set=inpath_set, date_set=date_set )
        tourrecord = self.find_regatta_tour_records(record)[tournum-1]
        tour = tourrecord['$regatta$tour']
        inpath = subroot/(str(tournum)+'.tex')
        if inpath not in self.inrecords:
            raise RecordNotFoundError(inpath, subroot)
        inpath_set.add(inpath)
        append(self.substitute_begin_problems())
        append({ 'inpath' : inpath,
            'select' : 'complete',
            'number' : self.substitute_regatta_number(
                subject_index=subject['index'],
                tour_index=tour['index'] )
        })
        append(self.substitute_end_problems())
        protorecord = {'body' : body}
        return protorecord

    def find_contest(self, record):
        mimickey = record['$mimic$key']
        if mimickey == '$contest':
            return record['$contest']
        elif mimickey == '$contest$league':
            league = record['$contest$league']
            return self.find_contest(self.outrecords[
                record['$mimic$root'].parent() ])
        else:
            raise AssertionError(mimickey, record)

    def find_contest_league(self, record):
        mimickey = record['$mimic$key']
        if mimickey == '$contest$league':
            return record['$contest$league']
        else:
            raise AssertionError(mimickey, record)

    def find_contest_league_records(self, record):
        mimickey = record['$mimic$key']
        if mimickey == '$contest':
            return ODict(
                (leaguekey, self.outrecords[record['$mimic$root']/leaguekey])
                for leaguekey in record['$contest']['leagues'] )
        else:
            raise AssertionError(mimickey, record)

    def find_regatta(self, record):
        mimickey = record['$mimic$key']
        if mimickey == '$regatta':
            return record['$regatta']
        elif mimickey == '$regatta$league':
            league = record['$regatta$league']
            return self.find_regatta(self.outrecords[
                record['$mimic$root'].parent() ])
        elif mimickey == '$regatta$subject':
            subject = record['$regatta$subject']
            return self.find_regatta(self.outrecords[
                record['$mimic$root'].parent(2) ])
        elif mimickey == '$regatta$tour':
            tour = record['$regatta$tour']
            return self.find_regatta(self.outrecords[
                record['$mimic$root'].parent(2) ])
        else:
            raise AssertionError(mimickey, record)

    def find_regatta_league(self, record):
        mimickey = record['$mimic$key']
        if mimickey == '$regatta$league':
            return record['$regatta$league']
        elif mimickey == '$regatta$subject':
            subject = record['$regatta$subject']
            return self.find_regatta_league(self.outrecords[
                record['$mimic$root'].parent() ])
        elif mimickey == '$regatta$tour':
            tour = record['$regatta$tour']
            return self.find_regatta_league(self.outrecords[
                record['$mimic$root'].parent() ])
        else:
            raise AssertionError(mimickey, record)

    def find_regatta_league_records(self, record):
        mimickey = record['$mimic$key']
        if mimickey == '$regatta':
            return ODict(
                (leaguekey, self.outrecords[record['$mimic$root']/leaguekey])
                for leaguekey in record['$regatta']['leagues'] )
        else:
            raise AssertionError(mimickey, record)

    def find_regatta_subject(self, record):
        mimickey = record['$mimic$key']
        if mimickey == '$regatta$subject':
            return record['$regatta$subject']
        else:
            raise AssertionError(mimickey, record)

    def find_regatta_subject_records(self, record):
        mimickey = record['$mimic$key']
        if mimickey == '$regatta$league':
            return ODict(
                (subjectkey, self.outrecords[record['$mimic$root']/subjectkey])
                for subjectkey in record['$regatta$league']['subjects'] )
        elif mimickey == '$regatta$tour':
            return self.find_regatta_subject_records(self.outrecords[
                record['$mimic$root'].parent() ])
        else:
            raise AssertionError(mimickey, record)

    def find_regatta_tour(self, record):
        mimickey = record['$mimic$key']
        if mimickey == '$regatta$tour':
            return record['$regatta$tour']
        else:
            raise AssertionError(mimickey, record)

    def find_regatta_tour_records(self, record):
        assert '$mimic$key' in record, record
        mimickey = record['$mimic$key']
        if mimickey == '$regatta$league':
            return [
                self.outrecords[record['$mimic$root']/str(tournum)]
                for tournum
                in range(1, 1 + record['$regatta$league']['tours'])
            ]
        elif mimickey == '$regatta$subject':
            return self.find_regatta_tour_records(self.outrecords[
                record['$mimic$root'].parent() ])
        else:
            raise AssertionError(mimickey, record)

    ##########
    # Record accessors

    # Extension
    # If e.g 'a/the-contest/$contest' outrecord exists and accessor is
    # requested a path 'a/the-contest/b/c' which does not exist, than the
    # return value will contain the following keys:
    # * $contest = <mimicvalue> = <value of /a/the-contest/$contest>
    # * $mimic$key = "$contest"
    # * $mimic$root = a/the-contest
    # * $mimic$path = b/c
    class OutrecordAccessor(CourseDriver.OutrecordAccessor):
        mimickeys = frozenset((
            '$contest', '$contest$league',
            '$regatta', '$regatta$league',
            '$regatta$subject', '$regatta$tour', ))

        # Extension
        def get_child(self, parent_path, parent_record, name, **kwargs):
            path, record = super().get_child(
                parent_path, parent_record, name, **kwargs )
            if record is not None:
                mimickeys = self.mimickeys & record.keys()
                if mimickeys:
                    mimickey, = mimickeys
                    record = record.copy()
                    record.update({
                        '$mimic$key' : mimickey,
                        '$mimic$root' : path,
                        '$mimic$path' : PurePath() })
                return path, record;
            if not (
                parent_record is not None and
                name not in parent_record and
                '$mimic$key' in parent_record
            ):
                return path, record;

            mimickey = parent_record['$mimic$key']
            record = {
                mimickey : parent_record[mimickey],
                '$mimic$key' : mimickey,
                '$mimic$root' : parent_record['$mimic$root'],
                '$mimic$path' : parent_record['$mimic$path']/name,
            }
            return path, record;

        contest_fluid_targets = \
        contest_league_fluid_targets = \
        regatta_fluid_targets = \
        regatta_league_fluid_targets = \
        regatta_subject_fluid_targets = \
            pathset('problems', 'solutions', 'complete', 'jury' )
        regatta_tour_fluid_targets = \
            pathset('problems', 'solutions', 'complete')

        def list_targets(self, outpath=PurePath(), outrecord=None):
            if outrecord is None:
                outrecord = self.records
            yield from super().list_targets(outpath, outrecord)
            if '$contest' in outrecord:
                for key in self.contest_fluid_targets:
                    yield outpath/key
            elif '$contest$league' in outrecord:
                for key in self.contest_league_fluid_targets:
                    yield outpath/key
            elif '$regatta' in outrecord:
                for key in self.regatta_fluid_targets:
                    yield outpath/key
            elif '$regatta$league' in outrecord:
                for key in self.regatta_league_fluid_targets:
                    yield outpath/key
            elif '$regatta$subject' in outrecord:
                for key in self.regatta_subject_fluid_targets:
                    yield outpath/key
            elif '$regatta$tour' in outrecord:
                for key in self.regatta_tour_fluid_targets:
                    yield outpath/key

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

        if select in {'problem', 'problems'}:
            body = self.substitute_input_problem(
                filename=alias, numeration=numeration )
        elif select in {'solution', 'solutions'}:
            body = self.substitute_input_solution(
                filename=alias, numeration=numeration )
        elif select in {'both', 'complete', 'jury'}:
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

    @classmethod
    def constitute_preamble_line(cls, metaline):
        if 'league' in metaline:
            return cls.substitute_leaguedef(league=metaline['league'])
        elif 'postword' in metaline:
            return cls.substitute_postworddef(postword=metaline['postword'])
        else:
            return super().constitute_preamble_line(metaline)

    leaguedef_template = r'\def\jeolmheaderleague{$league}'
    postworddef_template = r'\def\postword{\jeolmpostword$postword}'

    begin_problems_template = r'\begin{problems}'
    end_problems_template = r'\end{problems}'
    postword_template = r'\postword'

    jeolmheader_nospace_template = r'\jeolmheader*'
    rigid_regatta_caption_template = r'\regattacaption{$caption}{$mark}'
    hrule_template = r'\medskip\hrule'

    regatta_number_template = r'$tour_index$subject_index'

