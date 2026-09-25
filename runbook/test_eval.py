"""Offline contract tests only. Synthetic responses are NOT model eval results."""
import copy, json, shutil, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
import eval as e
import runtime as r

def fixture(task,characters=False):
    # Deliberately mechanically valid and aesthetically bad, not a gold example.
    sc={'sceneId':'L01','characters':['P01'] if characters else [],'flow':[{'action':'人物停下。'} for _ in range(int(task['target_seconds']/2.5))]}
    return {'source_id':'TEXT','cast':[{'id':'P01','name':'自报人物'}] if characters else [],'locations':[{'id':'L01','name':'自报场所'}],'scenes':[sc]}
def raw(doc): return json.dumps(doc,ensure_ascii=False)
def judged(rid,score=3):
    return {k:score for k in ['F','D','L']}

class Rules(unittest.TestCase):
    def setUp(self): self.task=copy.deepcopy(e.cases()['C01']['task']); self.doc=fixture(self.task,True)
    def grade(self): return e.grade(raw(self.doc),self.task)
    def test_dataset_contract(self): self.assertEqual(e.check_kit()['primary_cases'],10)
    def test_dataset_metadata_and_task_copies_cannot_drift(self):
        for kind in ['task_copies','character_count','line_range']:
            with self.subTest(kind=kind):
                data=copy.deepcopy(e.data())
                if kind=='task_copies':
                    for case in data['cases'][2:4]: case['task']['source_text']+='\n'
                elif kind=='character_count': data['sources']['RED']['nonspace_characters']+=1
                else: data['sources']['HAM_ZH']['selection']['start_line']=27
                with patch.object(e,'data',return_value=data): self.assertRaises(AssertionError,e.check_kit)
    def test_five_rules_pass(self): self.assertEqual(self.grade()['H'],20)
    def test_schema_extra(self): self.doc['score']=100; self.assertFalse(self.grade()['hard_pass'])
    def test_duplicate_keys(self): self.assertFalse(e.grade('{"source_id":"x","source_id":"y","scenes":[]}',self.task)['hard_pass'])
    def test_nan(self): self.assertRaises(ValueError,e.strict_json,'{"x":NaN}')
    def test_markdown_fence(self): self.assertEqual(e.grade('```json\n'+raw(self.doc)+'\n```',self.task)['H'],0)
    def test_blank_action(self): self.doc['scenes'][0]['flow'][0]['action']=' '; self.assertEqual(self.grade()['H'],0)
    def test_no_action(self): self.doc['scenes'][0]['flow']=[{'speaker':'P01','line':'你好。','mode':'spoken'}]; self.assertEqual(self.grade()['H'],0)
    def test_extra_beat_keys(self): self.doc['scenes'][0]['flow'][0]['speaker']='P01'; self.assertEqual(self.grade()['H'],0)
    def test_wrong_source(self): self.doc['source_id']='NO'; self.assertFalse(self.grade()['rules']['H2']['ok'])
    def test_wrong_cast(self): self.doc['scenes'][0]['characters']=['VO']; self.assertFalse(self.grade()['rules']['H2']['ok'])
    def test_duplicate_cast(self): self.doc['scenes'][0]['characters']=['P01','P01']; self.assertFalse(self.grade()['rules']['H2']['ok'])
    def test_unknown_location(self): self.doc['scenes'][0]['sceneId']='x'; self.assertFalse(self.grade()['rules']['H2']['ok'])
    def test_self_declared_tables_not_input_answers(self):
        self.doc['cast'][0]={'id':'speaker-x','name':'模型自行识别的名字'}
        self.doc['locations'][0]={'id':'place-x','name':'模型自行安排的场所'}
        self.doc['scenes'][0].update(sceneId='place-x',characters=['speaker-x'])
        self.assertTrue(self.grade()['rules']['H2']['ok'])
        view=e.display_script(raw(self.doc),self.task)
        self.assertIn('模型自行识别的名字',view)
        self.assertIn('模型自行安排的场所',view)
    def test_declaration_structure_and_unique_ids(self):
        for key in ['cast','locations']:
            with self.subTest(key=key):
                doc=copy.deepcopy(self.doc); doc[key].append(copy.deepcopy(doc[key][0]))
                result=e.grade(raw(doc),self.task)
                self.assertTrue(result['rules']['H1']['ok']); self.assertFalse(result['rules']['H2']['ok'])
                doc[key][0]['name']=' '
                self.assertFalse(e.grade(raw(doc),self.task)['rules']['H1']['ok'])
    def test_no_predeclared_tables_or_extra_analysis_in_output(self):
        for key in ['cast','locations']:
            doc=copy.deepcopy(self.doc); del doc[key]
            self.assertFalse(e.grade(raw(doc),self.task)['rules']['H1']['ok'])
        self.doc['cast'][0]['role']='预先分析'
        self.assertFalse(self.grade()['rules']['H1']['ok'])
    def test_empty_cast_for_characterless_staging(self):
        self.assertTrue(e.grade(raw(fixture(self.task)),self.task)['hard_pass'])
    def test_length35(self):
        self.doc['scenes'][0]['flow'].append({'speaker':'P01','line':'字'*35,'mode':'spoken'}); self.assertTrue(self.grade()['rules']['H3']['ok'])
    def test_length36(self):
        self.doc['scenes'][0]['flow'].append({'speaker':'P01','line':'字'*36,'mode':'spoken'}); self.assertFalse(self.grade()['rules']['H3']['ok'])
    def test_unicode_codepoints(self): self.assertEqual(e.char_count('🧭 中\n文 e\u0301'),4)
    def test_invisible(self): self.doc['scenes'][0]['flow'][0]['action']='人\u200b物'; self.assertEqual(self.grade()['H'],0)
    def test_duration(self): self.doc['scenes'][0]['flow']*=2; self.assertFalse(self.grade()['rules']['H4']['ok'])
    def test_inner_forbidden(self):
        self.doc['scenes'][0]['flow'].append({'speaker':'P01','line':'怎么回事？','mode':'inner'}); self.assertFalse(self.grade()['rules']['H5']['ok'])
    def test_inner_two_allowed(self):
        self.task['interior_policy']='allow_limited'; self.doc['scenes'][0]['flow'] += [{'speaker':'P01','line':'怎么回事？','mode':'inner'}]*2; self.assertTrue(self.grade()['rules']['H5']['ok'])
    def test_inner_three_denied(self):
        self.task['interior_policy']='allow_limited'; self.doc['scenes'][0]['flow'] += [{'speaker':'P01','line':'怎么回事？','mode':'inner'}]*3; self.assertFalse(self.grade()['rules']['H5']['ok'])
    def test_missing_speaker_membership(self):
        self.doc['scenes'][0]['flow'].append({'speaker':'P04','line':'怎么回事？','mode':'spoken'}); self.assertFalse(self.grade()['rules']['H2']['ok'])
    def test_metadata_not_injected(self): self.assertNotIn('DISTRIBUTION_NOTICE',e.generation_system()); self.assertNotIn('shuohao',e.generation_system())
    def test_task_no_private_reference(self): self.assertNotIn('REFERENCE',e.user_prompt(self.task)); self.assertNotIn('split',e.user_prompt(self.task))
    def test_public_task_drops_provenance_and_preserves_source(self):
        original=copy.deepcopy(self.task)
        self.task.update(citation='PRIVATE_CITATION',reference={'url':'https://private.invalid'},author='PRIVATE_AUTHOR',title='PRIVATE_TITLE',cast=[{'id':'P01','name':'PRIVATE_CAST'}],locations=[{'id':'L01','name':'PRIVATE_LOCATION'}],adaptation_goal='PRIVATE_GOAL',adaptation_limits='PRIVATE_LIMITS')
        public=e.model_task(self.task); prompt=e.user_prompt(self.task)
        self.assertEqual(public['source_id'],'TEXT')
        self.assertEqual(public['source_text'],original['source_text'])
        self.assertNotIn('title',public)
        self.assertNotIn('PRIVATE_',prompt)
        self.assertEqual(set(public),{'source_id','source_text','target_seconds','interior_policy','output_language'})
        self.assertEqual(prompt,original['source_text'])
        self.assertNotIn('PRIVATE_',e.generation_system(self.task))
        self.assertNotIn('PRIVATE_',raw(e.judge_payload('test',self.task,raw(self.doc))))
        self.assertEqual(self.task['source_id'],original['source_id'])
        self.assertEqual(e.model_task(public),public)
    def test_public_task_pairs_keep_only_intended_difference(self):
        for left,right,field in [('C01','C02','interior_policy'),('C03','C04','target_seconds')]:
            a=e.model_task(e.cases()[left]['task']); b=e.model_task(e.cases()[right]['task'])
            self.assertEqual({k for k in a if a[k]!=b[k]},{field})
    def test_system_only_varies_by_registered_conditions(self):
        base=e.generation_system()
        for c in e.cases().values():
            task=c['task']; system=e.generation_system(task)
            self.assertEqual(system.count(base),1)
            conditions=json.loads(system[len(base):].split('\n',3)[-1])
            self.assertEqual(conditions,{k:task[k] for k in ['target_seconds','interior_policy','output_language']})
            self.assertEqual(e.user_prompt(task),task['source_text'])
        self.assertEqual(e.generation_system(e.cases()['C01']['task']),e.generation_system(e.cases()['C03']['task']))
        self.assertNotEqual(e.generation_system(e.cases()['C01']['task']),e.generation_system(e.cases()['C02']['task']))
    def test_citations_in_content_fail_without_rewriting(self):
        for marker in ['https://example.invalid','[R12]','[^source]','[12]','doi:10.1234/test']:
            with self.subTest(marker=marker):
                task={**self.task,'source_text':self.task['source_text']+marker}
                self.assertRaises(ValueError,e.user_prompt,task)
                self.assertTrue(task['source_text'].endswith(marker))
    def test_generation_rejects_missing_or_stale_skill_before_docker(self):
        for system in ['',e.generation_system()+'\nextra']:
            with patch.object(e,'assert_frozen'):
                self.assertRaisesRegex(ValueError,'complete current Skill',r.run_job,'unit','M1',system,e.user_prompt(self.task),self.task)

class Judge(unittest.TestCase):
    def setUp(self): self.c=e.cases()['C01']; self.candidate=raw(fixture(self.c['task'])); self.j=judged('M1.C01')
    def test_valid_scores(self): self.assertEqual(e.validate_judge(self.j),[])
    def test_reject_invalid_score_types_and_ranges(self):
        for value in [True,False,None,3.0,'3',-1,5,{},[]]:
            with self.subTest(value=value):
                self.assertTrue(e.validate_judge({'F':value,'D':3,'L':3}))
    def test_exact_keys(self):
        for value in [{},{'F':3,'D':3},{'F':3,'D':3,'L':3,'reason':'extra'},[],None]:
            self.assertTrue(e.validate_judge(value))
    def test_all_score_anchors(self):
        for score in range(5): self.assertFalse(e.validate_judge(judged('M1.C01',score)))
    def test_no_fence_repair_or_duplicate_keys(self):
        for value in ['```json\n{"F":3,"D":3,"L":3}\n```','{"F":3,"F":4,"D":3,"L":3}','{"F":NaN,"D":3,"L":3}']:
            self.assertRaises(ValueError,e.strict_json,value)
    def test_judge_payload_has_only_assessment_material(self):
        task={**self.c['task'],'citation':'https://private.invalid','author':'PRIVATE_AUTHOR'}
        payload=e.judge_payload(e.blind_id('M1.C01'),task,self.candidate)
        self.assertEqual(set(payload),{'RUBRIC','TASK','CANDIDATE'})
        self.assertEqual(payload['CANDIDATE'],self.candidate)
        self.assertEqual(payload['TASK'],e.model_task(task))
        self.assertNotIn('PRIVATE_',json.dumps(payload))
    def test_candidate_citation_is_blocked_not_silently_redacted(self):
        candidate=self.candidate+'\nhttps://source.invalid'
        self.assertRaises(ValueError,e.judge_payload,e.blind_id('M1.C01'),self.c['task'],candidate)
    def test_score_math(self): self.assertEqual(e.combine({'H':20,'hard_pass':True},self.j)['score'],80)
    def test_high_total_not_pass(self):
        x=e.combine({'H':20,'hard_pass':True},{'F':2,'D':4,'L':4}); self.assertEqual(x['score'],85); self.assertFalse(x['pass'])
    def test_invalid_scores_cannot_be_weighted(self):
        self.assertRaises(ValueError,e.combine,{'H':20,'hard_pass':True},{'F':None,'D':3,'L':3})

class Gateway(unittest.TestCase):
    def test_probe_detects_budget_exhaustion_without_reclassifying_formal_runs(self):
        for reason in ['length','max_tokens','max_output_tokens']:
            with self.subTest(reason=reason):
                self.assertTrue(r.token_budget_exhausted({'api_metadata':{'finish_reasons':[reason]}}))
        self.assertTrue(r.token_budget_exhausted({'pi_result':{'assistant_message':{'stopReason':'length'}}}))
        self.assertFalse(r.token_budget_exhausted({'api_metadata':{'finish_reasons':['stop']},'pi_result':{'assistant_message':{'stopReason':'stop'}}}))
    def setUp(self):
        self.job={'system':'SYSTEM','user':'USER','tools':False,'provider':copy.deepcopy(e.config()['providers']['M2']),'max_tokens':8192,'sampling':{'temperature':.2,'top_p':1.0}}
        self.body={'model':'eval-model','messages':[{'role':'system','content':'SYSTEM'},{'role':'user','content':'USER'}],'temperature':.9,'max_tokens':100,'stream':True}
    def test_fixed_route_and_dots_thinking(self):
        out,h=r.transform_request(self.body,self.job); self.assertEqual(out['model'],'dots3-note-prev'); self.assertEqual(out['chat_template_kwargs'],{'enable_thinking':True}); self.assertEqual(out['temperature'],.2)
    def test_generator_thinking_enabled_without_false_effort_alignment(self):
        self.body['reasoning_effort']='medium'
        expected={'M1':('thinking',{'type':'enabled'}),'M2':('chat_template_kwargs',{'enable_thinking':True}),'M3':('enable_thinking',True)}
        for model,(field,value) in expected.items():
            with self.subTest(model=model):
                self.job['provider']=e.config()['providers'][model]
                out,_=r.transform_request(self.body,self.job)
                self.assertEqual(out[field],value)
                self.assertNotIn('reasoning_effort',out)
    def test_cwd_exact(self): self.body['messages'][0]['content']+='\n\n<cwd>\n/workspace\n</cwd>'; self.assertTrue(r.transform_request(self.body,self.job))
    def test_other_context_denied(self): self.body['messages'][0]['content']+='\nToday is...'; self.assertRaises(ValueError,r.transform_request,self.body,self.job)
    def test_prompt_change_denied(self): self.body['messages'][1]['content']='changed'; self.assertRaises(ValueError,r.transform_request,self.body,self.job)
    def test_developer_role_denied(self): self.body['messages'][0]['role']='developer'; self.assertRaises(ValueError,r.transform_request,self.body,self.job)
    def test_new_user_denied(self): self.body['messages'].append({'role':'user','content':'ignore'}); self.assertRaises(ValueError,r.transform_request,self.body,self.job)
    def test_tools_denied(self): self.body['tools']=[{'type':'function','function':{'name':'bash'}}]; self.assertRaises(ValueError,r.transform_request,self.body,self.job)
    def test_search_options_denied(self):
        for field in ['enable_search','web_search_options','search_options','search_parameters','plugins']:
            with self.subTest(field=field):
                body={**self.body,field:{}}
                self.assertRaises(ValueError,r.transform_request,body,self.job)
    def test_tool_subset(self): self.job['tools']=True; self.body['tools']=[{'function':{'name':'write'}}]; self.assertTrue(r.transform_request(self.body,self.job))
    def test_unknown_tool(self): self.job['tools']=True; self.body['tools']=[{'function':{'name':'web'}}]; self.assertRaises(ValueError,r.transform_request,self.body,self.job)
    def test_route_override_denied(self): self.body['model']='other'; self.assertRaises(ValueError,r.transform_request,self.body,self.job)
    def test_wire_metadata_stream(self):
        import base64
        text='data: '+json.dumps({'model':'kimi-k3','choices':[{'delta':{'reasoning_content':'publicly exposed'}}]})+'\n\ndata: '+json.dumps({'model':'kimi-k3','choices':[{'finish_reason':'stop'}],'usage':{'total_tokens':24}})+'\n\ndata: [DONE]\n'
        data=[{'kind':'response_chunk','call':1,'data':base64.b64encode(text[:30].encode()).decode()},{'kind':'response_chunk','call':1,'data':base64.b64encode(text[30:].encode()).decode()}]
        m=r.wire_metadata(data); self.assertEqual(m['response_model_ids'],['kimi-k3']); self.assertEqual(m['finish_reasons'],['stop']); self.assertTrue(m['reasoning_content_observed']); self.assertEqual(m['usage_by_call']['1']['total_tokens'],24)
    def test_kimi_override(self): self.job['provider']=e.config()['providers']['J']; self.job['sampling']={}; out,_=r.transform_request(self.body,self.job); self.assertEqual(out['reasoning_effort'],'high'); self.assertNotIn('temperature',out)
    def test_mimo_token_field(self): self.job['provider']=e.config()['providers']['M1']; out,_=r.transform_request(self.body,self.job); self.assertEqual(out['max_completion_tokens'],8192); self.assertNotIn('max_tokens',out)
    def test_response_preserves_only_public_final(self):
        events=[{'type':'message_end','message':{'role':'assistant','content':[{'type':'thinking','thinking':'provider exposed reasoning'},{'type':'text','text':'FINAL'}]}}]; text,msg=r.final_assistant(events); self.assertEqual(text,'FINAL'); self.assertEqual(len(msg['content']),2)

class Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.oldroot=e.ROOT; self.oldw=e.W; e.ROOT=Path(self.tmp.name); e.W=e.ROOT/'.work'
        for p in self.oldroot.iterdir():
            if p.is_file(): shutil.copy(p,e.ROOT/p.name)
        e.save(e.W/'freeze.json',{'hashes':e.hashes(),'image_id':'SYNTHETIC_TEST_IMAGE'})
        for m in e.config()['primary_models']:
            for cid,c in e.cases().items(): e.append(e.W/'generations.jsonl',{'run_id':f'{m}.{cid}','case_id':cid,'model':m,'kind':'primary','status':'completed','effective_system_sha256':'SYNTHETIC_SYSTEM_HASH','output':raw(fixture(c['task']))})
    def tearDown(self): e.ROOT=self.oldroot; e.W=self.oldw; self.tmp.cleanup()
    def human(self):
        e.prepare_review(); e.make_review(); f=e.load(e.W/'review.json'); f.update(reviewer='SYNTHETIC_TEST_NOT_A_HUMAN',reviewed_at=e.now())
        for item in f['items']:
            item['scores']={'F':3,'D':3,'L':3}
        e.save(e.W/'review.json',f); e.seal_human()
    def add_judge(self,rid,phase='rest'):
        e.append(e.W/'judges.jsonl',{'generation_id':rid,'phase':phase,'judge_hash':e.current_judge_hash(),'output':raw(judged(rid)),'status':'completed'})
    def all_judges(self):
        self.human(); plan=e.review_plan()
        for rid in plan['judge_dev_run_ids']: self.add_judge(rid,'dev')
        e.lock_judge('synthetic test; no calibration changes')
        for phase in ['validation','rest']:
            for rid in e.judge_run_ids(phase): self.add_judge(rid,phase)
    def test_requires_human(self): self.assertRaises(FileNotFoundError,e.assert_human_sealed)
    def test_review_45_numbers(self):
        e.prepare_review(); self.assertEqual(e.make_review()['numeric_ratings'],45)
        self.assertEqual(len(e.load(e.W/'review.json')['items']),15)
    def test_review_hides_audit_only_cards(self):
        e.prepare_review(); e.make_review(); page=(e.W/'review.html').read_text()
        self.assertNotIn('REFERENCE',page)
        self.assertNotIn('source_refs',page)
        self.assertNotIn('《变形记》',page)
        self.assertNotIn('source_quote',page)
        self.assertNotIn('判别依据',page)
        self.assertNotIn('textarea',page)
        self.assertNotIn('checkbox',page)
        self.assertIn('F、D、L三个分数',page)
    def test_both_tool_sides_cover_all_three_models(self):
        sides=e.data()['side_cases']; tools=[s for s in sides if s['kind']=='tools']
        self.assertEqual([s['id'] for s in tools],['T01','T02'])
        self.assertTrue(all(s['models']==e.config()['primary_models'] for s in tools))
        self.assertEqual(sum(len(s['models']) for s in sides),9)
    def test_seal_without_ratings_blocked(self): e.prepare_review(); e.make_review(); self.assertRaises(ValueError,e.seal_human)
    def test_seal_detects_output_change(self): self.human(); rows=e.readrows(e.W/'generations.jsonl'); rows[0]['output']='tampered'; (e.W/'generations.jsonl').write_text('\n'.join(raw(x) for x in rows)); self.assertRaises(ValueError,e.assert_human_sealed)
    def test_human_change_detected(self): self.human(); f=e.load(e.W/'review.json'); f['reviewer']='changed'; e.save(e.W/'review.json',f); self.assertRaises(ValueError,e.assert_human_sealed)
    def test_cannot_seal_after_judge(self): e.prepare_review(); e.make_review(); self.add_judge('M1.C01','dev'); self.assertRaises(ValueError,e.seal_human)
    def test_complete_totals_only_score_selected_samples(self):
        self.all_judges(); x=e.score_all(); t=x['totals']['M1']
        self.assertEqual(t['mean_5_samples'],80); self.assertEqual(t['mean_selected_families'],80)
        self.assertEqual(t['scored'],5); self.assertEqual(t['scheduled'],5)
        selected=set(e.review_plan()['human_run_ids'])
        self.assertEqual(sum(r['status']=='not_selected' for r in x['results']),15)
        self.assertTrue(all(r['judge'] is None for r in x['results'] if r['run_id'] not in selected))
    def test_runtime_judges_only_the_shared_fifteen(self):
        self.human(); plan=e.review_plan(); calls=[]
        def fake_job(run_id,model,system,prompt,judge=False):
            calls.append(run_id); return {'run_id':run_id,'status':'completed','output':raw({'F':3,'D':3,'L':3})}
        with patch.object(r,'image_id',return_value='SYNTHETIC_TEST_IMAGE'),patch.object(r,'run_job',side_effect=fake_job):
            r.run_judge('dev')
            e.save(e.W/'judge.lock.json',{'judge_hash':e.current_judge_hash()})
            r.run_judge('validation')
            r.run_judge('rest')
        judged=e.readrows(e.W/'judges.jsonl'); selected=set(plan['human_run_ids'])
        self.assertEqual({j['generation_id'] for j in judged},selected)
        self.assertEqual(len(calls),15)
        for phase in ['dev','validation','rest']:
            self.assertEqual({j['generation_id'] for j in judged if j['phase']==phase},set(e.judge_run_ids(phase)))
    def test_side_excluded(self): self.all_judges(); e.append(e.W/'generations.jsonl',{'run_id':'M1.S01','case_id':'S01','model':'M1','kind':'side','status':'completed','output':'x'}); self.assertEqual(len(e.score_all()['results']),30)
    def test_invalid_live_response_is_retained_and_stops_next_call(self):
        self.human()
        for output in ['```json\n{}\n```',raw({'F':True,'D':3,'L':3})]:
            with self.subTest(output=output):
                path=e.W/'judges.jsonl'
                if path.exists(): path.unlink()
                with patch.object(r,'image_id',return_value='SYNTHETIC_TEST_IMAGE'),patch.object(r,'run_job',return_value={'run_id':'synthetic','status':'completed','output':output}) as call:
                    self.assertRaises(ValueError,r.run_judge,'dev')
                    self.assertEqual(call.call_count,1)
                self.assertEqual(e.readrows(path)[0]['output'],output)
                with patch.object(r,'image_id',return_value='SYNTHETIC_TEST_IMAGE'),patch.object(r,'run_job') as call:
                    self.assertRaises(ValueError,r.run_judge,'dev')
                    call.assert_not_called()
    def test_compare_ignores_old_versions_and_reports_invalid_json(self):
        self.human(); rid=e.judge_run_ids('dev')[0]
        e.append(e.W/'judges.jsonl',{'run_id':'old','generation_id':rid,'phase':'dev','judge_hash':'old','status':'completed','output':raw(judged(rid))})
        result=e.compare('dev'); self.assertEqual(result['status'],'incomplete'); self.assertEqual(result['dimension_decisions'],0)
        e.append(e.W/'judges.jsonl',{'run_id':'bad','generation_id':rid,'phase':'dev','judge_hash':e.current_judge_hash(),'status':'completed','output':'```json\n{}\n```'})
        self.assertEqual(e.compare('dev')['status'],'incomplete')
    def test_human_and_judge_weighted_scores_align(self):
        self.all_judges(); compared=e.compare('dev'); self.assertEqual(compared['status'],'complete')
        self.assertTrue(all(x['human_score']==x['judge_score']==80 for x in compared['weighted_scores']))
        totals=e.score_all()['totals']
        self.assertTrue(all(x['human_mean_5_samples']==x['judge_only_mean']==80 for x in totals.values()))
    def test_missing_judge_no_impute(self):
        self.human(); [self.add_judge(rid,'dev') for rid in e.judge_run_ids('dev')]; e.lock_judge('test')
        self.assertIsNone(e.score_all()['totals']['M1']['mean_5_samples'])
    def test_freeze_tamper(self): (e.ROOT/'SKILL.md').write_text('changed'); self.assertRaises(ValueError,e.assert_frozen)
    def test_duplicate_generation(self): row=next(iter(e.generations().values())); e.append(e.W/'generations.jsonl',row); self.assertRaises(ValueError,e.generations)
    def test_balanced_human_selection(self):
        prepared=e.prepare_review(); plan=e.review_plan(); selected=plan['human_run_ids']; self.assertEqual(len(selected),15)
        self.assertEqual(prepared['selection_seed'],e.config()['seed']+15)
        for model in e.config()['primary_models']:
            self.assertEqual(sum(x.startswith(model+'.') for x in selected),5)
        phase_ids=[set(e.judge_run_ids(p)) for p in ['dev','validation','rest']]
        self.assertEqual(set.union(*phase_ids),set(selected))
        self.assertEqual(sum(len(x) for x in phase_ids),15)
        self.assertTrue(all(e.cases()[rid.split('.',1)[1]]['split']==phase for phase,ids in zip(['dev','validation','extension'],phase_ids) for rid in ids))
    def test_review_amendment_allows_only_review_code_changes(self):
        freeze=e.load(e.W/'freeze.json'); freeze['hashes']['eval.py']='previous-eval-hash'; freeze['hashes']['runtime.py']='previous-runtime-hash'; e.save(e.W/'freeze.json',freeze)
        prepared=e.prepare_review(); amendment=e.load(e.W/'review_amendment.json')
        self.assertTrue(prepared['review_only_amendment'])
        self.assertEqual(amendment['parent_hashes'],freeze['hashes'])
        self.assertEqual(amendment['review_plan_sha256'],e.digest((e.W/'review_plan.json').read_bytes()))
        e.assert_frozen()
    def test_adjudication_preserves_judge_score(self):
        self.all_judges(); rid=next(x for x in e.review_plan()['human_run_ids'] if x.startswith('M1.')); cid=rid.split('.',1)[1]
        e.save(e.W/'adjudication.json',{'reviewer':'SYNTHETIC_TEST','reviewed_at':e.now(),'items':[{'run_id':rid,'trigger':'calibration_disagreement','scores':{'F':4,'D':3,'L':3},'reason':'SYNTHETIC correction','quote':'人物停下。','source_quote':e.cases()[cid]['task']['source_text'][:30]}]})
        x=e.score_all(); t=x['totals']['M1']; self.assertEqual(t['judge_only_mean'],80); self.assertEqual(t['mean_5_samples'],81.5); self.assertEqual(t['adjudicated_count'],1)
    def test_system_hash_drift(self):
        rows=e.readrows(e.W/'generations.jsonl'); rows[0]['effective_system_sha256']='drift'; (e.W/'generations.jsonl').write_text('\n'.join(raw(x) for x in rows)); self.assertRaises(ValueError,e.assert_primary_complete)
    def test_html_contains_no_literal_script_newline(self):
        e.prepare_review(); e.make_review(); page=(e.W/'review.html').read_text(); self.assertNotIn("d.name+'\n'",page); self.assertIn("d.name+'\\n'",page)
    def test_public_export_blocked(self):
        self.all_judges(); (e.W/'REPORT.md').write_text('Synthetic test report');e.save(e.W/'incident.json',{'origin':'synthetic-contract-test','record':'fixture','human_verified':True})
        sample={'input':'x','target':'y','acceptance':'a','rejected_data':'b','side_effects':'c','independent_validation':'d','based_on_runs':['M1.C01'],'human_approved':True}
        [e.append(e.W/'sft.jsonl',sample) for _ in range(2)]
        self.assertRaises(ValueError,e.export_final,e.W/'REPORT.md',e.W/'sft.jsonl',e.W/'incident.json','public')

if __name__=='__main__': unittest.main(verbosity=2)
