#!/usr/bin/env python3
"""Verify published bytes and recompute results offline; no API, Docker, or .env reads."""
import collections
import gzip
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import eval as evaluator


def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf8'))


def rows(name):
    return [json.loads(line) for line in (ROOT / name).read_text(encoding='utf8').splitlines() if line.strip()]


def digest_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def message_text(value):
    if isinstance(value, str):
        return value
    require(isinstance(value, list) and all(isinstance(x, dict) and x.get('type') == 'text' for x in value), 'Unexpected message content')
    return ''.join(x['text'] for x in value)


def aggregate(records):
    known = [r for r in records if r['usage_available']]
    return {
        'api_calls': len(records), 'usage_available_calls': len(known),
        'usage_missing_calls': len(records) - len(known),
        **{k: sum(r['usage'].get(k, 0) for r in known) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')},
        'reasoning_tokens_known_sum': sum(r['reasoning_tokens'] for r in records if r['reasoning_tokens'] is not None),
        'reasoning_tokens_known_calls': sum(r['reasoning_tokens'] is not None for r in records),
        'cached_tokens_known_sum': sum(r['cached_tokens'] for r in records if r['cached_tokens'] is not None),
        'cached_tokens_known_calls': sum(r['cached_tokens'] is not None for r in records),
    }


def main():
    manifest = load('manifest.json')
    for item in manifest['files']:
        p = ROOT / item['path']
        require(p.is_file() and p.stat().st_size == item['bytes'] and digest_file(p) == item['sha256'], 'Manifest mismatch: ' + item['path'])
    freeze = load('frozen/metadata/freeze.json')
    for name, h in freeze['hashes'].items():
        require(digest_file(ROOT / 'frozen/generation_sources' / name) == h, 'Generation baseline changed: ' + name)
    amendment = load('frozen/metadata/review_amendment.json')
    require(evaluator.hashes() == amendment['amended_hashes'], 'Final evaluation source hashes changed')
    require(digest_file(ROOT / 'frozen/metadata/freeze.json') == amendment['parent_freeze_sha256'], 'Freeze lineage changed')
    require(digest_file(ROOT / 'frozen/metadata/review_plan.json') == amendment['review_plan_sha256'], 'Selection lineage changed')
    require(digest_file(ROOT / 'frozen/metadata/judge_execution_plan.json') == amendment['judge_execution_plan_sha256'], 'Execution plan changed')
    evaluator.check_kit()
    generations = rows('frozen/generations.jsonl')
    generation_map = {r['run_id']: r for r in generations}
    require(len(generations) == len(generation_map) == 39, 'Generation count/identity')
    plan = load('frozen/metadata/review_plan.json')
    selected = set(plan['human_run_ids'])
    seeded = random.Random(evaluator.config()['seed'] + 15)
    expected_selection = [f'{m}.{c}' for m in evaluator.config()['primary_models'] for c in sorted(seeded.sample(sorted(evaluator.cases()), 5))]
    require(plan['human_run_ids'] == expected_selection, 'Sampling does not reproduce')
    judgments = rows('frozen/judges.jsonl')
    judge_map = {r['generation_id']: r for r in judgments}
    lock = load('frozen/metadata/judge.lock.json')
    require(len(judgments) == len(judge_map) == 15 and set(judge_map) == selected, 'Judge coverage/identity')
    require(evaluator.current_judge_hash() == lock['judge_hash'], 'Judge version changed')
    require(all(j['judge_hash'] == lock['judge_hash'] and j['status'] == 'completed' for j in judgments), 'Invalid Judge scope/status')
    review = load('frozen/human/review.json')
    seal = load('frozen/human/human.seal.json')
    require(evaluator.digest(review) == seal['review_sha256'], 'Human review seal changed')
    require(seal['output_hashes'] == {r['run_id']: evaluator.digest(r['output']) for r in generations if r['kind'] == 'primary'}, 'Sealed candidates changed')
    require(set(seal['human_run_ids']) == selected, 'Human/Judge selection differs')
    human = {item['sample_id']: item['scores'] for item in review['items']}
    expected_hard = {x['run_id']: x['hard'] for x in load('frozen/mechanical_checks.json')}
    hard = {}
    tasks = {}
    for record in generations:
        if record['kind'] == 'primary':
            task = evaluator.cases()[record['case_id']]['task']
        else:
            side = next(s for s in evaluator.data()['side_cases'] if s['id'] == record['case_id'])
            task = side.get('task', evaluator.cases()[side['base_case']]['task'])
        rid = record['run_id']
        tasks[rid] = task
        hard[rid] = evaluator.grade(record['output'], task)
        require(hard[rid] == expected_hard[rid], 'Hard score mismatch: ' + rid)
    prompts = rows('frozen/prompts.jsonl')
    pmap = {p['run_id']: p for p in prompts}
    require(len(prompts) == len(pmap) == 54, 'Prompt coverage/duplicates')
    for rid, record in generation_map.items():
        p = pmap[rid]
        require(p['user'] == evaluator.user_prompt(tasks[rid]), 'Source text projection changed: ' + rid)
        require(p['requested_system'] == evaluator.generation_system(tasks[rid]), 'Requested skill changed: ' + rid)
        wire = p['effective_request']['messages']
        actual_system = message_text(wire[0]['content'])
        require(actual_system in {p['requested_system'],p['requested_system']+'\n\n<cwd>\n/workspace\n</cwd>'}, 'Unexpected Pi system context')
        require(evaluator.digest(actual_system) == record['effective_system_sha256'], 'Wire system hash mismatch: ' + rid)
        require(message_text(wire[1]['content']) == p['user'], 'Actual user text changed: ' + rid)
    for cid in evaluator.cases():
        systems = {generation_map[m+'.'+cid]['effective_system_sha256'] for m in evaluator.config()['primary_models']}
        require(len(systems)==1, 'Same-case system differs across models: '+cid)
    for side in evaluator.data()['side_cases']:
        if side['kind']=='tools':
            for model in side['models']:
                require(generation_map[model+'.'+side['id']]['effective_system_sha256']==generation_map[model+'.'+side['base_case']]['effective_system_sha256'], 'Tool comparison system differs')
    for j in judgments:
        p = pmap[j['run_id']]
        rid = j['generation_id']
        require(p['requested_system'] == (ROOT / 'JUDGE.md').read_text().strip(), 'Judge system changed')
        actual_system = message_text(p['effective_request']['messages'][0]['content'])
        require(actual_system in {p['requested_system'],p['requested_system']+'\n\n<cwd>\n/workspace\n</cwd>'} and evaluator.digest(actual_system)==j['effective_system_sha256'], 'Judge wire system hash mismatch')
        require(json.loads(p['user']) == evaluator.judge_payload(evaluator.blind_id(rid), tasks[rid], generation_map[rid]['output']), 'Judge input contains unexpected data')
        require(not evaluator.validate_judge(evaluator.strict_json(j['output'])), 'Invalid score-only output')
    scores = load('frozen/scores.json')
    recomputed = {}
    for r in scores['results']:
        rid = r['run_id']
        if rid not in selected:
            require(r['status'] == 'not_selected' and r['score'] is None, 'Unselected candidate received score')
            continue
        judge = evaluator.combine(hard[rid], evaluator.strict_json(judge_map[rid]['output']))
        expert = evaluator.combine(hard[rid], human[evaluator.blind_id(rid)])
        require(judge['score'] == r['score'] == r['judge_score'] and expert['score'] == r['human_score'], 'Weighted score mismatch: ' + rid)
        require(judge['pass'] == r['pass'] and expert['pass'] == r['human_pass'], 'Pass criterion mismatch: ' + rid)
        recomputed[rid] = (judge, expert, r['family'])
    for m, total in scores['totals'].items():
        rr = [v for rid, v in recomputed.items() if rid.startswith(m + '.')]
        require(len(rr) == 5, 'Per-model denominator changed')
        families = collections.defaultdict(list)
        for judge, _, family in rr:
            families[family].append(judge['score'])
        require(sum(j['score'] for j,h,f in rr)/5 == total['judge_only_mean'], 'Judge mean mismatch')
        require(sum(h['score'] for j,h,f in rr)/5 == total['human_mean_5_samples'], 'Human mean mismatch')
        require(sum(j['pass'] for j,h,f in rr) == total['pass_count'], 'Pass count mismatch')
        require(sum(sum(v)/len(v) for v in families.values())/len(families) == total['mean_selected_families'], 'Family mean mismatch')
    ledger = rows('usage/calls.jsonl')
    require(len({(u['run_id'], u['call']) for u in ledger}) == len(ledger), 'Duplicate usage records')
    summary = load('usage/summary.json')
    for m in evaluator.config()['providers']:
        require(aggregate([u for u in ledger if u['model']==m and u['included_formal']]) == summary['formal'][m], 'Formal usage mismatch')
        require(aggregate([u for u in ledger if u['model']==m]) == summary['all_retained_known'][m], 'Process usage mismatch')
    scope = load('audit/scope.json')
    authorization = load('audit/publish_authorization.json')
    require(authorization['dataset_sha256']==digest_file(ROOT/'dataset.json'), 'Publication authorization is not bound to this dataset')
    trace_rows = collections.Counter()
    requests = {}
    # Validate the usage ledger against raw provider stream usage for formal and setup runs.
    streams = collections.defaultdict(bytearray)
    for name, allowed in [('frozen/trajectory.jsonl.gz',set(scope['formal_runs'])), ('frozen/setup/trajectory.jsonl.gz',set(scope['setup_runs']))]:
        with gzip.open(ROOT/name, 'rt', encoding='utf8') as stream:
            for line in stream:
                event = json.loads(line)
                rid = event['run_id']
                require(rid in allowed, 'Excluded record in published trajectory')
                trace_rows[rid] += 1
                if event['kind'] == 'request':
                    requests[(rid, event['call'])] = event['wire_request']
                elif event['kind'] == 'response_chunk':
                    import base64
                    streams[(rid,event['call'])].extend(base64.b64decode(event['data']))
    actual_usage = {}
    for key, content in streams.items():
        for line in content.decode('utf8').splitlines():
            if not line.startswith('data:'):
                continue
            payload = line[5:].strip()
            if payload == '[DONE]':
                continue
            value = json.loads(payload)
            if value.get('usage'):
                actual_usage[key] = value['usage']
    for u in ledger:
        if u['scope'] == 'excluded_judge':
            continue
        key = (u['run_id'],u['call'])
        require(key in requests and actual_usage.get(key) == u['usage'], 'Raw provider usage mismatch')
    require(all(trace_rows[rid] == scope['trajectory_rows_by_run'][rid] for rid in scope['formal_runs'] + scope['setup_runs']), 'Trajectory truncation')
    sft = rows('sft/sft.jsonl')
    require(len(sft) == 2, 'SFT count')
    for sample in sft:
        conditions = json.loads(sample['input']['system'].split('## 本次实验条件\n')[-1])
        task = {'source_id':'TEXT','source_text':sample['input']['user'],**conditions}
        require(evaluator.generation_system(task) == sample['input']['system'], 'SFT system mismatch')
        require(evaluator.grade(json.dumps(sample['target'],ensure_ascii=False),task)['H'] == 20, 'SFT mechanical check failed')
        require(sample['human_approved'] is False, 'SFT approval status changed')
    print(json.dumps({'status':'passed','manifest_files':len(manifest['files']),'formal_runs':54,'formal_api_calls':67,'primary_hard_checks':30,'scored_samples':15,'side_samples':9,'formal_tokens':sum(x['total_tokens'] for x in summary['formal'].values()),'process_known_tokens':sum(x['total_tokens'] for x in summary['all_retained_known'].values()),'missing_usage_calls':sum(x['usage_missing_calls'] for x in summary['all_retained_known'].values()),'sft_human_approval':'pending'},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, FileNotFoundError, TypeError) as exc:
        print('FAILED: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
