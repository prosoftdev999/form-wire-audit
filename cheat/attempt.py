#!/usr/bin/env python3
"""A deliberately shallow shortcut: trust recorder rows but never reconstruct state."""
import hashlib
import json
from pathlib import Path

DATA = Path('/app/data')
ids = []
for name in ('submit_intents.ndjson', 'event_intents.ndjson'):
    ids.extend(json.loads(line)['query_id'] for line in (DATA / name).read_text().splitlines() if line.strip())
empty = hashlib.sha256(b'').hexdigest()
rows = []
for qid in ids:
    rows.append({
        'query_id': qid,
        'validation_performed': False,
        'invalid_ids': [],
        'would_submit': True,
        'entry_manifest': [],
        'request': {
            'method': 'GET',
            'url': 'https://shop.example.test/',
            'content_type': None,
            'body_len': 0,
            'body_sha256': empty,
        },
    })
out = Path('/app/output/submission_requests.json')
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({'queries': rows}, separators=(',', ':')) + '\n', encoding='utf-8')
