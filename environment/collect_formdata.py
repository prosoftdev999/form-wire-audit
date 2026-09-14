#!/usr/bin/env python3
"""Quick capture inspector from the checkout incident.

This was written to list obvious direct controls and form defaults. It does not
implement ownership, validation, entry construction, submitter overrides, or
wire serialization.
"""
import json
from pathlib import Path
D=Path('/app/data')
def read(name): return [json.loads(x) for x in (D/name).read_text().splitlines() if x.strip()]
nodes=read('nodes.ndjson'); state={r['id']:r for r in read('runtime.ndjson')}
for n in nodes:
    if n['tag']=='form': print('FORM',n['id'],n['attrs'].get('method'),n['attrs'].get('action'),n['attrs'].get('enctype'))
    elif n['tag']=='input' and n['attrs'].get('name'): print('INPUT',n['id'],n['attrs']['name'],state.get(n['id'],{}).get('value',''))
