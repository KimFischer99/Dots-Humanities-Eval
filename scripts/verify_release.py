#!/usr/bin/env python3
"""Offline release verifier. No API calls, Docker use, credential reads, or deletions.
Core mechanical contract matches the pinned repository's eval.py. On a full
checkout its actual eval.grade is also used. Historical and release manifests
are kept separate. Run --check-sft-only or --self-test in the delivery overlay.
"""
from __future__ import annotations
import argparse, base64, collections, copy, gzip, hashlib, importlib.util
import json, re, statistics, sys, unicodedata
from pathlib import Path

COMMIT='bf33da8d35715602c7daab0aed53ba2c4733d698'
BASELINE_MANIFEST_BLOB='293b61c9f39500d9d3bad41cfaa6310204bc79dd'
SKILL_BODY_SHA='5a13239d24658b34c330f4d94ef885977e799436eedad86ec29db3a985376713'
LEGACY_SOURCE_FILENAME='\u4eba\u6587\u8bad\u7ec3\u5e08\u7b14\u8bd5\u9898.pdf'
ROOT=Path(__file__).resolve().parents[1]

def require(ok, message):
    if not ok: raise ValueError(message)
def sha(x): return hashlib.sha256(x.encode('utf-8') if isinstance(x,str) else x).hexdigest()
def canonical(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def readj(p): return json.loads(p.read_text(encoding='utf-8'))
def rows(p):
    with p.open(encoding='utf-8') as f:
        for line in f:
            if line.strip():yield strict_json(line)
def strict_json(s):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('Duplicate JSON key: '+k)
            d[k]=v
        return d
    def bad(v):raise ValueError('Non-finite JSON: '+v)
    return json.loads(s,object_pairs_hook=pairs,parse_constant=bad)
def keys(d,req,opt=()):return isinstance(d,dict) and set(req)<=set(d)<=set(req)|set(opt)
def text(s):return isinstance(s,str) and bool(s.strip())
def strings(v):
    if isinstance(v,str):yield v
    elif isinstance(v,list):
        for a in v:yield from strings(a)
    elif isinstance(v,dict):
        for k,a in v.items():yield k;yield from strings(a)
def count(s):return len(re.sub(r'\s','',unicodedata.normalize('NFC',s)))
def schema_ok(d):
    if not keys(d,['source_id','cast','locations','scenes']) or not text(d['source_id']):return False
    if not isinstance(d['scenes'],list) or not d['scenes']:return False
    for k in ['cast','locations']:
        if not isinstance(d[k],list) or (k=='locations' and not d[k]):return False
        for item in d[k]:
            if not keys(item,['id','name']) or not all(text(item[x]) for x in ['id','name']):return False
    if any(unicodedata.category(c) in ('Cf','Cs') for s in strings(d) for c in s):return False
    for sc in d['scenes']:
        if not keys(sc,['sceneId','characters','flow']) or not text(sc['sceneId']):return False
        if not isinstance(sc['characters'],list) or not all(text(x) for x in sc['characters']):return False
        if not isinstance(sc['flow'],list) or not sc['flow']:return False
        has_action=False
        for b in sc['flow']:
            if keys(b,['action']) and text(b['action']):has_action=True
            elif keys(b,['speaker','line','mode'],['delivery']) and all(text(b[x]) for x in ['speaker','line','mode']) and b['mode'] in ('spoken','inner') and ('delivery' not in b or isinstance(b['delivery'],str)):pass
            else:return False
        if not has_action:return False
    return True

def grade(raw, conditions):
    try:
        d=strict_json(raw)
        if not schema_ok(d):raise ValueError('schema')
    except (ValueError,TypeError,KeyError):return {'H':0,'hard_pass':False,'H1':False,'H2':None,'H3':None,'H4':None,'H5':None,'estimated_seconds':None}
    ids={a['id'] for a in d['cast']};locs={a['id'] for a in d['locations']}
    ref=d['source_id']=='TEXT' and len(ids)==len(d['cast']) and len(locs)==len(d['locations'])
    lengths=[];acts=inner=0
    for sc in d['scenes']:
        ref &= sc['sceneId'] in locs and set(sc['characters'])<=ids and len(set(sc['characters']))==len(sc['characters'])
        for b in sc['flow']:
            if 'action' in b:acts+=1
            else:
                ref &= b['speaker'] in sc['characters'];lengths.append(count(b['line']));inner+=b['mode']=='inner'
    seconds=sum(lengths)/4.5+acts*2.5;t=conditions['target_seconds']
    flags=[True,bool(ref),all(n<=35 for n in lengths),t*.85-1e-9<=seconds<=t*1.15+1e-9,inner<=(2 if conditions['interior_policy']=='allow_limited' else 0)]
    return {'H':4*sum(flags),'hard_pass':all(flags),**dict(zip(['H1','H2','H3','H4','H5'],flags)),'estimated_seconds':round(seconds,6),'line_characters':sum(lengths),'line_lengths':lengths,'maximum_line_characters':max(lengths,default=0),'action_beats':acts}

def pointer(d,p):
    for part in p.strip('/').split('/'):
        part=part.replace('~1','/').replace('~0','~');d=d[int(part)] if isinstance(d,list) else d[part]
    return d

def check_sft(root, evaluator=None):
    samples=list(rows(root/'sft/sft.jsonl'));require(len(samples)==2,'Expected exactly two SFT examples')
    out={}
    for s in samples:
        require(type(s.get('human_approved')) is bool,'Missing factual approval flag')
        body,separator,tail=s['input']['system'].rpartition('\n\n## 本次实验条件\n')
        require(bool(separator) and sha(body)==SKILL_BODY_SHA,'SFT skill body differs from frozen body')
        conditions=strict_json(tail);raw=json.dumps(s['target'],ensure_ascii=False)
        result=grade(raw,conditions);require(result['hard_pass'],'SFT hard rule failed: '+s['case_id'])
        declared=s['acceptance']['mechanical_result']
        for k in ['H','hard_pass','line_characters','action_beats','estimated_seconds']:
            require(declared[k]==result[k],'Stale declared SFT metric '+k)
        for step in s['task_trajectory']['steps']:
            require(step['source_quote'] in s['input']['user'],'SFT source quote does not match')
            for pt in step['output_pointers']:pointer(s['target'],pt)
        if evaluator:
            task={'source_id':'TEXT','source_text':s['input']['user'],**conditions}
            require(evaluator.generation_system(task)==s['input']['system'],'Original evaluator: SFT system differs')
            upstream=evaluator.grade(raw,task)
            for k in ['H','hard_pass','estimated_seconds','line_characters','action_beats']:
                require(result[k]==upstream[k],'Original evaluator mismatch: '+k)
        result['target_sha256']=sha(canonical(s['target']));result['input_sha256']=sha(canonical(s['input']))
        out[s['case_id']]=result
    return samples,out

def self_test(root):
    samples,_=check_sft(root);n=0
    cond={'target_seconds':35,'interior_policy':'forbid'}
    base=copy.deepcopy(samples[0]['target'])
    def test(obj,passed):
        nonlocal n
        raw=obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False)
        require(grade(raw,cond)['hard_pass']==passed,'Self-test failed at '+str(n+1));n+=1
    for s in samples:test(s['target'],True)
    test('```json\n'+json.dumps(base)+'\n```',False)
    test('{"source_id":"TEXT","source_id":"OTHER"}',False)
    test('NaN',False);test('{}',False);test('[]',False)
    for field in ['source_id','cast','locations','scenes']:
        b=copy.deepcopy(base);del b[field];test(b,False)
    b=copy.deepcopy(base);b['extra']=1;test(b,False)
    b=copy.deepcopy(base);b['scenes']=[];test(b,False)
    b=copy.deepcopy(base);b['locations']=[];test(b,False)
    b=copy.deepcopy(base);b['source_id']='OTHER';test(b,False)
    b=copy.deepcopy(base);b['cast'][1]['id']='P01';test(b,False)
    b=copy.deepcopy(base);b['scenes'][0]['characters']=['P01','P01'];test(b,False)
    b=copy.deepcopy(base);b['scenes'][0]['sceneId']='OTHER';test(b,False)
    j=next(i for i,x in enumerate(base['scenes'][0]['flow']) if 'line' in x)
    for key,val in [('speaker','UNKNOWN'),('line','x'*36),('mode','inner'),('mode','wrong'),('delivery',3)]:
        b=copy.deepcopy(base);b['scenes'][0]['flow'][j][key]=val;test(b,False)
    b=copy.deepcopy(base);b['cast'][0]['name']='a\u200bb';test(b,False)
    b=copy.deepcopy(base);b['scenes'][0]['flow']=[{'action':'one'}];test(b,False)
    b=copy.deepcopy(base);b['scenes'][0]['flow']*=5;test(b,False)
    # A deliberately wrong attribution can pass mechanics: do not claim semantic validation.
    b=copy.deepcopy(base);b['scenes'][0]['flow'][j]['speaker']='P01';test(b,True)
    b=copy.deepcopy(base);b['scenes'][0]['flow'][0]['action']='He says a hidden sentence.';test(b,True)
    require(count('a b\n')==2,'Whitespace counting');n+=1
    require(count('e\u0301')==1,'NFC counting');n+=1
    return {'status':'passed','fixture_assertions':n,'scope':'Mechanical and projection tests only; not the repository historical 84 tests.'}

def load_evaluator(root):
    require((root/'eval.py').is_file(),'Full repository missing eval.py. Overlay alone: use --check-sft-only.')
    spec=importlib.util.spec_from_file_location('release_eval',root/'eval.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def file_sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def aggregate(records):
    known=[r for r in records if r['usage_available']]
    return {'api_calls':len(records),'usage_available_calls':len(known),'usage_missing_calls':len(records)-len(known),
            **{k:sum(r['usage'].get(k,0) for r in known) for k in ('prompt_tokens','completion_tokens','total_tokens')},
            'reasoning_tokens_known_sum':sum(r['reasoning_tokens'] for r in records if r['reasoning_tokens'] is not None),
            'reasoning_tokens_known_calls':sum(r['reasoning_tokens'] is not None for r in records),
            'cached_tokens_known_sum':sum(r['cached_tokens'] for r in records if r['cached_tokens'] is not None),
            'cached_tokens_known_calls':sum(r['cached_tokens'] is not None for r in records)}

def expected_public_files(root):
    doc=(root/'REPOSITORY_FILES.md').read_text(encoding='utf-8')
    match=re.search(r'```(?:text)?\s*\n(.*?)\n```',doc,re.S)
    require(match is not None,'REPOSITORY_FILES.md is missing its final-tree block')
    stack=[];result=set();found_root=False
    for line in match.group(1).splitlines():
        m=re.match(r'^( *)(\S+)',line)
        if not m:continue
        indent=len(m.group(1));token=m.group(2)
        if not found_root:
            found_root=True
            continue
        level=indent//2
        while len(stack)>=level:stack.pop()
        if token.endswith('/'):
            stack.append(token[:-1]);continue
        result.add(Path(*stack,token).as_posix())
    require(found_root,'REPOSITORY_FILES.md tree is empty')
    result.add('Real_Trace_Example.md')
    result.discard('manifest.json')
    require('REPOSITORY_FILES.md' in result and 'scripts/verify_release.py' in result,'Final tree must list the verifier and inventory')
    require('analysis.json' in result and 'index.html' in result and 'sft/checks.json' in result,'Final tree is missing required analysis/SFT artifacts')
    return result

def ignored_release_path(rel):
    return any(part=='.git' or part.startswith('.work') or part=='__pycache__' for part in rel.parts) or rel.suffix=='.pyc'

def public_tree_files(root):
    found=set()
    for p in root.rglob('*'):
        rel=p.relative_to(root)
        if ignored_release_path(rel):continue
        require(not p.is_symlink(),'Release tree contains symlink: '+rel.as_posix())
        if p.is_dir():continue
        require(p.name!='.DS_Store','Release tree contains .DS_Store')
        require(p.name!='.env','Release tree contains .env')
        require(p.is_file(),'Release tree contains unsupported filesystem entry: '+rel.as_posix())
        if rel.as_posix()=='manifest.json':continue
        found.add(rel.as_posix())
    return found

def check_public_tree(root):
    expected=expected_public_files(root);actual=public_tree_files(root)
    extra=sorted(actual-expected);missing=sorted(expected-actual)
    require(not extra,'Unexpected release files: '+', '.join(extra[:12]))
    require(not missing,'Missing release files: '+', '.join(missing[:12]))
    return expected

def verify_release_manifest(root):
    expected=check_public_tree(root)
    manifest=readj(root/'manifest.json')
    require(manifest.get('kind')=='release_manifest' and manifest.get('self_excluded') is True,'manifest.json is not a release manifest')
    require(manifest.get('historical_manifest')=='frozen/publication_manifest.json','Release manifest lost historical manifest pointer')
    entries=manifest.get('files');require(isinstance(entries,list),'Release manifest files is not a list')
    paths=[x.get('path') for x in entries if isinstance(x,dict)]
    require(len(paths)==len(entries) and len(set(paths))==len(paths),'Release manifest contains malformed/duplicate paths')
    require(set(paths)==expected,'Release manifest path set differs from REPOSITORY_FILES.md')
    for item in entries:
        rel=item['path'];p=root/rel
        require(p.is_file() and not p.is_symlink(),'Release manifest file missing or unsafe: '+rel)
        require(p.stat().st_size==item.get('bytes') and file_sha(p)==item.get('sha256'),'Release manifest hash/size mismatch: '+rel)
    return len(entries)

def verify_analysis(root,saved_scores,hard,gens,selected,sft_results,samples):
    analysis=readj(root/'analysis.json')
    index=(root/'index.html').read_text(encoding='utf-8')
    scripts=re.findall(r'<script\b([^>]*)>(.*?)</script\s*>',index,re.I|re.S)
    embedded=[]
    for attrs,body in scripts:
        if re.search(r'\btype\s*=\s*["\']application/json["\']',attrs,re.I):
            embedded.append(strict_json(body.strip()))
    require(len(embedded)==1 and embedded[0]==analysis,'index.html embedded analysis differs from analysis.json')
    rows_=analysis.get('rows');require(isinstance(rows_,list) and len(rows_)==15,'analysis.json must contain 15 scored rows')
    scoremap={r['run_id']:r for r in saved_scores['results']}
    require(len({r.get('run_id') for r in rows_})==15 and {r['run_id'] for r in rows_}==selected,'analysis score-row coverage differs')
    for row in rows_:
        old=scoremap[row['run_id']]
        for key in ('run_id','model','case_id','family','human_score','human_pass','judge_score','judge_pass'):
            expected=old.get(key)
            if key=='judge_score':expected=old.get('judge_score')
            require(row.get(key)==expected,'analysis score mismatch: '+row['run_id']+' '+key)
        require(row.get('H')==old['hard']['H'],'analysis hard score mismatch: '+row['run_id'])
        require(row.get('human')==old.get('human_quality') and row.get('judge')==old.get('judge_quality'),'analysis dimension scores mismatch: '+row['run_id'])
        require(row.get('delta')==old['judge_score']-old['human_score'],'analysis score delta mismatch: '+row['run_id'])
    primary={g['run_id']:g for g in gens if g['kind']=='primary'}
    hard_rows=analysis.get('hard_checks');require(isinstance(hard_rows,list) and len(hard_rows)==30,'analysis.json must contain 30 hard checks')
    require(len({r.get('run_id') for r in hard_rows})==30 and {r['run_id'] for r in hard_rows}==set(primary),'analysis hard-check coverage differs')
    for row in hard_rows:
        rid=row['run_id'];result=hard[rid]
        failed=[name for name in ('H1','H2','H3','H4','H5') if result['rules'][name]['status']=='fail']
        unavailable=[name for name in ('H1','H2','H3','H4','H5') if result['rules'][name]['status']=='unavailable']
        seconds=result.get('estimated_seconds')
        seconds=round(seconds,2) if seconds is not None else None
        require(row.get('H')==result['H'] and row.get('seconds')==seconds,'analysis mechanical score mismatch: '+rid)
        require(row.get('failed')==failed and row.get('unavailable')==unavailable and row.get('scored')==(rid in selected),'analysis mechanical details mismatch: '+rid)
    revised=analysis.get('revised_sft_checks');require(isinstance(revised,list) and len(revised)==len(samples)==2,'analysis SFT check count differs')
    for sample,entry in zip(samples,revised):
        check=sft_results[sample['case_id']];conditions=strict_json(sample['input']['system'].rsplit('\n\n## 本次实验条件\n',1)[1])
        for key in ('H','hard_pass','H1','H2','H3','H4','H5','line_characters','line_lengths','maximum_line_characters','action_beats','estimated_seconds'):
            require(entry.get(key)==check[key],'analysis SFT mechanical mismatch: '+sample['case_id']+' '+key)
        require(entry.get('target_seconds')==conditions['target_seconds'] and entry.get('acceptable_interval_seconds')==[conditions['target_seconds']*.85,conditions['target_seconds']*1.15],'analysis SFT condition mismatch: '+sample['case_id'])
    sft_file=readj(root/'sft/checks.json')
    require(sft_file=={'status':'passed','scope':'SFT-only; no historical repository replay','checks':sft_results},'sft/checks.json differs from --check-sft-only output')
    return analysis

def verify_repository(root):
    baseline=root/'frozen/publication_manifest.json'
    if not baseline.exists():baseline=root/'manifest.json'
    require(baseline.is_file(),'Save the ORIGINAL manifest as frozen/publication_manifest.json first')
    b=baseline.read_bytes();blob=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
    require(blob==BASELINE_MANIFEST_BLOB,'Historical manifest is not the pinned original; do not regenerate it')
    original=json.loads(b);verified=0
    core={'dataset.json','SKILL.md','JUDGE.md','rubric.json','config.json','eval.py','runtime.py','Dockerfile','test_eval.py','LICENSE','NOTICE'}
    audit={'audit/scope.json','audit/exclusions.json','audit/publish_authorization.json'}
    historical={item['path']:item for item in original['files']}
    for item in original['files']:
        name=item['path']
        if name in core|audit or name.startswith(('frozen/','usage/')):
            p=root/name
            require(p.is_file() and not p.is_symlink(),'Frozen evidence changed/missing: '+name)
            if name=='audit/scope.json':
                raw=p.read_text(encoding='utf-8')
                scope=strict_json(raw)
                require(scope['source_pdf']['filename']=='reference.pdf','Unexpected audit source PDF filename redaction')
                quoted=json.dumps(LEGACY_SOURCE_FILENAME,ensure_ascii=False)
                restored,n=re.subn(r'("filename"\s*:\s*)"reference\.pdf"',lambda m:m.group(1)+quoted,raw)
                require(n==1,'audit/scope.json must contain exactly one redacted source filename')
                data=restored.encode('utf-8')
                require(len(data)==item['bytes'] and sha(data)==item['sha256'],'audit/scope.json differs beyond the approved filename redaction')
            else:
                require(p.stat().st_size==item['bytes'] and file_sha(p)==item['sha256'],'Frozen evidence changed/missing: '+name)
            verified+=1
    e=load_evaluator(root);e.check_kit()
    amendment=readj(root/'frozen/metadata/review_amendment.json')
    require(e.hashes()==amendment['amended_hashes'],'Frozen runtime/data/skill changed')
    freeze=readj(root/'frozen/metadata/freeze.json')
    for name,digest in freeze['hashes'].items():
        require(file_sha(root/'frozen/generation_sources'/name)==digest,'Generation baseline changed: '+name)
    require(file_sha(root/'frozen/metadata/freeze.json')==amendment['parent_freeze_sha256'],'Freeze lineage changed')
    require(file_sha(root/'frozen/metadata/review_plan.json')==amendment['review_plan_sha256'],'Selection lineage changed')
    require(file_sha(root/'frozen/metadata/judge_execution_plan.json')==amendment['judge_execution_plan_sha256'],'Judge execution-plan lineage changed')
    gens=list(rows(root/'frozen/generations.jsonl'));gm={r['run_id']:r for r in gens}
    require(len(gens)==len(gm)==39,'Generation count/duplicates')
    plan=readj(root/'frozen/metadata/review_plan.json');selected=set(plan['human_run_ids'])
    import random
    rng=random.Random(e.config()['seed']+15)
    expected=[f'{m}.{c}' for m in e.config()['primary_models'] for c in sorted(rng.sample(sorted(e.cases()),5))]
    require(expected==plan['human_run_ids'],'Sampling does not reproduce')
    review=readj(root/'frozen/human/review.json');seal=readj(root/'frozen/human/human.seal.json')
    require(e.digest(review)==seal['review_sha256'],'Human review seal changed')
    require(seal['output_hashes']=={r['run_id']:e.digest(r['output']) for r in gens if r['kind']=='primary'},'Human-sealed outputs changed')
    require(set(seal['human_run_ids'])==selected,'Human/Judge selection differs')
    human={r['sample_id']:r['scores'] for r in review['items']}
    judges=list(rows(root/'frozen/judges.jsonl'));jm={r['generation_id']:r for r in judges}
    lock=readj(root/'frozen/metadata/judge.lock.json')
    require(len(judges)==len(jm)==15 and set(jm)==selected,'Judge selection coverage differs')
    require(e.current_judge_hash()==lock['judge_hash'],'Locked judge changed')
    hard={};tasks={};tool_audit=[]
    for g in gens:
        rid=g['run_id'];require(sha(g['output'])==g['output_sha256'],'Output hash mismatch '+rid)
        if g['kind']=='primary':task=e.cases()[g['case_id']]['task']
        else:
            side=next(x for x in e.data()['side_cases'] if x['id']==g['case_id'])
            task=side['task'] if 'task' in side else e.cases()[side['base_case']]['task']
        tasks[rid]=task;hard[rid]=e.grade(g['output'],task)
        if g['case_id'].startswith('T'):
            artifact=g.get('pi_result',{}).get('artifact_text');same=None
            if artifact is not None:
                try:same=e.strict_json(artifact)==e.strict_json(g['output'])
                except (TypeError,ValueError):same=None
            tool_audit.append({'run_id':rid,'tool_calls':g.get('pi_result',{}).get('tool_calls'),'artifact_present':artifact is not None,'byte_equal':artifact==g['output'] if artifact is not None else None,'json_equal':same})
    expected_hard={r['run_id']:r['hard'] for r in readj(root/'frozen/mechanical_checks.json')}
    require(hard==expected_hard,'Mechanical recomputation differs')
    prompts=list(rows(root/'frozen/prompts.jsonl'));pm={p['run_id']:p for p in prompts}
    require(len(prompts)==len(pm)==54,'Prompt coverage/duplicates')
    def message_text(v):
        if isinstance(v,str):return v
        require(isinstance(v,list) and all(x.get('type')=='text' for x in v),'Unexpected message content')
        return ''.join(x['text'] for x in v)
    for rid,g in gm.items():
        p=pm[rid];require(p['user']==e.user_prompt(tasks[rid]),'Prompt input changed')
        require(p['requested_system']==e.generation_system(tasks[rid]),'Generation skill changed')
        ms=p['effective_request']['messages'];actual=message_text(ms[0]['content'])
        require(actual in {p['requested_system'],p['requested_system']+'\n\n<cwd>\n/workspace\n</cwd>'},'Unexpected wire system')
        require(e.digest(actual)==g['effective_system_sha256'],'Effective system hash changed')
        require(message_text(ms[1]['content'])==p['user'],'Wire source changed')
    for cid in e.cases():
        require(len({gm[m+'.'+cid]['effective_system_sha256'] for m in e.config()['primary_models']})==1,'Cross-model system differs')
    for side in e.data()['side_cases']:
        if side['kind']=='tools':
            for model in side['models']:
                require(gm[model+'.'+side['id']]['effective_system_sha256']==gm[model+'.'+side['base_case']]['effective_system_sha256'],'Tool comparison system differs')
    score_rows=[];judge_analysis=[]
    for rid in sorted(selected):
        j=jm[rid];require(j['status']=='completed' and j['judge_hash']==lock['judge_hash'],'Invalid judge run/version')
        d=e.strict_json(j['output']);require(not e.validate_judge(d),'Judge contract failed')
        p=pm[j['run_id']]
        require(json.loads(p['user'])==e.judge_payload(e.blind_id(rid),tasks[rid],gm[rid]['output']),'Unexpected Judge payload')
        require(p['requested_system']==(root/'JUDGE.md').read_text(encoding='utf-8').strip(),'Judge system changed')
        actual=message_text(p['effective_request']['messages'][0]['content'])
        require(actual in {p['requested_system'],p['requested_system']+'\n\n<cwd>\n/workspace\n</cwd>'} and e.digest(actual)==j['effective_system_sha256'],'Judge wire system/hash mismatch')
        hu=e.combine(hard[rid],human[e.blind_id(rid)]);ju=e.combine(hard[rid],d)
        score_rows.append({'run_id':rid,'human_score':hu['score'],'judge_score':ju['score'],'human_pass':hu['pass'],'judge_pass':ju['pass']})
        content=j.get('pi_result',{}).get('assistant_message',{}).get('content',[])
        reasoning=[x.get('thinking','') for x in content if isinstance(x,dict) and x.get('type')=='thinking'] if isinstance(content,list) else []
        judge_analysis.append({'generation_id':rid,'visible_analysis_present':any(reasoning),'characters':sum(map(len,reasoning))})
    saved=readj(root/'frozen/scores.json');sr={r['run_id']:r for r in saved['results']}
    primary_ids={r['run_id'] for r in gens if r['kind']=='primary'}
    require(len(sr)==len(saved['results'])==30 and set(sr)==primary_ids,'Score table primary coverage differs')
    for rid,old in sr.items():
        if rid not in selected:
            require(old['status']=='not_selected' and all(old.get(k) is None for k in ('score','pass','judge_score','judge_pass','human_score','human_pass')),'Unselected candidate received a score: '+rid)
    for r in score_rows:
        old=sr[r['run_id']]
        require(r['judge_score']==old['score']==old['judge_score'] and r['human_score']==old['human_score'],'Weighted scores changed')
        require(r['judge_pass']==old['pass'] and r['human_pass']==old['human_pass'],'Pass status changed')
    for m,total in saved['totals'].items():
        rr=[r for r in score_rows if r['run_id'].startswith(m+'.')];require(len(rr)==5,'Mean denominator changed')
        require(statistics.mean(r['judge_score'] for r in rr)==total['judge_only_mean'],'Judge mean mismatch')
        require(statistics.mean(r['human_score'] for r in rr)==total['human_mean_5_samples'],'Human mean mismatch')
        require(sum(r['judge_pass'] for r in rr)==total['pass_count'],'Pass count mismatch')
        families=collections.defaultdict(list)
        for row in rr:families[sr[row['run_id']]['family']].append(row['judge_score'])
        require(statistics.mean(statistics.mean(vals) for vals in families.values())==total['mean_selected_families'],'Selected-family mean mismatch')
    # Stream client-visible events; do not retain the full trace in memory.
    scope=readj(root/'audit/scope.json');counts=collections.Counter();requests=set();pending={};raw_usage={}
    for name,allowed in [('frozen/trajectory.jsonl.gz',set(scope['formal_runs'])),('frozen/setup/trajectory.jsonl.gz',set(scope['setup_runs']))]:
        with gzip.open(root/name,'rt',encoding='utf-8') as f:
            for line_ in f:
                ev=json.loads(line_);rid=ev['run_id'];require(rid in allowed,'Unexpected trajectory run');counts[rid]+=1
                if ev['kind']=='request':requests.add((rid,ev['call']))
                if ev['kind']!='response_chunk':continue
                k=(rid,ev['call']);buf=pending.pop(k,b'')+base64.b64decode(ev['data'])
                parts=buf.split(b'\n');pending[k]=parts.pop()
                for part in parts:
                    if not part.startswith(b'data:'):continue
                    txt=part[5:].strip()
                    if not txt or txt==b'[DONE]':continue
                    obj=json.loads(txt)
                    if obj.get('usage'):raw_usage[k]=obj['usage']
    require(all(counts[rid]==scope['trajectory_rows_by_run'][rid] for rid in scope['formal_runs']+scope['setup_runs']),'Trajectory row coverage differs')
    ledger=list(rows(root/'usage/calls.jsonl'))
    require(len({(r['run_id'],r['call']) for r in ledger})==len(ledger),'Duplicate token accounting')
    summary=readj(root/'usage/summary.json')
    for model in e.config()['providers']:
        require(aggregate([r for r in ledger if r['model']==model and r['included_formal']])==summary['formal'][model],'Formal usage summary mismatch: '+model)
        require(aggregate([r for r in ledger if r['model']==model])==summary['all_retained_known'][model],'Process usage summary mismatch: '+model)
    authorization=readj(root/'audit/publish_authorization.json')
    require(authorization['dataset_sha256']==file_sha(root/'dataset.json'),'Publication authorization is not bound to this dataset')
    for r in ledger:
        if r['scope']=='excluded_judge':continue
        k=(r['run_id'],r['call']);require(k in requests and raw_usage.get(k)==r['usage'],'Raw usage mismatch')
    formal=sum(r['usage']['total_tokens'] for r in ledger if r['included_formal'] and r['usage_available'])
    require(formal==1095748,'Formal token total changed')
    samples,sft=check_sft(root,e)
    verify_analysis(root,saved,hard,gens,selected,sft,samples)
    analysis=readj(root/'analysis.json')
    usage_by_model={r['id']:r for r in analysis['formal_usage']}
    require(set(usage_by_model)==set(e.config()['providers']),'analysis formal usage model coverage differs')
    for model in e.config()['providers']:
        expected=summary['formal'][model];row=usage_by_model[model]
        reasoning=expected['reasoning_tokens_known_sum'] if expected['reasoning_tokens_known_calls'] else None
        primary_scope=summary['by_scope'][model]['primary']
        primary=primary_scope['total_tokens'] if primary_scope['api_calls'] else None
        require(row=={'id':model,'calls':expected['api_calls'],'input':expected['prompt_tokens'],'output':expected['completion_tokens'],'total':expected['total_tokens'],'reasoning':reasoning,'primary_total':primary},'analysis formal usage differs: '+model)
    require(analysis['formal_tokens']==sum(v['total_tokens'] for v in summary['formal'].values()),'analysis formal token total differs')
    require(analysis['known_process_tokens']==sum(v['total_tokens'] for v in summary['all_retained_known'].values()),'analysis known process token total differs')
    require(analysis['unknown_usage_calls']==sum(v['usage_missing_calls'] for v in summary['all_retained_known'].values()),'analysis unknown usage count differs')
    return {'status':'passed','source_commit':COMMIT,'historical_files_checked':verified,'generations':39,'scored':15,'formal_runs':54,'formal_tokens':formal,'score_rows':score_rows,'tool_artifact_diagnostics':tool_audit,'judge_visible_analysis':judge_analysis,'sft_checks':sft}

def seal_release(root):
    require((root/'frozen/publication_manifest.json').exists(),'Preserve the original manifest before sealing the release')
    expected=check_public_tree(root)
    entries=[]
    for name in sorted(expected):
        p=root/name
        entries.append({'path':name,'bytes':p.stat().st_size,'sha256':file_sha(p)})
    data={'schema_version':2,'kind':'release_manifest','self_excluded':True,'source_commit':COMMIT,'historical_manifest':'frozen/publication_manifest.json','files':entries}
    (root/'manifest.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return len(entries)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=ROOT)
    ap.add_argument('--check-sft-only',action='store_true')
    ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--check-release',action='store_true',help='Run full verification and check exact release paths, sizes, and hashes')
    ap.add_argument('--seal-release',action='store_true',help='Verify first, then write only the new publication manifest')
    ap.add_argument('--export-training',type=Path,help='Export messages only; requires factual human_approved=true for both records')
    ap.add_argument('--output',type=Path,help='Optionally save the verification result; refuses to overwrite an existing file')
    a=ap.parse_args();root=a.root.resolve()
    require(not(a.check_sft_only and (a.seal_release or a.check_release)),'Release operations require full repository verification')
    require(not(a.self_test and (a.seal_release or a.check_release)),'Release operations require full repository verification')
    if a.self_test:result=self_test(root)
    elif a.check_sft_only:
        _,checks=check_sft(root);result={'status':'passed','scope':'SFT-only; no historical repository replay','checks':checks}
    else:result=verify_repository(root)
    if a.seal_release:
        require(not a.self_test,'Sealing requires full repository verification');result['release_manifest_entries']=seal_release(root)
        result['release_files_verified']=verify_release_manifest(root)
    elif a.check_release:
        result['release_files_verified']=verify_release_manifest(root)
    if a.export_training:
        samples,_=check_sft(root);require(all(s['human_approved'] is True for s in samples),'Training export requires actual human approval; the verifier never changes approval flags')
        require(not a.export_training.exists(),'Export target already exists')
        a.export_training.parent.mkdir(parents=True,exist_ok=True)
        with a.export_training.open('x',encoding='utf-8') as f:
            for s in samples:
                msg={'messages':[{'role':'system','content':s['input']['system']},{'role':'user','content':s['input']['user']},{'role':'assistant','content':json.dumps(s['target'],ensure_ascii=False,separators=(',',':'))}]}
                f.write(json.dumps(msg,ensure_ascii=False,separators=(',',':'))+'\n')
    content=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if a.output:
        require(not a.output.exists(),'Verification output already exists');a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(content,encoding='utf-8')
    print(content,end='')
if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,FileNotFoundError,TypeError,AssertionError) as exc:
        print('FAILED: '+str(exc),file=sys.stderr);raise SystemExit(1)
