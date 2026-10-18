#!/usr/bin/env python3
"""Extract chapter client evidence without API calls. --check verifies saved evidence.
The inspected fields describe the decompiled client, not guaranteed server fields.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 'app/modules/app/m1997.js'


def extract():
    text = (ROOT / SCHEMA).read_text()
    blocks = {}
    for name, lower, upper in [('task', 14, 15), ('revision', 15, 16), ('score', 16, 17), ('chapter', 20, 21)]:
        start = re.search(r'var _closure1_slot' + str(lower) + r' = .*?;', text).end()
        end = re.search(r'var _closure1_slot' + str(upper) + r' = .*?;', text).start()
        body = text[start:end]
        blocks[name] = dict(path=SCHEMA, first_line=text[:start].count('\n')+1,
                            last_line=text[:end].count('\n')+1,
                            fields=sorted(set(re.findall(r"r\d+\['([^']+)'\] =", body))))
    refs = []
    for path, needle in [
        ('app/modules/app/m1996.js', "'/academics/chapters'"),
        ('app/modules/app/m1996.js', "'/academics/context'"),
        ('app/modules/routes/academics_chapter_id_.tsx.js', "'key': 'read_textbook'"),
        ('app/modules/routes/academics_chapter_id_.tsx.js', "'key': 'revise_notes'"),
        (SCHEMA, "['NotStarted', 'HaveStarted', 'InProgress', 'SignificantlyDone', 'Done', 'NotRequired']"),
        (SCHEMA, "['Worksheet', 'Mocktest']"),
        ('app/modules/routes/academics_study-planner.tsx.js', "r10 = r8.TimeBudgetTrendChart;"),
        ('student-tracker/sql/schema/student.sql', 'CREATE TABLE IF NOT EXISTS chapter_progress'),
        ('student-tracker/sql/metrics/given.sql', '-- name: chapter_activity'),
    ]:
        content = (ROOT / path).read_text()
        if needle not in content:
            raise ValueError(f'Chapter evidence changed: {path}: {needle}')
        refs.append(dict(path=path, line=content[:content.index(needle)].count('\n')+1, match=needle))
    return dict(scope='Student tracker only; static client evidence, no fresh server observations',
                schema_sha256=hashlib.sha256(text.encode()).hexdigest(), blocks=blocks, references=refs,
                missing_in_inspected_blocks={
                    name: [field for field in ['plannedMonth', 'planned_month', 'completedAt', 'updatedAt', 'timedPastPaper'] if field not in info['fields']]
                    for name, info in blocks.items()},
                warning='Absence in these client schemas does not prove absence from the backend. Prior docs report live completedAt extras; obtain a sanitized sample to reconcile.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    output = ROOT / 'n8n/audit/chapter-evidence.json'
    content = json.dumps(extract(), indent=2) + '\n'
    if args.check:
        if not output.exists() or output.read_text() != content:
            raise SystemExit('Chapter evidence is stale; review sources and regenerate.')
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content)
    print('Chapter evidence matches inspected client sources.' if args.check else 'Wrote n8n/audit/chapter-evidence.json')


if __name__ == '__main__':
    main()
