import json
from pathlib import Path
ART=Path('/app/output/submission_requests.json'); EXP=Path('/tests/expected.json')
def load(p):
    with p.open('r',encoding='utf-8') as f:return json.load(f)
def test_submission_requests_exact():
    assert ART.exists(), 'missing /app/output/submission_requests.json'
    got=load(ART); exp=load(EXP)
    assert set(got)=={'queries'} and isinstance(got['queries'],list)
    assert len(got['queries'])==len(exp['queries'])
    ids=[r.get('query_id') for r in got['queries']]
    assert len(ids)==len(set(ids)) and set(ids)=={r['query_id'] for r in exp['queries']}
    for r in got['queries']:
        assert set(r)=={'query_id','validation_performed','invalid_ids','would_submit','entry_manifest','request'}
        assert isinstance(r['validation_performed'],bool) and isinstance(r['would_submit'],bool)
        assert isinstance(r['invalid_ids'],list) and all(isinstance(x,str) for x in r['invalid_ids'])
        assert isinstance(r['entry_manifest'],list)
        for e in r['entry_manifest']:
            assert e.get('kind') in {'text','file'} and isinstance(e.get('name'),str)
            if e['kind']=='text': assert set(e)=={'name','kind','value'} and isinstance(e['value'],str)
            else: assert set(e)=={'name','kind','filename','mime','size','sha256'} and isinstance(e['size'],int)
        if r['request'] is not None:
            q=r['request']; assert set(q)=={'method','url','content_type','body_len','body_sha256'}
            assert q['method'] in {'GET','POST'} and isinstance(q['url'],str) and isinstance(q['body_len'],int) and isinstance(q['body_sha256'],str)
    assert {r['query_id']:r for r in got['queries']}=={r['query_id']:r for r in exp['queries']}
