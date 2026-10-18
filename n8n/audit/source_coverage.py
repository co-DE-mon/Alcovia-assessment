#!/usr/bin/env python3
"""Audit student KPIs against explicit source contracts. Standard library only.

Run from any directory: python3 -B n8n/audit/source_coverage.py [--check]
SQL table references are conservative query dependencies, not column lineage.
Capability assignments below are reviewed semantic mappings for selected KPI outputs.
No dashboard imports, credentials, API requests, or database writes are needed.
"""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'n8n/audit'
NORMALISE = 'n8n/code/normalise.js'
README = 'student-tracker/README.md'


def contract(status, columns, endpoints, evidence, limitation, next_step):
    return dict(status=status, required_columns=columns.split(), endpoints=endpoints,
                evidence=evidence, limitation=limitation, next_step=next_step)


# loaded = selected inputs are mapped for the one-student prototype; never a production certification.
# partial = mapped, but a known timing, completeness, or interpretation gap affects the KPI.
# missing = a required loader, field, or source contract is absent.
CONTRACTS = {
    'tasks': contract('loaded', 'todos.todo_id todos.student_id todos.due_date todos.status todos.source', ['/student/todos'], [(NORMALISE, '// to-dos'), (README, '| `todos` |')],
        'A due to-do is a timetable proxy. Student-auth scope and current-state history limits apply.', 'Retain the proxy label; validate other students and roster coverage before cohort use.'),
    'task_deadlines': contract('partial', 'todos.status todos.due_date todos.updated_at', ['/student/todos'], [(NORMALISE, '// to-dos'), (README, '| `todos` |')],
        'updatedAt is not completedAt; later edits can change apparent deadline adherence.', 'Obtain a completion timestamp or explicitly accept and label the approximation.'),
    'student_inputs': contract('partial', 'todos.source todos.created_at todos.status todos.updated_at', ['/student/todos'], [('student-tracker/sql/metrics/weekly.sql', '-- name: student_input_cadence'), (NORMALISE, '// to-dos')],
        'Creating a manual to-do or updating a done task is a proxy for filling academic inputs.', 'Confirm this proxy with Alcovia; do not equate it with the advisor checklist.'),
    'focus': contract('partial', 'focus_sessions.session_id focus_sessions.student_id focus_sessions.started_at focus_sessions.status focus_sessions.actual_minutes focus_sessions.fail_reason', ['/schedule/focus/score/today', '/schedule/focus/score/history', '/schedule/focus/pit-history (candidate)'],
        [(NORMALISE, '// focus sessions:'), ('n8n/build/build.py', 'Schedule (daily 23:55 IST)'), ('app/modules/app/m2004.js', "'/schedule/focus/pit-history'"), ('app/modules/app/m2006.js', "r1['durationSeconds']"), (README, '| Focus history |')],
        'The poll runs at 23:55 IST so /today is still the day being captured; sessions after 23:55 and a missed run are not recoverable at session level. Daily history gives per-day totals only (date, score, session count, minutes), no session ids or failure reasons. Pit history has id/type/timestamp/durationSeconds in code, but start-vs-end timestamp and ID equivalence are unverified.',
        'Confirm /today at 23:55 IST returns that day on the live service; pit-history looks like a mentor-session marker (sessionId, markedAt, sessionType), not a focus-session source, so a session-level backfill is not available.'),
    'calendar': contract('missing', 'students.calendar_connected_on students.calendar_disconnected_on', ['/google/status'],
        [('app/modules/lib/m2038.js', "'/google/status'"), ('app/modules/lib/m2039.js', "r1['isConnected']"), (NORMALISE, 'calendar_connected_on: null')],
        'No calendar status read; current upserts preserve nulls. Historical connection dates are unavailable.', 'Add status snapshots and first-observed transition rules; retention becomes measurable only after the observation window.'),
    'wearable_connection': contract('partial', 'students.wearable students.wearable_connected_on students.wearable_disconnected_on', ['/whoop/status'],
        [(NORMALISE, 'const connected = whoop.isConnected'), ('n8n/build/build.py', 'wearable_connected_on'), (README, '| `students` connection dates |')],
        'Dates are first observed; reconnect episodes are collapsed. needsReconnect/lastSyncAt do not determine this connection field.', 'Confirm retention semantics and observation window; keep connection separate from healthy syncing.'),
    'wellness': contract('missing', 'wearable_daily.student_id wearable_daily.day wearable_daily.strain wearable_daily.recovery_pct wearable_daily.sleep_hours wearable_daily.data_source', ['/wellness/history', '/wellness/daily/<date>'],
        [('app/modules/app/m2016.js', "'/wellness/history'"), ('app/modules/app/m2015.js', "r1['recoveryScore']"), ('app/modules/app/m2015.js', "r1['sleepStageLightMs']"), ('app/modules/app/m2015.js', "r1['manualSleepHours']"), ('n8n/code/wellness.js', 'function mapWellness'), (README, '| `wearable_daily` |')],
        'Daily poll has no wellness loader or populated real fixture. The separate synthetic manual demo verifies Whoop/manual separation, sleep units, nulls and KPI behavior (n8n/code/wellness.js). Only Whoop integration is evidenced.', 'Confirm populated real history/daily responses, day semantics, completeness and corrections before integrating the tested synthetic mapper; other brands still need actual integrations.'),
    'study_plan': contract('loaded', 'students.weekday_study_hours students.weekend_study_hours', ['/academics/time-budget'],
        [(NORMALISE, 'weekday_study_hours: tb'), ('n8n/tests/fixtures/time_budget.json', 'weekdayStudyHours')],
        'This measures whether both hours are set, not whether the plan is good or followed. The normalizer rounds reported hours.', 'Confirm fractional-hour handling and per-grade planning policy before treating this as a quality measure.'),
    'study_hours': contract('partial', 'study_hours.student_id study_hours.subject study_hours.quarter study_hours.as_of study_hours.estimated_hours study_hours.actual_hours', ['/academics/time-budget'],
        [(NORMALISE, '// study hours:'), ('n8n/tests/fixtures/time_budget.json', 'totalEstHours'), ('student-tracker/sql/metrics/given.sql', '-- name: time_estimation')],
        'Daily snapshots are mapped. Accuracy against elapsed-quarter pace is an assumption; reported live actual hours were zero, and free-text subject names need normalization.', 'Verify a populated actual-hours example and subject mapping; agree pace-accuracy interpretation.'),
    'syllabus': contract('loaded', 'syllabus_daily.student_id syllabus_daily.day syllabus_daily.chapters_completed syllabus_daily.total_chapters', ['/academics/my-syllabus-history'],
        [(NORMALISE, '// syllabus history'), ('n8n/tests/fixtures/syllabus_history.json', 'chaptersCompleted')],
        'The API gives running totals; denominator consistency and the configured academic-quarter pace remain assumptions.', 'Cross-check totals and zero-chapter behavior; confirm the 25%-per-quarter pace and enrollment denominator.'),
    'sessions': contract('partial', 'events.event_id events.kind events.planned_for events.status', ['/schedule/sessions'],
        [(NORMALISE, 'const SESSION_KIND'), (NORMALISE, "const status = s.cancelledAt"), ('n8n/tests/fixtures/sessions.json', 'sessionType')],
        'Only mapped kinds are loaded. A past start time is inferred held, not confirmed delivery. Student-visible records may omit cohort events. Policy targets are configured, not fetched each run.', 'Verify completion/cancellation semantics, event visibility and per-grade policy against monthly-progress/admin delivery data.'),
    'attendance': contract('partial', 'event_attendance.event_id event_attendance.student_id event_attendance.invited event_attendance.attended', ['/schedule/sessions'],
        [(NORMALISE, '// sessions:'), (README, '| `events` + `event_attendance` (sessions) |')],
        'Only the signed-in participant is loaded. Participation means invited=true; the full invitation roster and denominator are unverified.', 'Confirm participant/invitee semantics and cohort permissions; reconcile against attendance totals.'),
    'nps': contract('loaded', 'events.nps_score', ['/schedule/sessions'],
        [(NORMALISE, 'const nps ='), ('student-tracker/sql/metrics/events.sql', 'nps AS (SELECT kind, avg(nps_score)')],
        'This is the API event-level value divided by 10, not a recomputed Net Promoter Score. It does not require the feedback table.', 'Confirm the upstream meaning and label; test with feedback empty.'),
    'quiz_events': contract('missing', 'events.event_id events.kind events.planned_for events.status', ['/quizzes/scheduled', '/quizzes/my-history'],
        [('app/modules/app/m2019.js', "'/quizzes/scheduled'"), ('app/modules/lib/m2020.js', "r1['scheduledAt']"), (README, '| Quiz events and `quiz_attempts` |')],
        'Daily poll has no quiz mapping. A separate synthetic manual demo exists (n8n/code/quizzes.js); taken-only history cannot identify held-but-skipped or cancelled quizzes.', 'Define event ID/status/timestamp mapping and schedule capture; obtain a populated example before claiming real coverage.'),
    'quiz_attempts': contract('missing', 'quiz_attempts.event_id quiz_attempts.student_id quiz_attempts.started_at quiz_attempts.completed_at quiz_attempts.score quiz_attempts.total_questions', ['/quizzes/my-history', '/quizzes/scheduled'],
        [('app/modules/app/m2019.js', "'/quizzes/my-history'"), ('app/modules/lib/m2020.js', "r1['quizId']"), (README, '| Quiz events and `quiz_attempts` |')],
        'Daily poll has no attempt loader or populated real fixture. A separate synthetic manual demo verifies event linkage and incomplete/completed attempts (n8n/code/quizzes.js).', 'Confirm populated real responses, history completeness, retakes and corrections before integrating the tested synthetic mapper.'),
    'session_feedback': contract('missing', 'feedback.feedback_id feedback.student_id feedback.event_id feedback.kind feedback.composite feedback.submitted_at feedback.has_comment', ['/admin/feedback (candidate)', '/schedule/sessions/feedback/pending (pending only)'],
        [('app/modules/app/m3213.js', "'/admin/feedback'"), ('app/modules/app/m3214.js', "r1['submittedAt']"), ('n8n/code/feedback.js', 'function mapFeedback'), ('app/modules/lib/m2030.js', "'/schedule/sessions/feedback/pending'")],
        'Daily poll has no feedback loader. Separate synthetic submitted-feedback demo verifies mapping and KPIs; admin read permissions, kind coverage and populated real responses remain unverified. Pending lists are not submitted history.', 'Request authorized admin access or an export; map each feedback kind separately and retain only has_comment, not comment text.'),
    'roadmap_feedback': contract('missing', 'feedback.kind feedback.student_id feedback.q1_rating feedback.q2_rating feedback.q3_rating feedback.composite feedback.submitted_at', ['/schedule/roadmap/student-feedback (submission only)', 'Authorized submitted-feedback export/read API (unknown)'],
        [('app/modules/lib/m2030.js', "'/schedule/roadmap/student-feedback'"), ('app/modules/app/m2398.js', 'How would you rate the pace'), ('student-tracker/sql/metrics/roadmaps.sql', 'avg(q1_rating) AS avg_pace')],
        'Question meanings are evidenced: q1 pace, q2 investment, q3 confidence. The synthetic demo verifies these mappings through a proposed export, but no real submitted-roadmap read source is established.', 'Find an authorized readable record/export with stable IDs, submittedAt, kind and the three ratings; a submit endpoint is not a loader.'),
    'proposed_feedback': contract('missing', 'feedback.kind feedback.student_id feedback.event_id feedback.composite feedback.submitted_at', ['Proposed form/export; no existing source established'],
        [('student-tracker/sql/metrics/quarterly.sql', '-- name: entrepreneurship_rating'), (README, 'Social work, entrepreneurship and summer program have no form')],
        'Social work, entrepreneurship and summer-support ratings use a proposed synthetic export in the manual demo. No real collection source or feedback-sending workflow is established.', 'Agree the rating question, cadence, owner, consent/access and event linkage before implementing a collection path.'),
    'additional_events': contract('missing', 'events.event_id events.kind events.planned_for events.status', ['ClickUp List tasks (proposed)', 'Authorized admin activity records (candidate)'],
        [(NORMALISE, 'const SESSION_KIND'), (README, 'Quarterly items (podcast')],
        'The current kind map excludes peer_session, branding_shoot, podcast, competition, parent_workshop, trip, social_work, summer_support and entrepreneurship_checkin.', 'Obtain real lists/fields/statuses and stable app-student ID mappings or verify an authorized backend source; do not invent workspace IDs.'),
    'publishing': contract('missing', 'events.posted_on events.views', ['ClickUp fields or publishing analytics (unknown)'],
        [(NORMALISE, 'posted_on: null, views: null'), ('student-tracker/sql/metrics/events.sql', '-- name: posted_clips')],
        'Publication dates and views are hardcoded null. Current view counts cannot reconstruct historical reach.', 'Specify the publishing system, clip/event linkage, metrics access and snapshot policy.'),
    'groups': contract('missing', 'events.group_id event_attendance.student_id event_attendance.invited', ['ClickUp group membership (proposed)'],
        [(NORMALISE, 'group_id: null'), ('student-tracker/sql/metrics/quarterly.sql', '-- name: social_work_groups')],
        'Group IDs are hardcoded null; group counts cannot be recovered just by adding social-work events.', 'Obtain stable group IDs and membership/invitation records; verify the assumed group size.'),
    'outcomes': contract('missing', 'event_attendance.outcome', ['ClickUp application outcomes (proposed)', 'Authorized application records (unknown)'],
        [(NORMALISE, 'outcome: null'), ('student-tracker/sql/metrics/quarterly.sql', '-- name: summer_applications')],
        'Application outcomes are hardcoded null; event attendance does not establish application submission or acceptance.', 'Agree submitted/accepted states, source owner and update timestamps, linked to student and support event.'),
    'goals': contract('partial', 'roadmap_items.item_id roadmap_items.student_id roadmap_items.roadmap roadmap_items.level roadmap_items.created_at roadmap_items.due_date roadmap_items.done_at', ['/goals/annual', '/goals/quarterly'],
        [(NORMALISE, '// roadmap items = goals.'), ('n8n/tests/fixtures/quarterly_goals.json', 'monthlyGoals')],
        'Quarterly/monthly creation and completion use first-observed dates, not historical timestamps. Some due dates are null. Venture becomes entrepreneurship but may not mean the agreed startup-plan artifact.', 'Confirm categories and artifact semantics. Keep observed-vs-actual dates explicit; do not claim exact historical deadline adherence.'),
    'social_goals': contract('missing', 'roadmap_items.roadmap roadmap_items.due_date roadmap_items.done_at', ['ClickUp social-work milestones (proposed)'],
        [(NORMALISE, 'const GOAL_ROADMAP'), (README, '`social_work` has no category')],
        'No social_work category mapping exists, although the schema and KPI require it.', 'Identify the milestone source and stable student/goal IDs; agree deadline and completion fields.'),
    'chapters': contract('missing', 'chapter_progress.student_id chapter_progress.chapter_id chapter_progress.subject chapter_progress.quarter chapter_progress.planned_month chapter_progress.stage_reached chapter_progress.updated_at', ['/academics/chapters', '/academics/context', '/academics/subjects (lookup candidate)'],
        [('n8n/code/chapters.js', 'function mapChapters'), ('app/modules/app/m1996.js', "'/academics/chapters'"), ('app/modules/app/m1997.js', "r1['taskStatus']"), ('app/modules/app/m1997.js', "r1['accuracyPercentage']"), (README, '| `chapter_progress` |')],
        'Task/revision/score fields exist in static code; prior notes report populated tasks but empty scores. The checked-in ChapterSchema does not establish planned_month, stage-change timestamp, timed-paper evidence or exact five-stage semantics. Earlier notes claim task completedAt from live data, but no raw sample is checked in.',
        'Obtain sanitized chapter/task/score and planning samples; resolve subject/quarter lookups, planned month, NotRequired, threshold boundaries, contiguous stages and change timestamps. Do not use poll time as student activity.'),
    'advisor_inputs': contract('missing', 'advisor_inputs.student_id advisor_inputs.month advisor_inputs.input_kind advisor_inputs.done advisor_inputs.source', ['ClickUp advisor checklist (proposed)'],
        [('student-tracker/config.yaml', 'advisor_input_kinds:'), ('student-tracker/sql/schema/student.sql', 'CREATE TABLE IF NOT EXISTS advisor_inputs')],
        'No list, custom-field IDs, completion events or source rows have been seen. A roster of expected duties is needed to represent not-done, not just completed tasks.', 'Agree expected duty cadence and owner; map real task/custom-field IDs and student IDs; reconcile planned and completed duties.'),
    'exam_targets': contract('missing', 'exam_targets.student_id exam_targets.subject exam_targets.exam_type exam_targets.target_score exam_targets.actual_score', ['/academics/performance/subjects', 'ClickUp score targets (proposed)'],
        [('app/modules/app/m1996.js', "'/academics/performance/subjects'"), (README, '| `exam_targets` |'), ('student-tracker/sql/schema/student.sql', 'CREATE TABLE IF NOT EXISTS exam_targets')],
        'Actual-score code is term-oriented; targets and an exact formative/unit_test/mid_term mapping are unknown. The schema cannot distinguish repeated exams or years. The scorecard selects formative only.', 'Obtain targets and actuals for an identified exam/year; agree exam-type mapping, score units and schema grain before loading.'),
}


EVIDENCE_LEVELS = {
    **dict.fromkeys(('tasks', 'task_deadlines', 'student_inputs', 'focus', 'wearable_connection', 'study_plan', 'study_hours', 'syllabus', 'sessions', 'attendance', 'nps', 'goals'), 'fixture-backed mapping; previous live observations documented, not rechecked'),
    **dict.fromkeys(('wellness', 'quiz_events', 'quiz_attempts'), 'client code plus previously reported empty live responses; populated shape unverified'),
    **dict.fromkeys(('calendar', 'session_feedback', 'roadmap_feedback'), 'client code only for candidate read/submit contract; usable submitted data unverified'),
    **dict.fromkeys(('proposed_feedback', 'additional_events', 'publishing', 'groups', 'outcomes', 'social_goals', 'advisor_inputs', 'exam_targets'), 'proposed or incomplete source; actual access/field mapping unknown'),
    'chapters': 'client code plus previously reported populated tasks and empty scores; planning/stage-change fields unresolved',
}


def query_capabilities(file, query, pick):
    selector = pick
    while isinstance(selector, ast.Call) and isinstance(selector.func, ast.Name) and selector.func.id == 'one_minus':
        selector = selector.args[0]
    fields = [ast.literal_eval(x) for x in selector.args]
    filters = {x.arg: ast.literal_eval(x.value) for x in selector.keywords}
    lookup = {
        'focus_summary': ['focus'], 'quiz_regular_takers': ['quiz_events', 'quiz_attempts'],
        'wearable_summary': ['wellness'], 'whoop_syncing': ['wearable_connection', 'wellness'],
        'study_plan_set': ['study_plan'], 'time_estimation': ['study_hours'],
        'syllabus_pace': ['syllabus'], 'syllabus_progress': ['syllabus'],
        'student_input_cadence': ['student_inputs'], 'roadmap_feedback': ['roadmap_feedback'],
        'advisor_inputs_by_kind': ['advisor_inputs'], 'exam_score_vs_target': ['exam_targets'],
        'chapter_readiness': ['chapters'], 'rigour_adherence': ['chapters'],
        'rigour_closed_months': ['chapters'], 'chapter_activity': ['chapters'],
        'entrepreneurship_rating': ['proposed_feedback'], 'session_feedback': ['sessions', 'session_feedback'],
        'competition_outcomes': ['additional_events', 'attendance'],
        'summer_applications': ['additional_events', 'attendance', 'outcomes'],
    }
    if query == 'social_work_groups':
        extra = ['groups', 'attendance'] if fields == ['groups_formed_rate'] else ['attendance'] if fields == ['attended_rate'] else []
        return ['additional_events'] + extra, fields, filters
    if query in lookup:
        return lookup[query], fields, filters
    if query == 'quiz_summary':
        return ['quiz_events'] + ([] if fields == ['held_rate'] else ['quiz_attempts']), fields, filters
    if query == 'connection_retention':
        return ['calendar' if filters['kind'] == 'calendar' else 'wearable_connection'], fields, filters
    if query in ('task_metrics', 'advisor_todos', 'timetable_summary'):
        deadline = fields[0] in ('deadline_adherence', 'on_time_rate', 'done_same_day_rate')
        return ['tasks'] + (['task_deadlines'] if deadline else []), fields, filters
    if query in ('roadmap_coverage', 'roadmap_completion', 'roadmap_status'):
        return ['social_goals' if filters.get('roadmap') == 'social_work' else 'goals'], fields, filters
    if query in ('session_delivery', 'event_delivery', 'event_attendance_rates', 'event_feedback', 'posted_clips', 'clip_reach'):
        supported = filters.get('kind') in writer_event_kinds()
        caps = ['sessions'] if supported else ['additional_events']
        if query == 'event_feedback':
            if fields == ['avg_nps']:
                caps += ['nps']
            else:
                caps += ['proposed_feedback' if filters.get('kind') in ('social_work', 'summer_support') else 'session_feedback']
        if query == 'event_attendance_rates' or fields == ['attended_rate']:
            caps += ['attendance']
        if query in ('posted_clips', 'clip_reach'):
            caps += ['publishing']
        return caps, fields, filters
    raise ValueError(f'No reviewed source contract for {file}.{query}: {ast.unparse(pick)}')


def writer_event_kinds():
    text = (ROOT / NORMALISE).read_text()
    block = re.search(r'const SESSION_KIND = \{(.*?)\};', text, re.S).group(1)
    return set(re.findall(r":\s*'([^']+)'", block))


def evidence(path, needle):
    text = (ROOT / path).read_text()
    if needle not in text:
        raise ValueError(f'Missing evidence: {path}: {needle}')
    return dict(path=path, line=text[:text.index(needle)].count('\n') + 1, match=needle)


def collect():
    schema = (ROOT / 'student-tracker/sql/schema/student.sql').read_text()
    tables = {}
    for name, body in re.findall(r'CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);', schema, re.S):
        tables[name] = set(re.findall(r'^    (\w+)\s+(?:VARCHAR|INTEGER|DOUBLE|DATE|TIMESTAMP|BOOLEAN)\b', body, re.M))
    loaded = set(re.findall(r'^  (\w+): \[', (ROOT / NORMALISE).read_text(), re.M))
    assert loaded <= tables.keys(), 'Writer contains unknown tables'
    caps = {}
    for key, item in CONTRACTS.items():
        for column in item['required_columns']:
            table, field = column.split('.')
            if field not in tables.get(table, set()):
                raise ValueError(f'{key}: unknown schema field {column}')
        caps[key] = {**item, 'evidence_level': EVIDENCE_LEVELS[key], 'evidence': [evidence(*e) for e in item['evidence']]}
    queries = {}
    for path in sorted((ROOT / 'student-tracker/sql/metrics').glob('*.sql')):
        text = path.read_text()
        matches = list(re.finditer(r'^-- name: (\w+)\s*$', text, re.M))
        for i, match in enumerate(matches):
            body = text[match.end():matches[i+1].start() if i+1 < len(matches) else len(text)]
            sql = re.sub(r'--[^\n]*', '', body)
            refs = set(re.findall(r'\b(?:FROM|JOIN)\s+(\w+)', sql, re.I)) & tables.keys()
            key = f'{path.stem}.{match[1]}'
            if key in queries:
                raise ValueError(f'Duplicate query: {key}')
            queries[key] = dict(path=str(path.relative_to(ROOT)), line=text[:match.start()].count('\n')+1,
                                tables=sorted(refs), unloaded_tables=sorted(refs-loaded-{'ingest_log'}))
    code = ast.parse((ROOT / 'student-tracker/scorecard.py').read_text())
    calls = next(n.value.elts for n in code.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'KPIS' for t in n.targets))
    kpis = []
    identities = set()
    for call in calls:
        cadence, activity, lens, name, file, query = [ast.literal_eval(n) for n in call.args[:6]]
        identity = (cadence, activity, lens, name)
        assert identity not in identities, identity
        identities.add(identity)
        query_id = f'{file}.{query}'
        info = queries[query_id]
        needed, fields, filters = query_capabilities(file, query, call.args[6])
        status = max((caps[c]['status'] for c in needed), key={'loaded': 0, 'partial': 1, 'missing': 2}.get)
        kpis.append(dict(cadence=cadence, activity=activity, lens=lens, name=name, query=query_id,
                         output_fields=fields, selection_expression=ast.unparse(call.args[6]), filters=filters, scorecard_line=call.lineno,
                         required_columns=sorted({column for c in needed for column in caps[c]['required_columns']}),
                         required_unloaded_tables=sorted({column.split('.')[0] for c in needed for column in caps[c]['required_columns']} - loaded - {'ingest_log'}),
                         query_tables=info['tables'], query_unloaded_tables=info['unloaded_tables'],
                         capabilities=needed, status=status))
    return dict(scope='student-tracker only; one-student prototype; no fresh live API verification',
                definitions={'loaded': 'Selected inputs mapped for the prototype; global limits still apply.',
                             'partial': 'Mapped inputs have a known timing, completeness or interpretation gap.',
                             'missing': 'A required loader, field or source contract is absent.'},
                summary=dict(kpis=len(kpis), named_queries=len(queries), statuses=dict(Counter(k['status'] for k in kpis)),
                             query_missing_table_kpis=sum(bool(k['query_unloaded_tables']) for k in kpis),
                             selected_input_missing_table_kpis=sum(bool(k['required_unloaded_tables']) for k in kpis),
                             data_tables_loaded=sorted(loaded), tables_unloaded=sorted(tables.keys()-loaded-{'ingest_log'})),
                capabilities=caps, queries=queries, kpis=kpis)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args=parser.parse_args()
    data=collect()
    output=OUT/'source-coverage.json'
    text=json.dumps(data,indent=2,ensure_ascii=False)+'\n'
    if args.check:
        if not output.exists() or output.read_text()!=text:
            raise SystemExit('Stale coverage report: source-coverage.json')
    else:
        output.write_text(text)
    print(json.dumps(data['summary'],indent=2))


if __name__ == '__main__':
    main()
