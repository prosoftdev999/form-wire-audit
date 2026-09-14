#!/usr/bin/env python3
import hashlib
import json
import os
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote_plus, urldefrag, urljoin, urlsplit, urlunsplit

DATA = Path(os.environ.get('FORM_WIRE_DATA', '/app/data'))
OUT = Path(os.environ.get('FORM_WIRE_OUT', '/app/output/submission_requests.json'))


def load_ndjson(name):
    path = DATA / name
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


nodes = deepcopy(load_ndjson('nodes.ndjson'))
runtime = {row['id']: deepcopy(row) for row in load_ndjson('runtime.ndjson')}
face = {row['id']: deepcopy(row) for row in load_ndjson('face_state.ndjson')}
intents = load_ndjson('submit_intents.ndjson')
timeline = {row['query_id']: row['seq'] for row in load_ndjson('intent_timeline.ndjson')}
mutations = load_ndjson('mutations.ndjson')
base_url = json.loads((DATA / 'request_context.json').read_text(encoding='utf-8'))['base_url']

render_journal = load_ndjson('render_journal.ndjson') if (DATA / 'render_journal.ndjson').exists() else []
render_by_id = {row['commit_id']: row for row in render_journal}
render_heads = {row['query_id']: row['head'] for row in load_ndjson('render_heads.ndjson')} if (DATA / 'render_heads.ndjson').exists() else {}


def indexes():
    by_id = {n['id']: n for n in nodes}
    children = {}
    for n in nodes:
        children.setdefault(n.get('parent'), []).append(n['id'])
    for ids in children.values():
        ids.sort(key=lambda nid: by_id[nid]['order'])
    forms = {
        n['attrs'].get('id'): n['id']
        for n in nodes
        if n['tag'] == 'form' and n['attrs'].get('id')
    }
    return by_id, children, forms


def apply_mutation(m):
    by_id, _, _ = indexes()
    op = m['op']
    if op == 'insert_node':
        node = deepcopy(m['node'])
        if node['id'] in by_id:
            raise RuntimeError(f'duplicate inserted node {node["id"]}')
        nodes.append(node)
        return
    nid = m['id']
    if nid not in by_id:
        raise RuntimeError(f'mutation references missing node {nid}')
    if op == 'set_attr':
        attrs = by_id[nid]['attrs']
        if m['value'] is None:
            attrs.pop(m['name'], None)
        else:
            attrs[m['name']] = m['value']
    elif op == 'set_runtime':
        state = runtime.setdefault(nid, {'id': nid})
        state.update(deepcopy(m['changes']))
    elif op == 'set_parent':
        by_id[nid]['parent'] = m['parent']
    elif op == 'set_face':
        state = face.setdefault(nid, {'id': nid, 'entries': [], 'valid': True, 'message': ''})
        state.update(deepcopy(m['changes']))
    else:
        raise RuntimeError(f'unknown mutation op {op}')


def state_helpers():
    by_id, children, forms = indexes()

    def ancestors(nid):
        cur = by_id[nid].get('parent')
        seen = set()
        while cur is not None:
            if cur in seen:
                raise RuntimeError('parent cycle in capture')
            seen.add(cur)
            yield cur
            cur = by_id[cur].get('parent')

    def is_desc(nid, anc):
        return any(x == anc for x in ancestors(nid))

    def owner(nid):
        attrs = by_id[nid]['attrs']
        if 'form' in attrs:
            return forms.get(attrs.get('form'))
        for aid in ancestors(nid):
            if by_id[aid]['tag'] == 'form':
                return aid
        return None

    def first_legend(fieldset_id):
        for cid in children.get(fieldset_id, []):
            if by_id[cid]['tag'] == 'legend':
                return cid
        return None

    def disabled(nid):
        if by_id[nid]['attrs'].get('disabled') is True:
            return True
        for aid in ancestors(nid):
            a = by_id[aid]
            if a['tag'] != 'fieldset' or a['attrs'].get('disabled') is not True:
                continue
            legend = first_legend(aid)
            if legend is not None and (nid == legend or is_desc(nid, legend)):
                continue
            return True
        return False

    def option_available(oid):
        if by_id[oid]['attrs'].get('disabled') is True:
            return False
        for aid in ancestors(oid):
            a = by_id[aid]
            if a['tag'] == 'optgroup' and a['attrs'].get('disabled') is True:
                return False
            if a['tag'] == 'select':
                break
        return True

    def selected_options(select_id):
        out = []
        for n in nodes:
            if n['tag'] != 'option':
                continue
            if select_id not in tuple(ancestors(n['id'])):
                continue
            if runtime.get(n['id'], {}).get('selected') and option_available(n['id']):
                out.append(n)
        return sorted(out, key=lambda n: n['order'])

    return by_id, forms, ancestors, owner, disabled, selected_options


def normalize_crlf(value):
    return re.sub(r'\r\n|\r|\n', '\r\n', value)


def effective_submitter(form_node_id, submitter_id, by_id, owner):
    if submitter_id in by_id and owner(submitter_id) == form_node_id:
        return submitter_id
    return None


def successful_entries(form_node_id, submitter_id, intent, by_id, owner, disabled, selected_options):
    out = []
    for n in sorted(nodes, key=lambda x: x['order']):
        nid = n['id']
        attrs = n['attrs']
        tag = n['tag']
        st = runtime.get(nid, {})
        if owner(nid) != form_node_id or disabled(nid):
            continue
        name = attrs.get('name') or ''

        if tag == 'x-token':
            if name:
                for e in face[nid]['entries']:
                    if e['kind'] == 'text':
                        out.append({'name': e['name'], 'kind': 'text', 'value': str(e['value'])})
                    else:
                        out.append({
                            'name': e['name'], 'kind': 'file', 'filename': e['filename'],
                            'mime': e['mime'], 'path': e['path']
                        })
            continue

        if tag == 'select':
            if name:
                for option in selected_options(nid):
                    out.append({'name': name, 'kind': 'text', 'value': str(option['attrs'].get('value', ''))})
            continue

        if tag == 'textarea':
            if name:
                out.append({'name': name, 'kind': 'text', 'value': normalize_crlf(str(st.get('value', '')))})
                if attrs.get('dirname'):
                    out.append({'name': attrs['dirname'], 'kind': 'text', 'value': st.get('dir', 'ltr')})
            continue

        if tag not in {'input', 'button'}:
            continue
        typ = str(attrs.get('type', 'text')).lower()
        if typ in {'reset', 'button'}:
            continue
        if typ in {'submit', 'image'} and nid != submitter_id:
            continue
        if typ in {'checkbox', 'radio'} and not st.get('checked', False):
            continue
        if typ == 'image':
            x = str(intent.get('image_x', 0))
            y = str(intent.get('image_y', 0))
            if name:
                out.extend([
                    {'name': name + '.x', 'kind': 'text', 'value': x},
                    {'name': name + '.y', 'kind': 'text', 'value': y},
                ])
            else:
                out.extend([
                    {'name': 'x', 'kind': 'text', 'value': x},
                    {'name': 'y', 'kind': 'text', 'value': y},
                ])
            continue
        if not name:
            continue
        if typ == 'submit':
            out.append({'name': name, 'kind': 'text', 'value': str(attrs.get('value', st.get('value', '')))})
        else:
            out.append({'name': name, 'kind': 'text', 'value': str(st.get('value', attrs.get('value', 'on')))})
            if attrs.get('dirname') and typ in {'text', 'email'}:
                out.append({'name': attrs['dirname'], 'kind': 'text', 'value': st.get('dir', 'ltr')})
    return out


def invalid_controls(form_node_id, by_id, owner, disabled, selected_options):
    bad = []
    handled_radio_groups = set()

    def barred(nid):
        n = by_id[nid]
        attrs = n['attrs']
        if disabled(nid):
            return True
        if n['tag'] == 'button':
            return True
        if n['tag'] == 'input':
            typ = str(attrs.get('type', 'text')).lower()
            if typ in {'hidden', 'submit', 'image', 'reset', 'button'}:
                return True
            if attrs.get('readonly') is True and typ in {'text', 'email', 'number'}:
                return True
        return False

    for n in sorted(nodes, key=lambda x: x['order']):
        nid = n['id']
        attrs = n['attrs']
        tag = n['tag']
        st = runtime.get(nid, {})
        if owner(nid) != form_node_id or barred(nid):
            continue

        if tag == 'x-token':
            if not face[nid]['valid']:
                bad.append(nid)
            continue
        if tag == 'select':
            if attrs.get('required') is True:
                if not any((op['attrs'].get('value') or '') != '' for op in selected_options(nid)):
                    bad.append(nid)
            continue
        if tag == 'textarea':
            if attrs.get('required') is True and str(st.get('value', '')) == '':
                bad.append(nid)
            continue
        if tag != 'input':
            continue

        typ = str(attrs.get('type', 'text')).lower()
        if typ == 'radio':
            key = (form_node_id, attrs.get('name') or '')
            if key in handled_radio_groups:
                continue
            handled_radio_groups.add(key)
            group = [
                x for x in nodes
                if x['tag'] == 'input'
                and str(x['attrs'].get('type', 'text')).lower() == 'radio'
                and (x['attrs'].get('name') or '') == (attrs.get('name') or '')
                and owner(x['id']) == form_node_id
                and not barred(x['id'])
            ]
            required = [x for x in group if x['attrs'].get('required') is True]
            if required and not any(runtime.get(x['id'], {}).get('checked', False) for x in group):
                bad.append(min(required, key=lambda x: x['order'])['id'])
            continue
        if typ == 'checkbox':
            if attrs.get('required') is True and not st.get('checked', False):
                bad.append(nid)
            continue

        value = str(st.get('value', ''))
        invalid = attrs.get('required') is True and value == ''
        if not invalid and value and typ == 'text' and attrs.get('pattern'):
            invalid = re.fullmatch(str(attrs['pattern']), value) is None
        if not invalid and value and typ == 'email':
            if value.count('@') != 1:
                invalid = True
            else:
                local, domain = value.split('@', 1)
                invalid = not local or not domain or '.' not in domain or domain.startswith('.') or domain.endswith('.')
        if not invalid and value and typ == 'number':
            try:
                d = Decimal(value)
                if 'min' in attrs and d < Decimal(str(attrs['min'])):
                    invalid = True
                if 'max' in attrs and d > Decimal(str(attrs['max'])):
                    invalid = True
                if not invalid and 'step' in attrs:
                    base = Decimal(str(attrs.get('min', '0')))
                    step = Decimal(str(attrs['step']))
                    if step <= 0 or (d - base) % step != 0:
                        invalid = True
            except InvalidOperation:
                invalid = True
        if invalid:
            bad.append(nid)
    return bad


def text_value(entry):
    return entry['value'] if entry['kind'] == 'text' else entry['filename']


def urlencoded(entries):
    pairs = []
    for e in entries:
        name = quote_plus(e['name'], safe='*-._', encoding='utf-8', errors='strict')
        value = quote_plus(text_value(e), safe='*-._', encoding='utf-8', errors='strict')
        pairs.append(name + '=' + value)
    return '&'.join(pairs).encode('ascii')


def text_plain(entries):
    return ''.join(e['name'] + '=' + text_value(e) + '\r\n' for e in entries).encode('utf-8')


def multipart(entries, boundary):
    body = bytearray()
    b = boundary.encode('ascii')
    for e in entries:
        body += b'--' + b + b'\r\n'
        if e['kind'] == 'text':
            body += ('Content-Disposition: form-data; name="' + e['name'] + '"\r\n\r\n').encode('utf-8')
            body += e['value'].encode('utf-8') + b'\r\n'
        else:
            body += ('Content-Disposition: form-data; name="' + e['name'] + '"; filename="' + e['filename'] + '"\r\n').encode('utf-8')
            body += ('Content-Type: ' + e['mime'] + '\r\n\r\n').encode('ascii')
            body += (DATA / e['path']).read_bytes() + b'\r\n'
    body += b'--' + b + b'--\r\n'
    return bytes(body)


def effective_attr(form_node_id, submitter_id, key, submitter_key, default, by_id):
    if submitter_id is not None:
        value = by_id[submitter_id]['attrs'].get(submitter_key)
        if value not in (None, ''):
            return str(value)
    value = by_id[form_node_id]['attrs'].get(key)
    return str(value) if value not in (None, '') else default


def make_request(form_node_id, submitter_id, intent, entries, by_id):
    method = effective_attr(form_node_id, submitter_id, 'method', 'formmethod', 'get', by_id).upper()
    action = effective_attr(form_node_id, submitter_id, 'action', 'formaction', base_url, by_id)
    target = urldefrag(urljoin(base_url, action))[0]
    enctype = effective_attr(
        form_node_id, submitter_id, 'enctype', 'formenctype',
        'application/x-www-form-urlencoded', by_id
    ).lower()

    if method == 'GET':
        query = urlencoded(entries).decode('ascii')
        parts = urlsplit(target)
        merged = parts.query + ('&' if parts.query and query else '') + query
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, merged, ''))
        empty_hash = hashlib.sha256(b'').hexdigest()
        return {'method': 'GET', 'url': url, 'content_type': None, 'body_len': 0, 'body_sha256': empty_hash}

    if enctype == 'multipart/form-data':
        body = multipart(entries, intent['boundary'])
        content_type = 'multipart/form-data; boundary=' + intent['boundary']
    elif enctype == 'text/plain':
        body = text_plain(entries)
        content_type = 'text/plain'
    else:
        body = urlencoded(entries)
        content_type = 'application/x-www-form-urlencoded'
    return {
        'method': 'POST', 'url': target, 'content_type': content_type,
        'body_len': len(body), 'body_sha256': hashlib.sha256(body).hexdigest()
    }


def manifest(entries):
    out = []
    for e in entries:
        if e['kind'] == 'text':
            out.append({'name': e['name'], 'kind': 'text', 'value': e['value']})
        else:
            data = (DATA / e['path']).read_bytes()
            out.append({
                'name': e['name'], 'kind': 'file', 'filename': e['filename'], 'mime': e['mime'],
                'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()
            })
    return out


answers = []
mi = 0
base_render_state = None

def apply_render_head(head):
    chain = []
    seen = set()
    cur = head
    while cur != 'base-q060':
        if cur in seen or cur not in render_by_id:
            raise RuntimeError(f'bad render lineage at {cur}')
        seen.add(cur)
        rec = render_by_id[cur]
        chain.append(rec)
        cur = rec['parent']
    for rec in reversed(chain):
        for patch in rec['patches']:
            apply_mutation(patch)

for intent in sorted(intents, key=lambda q: timeline[q['query_id']]):
    qid = intent['query_id']
    seq = timeline[qid]
    if qid in render_heads:
        if base_render_state is None:
            raise RuntimeError('render intent encountered before q060 baseline')
        nodes, runtime, face = deepcopy(base_render_state[0]), deepcopy(base_render_state[1]), deepcopy(base_render_state[2])
        apply_render_head(render_heads[qid])
    else:
        while mi < len(mutations) and mutations[mi]['seq'] <= seq:
            apply_mutation(mutations[mi])
            mi += 1

    by_id, forms, ancestors, owner, disabled, selected_options = state_helpers()
    form_node_id = forms[intent['form_id']]
    submitter_id = effective_submitter(form_node_id, intent.get('submitter_id'), by_id, owner)
    form_no_validate = by_id[form_node_id]['attrs'].get('novalidate') is True
    submit_no_validate = submitter_id is not None and by_id[submitter_id]['attrs'].get('formnovalidate') is True
    skip_validation = form_no_validate or submit_no_validate

    invalid = [] if skip_validation else invalid_controls(form_node_id, by_id, owner, disabled, selected_options)
    entries = successful_entries(form_node_id, submitter_id, intent, by_id, owner, disabled, selected_options)
    would_submit = skip_validation or not invalid
    request = make_request(form_node_id, submitter_id, intent, entries, by_id) if would_submit else None
    answers.append({
        'query_id': intent['query_id'],
        'validation_performed': not skip_validation,
        'invalid_ids': invalid,
        'would_submit': would_submit,
        'entry_manifest': manifest(entries),
        'request': request,
    })
    if qid == 'q060':
        base_render_state = (deepcopy(nodes), deepcopy(runtime), deepcopy(face))


# Phase 3: replay captured DOM event dispatch after q096.  These records are
# chronological and intentionally stateful: listener lifetime and microtasks
# carry forward to later interaction attempts.
event_intents = load_ndjson('event_intents.ndjson') if (DATA / 'event_intents.ndjson').exists() else []
event_listener_rows = load_ndjson('event_listeners.ndjson') if (DATA / 'event_listeners.ndjson').exists() else []
event_clock_sync = load_ndjson('event_clock_sync.ndjson') if (DATA / 'event_clock_sync.ndjson').exists() else []
listener_defs = {row['listener_id']: deepcopy(row) for row in event_listener_rows}
listener_active = {row['listener_id']: bool(row.get('initially_active', True)) for row in event_listener_rows}


def recover_clock_models():
    by_source = {}
    for row in event_clock_sync:
        by_source.setdefault(row['clock_source'], []).append(row)
    models = {}
    for source, rows in by_source.items():
        rows = sorted(rows, key=lambda r: r['local_tick'])
        if len(rows) < 2:
            raise RuntimeError(f'not enough clock beacons for {source}')
        a = Fraction(rows[1]['coordinator_tick'] - rows[0]['coordinator_tick'], rows[1]['local_tick'] - rows[0]['local_tick'])
        b = Fraction(rows[0]['coordinator_tick']) - a * rows[0]['local_tick']
        for r in rows:
            if a * r['local_tick'] + b != r['coordinator_tick']:
                raise RuntimeError(f'non-affine event clock for {source}')
        models[source] = (a, b)
    return models


event_clock_models = recover_clock_models()

def event_coord(row):
    a, b = event_clock_models[row['clock_source']]
    return a * row['local_tick'] + b

listener_order = {row['listener_id']: event_coord(row) for row in event_listener_rows}
event_intents = sorted(event_intents, key=lambda row: (event_coord(row), row['query_id']))


def event_condition_true(cond, ev):
    if cond is None:
        return True
    if 'all' in cond:
        return all(event_condition_true(c, ev) for c in cond['all'])
    if 'not' in cond:
        return not event_condition_true(cond['not'], ev)
    if 'target_is' in cond:
        return ev['target_id'] == cond['target_is']
    if 'runtime_equals' in cond:
        c = cond['runtime_equals']
        return runtime.get(c['id'], {}).get(c['field']) == c.get('value')
    if 'attr_equals' in cond:
        c = cond['attr_equals']; by_id, _, _ = indexes()
        return by_id[c['id']]['attrs'].get(c['name']) == c.get('value')
    if 'face_valid' in cond:
        c = cond['face_valid']
        return bool(face.get(c['id'], {}).get('valid')) == bool(c['value'])
    if 'listener_active' in cond:
        c = cond['listener_active']
        return bool(listener_active.get(c['listener_id'], False)) == bool(c['value'])
    raise RuntimeError(f'unknown event condition {cond}')


def event_action(a, ev, microtasks):
    if not event_condition_true(a.get('when'), ev):
        return
    op = a['op']
    if op in {'set_attr', 'set_runtime', 'set_parent', 'set_face'}:
        patch = {k: deepcopy(v) for k, v in a.items() if k not in {'when'}}
        apply_mutation(patch)
        return
    if op == 'add_listener':
        if a['listener_id'] not in listener_defs:
            raise RuntimeError(f'unknown listener {a["listener_id"]}')
        listener_active[a['listener_id']] = True
        return
    if op == 'remove_listener':
        if a['listener_id'] not in listener_defs:
            raise RuntimeError(f'unknown listener {a["listener_id"]}')
        listener_active[a['listener_id']] = False
        return
    if op == 'prevent_default':
        if ev.get('cancelable', True) and not ev.get('_passive', False):
            ev['default_prevented'] = True
        return
    if op == 'stop_propagation':
        ev['propagation_stopped'] = True
        return
    if op == 'stop_immediate':
        ev['propagation_stopped'] = True
        ev['immediate_stopped'] = True
        return
    if op == 'queue_microtask':
        microtasks.append(deepcopy(a['actions']))
        return
    if op == 'dispatch':
        dispatch_event(a['target_id'], a['event_type'], microtasks)
        return
    raise RuntimeError(f'unknown event action {op}')


def listeners_for(node_id, event_type, capture):
    rows = [
        row for row in listener_defs.values()
        if row['node_id'] == node_id and row['type'] == event_type and bool(row['capture']) == bool(capture)
        and listener_active.get(row['listener_id'], False)
    ]
    return sorted(rows, key=lambda row: (listener_order[row['listener_id']], row['listener_id']))


def invoke_event_phase(node_id, event_type, capture, ev, microtasks):
    # Snapshot the matching ids for this node-phase now. A later addition does
    # not join this phase; a later removal is still honored before invocation.
    snapshot = [row['listener_id'] for row in listeners_for(node_id, event_type, capture)]
    for lid in snapshot:
        if ev.get('immediate_stopped'):
            break
        if not listener_active.get(lid, False):
            continue
        row = listener_defs[lid]
        if row.get('once'):
            listener_active[lid] = False
        ev['_passive'] = bool(row.get('passive'))
        for a in row.get('actions', []):
            event_action(a, ev, microtasks)
            if ev.get('immediate_stopped'):
                break
        ev['_passive'] = False


def dispatch_event(target_id, event_type, microtasks):
    by_id, _, _ = indexes()
    if target_id not in by_id:
        raise RuntimeError(f'event target missing: {target_id}')
    # Snapshot the propagation path before any callback can reparent a node.
    path = [target_id]
    cur = by_id[target_id].get('parent')
    seen = {target_id}
    while cur is not None:
        if cur in seen or cur not in by_id:
            raise RuntimeError('bad event path in capture')
        seen.add(cur); path.append(cur); cur = by_id[cur].get('parent')
    ev = {
        'target_id': target_id,
        'type': event_type,
        'bubbles': True,
        'cancelable': True,
        'default_prevented': False,
        'propagation_stopped': False,
        'immediate_stopped': False,
        '_passive': False,
    }
    # Capture: root to target parent.
    for nid in reversed(path[1:]):
        ev['immediate_stopped'] = False
        invoke_event_phase(nid, event_type, True, ev, microtasks)
        if ev['propagation_stopped']:
            return ev
    # Target capture and target bubble listeners both run at the target.  A
    # plain stopPropagation at target does not suppress other target listeners.
    ev['immediate_stopped'] = False
    invoke_event_phase(target_id, event_type, True, ev, microtasks)
    if not ev['immediate_stopped']:
        ev['immediate_stopped'] = False
        invoke_event_phase(target_id, event_type, False, ev, microtasks)
    # Bubble: target parent to root, unless propagation was stopped at target.
    if not ev['propagation_stopped']:
        for nid in path[1:]:
            ev['immediate_stopped'] = False
            invoke_event_phase(nid, event_type, False, ev, microtasks)
            if ev['propagation_stopped']:
                break
    return ev


def event_answer(intent, ev):
    by_id, forms, ancestors, owner, disabled, selected_options = state_helpers()
    form_node_id = forms[intent['form_id']]
    target_id = intent['target_id']
    submitter_id = None
    if target_id in by_id:
        n = by_id[target_id]
        typ = str(n['attrs'].get('type', 'text')).lower()
        if n['tag'] in {'button', 'input'} and typ in {'submit', 'image'} and owner(target_id) == form_node_id and not disabled(target_id):
            submitter_id = target_id
    entries = successful_entries(form_node_id, submitter_id, intent, by_id, owner, disabled, selected_options)
    can_activate = not ev['default_prevented'] and submitter_id is not None
    if not can_activate:
        return {
            'query_id': intent['query_id'],
            'validation_performed': False,
            'invalid_ids': [],
            'would_submit': False,
            'entry_manifest': manifest(entries),
            'request': None,
        }
    form_no_validate = by_id[form_node_id]['attrs'].get('novalidate') is True
    submit_no_validate = by_id[submitter_id]['attrs'].get('formnovalidate') is True
    skip_validation = form_no_validate or submit_no_validate
    invalid = [] if skip_validation else invalid_controls(form_node_id, by_id, owner, disabled, selected_options)
    would_submit = skip_validation or not invalid
    request = make_request(form_node_id, submitter_id, intent, entries, by_id) if would_submit else None
    return {
        'query_id': intent['query_id'],
        'validation_performed': not skip_validation,
        'invalid_ids': invalid,
        'would_submit': would_submit,
        'entry_manifest': manifest(entries),
        'request': request,
    }


for intent in event_intents:
    microtasks = []
    ev = dispatch_event(intent['target_id'], intent.get('event_type', 'click'), microtasks)
    answers.append(event_answer(intent, ev))
    # The activation checkpoint above occurs before the task's microtask
    # checkpoint. Microtask state is nevertheless persistent for later events.
    while microtasks:
        actions = microtasks.pop(0)
        micro_ev = {'target_id': intent['target_id'], 'type': 'microtask', 'cancelable': False,
                    'default_prevented': False, 'propagation_stopped': False,
                    'immediate_stopped': False, '_passive': False}
        for a in actions:
            event_action(a, micro_ev, microtasks)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({'queries': answers}, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
