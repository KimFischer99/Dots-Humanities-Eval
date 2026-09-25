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
    payload={'sample_id':sample,'rubric_version':rubric()['version'],'RUBRIC':rubric()['dimensions'],'TASK':model_task(task),'CANDIDATE':candidate}
    reject_citations(json.dumps(payload,ensure_ascii=False))
    return payload

def validate_judge(j,raw,source,sample):
    errs=[]
    if not exact_keys(j,['sample_id','rubric_version','dimensions','critical_errors']): return ['judge top-level fields']
    if j['sample_id']!=sample or j['rubric_version']!=rubric()['version']: errs.append('judge identity/version')
    ds=j['dimensions']
    if not isinstance(ds,list) or len(ds)!=3 or {d.get('id') for d in ds if isinstance(d,dict)}!={'F','D','L'}: return errs+['three dimensions required']
    try: doc=strict_json(raw)
    except ValueError: doc=None
    for d in ds:
        if not exact_keys(d,['id','status','score','reason','evidence']): errs.append('dimension fields'); continue
        if not nonblank(d['reason']): errs.append(d['id']+': missing reason')
        if d['status']=='uncertain':
            if d['score'] is not None: errs.append('uncertain must be null')
            continue
        if d['status']!='scored' or type(d['score']) is not int or d['score'] not in range(5): errs.append('invalid score')
        e=d['evidence']
        if not exact_keys(e,['kind','pointer','quote','scope','source_quote']): errs.append('evidence fields'); continue
        sq=e['source_quote']
        if not isinstance(sq,str) or (sq and sq not in source): errs.append('source quote not in supplied text')
        if d['id']=='F' and not nonblank(sq): errs.append('F needs source evidence')
        try:
            if e['kind']=='quote':
                v=pointer(doc,e['pointer'])
                if not isinstance(v,str) or not nonblank(e['quote']) or e['quote'] not in v: raise ValueError('quote not in string at pointer')
            elif e['kind']=='raw':
                if not nonblank(e['quote']) or e['quote'] not in raw or e['pointer']!='': raise ValueError('raw quote invalid')
            elif e['kind']=='absence':
                if e['quote']!='' or e['pointer']!='' or e['scope']!='whole_candidate': raise ValueError('absence scope invalid')
            else: raise ValueError('evidence kind')
        except (ValueError,TypeError,KeyError,IndexError): errs.append(d['id']+': evidence cannot be verified')
    if not isinstance(j['critical_errors'],list): errs.append('critical_errors must be array')
    else:
        for e in j['critical_errors']:
            if not exact_keys(e,['category','reason','source_quote']) or not isinstance(e.get('source_quote'),str) or (e['source_quote'] and e['source_quote'] not in source): errs.append('critical error schema')
    return errs

def combine(h,j):
    ds={d['id']:d['score'] for d in j['dimensions']}
    if any(v is None for v in ds.values()): return {'score':None,'pass':None,'status':'uncertain','quality':ds}
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
    if lock['hashes']!=hashes(): raise ValueError('Frozen file changed: start a new experiment, do not reuse responses')
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
    assert_frozen(); rows=assert_primary_complete(); cfg=config(); selected=set(human_assignment().values())
    if (W/'human.seal.json').exists(): raise ValueError('Already sealed')
    if (W/'review.json').exists(): raise ValueError('Review exists; do not overwrite human work')
    cards=[]
    for rid,r in rows.items():
        c=cases()[r['case_id']]; cards.append({'sample_id':blind_id(rid),'case_id':r['case_id'],'task':model_task(c['task']),'output':r['output'],'display':display_script(r['output'],c['task']),'output_sha256':digest(r['output']),'detailed':rid in selected})
    random.Random(cfg['seed']).shuffle(cards)
    form={'reviewer':'','reviewed_at':'','rubric_sha256':digest((ROOT/'rubric.json').read_bytes()),'items':[{'sample_id':c['sample_id'],'output_sha256':c['output_sha256'],'read_and_integrity_checked':False,'scores':{'F':None,'D':None,'L':None} if c['detailed'] else None,'evidence_note':'','quote':'','source_quote':''} for c in cards]}
    save(W/'review.json',form)
    payload=json.dumps({'cards':cards,'form':form,'rubric':rubric()},ensure_ascii=False).replace('<','\\u003c')
    page='''<!doctype html><meta charset="utf-8"><title>匿名人工复核</title><style>body{max-width:1050px;margin:32px auto;font:16px/1.7 system-ui}article{border-top:2px solid #aaa;margin-top:30px;padding:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere}textarea{width:95%;min-height:75px}select,input{font-size:16px;margin:5px}button{padding:12px}summary{cursor:pointer}label{display:block}</style><h1>匿名人工复核</h1><p>先核对全部30份原始输出，不修改作品。只对标有“详细评分”的六份给3个分数和一条证据说明。F必须联系给定原文，分别填写作品引文和原文依据；遗漏可留空作品引文。评分时不得查看Kimi结果。</p><label>评审者<input id="who"></label><button onclick="download()">保存 review.json</button><p id="status"></p><details><summary>评分锚点</summary><pre id="rubric"></pre></details><main id="cards"></main><script>const DATA=__DATA__;const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));document.getElementById('rubric').textContent=DATA.rubric.dimensions.map(d=>d.id+' '+d.name+'\\n'+d.question+'\\n'+Object.entries(d.anchors).map(([k,v])=>k+'：'+v).join('\\n')+'\\n'+d.do_not).join('\\n\\n');const box=document.getElementById('cards');DATA.cards.forEach((c,i)=>{const a=document.createElement('article');a.innerHTML='<h2>'+esc(c.sample_id)+' / '+esc(c.case_id)+(c.detailed?' — 详细评分':' — 阅读核对')+'</h2><details><summary>原文与任务</summary><pre>'+esc(JSON.stringify({TASK:c.task},null,2))+'</pre></details><details open><summary>逐字内容的阅读视图（只替换ID显示名称）</summary><pre>'+esc(c.display)+'</pre></details><details><summary>原始JSON／原始回答</summary><pre>'+esc(c.output)+'</pre></details><label><input type="checkbox" id="read'+i+'">我已阅读并核对本份原始输出，未替模型改写</label>'+(c.detailed?['F','D','L'].map(k=>'<label>'+k+'<select id="'+k+i+'"><option value="">请选择</option>'+[0,1,2,3,4].map(n=>'<option>'+n+'</option>').join('')+'</select></label>').join('')+'<label>关键依据（三维可共用一条说明）<textarea id="note'+i+'"></textarea></label><label>作品逐字引文（只复制正文，不带视图添加的标签）；遗漏可空<input id="quote'+i+'"></label><label>原文逐字依据（从上方原文复制，不写出处）<input id="refs'+i+'" placeholder="原文中的一段文字"></label>':'');box.appendChild(a)});function download(){const f=structuredClone(DATA.form);f.reviewer=document.getElementById('who').value.trim();f.reviewed_at=new Date().toISOString();let ok=!!f.reviewer;f.items.forEach((r,i)=>{r.read_and_integrity_checked=document.getElementById('read'+i).checked;ok&&=r.read_and_integrity_checked;if(r.scores){for(const k of ['F','D','L']){let v=document.getElementById(k+i).value;r.scores[k]=v===''?null:Number(v);ok&&=v!=='';}r.evidence_note=document.getElementById('note'+i).value.trim();r.quote=document.getElementById('quote'+i).value;r.source_quote=document.getElementById('refs'+i).value;ok&&=!!r.evidence_note&&!!r.source_quote.trim();}});if(!ok){document.getElementById('status').textContent='请完成30项阅读核对、6份三维评分、证据及姓名。';return;}let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(f,null,2)],{type:'application/json'}));a.download='review.json';a.click();}</script>'''.replace('__DATA__',payload)
    (W/'review.html').write_text(page,encoding='utf8')
    return {'review_file':str(W/'review.html'),'detailed_responses':6,'numeric_ratings':18,'integrity_checks':30}

def seal_human():
    assert_frozen(); rows=assert_primary_complete(); f=load(W/'review.json'); cfg=config()
    if (W/'human.seal.json').exists(): raise ValueError('Seal exists')
    if readrows(W/'judges.jsonl'): raise ValueError('Judge already ran; cannot claim independent pre-judge human review')
    if not nonblank(f.get('reviewer')) or not nonblank(f.get('reviewed_at')): raise ValueError('Human identity/time missing')
    if f.get('rubric_sha256')!=digest((ROOT/'rubric.json').read_bytes()): raise ValueError('Wrong rubric')
    byblind={blind_id(k):v for k,v in rows.items()}; items=f['items']
    if len(items)!=30 or {x['sample_id'] for x in items}!=set(byblind): raise ValueError('Review coverage')
    for item in items:
        r=byblind[item['sample_id']]; cid=r['case_id']; detailed=r['run_id'] in set(human_assignment().values())
        if item.get('read_and_integrity_checked') is not True or item['output_sha256']!=digest(r['output']): raise ValueError('Unread or changed output')
        if detailed:
            scores=item.get('scores'); c=cases()[cid]
            if not isinstance(scores,dict) or set(scores)!={'F','D','L'} or any(type(v)is not int or v not in range(5) for v in scores.values()): raise ValueError('Need three integer human scores')
            if not nonblank(item.get('evidence_note')) or not nonblank(item.get('source_quote')) or item['source_quote'] not in c['task']['source_text']: raise ValueError('Human source evidence missing or not in supplied text')
            quote=item.get('quote','')
            try: strings=list(walk_strings(strict_json(r['output'])))
            except ValueError: strings=[]
            if quote and quote not in r['output'] and not any(quote in s for s in strings): raise ValueError('Human quote not in candidate')
    seal={'sealed_at':now(),'review_sha256':digest(f),'output_hashes':{k:digest(v['output']) for k,v in rows.items()},'reviewer':f['reviewer'],'human_cases':cfg['human_cases']}
    save(W/'human.seal.json',seal); return {'status':'human_sealed','scores':18}

def current_judge_hash(): return digest({'prompt':(ROOT/'JUDGE.md').read_text(),'rubric':rubric()})
def lock_judge(reason):
    assert_human_sealed(); js=readrows(W/'judges.jsonl'); cfg=config(); dev={human_assignment()[c] for c in cfg['judge_dev']}
    current=[j for j in js if j['phase']=='dev' and j['judge_hash']==current_judge_hash()]
    if not dev <= {j['generation_id'] for j in current}: raise ValueError('Run all three development judgments under the current prompt first')
    for j in current:
        rid=j['generation_id']; c=cases()[generations()[rid]['case_id']]
        if j['status']!='completed' or validate_judge(strict_json(j['output']),generations()[rid]['output'],c['task']['source_text'],blind_id(rid)): raise ValueError('Development judge schema/evidence is invalid')
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
        if rid in seen or rid not in index: raise ValueError('Adjudication identity/duplicate')
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
        r.update(combine(r['hard'],{'dimensions':[{'id':k,'score':v} for k,v in ss.items()]})); r['status']='human_adjudicated'
def score_all():
    assert_human_sealed(); lock=load(W/'judge.lock.json')
    if lock['judge_hash']!=current_judge_hash(): raise ValueError('Judge prompt/rubric changed after lock')
    js=readrows(W/'judges.jsonl'); last={}
    for j in js:
        if j['judge_hash']==lock['judge_hash']:
            if j['generation_id'] in last: raise ValueError('Duplicate same-version judge; explicit adjudication required')
            last[j['generation_id']]=j
    result=[]; cs=cases()
    for rid,r in sorted(generations().items()):
        c=cs[r['case_id']]; h=grade(r['output'],c['task']); jr=last.get(rid); x={'run_id':rid,'case_id':c['id'],'family':c['family'],'model':r['model'],'hard':h,'judge':jr,'score':None,'pass':None,'status':'judge_missing'}
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
        rr=[r for r in result if r['model']==model]; complete=len(rr)==10 and all(r['score'] is not None for r in rr); fam={}
        for r in rr: fam.setdefault(r['family'],[]).append(r['score'])
        totals[model]={'status':'complete' if complete else 'incomplete','scored':sum(r['score'] is not None for r in rr),'scheduled':10,'mean_10_cases':sum(r['score'] for r in rr)/10 if complete else None,'mean_8_families':sum(sum(v)/len(v) for v in fam.values())/8 if complete else None,'pass_count':sum(r['pass'] is True for r in rr),'hard_pass_count':sum(r['hard']['hard_pass'] for r in rr),'judge_only_mean':sum(r['judge_score'] for r in rr)/10 if len(rr)==10 and all(r['judge_score'] is not None for r in rr) else None,'adjudicated_count':sum('adjudication' in r for r in rr),'score_basis':'human_audited' if any('adjudication' in r for r in rr) else 'judge_only','mean_H':sum(r['hard']['H'] for r in rr)/10 if len(rr)==10 else None,'mean_quality':{k:sum(r['quality'][k] for r in rr)/10 for k in ['F','D','L']} if complete else None}
    out={'generated_at':now(),'judge_hash':lock['judge_hash'],'totals':totals,'results':result}; save(W/'scores.json',out); return out

def compare(phase):
    assert_human_sealed(); cfg=config(); wanted=cfg['judge_dev'] if phase=='dev' else cfg['judge_validation']; human={x['sample_id']:x for x in load(W/'review.json')['items']}; rows=generations(); out=[]
    for cid in wanted:
        rid=human_assignment()[cid]; matches=[j for j in readrows(W/'judges.jsonl') if j['generation_id']==rid]
        if not matches: raise ValueError('Missing judge: '+rid)
        j=matches[-1]; parsed=strict_json(j['output']); errors=validate_judge(parsed,rows[rid]['output'],cases()[cid]['task']['source_text'],blind_id(rid))
        if errors: out.append({'case_id':cid,'errors':errors}); continue
        scores=human[blind_id(rid)]['scores']
        for dd in parsed['dimensions']:
            v=dd['score']; out.append({'case_id':cid,'dimension':dd['id'],'human':scores[dd['id']],'judge':v,'absolute_difference':abs(scores[dd['id']]-v) if v is not None else None})
    ds=[x['absolute_difference'] for x in out if x.get('absolute_difference') is not None]
    return {'phase':phase,'rows':out,'MAE':sum(ds)/len(ds) if ds else None,'within_one':sum(v<=1 for v in ds)/len(ds) if ds else None,'dimension_decisions':len(ds),'case_count':3,'source_families':len({cases()[c]['family'] for c in wanted}),'warning':'Diagnostic small sample, not independent statistical reliability evidence.'}

def export_final(report,sft,incident,mode):
    scores=score_all()
    if any(t['status']!='complete' for t in scores['totals'].values()): raise ValueError('Incomplete 3x10 scores; resolve missing/uncertain judgments transparently first')
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
        r=generations()[x['run_id']]; append(out/'results.jsonl',{'kind':'primary',**x,'generation':r,'human':human[blind_id(x['run_id'])]})
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
    sp.add_parser('review'); sp.add_parser('seal')
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
