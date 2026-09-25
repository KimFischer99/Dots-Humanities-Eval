#!/usr/bin/env python3
"""Literary eval v3: data, deterministic grading, human seal, judge validation, export.
Python 3.11+; standard library only. Never makes model API requests.
"""
from __future__ import annotations
import argparse, copy, datetime as dt, hashlib, html, json, math, os, random, re
import sys, unicodedata, zipfile
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parent
W = ROOT / '.work'
FROZEN = ['dataset.json','rubric.json','SKILL.md','config.json','eval.py','runtime.py','Dockerfile']

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def digest(x):
    if not isinstance(x, (str, bytes)): x = json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',',':'))
    return hashlib.sha256(x.encode('utf8') if isinstance(x,str) else x).hexdigest()
def load(p): return json.loads(Path(p).read_text(encoding='utf8'))
def save(p,x):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp'); tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8'); tmp.replace(p)
def append(p,x):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    with open(p,'a',encoding='utf8') as f: f.write(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n'); f.flush()
def readrows(p):
    p=Path(p)
    return [json.loads(x) for x in p.read_text(encoding='utf8').splitlines() if x.strip()] if p.exists() else []
def config(): return load(ROOT/'config.json')
def data(): return load(ROOT/'dataset.json')
def rubric(): return load(ROOT/'rubric.json')
def cases(): return {c['id']:c for c in data()['cases']}
def source_text(task): return task['source_text']
def reject_citations(text):
    if re.search(r'https?://|www\.|\bdoi\s*:|\barxiv\s*:|\[R\d+\]|\[\^[^\]]+\]|\[\d+\]|cite',text,re.I):
        raise ValueError('Citation/URL markers are not allowed in generation prompts; review the source without silently rewriting it')
def model_task(task):
    # Provenance remains in the private dataset. The model gets only task fields,
    # verbatim source text and a neutral identifier, including in tool task files.
    out={'source_id':'TEXT'}
    for key in ['source_text','target_seconds','interior_policy','output_language']:
        out[key]=copy.deepcopy(task[key])
    reject_citations(json.dumps(out,ensure_ascii=False))
    return out
def generation_system(task=None):
    text=(ROOT/'SKILL.md').read_text(encoding='utf8')
    if not text.startswith('---\n'): raise ValueError('SKILL frontmatter missing')
    body=re.sub(r'<!-- DISTRIBUTION_NOTICE:.*?-->', '', text.split('---',2)[2], flags=re.S).strip()
    if not body: raise ValueError('Generation Skill body is empty')
    reject_citations(body)
    if task is not None:
        public=model_task(task)
        conditions={k:public[k] for k in ['target_seconds','interior_policy','output_language']}
        body+='\n\n## 本次实验条件\n'+json.dumps(conditions,ensure_ascii=False,separators=(',',':'))
    return body
def user_prompt(task): return model_task(task)['source_text']
def blind_id(run_id): return 'B'+digest('review-v3:'+run_id)[:12]
def strict_json(raw):
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d: raise ValueError('duplicate key: '+k)
            d[k]=v
        return d
    def bad(x): raise ValueError('non-finite JSON: '+x)
    return json.loads(raw,object_pairs_hook=unique,parse_constant=bad)
def walk_strings(x):
    if isinstance(x,str): yield x
    elif isinstance(x,dict):
        for k,v in x.items(): yield k; yield from walk_strings(v)
    elif isinstance(x,list):
        for v in x: yield from walk_strings(v)
def char_count(s): return len(re.sub(r'\s','',unicodedata.normalize('NFC',s)))
def exact_keys(d,required,optional=()): return isinstance(d,dict) and set(required)<=set(d)<=set(required)|set(optional)
def nonblank(s): return isinstance(s,str) and bool(s.strip())
def schema_errors(doc):
    errors=[]
    if not exact_keys(doc,['source_id','cast','locations','scenes']): return ['top-level contract']
    if not nonblank(doc['source_id']) or not isinstance(doc['scenes'],list) or not doc['scenes']: return ['source_id/scenes']
    for key in ['cast','locations']:
        if not isinstance(doc[key],list) or (key=='locations' and not doc[key]): errors.append(key+': declaration array'); continue
        for item in doc[key]:
            if not exact_keys(item,['id','name']) or not all(nonblank(item[k]) for k in ['id','name']): errors.append(key+': id/name required')
    for s in walk_strings(doc):
        if any(unicodedata.category(c) in ('Cf','Cs') for c in s): errors.append('invisible format/surrogate character')
    for i,sc in enumerate(doc['scenes']):
        if not exact_keys(sc,['sceneId','characters','flow']): errors.append(f'scene {i}: fields'); continue
        if not nonblank(sc['sceneId']) or not isinstance(sc['characters'],list) or any(not nonblank(x) for x in sc['characters']): errors.append(f'scene {i}: IDs')
        if not isinstance(sc['flow'],list) or not sc['flow']: errors.append(f'scene {i}: no flow'); continue
        has_action=False
        for j,b in enumerate(sc['flow']):
            if exact_keys(b,['action']) and nonblank(b['action']): has_action=True
            elif exact_keys(b,['speaker','line','mode'],['delivery']) and all(nonblank(b[x]) for x in ('speaker','line','mode')) and b['mode'] in ('spoken','inner') and ('delivery' not in b or isinstance(b['delivery'],str)): pass
            else: errors.append(f'scene {i} beat {j}: union contract')
        if not has_action: errors.append(f'scene {i}: no action')
    return errors

def grade(raw,task):
    task=model_task(task)
    rules={k:{'status':'unavailable','ok':False,'points':0} for k in ['H1','H2','H3','H4','H5']}
    try:
        doc=strict_json(raw); errs=schema_errors(doc)
        if errs: raise ValueError('; '.join(errs))
    except (ValueError,TypeError,KeyError) as e:
        rules['H1'].update(status='fail',detail=str(e)); return {'H':0,'hard_pass':False,'rules':rules,'estimated_seconds':None}
    ids={c['id'] for c in doc['cast']}; locs={s['id'] for s in doc['locations']}
    ref_ok=doc['source_id']==task['source_id'] and len(ids)==len(doc['cast']) and len(locs)==len(doc['locations'])
    chars=acts=inner=0; long=[]
    for i,sc in enumerate(doc['scenes']):
        ref_ok &= sc['sceneId'] in locs and set(sc['characters'])<=ids and len(set(sc['characters']))==len(sc['characters'])
        for j,b in enumerate(sc['flow']):
            if 'action' in b: acts+=1
            else:
                ref_ok &= b['speaker'] in sc['characters']; n=char_count(b['line']); chars+=n
                if n>35: long.append([i,j,n])
                inner+=b['mode']=='inner'
    seconds=chars/4.5+acts*2.5; t=task['target_seconds']
    vals=[True,bool(ref_ok),not long,t*.85-1e-9<=seconds<=t*1.15+1e-9,inner<= (2 if task['interior_policy']=='allow_limited' else 0)]
    for key,v in zip(rules,vals): rules[key]={'status':'pass' if v else 'fail','ok':v,'points':4 if v else 0}
    rules['H3']['overlength_beats']=long; rules['H5']['inner_count']=inner
    return {'H':sum(x['points'] for x in rules.values()),'hard_pass':all(vals),'rules':rules,'estimated_seconds':round(seconds,6),'line_characters':chars,'action_beats':acts}

def pointer(doc,p):
    if p=='': return doc
    if not p.startswith('/'): raise ValueError('bad pointer')
    v=doc
    for part in p.split('/')[1:]:
        part=part.replace('~1','/').replace('~0','~')
        if isinstance(v,list):
            if not re.fullmatch(r'0|[1-9][0-9]*',part): raise ValueError('bad array index')
            v=v[int(part)]
        elif isinstance(v,dict): v=v[part]
        else: raise ValueError('pointer to scalar')
    return v

def judge_payload(sample,task,candidate):
    payload={'RUBRIC':rubric()['dimensions'],'TASK':model_task(task),'CANDIDATE':candidate}
    reject_citations(json.dumps(payload,ensure_ascii=False))
    return payload

def validate_judge(j,raw=None,source=None,sample=None):
    # Identity, prompt version and candidate hashes are owned by the host record.
    if not exact_keys(j,['F','D','L']): return ['judge requires exactly F, D, L']
    return [k+': expected integer 0..4' for k in ['F','D','L'] if type(j[k]) is not int or j[k] not in range(5)]

def combine(h,j):
    errors=validate_judge(j)
    if errors: raise ValueError('; '.join(errors))
    ds={k:j[k] for k in ['F','D','L']}
    val=h['H']+7.5*ds['F']+7.5*ds['D']+5*ds['L']
    return {'score':val,'pass':h['hard_pass'] and min(ds.values())>=3,'status':'scored','quality':ds}

def check_kit():
    d=data(); cs=d['cases']; assert len(cs)==10 and len({c['family'] for c in cs})==8
    assert [c['id'] for c in cs]==[f'C{i:02}' for i in range(1,11)]
    for s in d['sources'].values():
        assert digest(s['original_utf8'])==s['raw_sha256']; a=s['selection']['start_codepoint']; b=s['selection']['end_codepoint_exclusive']
        assert s['original_utf8'][a:b]==s['text']; assert digest(s['text'])==s['text_sha256']
        assert len(re.sub(r'\s','',s['text']))==s['nonspace_characters']
        lines=s['original_utf8'].splitlines(keepends=True)
        assert ''.join(lines[s['selection']['start_line']-1:s['selection']['end_line']]).strip()==s['text']
    for c in cs+[s for s in d['side_cases'] if 'task' in s]:
        assert not {'reference','focus','acceptable','failure'} & set(c)
        assert set(c['task'])=={'source_id','source_text','target_seconds','interior_policy','output_language'}
        assert c['task']['source_text']==d['sources'][c['task']['source_id']]['text']
        public=model_task(c['task']); assert public['source_text']==c['task']['source_text']
    for a,b,key in [(0,1,'interior_policy'),(2,3,'target_seconds')]:
        aa=copy.deepcopy(cs[a]['task']); bb=copy.deepcopy(cs[b]['task']); aa.pop(key); bb.pop(key); assert aa==bb
    dev={c['family'] for c in cs if c['split']=='dev'}; val={c['family'] for c in cs if c['split']=='validation'}; assert not dev&val
    s=generation_system().lower()
    for x in ['shuohao','shouhao','codex','kimi','benchmark','recruit','rubric','评测','招聘']: assert x not in s, x
    assert len(rubric()['dimensions'])==3; assert sum(x['weight'] for x in rubric()['dimensions'])==80
    return {'status':'offline_data_contract_pass','sources':len(d['sources']),'primary_cases':10,'families':8,'side_new_runs':sum(len(s['models']) for s in d['side_cases'])}

def hashes(): return {n:digest((ROOT/n).read_bytes()) for n in FROZEN}
def assert_frozen():
    lock=load(W/'freeze.json')
    current=hashes()
    if lock['hashes']==current: return lock
    amendment_path=W/'review_amendment.json'; plan_path=W/'review_plan.json'
    if not amendment_path.exists() or not plan_path.exists(): raise ValueError('Frozen file changed without a review-only amendment')
    amendment=load(amendment_path)
    if amendment.get('parent_freeze_sha256')!=digest((W/'freeze.json').read_bytes()) or amendment.get('parent_hashes')!=lock['hashes']:
        raise ValueError('Review amendment does not match the parent freeze')
    if amendment.get('amended_hashes')!=current or amendment.get('review_plan_sha256')!=digest(plan_path.read_bytes()):
        raise ValueError('Review amendment or selection plan changed')
    if any(current[n]!=lock['hashes'][n] for n in current if n not in {'eval.py','runtime.py'}):
        raise ValueError('A frozen generation artifact changed; do not reuse responses')
    if amendment.get('judge_execution_plan_sha256') and amendment['judge_execution_plan_sha256']!=digest((W/'judge_execution_plan.json').read_bytes()):
        raise ValueError('Judge execution plan changed')
    return lock

def generations(primary=True):
    rows=readrows(W/'generations.jsonl'); out={}
    for r in rows:
        if primary and r['kind']!='primary': continue
        if r['run_id'] in out: raise ValueError('Duplicate primary trial: no implicit best-of-N selection')
        out[r['run_id']]=r
    return out

def human_assignment():
    cfg=config(); rng=random.Random(cfg['seed']+173); selected={}
    for split in ['judge_dev','judge_validation']:
        models=list(cfg['primary_models']); rng.shuffle(models)
        for cid,model in zip(cfg[split],models): selected[cid]=f'{model}.{cid}'
    return selected

def prepare_review():
    plan_path=W/'review_plan.json'; amendment_path=W/'review_amendment.json'
    if plan_path.exists() or amendment_path.exists(): raise ValueError('Review selection already prepared; do not replace it')
    if (W/'human.seal.json').exists() or readrows(W/'judges.jsonl'): raise ValueError('Cannot change review selection after human sealing or Judge execution')
    lock=load(W/'freeze.json'); current=hashes(); parent=lock['hashes']
    if set(parent)!=set(current): raise ValueError('Frozen artifact list changed; do not reuse responses')
    if any(current[n]!=parent[n] for n in current if n not in {'eval.py','runtime.py'}):
        raise ValueError('A frozen generation artifact changed; do not reuse responses')
    assert_primary_complete()
    cfg=config(); seed=cfg['seed']+15; rng=random.Random(seed); selected=[]
    for model in cfg['primary_models']:
        selected.extend(f'{model}.{cid}' for cid in sorted(rng.sample(sorted(cases()),5)))
    groups={'dev':[],'validation':[],'rest':[]}
    for rid in selected:
        split=cases()[rid.split('.',1)[1]]['split']
        groups['rest' if split=='extension' else split].append(rid)
    if not groups['dev'] or not groups['validation']:
        raise ValueError('Random selection must include development and validation samples')
    parent_sha=digest((W/'freeze.json').read_bytes())
    plan={'selection_method':'stratified_random_without_replacement','selection_seed':seed,'population_size':len(primary_expected()),'sample_size':len(selected),
          'per_model':{m:5 for m in cfg['primary_models']},'source_split_to_judge_phase':{'dev':'dev','validation':'validation','extension':'rest'},
          'human_run_ids':selected,'judge_dev_run_ids':groups['dev'],'judge_validation_run_ids':groups['validation'],'judge_rest_run_ids':groups['rest'],
          'parent_freeze_sha256':parent_sha}
    save(plan_path,plan)
    amended=current!=parent
    if amended:
        save(amendment_path,{'amended_at':now(),'purpose':'Expand blind human and Judge review to the same stratified random 15 Primary outputs; score only those outputs.',
            'parent_freeze_sha256':parent_sha,'parent_hashes':parent,'amended_hashes':current,'review_plan_sha256':digest(plan_path.read_bytes())})
    return {'status':'review_selection_prepared','selection_method':plan['selection_method'],'selection_seed':seed,'population_size':len(primary_expected()),
            'selected':len(selected),'by_model':plan['per_model'],'by_judge_phase':{k:len(v) for k,v in groups.items()},
            'review_only_amendment':amended,'review_plan_sha256':digest(plan_path.read_bytes())}

def review_plan():
    path=W/'review_plan.json'
    if not path.exists(): raise ValueError('Run prepare-review to record the review sample before generating or scoring it')
    p=load(path); selected=p.get('human_run_ids'); dev=p.get('judge_dev_run_ids'); validation=p.get('judge_validation_run_ids'); rest=p.get('judge_rest_run_ids')
    expected=primary_expected(); models=config()['primary_models']
    if not all(isinstance(xs,list) and all(isinstance(x,str) for x in xs) for xs in [selected,dev,validation,rest]): raise ValueError('Invalid review selection plan')
    if len(selected)!=15 or len(set(selected))!=15 or not set(selected)<=expected:
        raise ValueError('Review plan must contain 15 unique Primary samples')
    if set(dev)&set(validation) or set(dev)&set(rest) or set(validation)&set(rest) or set(dev)|set(validation)|set(rest)!=set(selected):
        raise ValueError('Review plan sample splits must partition the human/Judge selection')
    if not dev or not validation: raise ValueError('Review plan needs development and validation samples')
    if p.get('selection_method')!='stratified_random_without_replacement' or p.get('selection_seed')!=config()['seed']+15:
        raise ValueError('Review plan selection method or seed mismatch')
    rng=random.Random(p['selection_seed']); expected_selected=[]
    for model in models:
        expected_selected.extend(f'{model}.{cid}' for cid in sorted(rng.sample(sorted(cases()),5)))
    if selected!=expected_selected:
        raise ValueError('Review samples do not match the recorded stratified random seed')
    if p.get('population_size')!=len(expected) or p.get('sample_size')!=15 or p.get('per_model')!={m:5 for m in models}:
        raise ValueError('Review plan must select exactly five Primary outputs per model')
    phase_split={'dev':'dev','validation':'validation','rest':'extension'}
    expected_splits={phase:{rid for rid in selected if cases()[rid.split('.',1)[1]]['split']==split} for phase,split in phase_split.items()}
    actual_splits={'dev':set(dev),'validation':set(validation),'rest':set(rest)}
    if actual_splits!=expected_splits:
        raise ValueError('Judge and human selections must contain the same 15 runs')
    if p.get('source_split_to_judge_phase')!={'dev':'dev','validation':'validation','extension':'rest'}:
        raise ValueError('Review plan source split mapping changed')
    if p.get('parent_freeze_sha256')!=digest((W/'freeze.json').read_bytes()): raise ValueError('Review plan parent freeze mismatch')
    return p

def judge_run_ids(phase):
    if phase not in ['dev','validation','rest','final']: raise ValueError('Unknown judge sample split')
    p=review_plan()
    return p['human_run_ids'] if phase=='final' else p['judge_'+phase+'_run_ids']

def primary_expected(): return {f'{m}.{c}' for m in config()['primary_models'] for c in cases()}
def assert_primary_complete():
    rows=generations(); expected=primary_expected()
    if set(rows)!=expected: raise ValueError('Need exactly 30 primary results (including executed model failures)')
    if any(r['status']!='completed' for r in rows.values()): raise ValueError('Infrastructure/transport failure: incomplete experiment; never average fewer cases')
    for cid in cases():
        systems={rows[f'{m}.{cid}'].get('effective_system_sha256') for m in config()['primary_models']}
        if len(systems)!=1 or None in systems: raise ValueError('Primary effective system prompts are not identical/verifiable within case '+cid)
    return rows

def assert_human_sealed():
    assert_frozen(); seal=load(W/'human.seal.json'); review=load(W/'review.json'); rows=assert_primary_complete()
    if digest(review)!=seal['review_sha256']: raise ValueError('Human review changed after sealing')
    if {k:digest(v['output']) for k,v in rows.items()}!=seal['output_hashes']: raise ValueError('Candidate outputs changed')
    return seal

def display_script(raw,task):
    try:
        doc=strict_json(raw)
        if schema_errors(doc): return raw
        names={x['id']:x['name'] for x in doc['cast']}; places={x['id']:x['name'] for x in doc['locations']}
        lines=['人物表（模型自报，待核对）：'+json.dumps(doc['cast'],ensure_ascii=False), '场景表（模型自报，待核对）：'+json.dumps(doc['locations'],ensure_ascii=False), '']
        for i,sc in enumerate(doc['scenes'],1):
            lines.append(f"场{i}：{places.get(sc['sceneId'],sc['sceneId'])} / "+'、'.join(names.get(x,x) for x in sc['characters']))
            for b in sc['flow']:
                if 'action' in b: lines.append('【动作】'+b['action'])
                else:
                    hint=('内白；' if b['mode']=='inner' else '')+b.get('delivery','')
                    lines.append(names.get(b['speaker'],b['speaker'])+('（'+hint+'）' if hint else '')+'：'+b['line'])
            lines.append('')
        return '\n'.join(lines)
    except (ValueError,KeyError,TypeError): return raw

def make_review():
    assert_frozen(); rows=assert_primary_complete(); cfg=config(); plan=review_plan(); selected=set(plan['human_run_ids'])
    if (W/'human.seal.json').exists(): raise ValueError('Already sealed')
    old_review=W/'review.json'
    if old_review.exists():
        old=load(old_review); items=old.get('items',[])
        touched=bool(str(old.get('reviewer','')).strip() or str(old.get('reviewed_at','')).strip()) or any(
            x.get('read_and_integrity_checked') is True or
            any(v is not None for v in (x.get('scores') or {}).values()) or
            any(str(x.get(k,'')).strip() for k in ['evidence_note','quote','source_quote'])
            for x in items)
        if touched: raise ValueError('Review contains human work; refusing to overwrite it')
        backup=W/('review.initial-'+digest(old_review.read_bytes())[:12]+'.json')
        if not backup.exists(): backup.write_bytes(old_review.read_bytes())
    old_page=W/'review.html'
    if old_page.exists():
        backup=W/('review.initial-'+digest(old_page.read_bytes())[:12]+'.html')
        if not backup.exists(): backup.write_bytes(old_page.read_bytes())
    cards=[]
    for rid in plan['human_run_ids']:
        r=rows[rid]; c=cases()[r['case_id']]; cards.append({'sample_id':blind_id(rid),'case_id':r['case_id'],'task':model_task(c['task']),'output':r['output'],'display':display_script(r['output'],c['task']),'output_sha256':digest(r['output'])})
    random.Random(cfg['seed']).shuffle(cards)
    form={'reviewer':'','reviewed_at':'','rubric_sha256':digest((ROOT/'rubric.json').read_bytes()),'items':[{'sample_id':c['sample_id'],'output_sha256':c['output_sha256'],'scores':{'F':None,'D':None,'L':None}} for c in cards]}
    save(W/'review.json',form)
    payload=json.dumps({'cards':cards,'form':form,'rubric':{'dimensions':rubric()['dimensions']}},ensure_ascii=False).replace('<','\\u003c')
    page='''<!doctype html><meta charset="utf-8"><title>匿名人工评分</title><style>body{max-width:1050px;margin:32px auto;font:16px/1.7 system-ui}article{border-top:2px solid #aaa;margin-top:30px;padding:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere}select,input{font-size:16px;margin:5px}button{padding:12px}summary{cursor:pointer}label{display:block}.scores{border-top:1px solid #bbb;margin-top:18px;padding-top:10px}</style><h1>匿名人工评分</h1><p>本页为从30份Primary结果中分层随机抽取的15份匿名样本，每个模型5份。请阅读材料并为每份提供F、D、L三个分数；不要查看Kimi结果。</p><label>评审者<input id="who"></label><button onclick="download()">保存 review.json</button><p id="status"></p><details><summary>评分锚点</summary><pre id="rubric"></pre></details><main id="cards"></main><script>const DATA=__DATA__;const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));document.getElementById('rubric').textContent=DATA.rubric.dimensions.map(d=>d.id+' '+d.name+'\\n'+d.question+'\\n'+Object.entries(d.anchors).map(([k,v])=>k+'：'+v).join('\\n')+'\\n'+d.do_not).join('\\n\\n');const box=document.getElementById('cards');DATA.cards.forEach((c,i)=>{const a=document.createElement('article');a.innerHTML='<h2>'+esc(c.sample_id)+' / '+esc(c.case_id)+'</h2><details><summary>原文与任务</summary><pre>'+esc(JSON.stringify({TASK:c.task},null,2))+'</pre></details><details open><summary>逐字内容的阅读视图（只替换ID显示名称）</summary><pre>'+esc(c.display)+'</pre></details><details><summary>原始JSON／原始回答</summary><pre>'+esc(c.output)+'</pre></details><section class="scores"><strong>评分</strong>'+['F','D','L'].map(k=>'<label>'+k+'<select id="'+k+i+'"><option value="">请选择</option>'+[0,1,2,3,4].map(n=>'<option>'+n+'</option>').join('')+'</select></label>').join('')+'</section>';box.appendChild(a)});function download(){const f=structuredClone(DATA.form);f.reviewer=document.getElementById('who').value.trim();f.reviewed_at=new Date().toISOString();let ok=!!f.reviewer;f.items.forEach((r,i)=>{for(const k of ['F','D','L']){const v=document.getElementById(k+i).value;r.scores[k]=v===''?null:Number(v);ok&&=v!=='';}});if(!ok){document.getElementById('status').textContent='请完成15份F/D/L三维评分并填写评审者。';return;}let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(f,null,2)],{type:'application/json'}));a.download='review.json';a.click();}</script>'''.replace('__DATA__',payload)
    (W/'review.html').write_text(page,encoding='utf8')
    return {'review_file':str(W/'review.html'),'human_samples':len(selected),'numeric_ratings':3*len(selected),'review_fields_per_sample':3}

def seal_human():
    assert_frozen(); rows=assert_primary_complete(); f=load(W/'review.json'); plan=review_plan()
    if (W/'human.seal.json').exists(): raise ValueError('Seal exists')
    if readrows(W/'judges.jsonl'): raise ValueError('Judge already ran; cannot claim independent pre-judge human review')
    if not nonblank(f.get('reviewer')) or not nonblank(f.get('reviewed_at')): raise ValueError('Human identity/time missing')
    if f.get('rubric_sha256')!=digest((ROOT/'rubric.json').read_bytes()): raise ValueError('Wrong rubric')
    plan=review_plan(); selected=set(plan['human_run_ids']); byblind={blind_id(k):v for k,v in rows.items()}; items=f['items']
    if len(items)!=len(selected) or {x['sample_id'] for x in items}!={blind_id(rid) for rid in selected}: raise ValueError('Review coverage')
    for item in items:
        r=byblind[item['sample_id']]
        if set(item)!={'sample_id','output_sha256','scores'} or item['output_sha256']!=digest(r['output']): raise ValueError('Review fields or candidate output changed')
        scores=item.get('scores')
        if not isinstance(scores,dict) or set(scores)!={'F','D','L'} or any(type(v)is not int or v not in range(5) for v in scores.values()): raise ValueError('Need three integer human scores')
    seal={'sealed_at':now(),'review_sha256':digest(f),'output_hashes':{k:digest(v['output']) for k,v in rows.items()},'reviewer':f['reviewer'],'human_run_ids':plan['human_run_ids'],'review_plan_sha256':digest((W/'review_plan.json').read_bytes()) if (W/'review_plan.json').exists() else digest(plan)}
    save(W/'human.seal.json',seal); return {'status':'human_sealed','scores':3*len(plan['human_run_ids'])}

def current_judge_hash(): return digest({'prompt':(ROOT/'JUDGE.md').read_text(),'rubric':rubric()})
def active_judgments():
    rows=readrows(W/'judges.jsonl'); superseded=set()
    policy=load(W/'judge_execution_plan.json') if (W/'judge_execution_plan.json').exists() else {}
    for j in rows:
        if not j.get('retry_of'): continue
        previous=[x for x in rows if x.get('run_id')==j['retry_of']]
        if j['retry_of'] not in policy.get('authorized_retry_run_ids',[]) or len(previous)!=1:
            raise ValueError('Unregistered Judge retry')
        old=previous[0]
        if old['status']!='infrastructure_failure' or old.get('output') or old['generation_id']!=j['generation_id'] or old['judge_hash']!=j['judge_hash'] or j['retry_of'] in superseded:
            raise ValueError('Invalid Judge retry lineage')
        superseded.add(j['retry_of'])
    return [j for j in rows if j.get('run_id') not in superseded]
def lock_judge(reason):
    assert_human_sealed(); js=active_judgments(); dev=set(judge_run_ids('dev'))
    current=[j for j in js if j['phase']=='dev' and j['judge_hash']==current_judge_hash()]
    if not dev <= {j['generation_id'] for j in current}: raise ValueError(f'Run all {len(dev)} development judgments under the current prompt first')
    if len(current)!=len(dev): raise ValueError('Unexpected or duplicate development judgments')
    for j in current:
        rid=j['generation_id']; c=cases()[generations()[rid]['case_id']]
        if j['status']!='completed' or validate_judge(strict_json(j['output']),generations()[rid]['output'],c['task']['source_text'],blind_id(rid)): raise ValueError('Development Judge scores are invalid')
    if (W/'judge.lock.json').exists(): raise ValueError('Judge lock exists')
    if any(j['phase'] in ['validation','rest'] for j in js): raise ValueError('Cannot tune after validation')
    if not nonblank(reason): raise ValueError('Document change or no-change reason')
    x={'locked_at':now(),'judge_hash':current_judge_hash(),'reason':reason}; save(W/'judge.lock.json',x); return x

def apply_adjudications(result):
    """Post-judge human resolution is separate from the independent human seal.
    Preserve uniform K3 scores; expose every override and its evidence/count.
    """
    index={r['run_id']:r for r in result}
    for r in result:
        r['judge_score']=r['score']; r['judge_pass']=r['pass']; r['judge_status']=r['status']; r['judge_quality']=r.get('quality')
    path=W/'adjudication.json'
    if not path.exists(): return
    a=load(path)
    if not nonblank(a.get('reviewer')) or not nonblank(a.get('reviewed_at')): raise ValueError('Adjudication reviewer/time missing')
    seen=set()
    for item in a['items']:
        rid=item['run_id']
        if rid in seen or rid not in index or rid not in set(review_plan()['human_run_ids']): raise ValueError('Adjudication identity/duplicate/unselected')
        seen.add(rid); r=index[rid]; candidate=generations()[rid]['output']; source=cases()[r['case_id']]['task']['source_text']
        if r['status'] in ('infrastructure_failure','judge_infrastructure_failure','judge_missing'): raise ValueError('Cannot convert infrastructure/missing calls into a completed model score')
        if item.get('trigger') not in ['uncertain','invalid_judge','critical_error','calibration_disagreement','evidence_error']: raise ValueError('Undeclared adjudication trigger')
        ss=item.get('scores')
        if not isinstance(ss,dict) or set(ss)!={'F','D','L'} or any(type(v) is not int or v not in range(5) for v in ss.values()): raise ValueError('Invalid adjudication scores')
        if not nonblank(item.get('reason')) or not nonblank(item.get('source_quote')) or item['source_quote'] not in source: raise ValueError('Adjudication source evidence missing')
        quote=item.get('quote','')
        try: strings=list(walk_strings(strict_json(candidate)))
        except ValueError: strings=[]
        if quote and quote not in candidate and not any(quote in x for x in strings): raise ValueError('Adjudication quote not in candidate')
        r['adjudication']={**item,'reviewer':a['reviewer'],'reviewed_at':a['reviewed_at'],'post_judge':True}
        r.update(combine(r['hard'],ss)); r['status']='human_adjudicated'
def score_all():
    assert_human_sealed(); lock=load(W/'judge.lock.json')
    if lock['judge_hash']!=current_judge_hash(): raise ValueError('Judge prompt/rubric changed after lock')
    js=active_judgments(); last={}
    for j in js:
        if j['judge_hash']==lock['judge_hash']:
            if j['generation_id'] in last: raise ValueError('Duplicate same-version judge; explicit adjudication required')
            last[j['generation_id']]=j
    result=[]; cs=cases(); selected=set(review_plan()['human_run_ids']); human={x['sample_id']:x['scores'] for x in load(W/'review.json')['items']}
    for rid,r in sorted(generations().items()):
        c=cs[r['case_id']]; h=grade(r['output'],c['task']); jr=last.get(rid) if rid in selected else None; x={'run_id':rid,'case_id':c['id'],'family':c['family'],'model':r['model'],'hard':h,'judge':jr,'score':None,'pass':None,'status':'judge_missing' if rid in selected else 'not_selected'}
        if rid not in selected:
            result.append(x); continue
        hs=human[blind_id(rid)]; hc=combine(h,hs)
        x.update(human_quality=hs,human_score=hc['score'],human_pass=hc['pass'])
        if r['status']!='completed': x['status']='infrastructure_failure'
        elif jr and jr['status']!='completed': x['status']='judge_infrastructure_failure'
        elif jr:
            try:
                j=strict_json(jr['output']); errors=validate_judge(j,r['output'],c['task']['source_text'],blind_id(rid))
                if errors: x.update(status='invalid_judge',judge_errors=errors)
                else: x.update(combine(h,j))
            except (ValueError,TypeError,KeyError): x['status']='invalid_judge'
        result.append(x)
    apply_adjudications(result)
    totals={}
    for model in config()['primary_models']:
        rr=[r for r in result if r['model']==model and r['run_id'] in selected]; complete=len(rr)==5 and all(r['score'] is not None for r in rr); fam={}
        for r in rr: fam.setdefault(r['family'],[]).append(r['score'])
        totals[model]={'status':'complete' if complete else 'incomplete','scored':sum(r['score'] is not None for r in rr),'scheduled':5,'primary_population':10,'human_mean_5_samples':sum(r['human_score'] for r in rr)/5 if len(rr)==5 else None,'human_pass_count':sum(r['human_pass'] for r in rr),'mean_5_samples':sum(r['score'] for r in rr)/5 if complete else None,'mean_selected_families':sum(sum(v)/len(v) for v in fam.values())/len(fam) if complete and fam else None,'selected_family_count':len(fam),'pass_count':sum(r['pass'] is True for r in rr),'hard_pass_count':sum(r['hard']['hard_pass'] for r in rr),'judge_only_mean':sum(r['judge_score'] for r in rr)/5 if len(rr)==5 and all(r['judge_score'] is not None for r in rr) else None,'adjudicated_count':sum('adjudication' in r for r in rr),'score_basis':'human_audited' if any('adjudication' in r for r in rr) else 'judge_only','mean_H':sum(r['hard']['H'] for r in rr)/5 if len(rr)==5 else None,'mean_quality':{k:sum(r['quality'][k] for r in rr)/5 for k in ['F','D','L']} if complete else None}
    out={'generated_at':now(),'judge_hash':lock['judge_hash'],'totals':totals,'results':result}; save(W/'scores.json',out); return out

def compare(phase):
    assert_human_sealed(); wanted=judge_run_ids(phase); human={x['sample_id']:x for x in load(W/'review.json')['items']}; rows=generations(); out=[]; weighted=[]
    history=[j for j in active_judgments() if j['judge_hash']==current_judge_hash() and j['phase']==phase]
    for rid in wanted:
        cid=rows[rid]['case_id']; matches=[j for j in history if j['generation_id']==rid]
        errors=[]; parsed=None
        if len(matches)!=1: errors=['missing or duplicate current-version judgment']
        elif matches[0]['status']!='completed': errors=['Judge infrastructure failure']
        else:
            try:
                parsed=strict_json(matches[0]['output']); errors=validate_judge(parsed)
            except (ValueError,TypeError): errors=['Judge output is not strict JSON']
        if errors:
            out.append({'run_id':rid,'case_id':cid,'errors':errors}); continue
        scores=human[blind_id(rid)]['scores']
        for k in ['F','D','L']:
            out.append({'run_id':rid,'case_id':cid,'model':rows[rid]['model'],'dimension':k,'human':scores[k],'judge':parsed[k],'absolute_difference':abs(scores[k]-parsed[k])})
        hard=grade(rows[rid]['output'],cases()[cid]['task'])
        weighted.append({'run_id':rid,'human_score':combine(hard,scores)['score'],'judge_score':combine(hard,parsed)['score']})
    ds=[x['absolute_difference'] for x in out if 'absolute_difference' in x]
    return {'phase':phase,'judge_hash':current_judge_hash(),'status':'complete' if len(weighted)==len(wanted) else 'incomplete','rows':out,'weighted_scores':weighted,'MAE':sum(ds)/len(ds) if ds else None,'within_one':sum(v<=1 for v in ds)/len(ds) if ds else None,'dimension_decisions':len(ds),'sample_count':len(wanted),'case_count':len({rows[rid]['case_id'] for rid in wanted}),'source_families':len({cases()[rows[rid]['case_id']]['family'] for rid in wanted}),'warning':'Diagnostic small sample, not independent statistical reliability evidence.'}

def export_final(report,sft,incident,mode):
    scores=score_all()
    if any(t['status']!='complete' for t in scores['totals'].values()): raise ValueError('Incomplete 3x5 selected-sample scores; resolve missing/uncertain judgments transparently first')
    rr=Path(report).read_text(encoding='utf8'); ss=readrows(sft); inc=load(incident)
    if not rr.strip() or len(ss)!=2: raise ValueError('Need report and exactly 2 new SFT examples')
    if inc.get('human_verified') is not True or not nonblank(inc.get('record')) or not nonblank(inc.get('origin')): raise ValueError('Need a real, human-verified incident record; cannot fabricate prior experience')
    for x in ss:
        required={'input','target','acceptance','rejected_data','side_effects','independent_validation','based_on_runs','human_approved'}
        if not required<=set(x) or x['human_approved'] is not True or not x['based_on_runs'] or not set(x['based_on_runs'])<=primary_expected(): raise ValueError('Incomplete/unreviewed SFT example')
    if mode=='public' and any(s['public_text_permission']!='confirmed' for s in data()['sources'].values()): raise ValueError('Public full-text redistribution NOT authorized. Export private; do not publish raw materials/prompts/trajectories.')
    # This is a private/full-fidelity export by default. No silent redaction.
    out=W/'submission'; out.mkdir(exist_ok=True)
    for old in out.iterdir():
        if old.is_file(): old.unlink()
    (out/'REPORT.md').write_text(rr,encoding='utf8'); save(out/'dataset.json',data())
    for name in ['prompts.jsonl','trajectory.jsonl']:
        p=W/name
        if not p.exists() or not p.stat().st_size: raise ValueError('Missing actual execution evidence: '+name)
        (out/name).write_bytes(p.read_bytes())
    human={x['sample_id']:x for x in load(W/'review.json')['items']}
    for x in scores['results']:
        r=generations()[x['run_id']]; append(out/'results.jsonl',{'kind':'primary',**x,'generation':r,'human':human.get(blind_id(x['run_id']))})
    for r in generations(primary=False).values():
        if r['kind']!='primary': append(out/'results.jsonl',{'kind':'side','generation':r})
    append(out/'results.jsonl',{'kind':'audit','freeze':load(W/'freeze.json'),'human_seal':load(W/'human.seal.json'),'judge_lock':load(W/'judge.lock.json'),'judge_history':readrows(W/'judges.jsonl'),'incident':inc,'totals':scores['totals'],'calibration_dev':compare('dev'),'calibration_validation':compare('validation')})
    for x in ss: append(out/'sft.jsonl',x)
    archive=W/'submission.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.iterdir()): z.write(p,p.name)
    return {'archive':str(archive),'files':6,'mode':mode,'notice':'Do not upload a private export to a public repository.'}

def main():
    p=argparse.ArgumentParser(description=__doc__); sp=p.add_subparsers(dest='cmd',required=True)
    sp.add_parser('check-kit')
    a=sp.add_parser('check-script'); a.add_argument('output'); a.add_argument('task')
    a=sp.add_parser('freeze'); a.add_argument('--reviewer',required=True)
    sp.add_parser('prepare-review'); sp.add_parser('review'); sp.add_parser('seal')
    a=sp.add_parser('lock-judge'); a.add_argument('--reason',required=True)
    a=sp.add_parser('compare'); a.add_argument('--phase',choices=['dev','validation'],required=True)
    sp.add_parser('score')
    a=sp.add_parser('export'); a.add_argument('--report',required=True); a.add_argument('--sft',required=True); a.add_argument('--incident',required=True); a.add_argument('--mode',choices=['private','public'],default='private')
    a=p.parse_args()
    try:
        if a.cmd=='check-kit': x=check_kit()
        elif a.cmd=='check-script':
            t=load(a.task); x=grade(Path(a.output).read_text(encoding='utf8'),t.get('task',t)); print(json.dumps(x,ensure_ascii=False)); return 0 if x['hard_pass'] else 2
        elif a.cmd=='freeze':
            check_kit(); probe=load(W/'probe.json')
            if not probe.get('passed') or probe.get('artifact_hashes')!=hashes(): raise ValueError('Run successful fresh four-provider Pi probe before freezing')
            if (W/'freeze.json').exists(): raise ValueError('Already frozen; do not overwrite')
            x={'frozen_at':now(),'reviewer':a.reviewer,'hashes':hashes(),'image_id':probe['image_id'],'runtime_build':load(W/'build.json'),'probe_sha256':digest(probe),'materials_and_rubric_approved':True,'initial_judge_hash':current_judge_hash(),'human_assignment_sha256':digest(human_assignment())}; save(W/'freeze.json',x)
        elif a.cmd=='prepare-review': x=prepare_review()
        elif a.cmd=='review': x=make_review()
        elif a.cmd=='seal': x=seal_human()
        elif a.cmd=='lock-judge': x=lock_judge(a.reason)
        elif a.cmd=='compare': x=compare(a.phase)
        elif a.cmd=='score': x=score_all()
        else: x=export_final(a.report,a.sft,a.incident,a.mode)
        print(json.dumps(x,ensure_ascii=False,indent=2)); return 0
    except (ValueError,AssertionError,KeyError,TypeError,FileNotFoundError) as e:
        print('BLOCKED: '+str(e),file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
