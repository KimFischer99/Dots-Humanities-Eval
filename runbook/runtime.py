#!/usr/bin/env python3
"""Pinned Pi in a disposable Docker sandbox; fixed-route audited relay outside Pi.
Subcommands: build, probe, run, judge. Gateway/worker are internal container modes.
No semantic fallback, best-of-N, automatic answer repair, or direct judge API bypass.
"""
from __future__ import annotations
import argparse, base64, copy, hashlib, hmac, json, os, random, secrets, selectors, signal
import subprocess as sub, sys, threading, time, socket, re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
import ssl
import eval as e

ALLOWED_FIELDS={'thinking','reasoning_effort','enable_thinking','chat_template_kwargs'}
def text_content(v):
    if isinstance(v,str): return v
    if isinstance(v,list) and all(isinstance(b,dict) and b.get('type')=='text' and isinstance(b.get('text'),str) for b in v): return ''.join(b['text'] for b in v)
    raise ValueError('Only plain text messages are permitted')

def transform_request(body,job):
    if body.get('model')!='eval-model': raise ValueError('Wrong model alias')
    if {'enable_search','web_search_options','search_options','search_parameters','plugins'} & body.keys(): raise ValueError('Network search is forbidden')
    ms=body.get('messages')
    if not isinstance(ms,list) or len(ms)<2: raise ValueError('Missing messages')
    if ms[0].get('role')!='system' or ms[1].get('role')!='user': raise ValueError('First two roles must be system/user')
    system=text_content(ms[0].get('content')); user=text_content(ms[1].get('content'))
    permitted={job['system'],job['system']+'\n\n<cwd>\n/workspace\n</cwd>'}
    if system not in permitted: raise ValueError('Unexpected Pi system injection; inspect pinned source, do not whitelist arbitrary context')
    if user!=job['user']: raise ValueError('User prompt changed')
    tools=job['tools']
    if not tools:
        if len(ms)!=2 or body.get('tools') or any(m.get('tool_calls') for m in ms): raise ValueError('Tool/history leakage in text-only trial')
    else:
        names={t.get('function',{}).get('name') for t in body.get('tools',[])}
        if not names or not names<={'read','write','bash'}: raise ValueError('Unexpected tool schema')
        if any(m.get('role') not in ('assistant','tool') for m in ms[2:]): raise ValueError('New user/system message in tool loop')
    provider=job['provider']; overrides=provider['overrides']
    if not set(overrides)<=ALLOWED_FIELDS: raise ValueError('Unauthorized request rewrite')
    # Only model routing and documented generation parameters change. Message/tool
    # schemas pass unchanged. Sampling parameters are fixed before formal runs.
    wire=copy.deepcopy(body)
    for k in ['temperature','top_p','seed','max_tokens','max_completion_tokens','reasoning_effort','thinking','enable_thinking','chat_template_kwargs','store']:
        wire.pop(k,None)
    wire['model']=provider['id']; wire[provider['token_field']]=job['max_tokens']; wire.update(overrides)
    sampling=job.get('sampling',{})
    if not set(sampling)<={'temperature','top_p'}: raise ValueError('Unsupported sampling override')
    wire.update(sampling)
    return wire,{'system_sha256':e.digest(system),'user_sha256':e.digest(user)}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kw): return None
class Relay(HTTPServer):
    def __init__(self,job):
        super().__init__(('0.0.0.0',8080),Handler); self.job=job; self.count=0
        self.opener=build_opener(NoRedirect(),HTTPSHandler(context=ssl.create_default_context()))
    def record(self,kind,**kw): e.append('/log/relay.jsonl',{'run_id':self.job['run_id'],'at':e.now(),'kind':kind,**kw})
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,code,text):
        b=json.dumps({'error':{'message':text}}).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path=='/health': return self.reply(200,'ready')
        self.reply(404,'not available')
    def do_POST(self):
        job=self.server.job; expected='Bearer '+os.environ.get('EVAL_GATEWAY_TOKEN','')
        if self.path!='/v1/chat/completions': return self.reply(404,'fixed route only')
        if expected=='Bearer ' or not hmac.compare_digest(self.headers.get('Authorization',''),expected): return self.reply(401,'trial token invalid')
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=2*1024*1024: raise ValueError('request size limit')
            body=e.strict_json(self.rfile.read(n).decode('utf8')); wire,hashes=transform_request(body,job)
        except (ValueError,KeyError,TypeError) as exc:
            self.server.record('request_rejected',reason=str(exc)); return self.reply(400,str(exc))
        self.server.count+=1; call=self.server.count
        if call>job['max_requests']:
            self.server.record('request_rejected',reason='call_budget'); return self.reply(429,'trial request budget exhausted')
        self.server.record('request',call=call,pi_request=body,wire_request=wire,prompt_hashes=hashes,endpoint=job['provider']['url'])
        key=os.environ['UPSTREAM_KEY']; p=job['provider']; req=Request(p['url'],data=json.dumps(wire,ensure_ascii=False).encode('utf8'),method='POST',headers={p['auth_header']:p['auth_prefix']+key,'Content-Type':'application/json','Accept':'text/event-stream'})
        began=False; count=0; start=time.monotonic()
        try:
            with self.server.opener.open(req,timeout=job['deadline_seconds']) as response:
                self.server.record('response_start',call=call,http_status=response.status,content_type=response.headers.get('Content-Type',''),request_id=response.headers.get('x-request-id') or response.headers.get('request-id'))
                self.send_response(response.status); self.send_header('Content-Type',response.headers.get('Content-Type','application/octet-stream')); self.send_header('Connection','close'); self.end_headers(); self.close_connection=True; began=True
                while True:
                    chunk=response.read1(8192)
                    if not chunk: break
                    count+=len(chunk)
                    if count>16*1024*1024: raise ValueError('response byte limit')
                    self.server.record('response_chunk',call=call,encoding='base64',data=base64.b64encode(chunk).decode('ascii'))
                    self.wfile.write(chunk); self.wfile.flush()
                self.server.record('response_end',call=call,status='complete',bytes=count,elapsed_seconds=time.monotonic()-start)
        except HTTPError as exc:
            raw=exc.read(1024*1024); clean=raw.replace(key.encode(),b'[REDACTED_API_KEY]')
            self.server.record('response_error',call=call,http_status=exc.code,raw_sha256=e.digest(raw),body=clean.decode('utf8','replace'),credential_redacted=clean!=raw)
            self.reply(exc.code,'upstream rejected request; inspect private audit without credentials')
        except (URLError,OSError,ValueError,TimeoutError) as exc:
            self.server.record('transport_error',call=call,error_type=type(exc).__name__,body_started=began,bytes=count)
            if not began:
                try:self.reply(502,'upstream transport failure')
                except OSError:pass
            self.close_connection=True

def wire_metadata(records):
    streams={}; models=set(); reasons=set(); usages={}; thinking=False
    for row in records:
        if row.get('kind')=='response_chunk': streams.setdefault(row['call'],bytearray()).extend(base64.b64decode(row['data']))
    for call,buf in streams.items():
        text=bytes(buf).decode('utf8','replace'); objects=[]
        for line in text.splitlines():
            if line.startswith('data:'):
                part=line[5:].strip()
                if part=='[DONE]': continue
                try: objects.append(json.loads(part))
                except ValueError: pass
        if not objects:
            try: objects=[json.loads(text)]
            except ValueError: pass
        for obj in objects:
            if obj.get('model'): models.add(obj['model'])
            if obj.get('usage'): usages[str(call)]=obj['usage']
            for choice in obj.get('choices',[]):
                if choice.get('finish_reason'): reasons.add(choice['finish_reason'])
                msg=choice.get('delta') or choice.get('message') or {}
                thinking |= bool(msg.get('reasoning_content') or msg.get('reasoning'))
    return {'response_model_ids':sorted(models),'finish_reasons':sorted(reasons),'usage_by_call':usages,'reasoning_content_observed':thinking,'api_call_count':len(streams)}

def final_assistant(events):
    last=None
    for ev in events:
        if ev.get('type')=='message_end' and ev.get('message',{}).get('role')=='assistant': last=ev['message']
        if ev.get('type')=='agent_end':
            aa=[m for m in ev.get('messages',[]) if m.get('role')=='assistant']
            if aa: last=aa[-1]
    if last is None: return None,None
    cc=last.get('content',[])
    return cc if isinstance(cc,str) else ''.join(b.get('text','') for b in cc if b.get('type')=='text'),last

def worker():
    if os.environ.get('EVAL_SANDBOX')!='1' or Path.cwd()!=Path('/workspace'): raise ValueError('Worker must run inside sandbox at /workspace')
    job=e.load('/job/worker.json'); home=Path('/tmp/pi-agent'); home.mkdir(parents=True,exist_ok=True)
    settings={'compaction':{'enabled':False},'retry':{'enabled':False,'provider':{'maxRetries':0}},'cacheWarming':'off','enableInstallTelemetry':False,'enableAnalytics':False,'defaultProjectTrust':'never','packages':[],'skills':[],'extensions':[],'prompts':[],'defaultTools':[]}
    e.save(home/'settings.json',settings)
    models={'providers':{'eval-gateway':{'baseUrl':'http://eval-gateway:8080/v1','api':'openai-completions','apiKey':'${EVAL_GATEWAY_TOKEN}','models':[{'id':'eval-model','name':'Eval model','reasoning':True,'compat':{'supportsDeveloperRole':False},'input':['text'],'contextWindow':262144,'maxTokens':job['max_tokens']}]}}}
    e.save(home/'models.json',models)
    os.environ.update(HOME='/tmp/home',PI_CODING_AGENT_DIR=str(home),PI_OFFLINE='1',PI_SKIP_VERSION_CHECK='1',PI_TELEMETRY='0')
    Path('/tmp/home').mkdir(exist_ok=True)
    # Pi's nominal effort is not an upstream cross-provider budget. The gateway
    # removes it and applies only the frozen provider-specific thinking options.
    args=['/opt/pi/pi','-p','--mode','json','--no-session','--no-extensions','--no-skills','--no-prompt-templates','--no-context-files','--system-prompt',job['system'],'--provider','eval-gateway','--model','eval-model','--thinking','medium']
    args+=['--tools','read,write,bash'] if job['tools'] else ['--no-tools']; args+=[job['user']]
    def emit(kind,**kw): print(json.dumps({'kind':kind,'at':e.now(),**kw},ensure_ascii=False),flush=True)
    checks={'no_upstream_key':not bool(os.environ.get('UPSTREAM_KEY')),'no_host_socket':not Path('/var/run/docker.sock').exists(),'no_evaluator_dataset':not Path('/app/dataset.json').exists(),'no_proxy_env':not any(v for k,v in os.environ.items() if k.lower() in ('http_proxy','https_proxy','all_proxy'))}
    try:
        sock=socket.create_connection(('1.1.1.1',443),timeout=1); sock.close(); checks['external_tcp_denied']=False
    except OSError: checks['external_tcp_denied']=True
    try:
        socket.getaddrinfo('example.com',443); checks['external_dns_denied']=False
    except OSError: checks['external_dns_denied']=True
    emit('sandbox_checks',checks=checks)
    if not all(checks.values()):
        raise ValueError('Sandbox isolation check failed')
    pi_version=sub.check_output(['/opt/pi/pi','--version'],text=True).strip()
    proc=sub.Popen(args,stdout=sub.PIPE,stderr=sub.PIPE,start_new_session=True); sel=selectors.DefaultSelector(); sel.register(proc.stdout,selectors.EVENT_READ,'stdout'); sel.register(proc.stderr,selectors.EVENT_READ,'stderr')
    pending=b''; events=[]; total=tool_calls=0; stop=None; start=time.monotonic()
    emit('worker_start',pi_version=pi_version,cwd='/workspace',tools=job['tools'])
    try:
        while sel.get_map():
            if time.monotonic()-start>job['deadline_seconds']: stop='wall_timeout'; break
            for key,_ in sel.select(.2):
                chunk=os.read(key.fileobj.fileno(),8192)
                if not chunk: sel.unregister(key.fileobj); continue
                total+=len(chunk); emit('pi_'+key.data,encoding='base64',data=base64.b64encode(chunk).decode('ascii'))
                if total>32*1024*1024: stop='log_budget'; break
                if key.data=='stdout':
                    pending+=chunk
                    while b'\n' in pending:
                        line,pending=pending.split(b'\n',1)
                        if not line.strip(): continue
                        try: ev=json.loads(line); events.append(ev)
                        except ValueError: continue
                        if ev.get('type')=='tool_execution_start': tool_calls+=1
                        if tool_calls>(job['tool_limit'] if job['tools'] else 0): stop='tool_budget'; break
                if stop: break
            if stop: break
        if stop and proc.poll() is None: os.killpg(proc.pid,signal.SIGKILL)
        try: rc=proc.wait(timeout=5)
        except sub.TimeoutExpired: os.killpg(proc.pid,signal.SIGKILL); rc=proc.wait()
        if pending.strip():
            try: events.append(json.loads(pending))
            except ValueError: pass
        text,msg=final_assistant(events); artifact=None; f=Path('/workspace/script.json')
        if f.is_file() and not f.is_symlink() and f.stat().st_size<=262144: artifact=f.read_text(encoding='utf8',errors='replace')
        emit('worker_result',output=text,assistant_message=msg,exit_code=rc,stop=stop,tool_calls=tool_calls,artifact_text=artifact,elapsed_seconds=time.monotonic()-start)
    finally:
        if proc.poll() is None: os.killpg(proc.pid,signal.SIGKILL)
        sel.close()

def cmd(args,**kw):
    r=sub.run(args,check=True,text=True,stdout=sub.PIPE,stderr=sub.PIPE,**kw); return r.stdout.strip()
def image_id(): return cmd(['docker','image','inspect',e.config()['image_tag'],'--format','{{.Id}}'])
def build():
    cfg=e.config(); e.W.mkdir(exist_ok=True)
    base='python:3.12-slim-bookworm'; cmd(['docker','pull','--platform','linux/amd64',base])
    pinned=cmd(['docker','image','inspect',base,'--format','{{index .RepoDigests 0}}'])
    cmd(['docker','build','--platform','linux/amd64','--build-arg','BASE_IMAGE='+pinned,'--build-arg','PI_URL='+cfg['pi_url'],'--build-arg','PI_SHA256='+cfg['pi_sha256'],'-t',cfg['image_tag'],str(e.ROOT)],timeout=600)
    x={'built_at':e.now(),'base_digest':pinned,'pi_sha256':cfg['pi_sha256'],'image_id':image_id(),'platform':'linux/amd64','docker_server_version':cmd(['docker','version','--format','{{.Server.Version}}']),'host_python':sys.version,'runtime_hashes':{n:e.digest((e.ROOT/n).read_bytes()) for n in ['runtime.py','eval.py']}}; e.save(e.W/'build.json',x); return x

def read_keys():
    p=e.ROOT/'.env'; vals={}
    if p.exists():
        for line in p.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#'):
                k,v=line.split('=',1); vals[k.strip()]=v.strip().strip('\"').strip("'")
    for v in e.config()['providers'].values():
        k=v['key_env']; vals[k]=os.environ.get(k,vals.get(k,''))
        if not vals[k] or '\n' in vals[k] or '\r' in vals[k]: raise ValueError('Missing/invalid key: '+k)
    return vals

def run_job(run_id,model,system,user,task=None,tools=False,judge=False):
    if (e.W/'freeze.json').exists(): e.assert_frozen()
    e.reject_citations(system); e.reject_citations(user)
    if task is not None:
        if system!=e.generation_system(task) or user!=e.user_prompt(task): raise ValueError('Generation must load the complete current Skill and citation-free task')
        task=e.model_task(task)
    cfg=e.config(); iid=image_id(); provider=cfg['providers'][model]; u=urlsplit(provider['url'])
    if u.scheme!='https' or u.username or u.password or u.query or u.fragment: raise ValueError('Endpoint must be fixed HTTPS without credentials/query/fragment')
    keys=read_keys(); token=secrets.token_urlsafe(32); nonce=secrets.token_hex(6); net='eval-'+nonce; gw='eval-gw-'+nonce; agent='eval-pi-'+nonce
    folder=e.W/'jobs'/run_id
    if folder.exists(): raise ValueError('Job exists; do not overwrite attempts. Resolve infrastructure failure explicitly.')
    folder.mkdir(parents=True); jobdir=folder/'worker'; relaydir=folder/'relay'; logs=folder/'logs'
    for p in [jobdir,relaydir,logs]:p.mkdir(); p.chmod(0o755)
    logs.chmod(0o777)
    policy=e.load(e.W/'judge_execution_plan.json') if judge and (e.W/'judge_execution_plan.json').exists() else {}
    deadline=policy.get('deadline_seconds',cfg['deadline_seconds'])
    common={'run_id':run_id,'system':system,'user':user,'tools':tools,'max_tokens':cfg['judge_max_output_tokens'] if judge else cfg['max_output_tokens'],'deadline_seconds':deadline,'tool_limit':cfg['tool_call_limit']}
    e.save(jobdir/'worker.json',common); e.save(jobdir/'task.json',task or {})
    job={**common,'provider':provider,'sampling':cfg['sampling']['judge' if model=='J' else 'generators'],'max_requests':cfg['request_limit_tools'] if tools else cfg['request_limit_primary']}; e.save(relaydir/'relay.json',job)
    # Credentials exist only in a short-lived host-side env file and relay env.
    envfile=folder/'relay.env'; envfile.write_text('UPSTREAM_KEY='+keys[provider['key_env']]+'\nEVAL_GATEWAY_TOKEN='+token+'\n'); envfile.chmod(0o600)
    sandboxenv=folder/'agent.env'; sandboxenv.write_text('EVAL_GATEWAY_TOKEN='+token+'\nEVAL_SANDBOX=1\n'); sandboxenv.chmod(0o600)
    options=['--platform','linux/amd64','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit=128','--memory=2g','--cpus=2','--user','10001:10001']
    worker_rows=[]; rc=-1; wrapper_error=None
    try:
        cmd(['docker','network','create','--internal',net])
        cmd(['docker','create','--name',gw,*options,'--network','bridge','--env-file',str(envfile),'--tmpfs','/tmp:rw,nosuid,nodev,size=64m','--mount',f'type=bind,src={relaydir},dst=/job,readonly','--mount',f'type=bind,src={logs},dst=/log',iid,'python','/app/runtime.py','gateway'])
        cmd(['docker','network','connect','--alias','eval-gateway',net,gw]); cmd(['docker','start',gw])
        ready=False
        for _ in range(30):
            try:
                cmd(['docker','exec',gw,'python','-c',"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=1).read()"]); ready=True; break
            except sub.CalledProcessError: time.sleep(.2)
        if not ready: raise ValueError('Relay failed readiness check')
        gwip=cmd(['docker','inspect',gw,'--format','{{(index .NetworkSettings.Networks "'+net+'").IPAddress}}'])
        argv=['docker','run','--name',agent,*options,'--network',net,'--dns','127.0.0.1','--add-host','eval-gateway:'+gwip,'--env-file',str(sandboxenv),'--tmpfs','/tmp:rw,nosuid,nodev,size=256m','--tmpfs','/workspace:rw,nosuid,nodev,size=32m,uid=10001,gid=10001','--mount',f'type=bind,src={jobdir},dst=/job,readonly','--workdir','/workspace',iid,'python','/app/runtime.py','worker']
        with (folder/'worker.stdout').open('wb') as out,(folder/'worker.stderr').open('wb') as err:
            try: r=sub.run(argv,stdout=out,stderr=err,timeout=deadline+30); rc=r.returncode
            except sub.TimeoutExpired: wrapper_error='docker_wall_timeout'
        for line in (folder/'worker.stdout').read_text(errors='replace').splitlines():
            try: worker_rows.append(json.loads(line))
            except ValueError: worker_rows.append({'kind':'wrapper_non_json','text':line})
    finally:
        for name in [agent,gw]:
            sub.run(['docker','rm','-f',name],stdout=sub.DEVNULL,stderr=sub.DEVNULL)
        sub.run(['docker','network','rm',net],stdout=sub.DEVNULL,stderr=sub.DEVNULL)
        envfile.unlink(missing_ok=True); sandboxenv.unlink(missing_ok=True)
    relay=e.readrows(logs/'relay.jsonl'); first=next((r for r in relay if r['kind']=='request'),None)
    e.append(e.W/'prompts.jsonl',{'run_id':run_id,'at':e.now(),'model_label':model,'requested_system':system,'skill_body_sha256':e.digest(e.generation_system()) if task is not None else None,'user':user,'effective_request':first['wire_request'] if first else None,'image_id':iid})
    e.append(e.W/'trajectory.jsonl',{'run_id':run_id,'kind':'run_start','at':e.now(),'image_id':iid,'model_label':model,'tools':tools,'max_tokens':common['max_tokens']})
    for r in relay+worker_rows: e.append(e.W/'trajectory.jsonl',{'run_id':run_id,**r})
    if (folder/'worker.stderr').exists(): e.append(e.W/'trajectory.jsonl',{'run_id':run_id,'kind':'wrapper_stderr','text':(folder/'worker.stderr').read_text(errors='replace')})
    last=next((r for r in reversed(worker_rows) if r.get('kind')=='worker_result'),{})
    badwire=any(r['kind'] in ['transport_error','response_error','request_rejected'] for r in relay)
    complete=rc==0 and last.get('output') is not None and not last.get('stop') and not badwire and any(r['kind']=='response_end' and r['status']=='complete' for r in relay)
    # The raw finish/stop reason is preserved: token truncation is a model result,
    # not an excuse to obtain another answer. No post-hoc answer selection.
    return {'run_id':run_id,'model':model,'status':'completed' if complete else 'infrastructure_failure','output':last.get('output') or '', 'output_sha256':e.digest(last.get('output') or ''),'pi_result':last,'docker_exit_code':rc,'wrapper_error':wrapper_error,'wire_errors':badwire,'api_metadata':wire_metadata(relay),'effective_system_sha256':first['prompt_hashes']['system_sha256'] if first else None,'image_id':iid,'reported_pi_version':next((x['pi_version'] for x in worker_rows if x.get('kind')=='worker_start'),None),'sandbox_checks':next((x['checks'] for x in worker_rows if x.get('kind')=='sandbox_checks'),None),'at':e.now()}

def token_budget_exhausted(result):
    reasons=set(result.get('api_metadata',{}).get('finish_reasons',[]))
    reasons.add((result.get('pi_result',{}).get('assistant_message') or {}).get('stopReason'))
    return bool(reasons & {'length','max_tokens','max_output_tokens'})

def probe():
    e.check_kit(); cfg=e.config(); result=[]
    build_info=e.load(e.W/'build.json')
    if build_info['runtime_hashes']!={n:e.digest((e.ROOT/n).read_bytes()) for n in ['runtime.py','eval.py']}: raise ValueError('Runtime changed after build; rebuild image before probe')
    # Original engineering fixture, never a scored literary case. K3 only checks
    # connectivity here; no candidate assessment is performed before human seal.
    task={'source_id':'SMOKE','source_text':'小雨把误拿的杯子放回桌上，对店员道歉。店员把她自己的杯子递给她。','target_seconds':30,'interior_policy':'forbid','output_language':'zh'}
    for m in cfg['primary_models']:
        r=run_job('probe-'+m,m,e.generation_system(task),e.user_prompt(task),task); result.append(r)
    r=run_job('probe-J','J','Reply with the single word PONG.','Connectivity check only.',judge=True); result.append(r)
    passed=all(r['status']=='completed' and r.get('reported_pi_version') and re.search(r'\b0\.87\.1\b',r['reported_pi_version']) and all((r.get('sandbox_checks') or {'missing':False}).values()) for r in result) and len({r['effective_system_sha256'] for r in result[:3]})==1
    for r in result:
        expected=cfg['providers'][r['model']]['id']; actual=r['api_metadata']['response_model_ids']
        if actual and not all(v==expected or v.startswith(expected+'-') for v in actual): passed=False
        if r['model']!='J' and not r['api_metadata']['reasoning_content_observed']: passed=False
        if r['model']=='J' and r['output'].strip()!='PONG': passed=False
    exhausted=[r['run_id'] for r in result if token_budget_exhausted(r)]
    x={'at':e.now(),'passed':bool(passed and not exhausted),'budget_exhausted_runs':exhausted,'image_id':image_id(),'artifact_hashes':e.hashes(),'results':result,'note':'Thinking-on transport/system and token-budget probe; truncated probes cannot authorize freeze. Formal-run truncations remain model results without automatic retries. Not a claim of equal reasoning compute or literary quality.'}; e.save(e.W/'probe.json',x); return x

def run_phase(phase):
    lock=e.assert_frozen()
    if image_id()!=lock['image_id']: raise ValueError('Image drift')
    cfg=e.config(); cs=e.cases(); jobs=[]
    if phase=='primary':
        # Interleaved model order for each shuffled case, not all M1 then all M2.
        cc=list(cs); rng=random.Random(cfg['seed']); rng.shuffle(cc)
        for cid in cc:
            mm=list(cfg['primary_models']); rng.shuffle(mm)
            for m in mm: jobs.append((f'{m}.{cid}',m,cid,cs[cid]['task'],False,'primary'))
    else:
        for side in e.data()['side_cases']:
            for m in side['models']:
                task=side.get('task',cs[side['base_case']]['task']); jobs.append((f"{m}.{side['id']}",m,side['id'],task,side['kind']=='tools','side'))
    existing=e.generations(primary=False)
    for rid,m,cid,task,tools,kind in jobs:
        if rid in existing: continue
        r=run_job(rid,m,e.generation_system(task),e.user_prompt(task),task,tools); r.update(case_id=cid,kind=kind); e.append(e.W/'generations.jsonl',r)
        if r['status']!='completed': raise ValueError('Stopped after infrastructure failure: '+rid+'; keep evidence, do not silently retry')
    return {'status':'phase_finished','phase':phase,'planned_jobs':len(jobs)}

def run_judge(phase):
    e.assert_human_sealed()
    if image_id()!=e.load(e.W/'freeze.json')['image_id']: raise ValueError('Judge image drift')
    cs=e.cases(); rows=e.generations(); h=e.current_judge_hash(); hist=e.active_judgments()
    if phase=='dev':
        if (e.W/'judge.lock.json').exists(): raise ValueError('Judge already locked; use rest to ensure final-version dev scores')
        wanted=e.judge_run_ids('dev')
    else:
        lock=e.load(e.W/'judge.lock.json')
        if lock['judge_hash']!=h: raise ValueError('Judge changed after lock')
        wanted=e.judge_run_ids(phase)
        if phase=='rest' and e.compare('validation')['status']!='complete': raise ValueError('Complete valid untouched validation before rest')
    for rid in wanted:
        previous=[j for j in hist if j['generation_id']==rid and j['judge_hash']==h]
        if len(previous)>1: raise ValueError('Duplicate current-version Judge records')
        if previous and previous[-1]['status']=='completed':
            if e.validate_judge(e.strict_json(previous[-1]['output'])): raise ValueError('Existing Judge scores are invalid; no automatic retry')
            continue
        retry_of=None
        if previous:
            policy=e.load(e.W/'judge_execution_plan.json')
            retry_of=previous[-1]['run_id']
            if retry_of not in policy.get('authorized_retry_run_ids',[]) or previous[-1].get('output'):
                raise ValueError('Failed Judge attempt requires explicit recorded retry authorization')
        r=rows[rid]; c=cs[r['case_id']]; sample=e.blind_id(rid)
        payload=e.judge_payload(sample,c['task'],r['output'])
        attempt_id='judge-'+phase+'-'+sample+'-'+h[:10]+('-attempt2' if retry_of else '')
        print(json.dumps({'event':'judge_start','phase':phase,'sample_id':sample,'attempt':2 if retry_of else 1}),flush=True)
        jr=run_job(attempt_id,'J',(e.ROOT/'JUDGE.md').read_text().strip(),json.dumps(payload,ensure_ascii=False,separators=(',',':')),judge=True)
        jr.update(generation_id=rid,phase=phase,judge_hash=h,human_seal_sha256=e.digest(e.load(e.W/'human.seal.json')))
        if retry_of: jr['retry_of']=retry_of
        e.append(e.W/'judges.jsonl',jr)
        print(json.dumps({'event':'judge_end','phase':phase,'sample_id':sample,'status':jr['status']}),flush=True)
        if jr['status']!='completed': raise ValueError('Judge infrastructure failure; no fallback judge or repair')
        if e.validate_judge(e.strict_json(jr['output'])): raise ValueError('Judge scores are invalid; original output retained, no automatic retry')
    return {'status':'judge_phase_finished','phase':phase,'judge_hash':h}

def main():
    p=argparse.ArgumentParser(description=__doc__); sp=p.add_subparsers(dest='cmd',required=True)
    for n in ['build','probe','gateway','worker']: sp.add_parser(n)
    a=sp.add_parser('run');a.add_argument('--phase',choices=['primary','side'],default='primary')
    a=sp.add_parser('judge');a.add_argument('--phase',choices=['dev','validation','rest'],required=True)
    a=p.parse_args()
    try:
        if a.cmd=='gateway':
            job=e.load('/job/relay.json'); Relay(job).serve_forever(); return 0
        if a.cmd=='worker': worker(); return 0
        if a.cmd=='build': out=build()
        elif a.cmd=='probe': out=probe()
        elif a.cmd=='run': out=run_phase(a.phase)
        else: out=run_judge(a.phase)
        print(json.dumps(out,ensure_ascii=False,indent=2)); return 0
    except (ValueError,KeyError,FileNotFoundError,sub.CalledProcessError) as exc:
        # Never print the command/environment: they can contain ephemeral tokens.
        print('BLOCKED: '+(str(exc) if not isinstance(exc,sub.CalledProcessError) else 'Docker command failed; inspect local runtime.'),file=sys.stderr); return 2
if __name__=='__main__':raise SystemExit(main())
