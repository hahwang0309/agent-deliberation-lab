"""Frozen, blinded GLM adjudication and agreement audit; never edits source coding."""
import argparse
import asyncio
import csv
import hashlib
import json
import os
import random
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/research/position-change-mentions'
OUT = ROOT / 'docs/research/position-change-adjudication'
MODEL = 'zai-glm-5-3'
SEED = 20261025
LABELS = {'yes', 'partial', 'no', 'undeterminable'}
PRICE_INPUT = 1.4 / 1_000_000
PRICE_OUTPUT = 4.4 / 1_000_000
MAX_COST = 5.0
MAX_REQUESTS = 90


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read_jsonl(p):
    return [json.loads(s) for s in p.read_text().splitlines() if s.strip()] if p.exists() else []


def save(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def prepare():
    OUT.mkdir(exist_ok=True)
    if (OUT / 'protocol.json').exists():
        raise SystemExit('Frozen protocol exists: use code/analyze, do not resample.')
    a = pd.read_csv(SOURCE / 'classified-mistral-large-2512.csv').set_index('id')
    b = pd.read_csv(SOURCE / 'classified-mistral-small-2603.csv').set_index('id')
    assert set(a.index) == set(b.index) and len(a) == 1600
    assert (a.text_sha256 == b.reindex(a.index).text_sha256).all()
    disagreed = sorted(k for k in a.index if a.loc[k, 'label'] != b.loc[k, 'label'])
    agreed = sorted(set(a.index) - set(disagreed))
    assert len(disagreed) == 294 and len(agreed) == 1306
    rng = random.Random(SEED)
    audited = sorted(rng.sample(agreed, 160))
    blind = {x['id']: {k: x[k] for k in ['id', 'speaker', 'text']}
             for x in read_jsonl(SOURCE / 'blind-inputs.jsonl')}
    selected = disagreed + audited
    for k in selected:
        assert hashlib.sha256(blind[k]['text'].encode()).hexdigest() == a.loc[k, 'text_sha256']
    # The pilot is selected before labels from the judge exist. It includes both routes.
    pilot_ids = rng.sample(disagreed, 4) + rng.sample(audited, 4)
    rng.shuffle(pilot_ids)
    remaining = sorted(set(selected) - set(pilot_ids))
    rng.shuffle(remaining)
    order = pilot_ids + remaining
    (OUT / 'blind-inputs.jsonl').write_text(''.join(json.dumps(blind[k], ensure_ascii=False) + '\n' for k in order))
    selection = []
    for k in selected:
        selection.append({'id': k, 'route': 'disagreement' if k in disagreed else 'agreement_audit',
                          'inclusion_probability': 1.0 if k in disagreed else 160 / 1306,
                          'large_label': a.loc[k, 'label'], 'small_label': b.loc[k, 'label']})
    pd.DataFrame(selection).to_csv(OUT / 'selection.csv', index=False)
    system = (SOURCE / 'coding-system.txt').read_text().strip()
    system = system.replace('Return one result per input id, no extras.',
        'Return one result per input id, no extras.\n'
        'Use undeterminable only if the text cannot be assigned a label under these definitions; '
        'do not force a choice. Do not assume that any other annotator has judged this utterance.\n'
        'For each item also supply a brief one-sentence rationale grounded in the target text. '
        'For no, a representative short verbatim quote may be included; an empty quote is allowed. '
        'For undeterminable, explain what prevents classification. '
        'Output a JSON object with an items array. Each item has exactly id, label, quote, rationale.')
    (OUT / 'coding-system.txt').write_text(system + '\n')
    protected = {}
    for name in ['MethodsDraft.md', 'ResultsDraft.md', 'Discussion.md', 'IntroductionDraft.md',
                 'Abstract.md', 'AbstractEnglish.md', 'Outline.md', 'ManuscriptDraft.md']:
        p = ROOT / 'docs/research' / name
        protected[str(p.relative_to(ROOT))] = sha(p)
    originals = ['classified-mistral-large-2512.csv', 'classified-mistral-small-2603.csv',
                 'coded-mistral-large-2512.jsonl', 'coded-mistral-small-2603.jsonl',
                 'blind-inputs.jsonl', 'sample-metadata.csv', 'coding-system.txt', 'protocol.json',
                 'maintenance-audit-candidates.json', 'results.json', 'pooled-decomposition.csv']
    total_bytes = sum(len(json.dumps(blind[k], ensure_ascii=False).encode()) for k in selected)
    protocol = {
        'created_utc': datetime.now(timezone.utc).isoformat(), 'status': 'frozen_before_judging',
        'user_authorization': ['GLM 5.3; Mistral API 쓰면 되.', '좋아. 시작해'],
        'destination': 'https://api.mistral.ai/v1/chat/completions', 'model': MODEL,
        'scope': 'Only explicit own-position-change classification; no utterance-type/evidence coding.',
        'design': 'All 294 three-way label disagreements plus 160 simple-random agreed cases.',
        'audit_seed': SEED, 'agreement_frame_n': len(agreed), 'audit_n': len(audited),
        'disagreement_n': len(disagreed), 'total_n': len(selected), 'pilot_ids': pilot_ids,
        'pilot_policy': 'Technical format/evidence check only; retain valid pilot labels if rubric unchanged.',
        'blinding': ['prior labels', 'agreement/disagreement route', 'condition', 'task',
                     'instruction', 'stratum', 'original source identifier'],
        'input': 'Opaque item id, speaker, target utterance only; same target-only scope as original coders.',
        'rubric': 'Original yes/partial/no definitions unchanged; undeterminable is an abstention.',
        'label_combination': 'Use judge for disagreements; retain original agreed labels in main combined result. Audit labels do not selectively overwrite agreed labels.',
        'audit_analysis': 'Report disagreement with original consensus, not human accuracy. A separate design-weighted sensitivity extrapolates audit discrepancies over the agreed frame.',
        'unresolved': 'Keep unresolved cases; use lower/upper bounds rather than force no or silently drop.',
        'sampling_scope': 'Post-hoc follow-up; neither preregistration nor human validation.',
        'temperature': 0, 'max_tokens': 8000, 'batch_size': 8, 'concurrency': 3,
        'request_interval_seconds': 1.25, 'timeout_seconds': 150, 'max_attempts': 3,
        'spend_guard_usd': MAX_COST, 'max_http_requests': MAX_REQUESTS,
        'price_source': 'https://docs.mistral.ai/models/zai-glm-5-3',
        'price_usd_per_million_tokens': {'input': 1.4, 'output': 4.4},
        'pricing_note': 'Estimate from recorded tokens, not a billing receipt; no cached-input discount assumed.',
        'target_text_payload_bytes': total_bytes,
        'source_sha256': {str((SOURCE / n).relative_to(ROOT)): sha(SOURCE / n) for n in originals},
        'protected_manuscript_sha256': protected,
        'frozen_files': {n: sha(OUT / n) for n in ['blind-inputs.jsonl', 'selection.csv', 'coding-system.txt']},
        'code_sha256_at_freeze': sha(Path(__file__)),
    }
    save(OUT / 'protocol.json', protocol)
    print(json.dumps({k: protocol[k] for k in ['model', 'disagreement_n', 'audit_n', 'total_n', 'spend_guard_usd']}))


def check_frozen():
    p = json.loads((OUT / 'protocol.json').read_text())
    for name, h in p['frozen_files'].items():
        assert sha(OUT / name) == h, name
    for name, h in p['source_sha256'].items():
        assert sha(ROOT / name) == h, name
    return p


async def code(limit):
    protocol = check_frozen()
    load_dotenv(ROOT / '.env')
    key = os.getenv('MISTRAL_API_KEY')
    if not key:
        raise SystemExit('MISTRAL_API_KEY is not configured.')
    done = {x['id']: x for x in read_jsonl(OUT / 'judgments.jsonl')}
    assert len(done) == len(read_jsonl(OUT / 'judgments.jsonl')), 'duplicate judgments'
    todo = [x for x in read_jsonl(OUT / 'blind-inputs.jsonl') if x['id'] not in done]
    if limit:
        todo = todo[:limit]
    system = (OUT / 'coding-system.txt').read_text()
    request_logs = read_jsonl(OUT / 'requests.jsonl')
    cost = sum(x.get('estimated_cost_usd', 0) for x in request_logs)
    reserved = 0.0
    request_count = len(request_logs)
    sem, lock, pace_lock = asyncio.Semaphore(3), asyncio.Lock(), asyncio.Lock()
    next_time = 0.0
    stat = {'accepted': 0, 'failed': 0, 'api_requests': 0}
    print(json.dumps({'model': MODEL, 'pending_this_run': len(todo), 'already_preserved': len(done)}), flush=True)
    schema = {'type': 'object', 'properties': {'items': {'type': 'array', 'items': {
        'type': 'object', 'properties': {'id': {'type': 'string'},
            'label': {'type': 'string', 'enum': sorted(LABELS)},
            'quote': {'type': 'string'}, 'rationale': {'type': 'string'}},
        'required': ['id', 'label', 'quote', 'rationale'], 'additionalProperties': False}}},
        'required': ['items'], 'additionalProperties': False}
    if protocol.get('quote_output_max_characters'):
        schema['properties']['items']['items']['properties']['quote']['maxLength'] = protocol['quote_output_max_characters']

    async def one(client, batch, batch_no):
        nonlocal next_time, reserved, cost, request_count
        async with sem:
            remaining = {x['id']: x for x in batch}
            for attempt in range(1, 4):
                user = json.dumps(list(remaining.values()), ensure_ascii=False)
                # Byte count plus overhead is deliberately conservative for the preflight guard.
                ceiling = (len(system.encode()) + len(user.encode()) + 2048) * PRICE_INPUT + 8000 * PRICE_OUTPUT
                async with lock:
                    if cost + reserved + ceiling > MAX_COST or request_count >= MAX_REQUESTS:
                        raise RuntimeError('Local API budget/request guard reached; accepted labels are preserved.')
                    reserved += ceiling
                    request_count += 1
                    req_no = request_count
                async with pace_lock:
                    delay = max(0, next_time - time.monotonic())
                    if delay:
                        await asyncio.sleep(delay)
                    next_time = time.monotonic() + 1.25
                payload = {'model': MODEL, 'temperature': 0, 'max_tokens': 8000,
                           'reasoning_effort': protocol.get('reasoning_effort', 'low'),
                           'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                           'response_format': {'type': 'json_schema', 'json_schema': {
                               'name': 'position_change_labels', 'schema': schema, 'strict': True}}}
                log = {'request_no': req_no, 'batch_no': batch_no, 'attempt': attempt,
                       'ids': list(remaining), 'started_utc': datetime.now(timezone.utc).isoformat(),
                       'request_sha256': hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}
                accepted = []
                fatal = None
                transient_delay = 0
                try:
                    response = await client.post(protocol['destination'], json=payload,
                                                 headers={'Authorization': 'Bearer ' + key})
                    log['http_status'] = response.status_code
                    if response.status_code in [401, 402, 403]:
                        fatal = 'Provider access or balance unavailable: HTTP ' + str(response.status_code)
                    elif response.status_code == 429:
                        # Never log response headers or request headers containing credentials.
                        body = response.text.lower()
                        if any(x in body for x in ['spending cap', 'insufficient balance', 'credits exhausted', 'monthly limit']):
                            fatal = 'Provider usage quota exhausted'
                        else:
                            transient_delay = 20 * attempt
                    elif response.status_code >= 500:
                        transient_delay = 3 * attempt
                    elif response.status_code != 200:
                        log['error_type'] = 'http_error'
                        # A schema/configuration error is not fixed by repeatedly sending the same request.
                        fatal = 'Provider rejected request format: HTTP ' + str(response.status_code)
                    else:
                        raw = response.json()
                        usage = raw.get('usage', {})
                        log['usage'] = usage
                        log['returned_model'] = raw.get('model')
                        log['response_id'] = raw.get('id')
                        log['estimated_cost_usd'] = usage.get('prompt_tokens', 0) * PRICE_INPUT + usage.get('completion_tokens', 0) * PRICE_OUTPUT
                        # Preserve full provider output locally for evidence, usage, and provenance.
                        raw_path = OUT / 'raw' / f'request-{req_no:04d}.json'
                        raw_path.parent.mkdir(exist_ok=True)
                        save(raw_path, raw)
                        choice = raw['choices'][0]
                        log['finish_reason'] = choice.get('finish_reason')
                        content = choice['message'].get('content')
                        # GLM returns thinking/text chunks even at low reasoning effort.
                        # Only final text chunks are classification output.
                        if isinstance(content, list):
                            content = ''.join(x.get('text', '') for x in content
                                              if isinstance(x, dict) and x.get('type') == 'text')
                        if not isinstance(content, str):
                            raise ValueError('No textual structured output')
                        parsed = json.loads(content)
                        seen = set()
                        normalize = lambda s: re.sub(r'\s+', ' ', s).strip()
                        rejects = []
                        for item in parsed.get('items', []):
                            k = item.get('id')
                            if k not in remaining or k in seen:
                                rejects.append({'id': k, 'reason': 'unexpected_or_duplicate_id'})
                                continue
                            seen.add(k)
                            label, quote, why = item.get('label'), item.get('quote', ''), item.get('rationale', '')
                            if label not in LABELS or not isinstance(quote, str) or not isinstance(why, str) or not why.strip():
                                rejects.append({'id': k, 'reason': 'invalid_fields'})
                                continue
                            if label in ['yes', 'partial'] and not quote.strip():
                                rejects.append({'id': k, 'reason': 'missing_evidence'})
                                continue
                            if quote and (normalize(quote) not in normalize(remaining[k]['text']) or len(quote.split()) > 25):
                                rejects.append({'id': k, 'reason': 'quote_not_exact_target_span_or_over_25_words'})
                                continue
                            accepted.append({**item, 'model_requested': MODEL, 'model_returned': raw.get('model'),
                                             'response_id': raw.get('id'), 'request_no': req_no,
                                             'attempt': attempt, 'text_sha256': hashlib.sha256(remaining[k]['text'].encode()).hexdigest()})
                        log['rejected_items'] = rejects
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
                    log['error_type'] = type(exc).__name__
                    transient_delay = 3 * attempt
                except (ValueError, KeyError, TypeError) as exc:
                    log['error_type'] = type(exc).__name__
                    transient_delay = 2
                finally:
                    async with lock:
                        reserved -= ceiling
                        # Charge the upper bound if an ambiguous transport error has unknown usage.
                        observed = log.get('estimated_cost_usd', ceiling if log.get('error_type') in ['ReadTimeout'] else 0)
                        cost += observed
                        log['guard_cost_usd'] = observed
                        with (OUT / 'requests.jsonl').open('a') as f:
                            f.write(json.dumps(log, ensure_ascii=False) + '\n')
                        with (OUT / 'judgments.jsonl').open('a') as f:
                            for item in accepted:
                                assert item['id'] not in done
                                f.write(json.dumps(item, ensure_ascii=False) + '\n')
                                done[item['id']] = item
                                remaining.pop(item['id'])
                        stat['accepted'] += len(accepted)
                        stat['api_requests'] += 1
                        print(json.dumps({**stat, 'total_preserved': len(done), 'last_batch': batch_no,
                                          'estimated_cost_usd_this_and_previous_runs': round(cost, 4),
                                          'pending_in_batch': len(remaining), 'http_status': log.get('http_status'),
                                          'error_type': log.get('error_type')}), flush=True)
                if fatal:
                    raise RuntimeError(fatal)
                if not remaining:
                    return
                if transient_delay:
                    await asyncio.sleep(transient_delay)
            async with lock:
                with (OUT / 'unresolved-requests.jsonl').open('a') as f:
                    f.write(json.dumps({'ids': list(remaining), 'batch_no': batch_no}) + '\n')
                stat['failed'] += len(remaining)

    async with httpx.AsyncClient(timeout=httpx.Timeout(150, connect=20), follow_redirects=False) as client:
        jobs = [asyncio.create_task(one(client, todo[i:i + 8], i // 8)) for i in range(0, len(todo), 8)]
        try:
            await asyncio.gather(*jobs)
        except BaseException:
            for j in jobs:
                j.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)
            raise
    print(json.dumps(stat | {'preserved_total': len(done)}), flush=True)


def analyze():
    protocol = check_frozen()
    a = pd.read_csv(SOURCE / 'classified-mistral-large-2512.csv').set_index('id')
    b = pd.read_csv(SOURCE / 'classified-mistral-small-2603.csv').set_index('id')
    selection = pd.read_csv(OUT / 'selection.csv').set_index('id')
    judged = read_jsonl(OUT / 'judgments.jsonl')
    assert len(judged) == len({x['id'] for x in judged})
    assert {x['id'] for x in judged} == set(selection.index), 'Incomplete judging: do not silently exclude failed targets.'
    j = pd.DataFrame(judged).set_index('id')
    assert all(j.loc[k, 'text_sha256'] == a.loc[k, 'text_sha256'] for k in j.index)
    f = a.copy().rename(columns={'label': 'large_label'})
    f['small_label'] = b.label
    f['route'] = np.where(f.large_label != f.small_label, 'disagreement', 'agreement_unchecked')
    f.loc[selection[selection.route.eq('agreement_audit')].index, 'route'] = 'agreement_audit'
    f['judge_label'] = j.label.reindex(f.index)
    f['combined_label'] = f.large_label
    f.loc[f.route.eq('disagreement'), 'combined_label'] = f.loc[f.route.eq('disagreement'), 'judge_label']
    f['audit_differs'] = f.route.eq('agreement_audit') & f.judge_label.ne(f.large_label)
    # Original 159 maintenance-expression cases: keep separate, unchanged sensitivity definition.
    denial = set(json.loads((SOURCE / 'maintenance-audit-candidates.json').read_text())['ids'])
    f['is_maintenance_candidate'] = f.index.isin(denial)
    f.to_csv(OUT / 'combined-labels.csv', index_label='id')
    strata = ['none', 'closing', 'moved', 'direct']
    bootstrap_n = 2000

    def metrics(t):
        denom = t[..., 0]
        with np.errstate(divide='ignore', invalid='ignore'):
            out = {'baseline': t[..., 1] / denom, 'stateful': t[..., 2] / denom}
            out['difference'] = out['stateful'] - out['baseline']
            for i, s in enumerate(strata):
                ix = 3 + i * 3
                out[s + '_share'] = t[..., ix] / denom
                out[s + '_baseline_joint'] = t[..., ix + 1] / denom
                out[s + '_stateful_joint'] = t[..., ix + 2] / denom
                out[s + '_difference_contribution'] = out[s + '_stateful_joint'] - out[s + '_baseline_joint']
            out['cue_stateful_rate'] = ((out['direct_stateful_joint'] + out['moved_stateful_joint']) /
                                        (out['direct_share'] + out['moved_share']))
            out['cue_fraction_of_increase'] = ((out['direct_difference_contribution'] + out['moved_difference_contribution']) / out['difference'])
        return out

    def estimate(values):
        # Use identical original composition-block resampling for every coding variant.
        g = f.assign(outcome=values).reset_index()
        pairs = g.pivot(index=['study', 'pair_id', 'block', 'stratum', 'weight'], columns='arm', values='outcome').reset_index()
        rng = np.random.default_rng(20261026)
        totals, draws = {}, {}
        for task, part in pairs.groupby('study'):
            vectors = []
            for _, block in part.groupby('block'):
                v = [block.weight.sum(), (block.weight * block.baseline).sum(), (block.weight * block.stateful).sum()]
                for s in strata:
                    sub = block[block.stratum.eq(s)]
                    v.extend([sub.weight.sum(), (sub.weight * sub.baseline).sum(), (sub.weight * sub.stateful).sum()])
                vectors.append(v)
            mat = np.asarray(vectors, dtype=float)
            totals[task] = mat.sum(axis=0)
            draws[task] = rng.multinomial(len(mat), np.full(len(mat), 1 / len(mat)), size=bootstrap_n) @ mat
        points = {k: metrics(v) for k, v in totals.items()}
        boots = {k: metrics(v) for k, v in draws.items()}
        points['pooled_population'] = metrics(sum(totals.values()))
        boots['pooled_population'] = metrics(sum(draws.values()))
        points['equal_task'] = {k: np.mean([v[k] for v in points.values() if k in v][:2]) for k in next(iter(points.values()))}
        # Equal-task ratios must be derived from equal-task joint prevalences, not averages of ratios.
        et = np.mean([totals[k] / totals[k][0] for k in totals], axis=0)
        eb = np.mean([draws[k] / draws[k][:, :1] for k in draws], axis=0)
        points['equal_task'], boots['equal_task'] = metrics(et), metrics(eb)
        return {scope: {k: {'estimate': float(v), 'ci': np.nanquantile(boots[scope][k], [.025, .975]).tolist()}
                        for k, v in rec.items()} for scope, rec in points.items()}

    variants = {}
    for name, labels in [('mistral_large', f.large_label), ('mistral_small', f.small_label), ('glm_disagreement_combined', f.combined_label)]:
        variants[name] = estimate(labels.eq('yes').astype(float))
    unresolved = f.combined_label.eq('undeterminable')
    if unresolved.any():
        variants['combined_upper_bound'] = estimate((f.combined_label.eq('yes') | unresolved).astype(float))
    variants['combined_maintenance_sensitivity'] = estimate((f.combined_label.eq('yes') & ~f.is_maintenance_candidate).astype(float))
    audit = f[f.route.eq('agreement_audit')]
    known_audit = audit[~audit.judge_label.eq('undeterminable')]
    # Two-phase design sensitivity: all disagreements observed, agreed-label errors sampled at p=160/1306.
    # This is an extrapolation of judge judgments, not a human-reference correction.
    p = protocol['audit_n'] / protocol['agreement_frame_n']
    ht = f.combined_label.eq('yes').astype(float)
    if not unresolved.any() and len(known_audit) == len(audit):
        ht.loc[audit.index] += (audit.judge_label.eq('yes').astype(float) - audit.large_label.eq('yes').astype(float)) / p
        # Signed contributions are intentionally allowed; they are not per-item probability labels.
        ht_metrics = {}
        for scope, sub in [('pooled_population', f), *list(f.groupby('study'))]:
            rec = {}
            for arm, block in sub.groupby('arm'):
                rec[arm] = float(np.average(ht.loc[block.index], weights=block.weight))
            rec['difference'] = rec['stateful'] - rec['baseline']
            ht_metrics[scope] = rec
    else:
        ht_metrics = None
    dis = f[f.route.eq('disagreement')]
    transitions = pd.crosstab(dis.large_label + ' / ' + dis.small_label, dis.judge_label).to_dict()
    audit_transitions = pd.crosstab(audit.large_label, audit.judge_label).to_dict()
    usage = read_jsonl(OUT / 'requests.jsonl')
    examples = []
    blind = {x['id']: x for x in read_jsonl(OUT / 'blind-inputs.jsonl')}
    # Examples selected after aggregate results by deterministic ID; frequencies use all judgments.
    for group_name, pool in [('disagreement', dis), ('agreement_audit_changed', audit[audit.audit_differs])]:
        by_pattern = {}
        for k, row in pool.sort_index().iterrows():
            pattern = row.large_label + '/' + row.small_label + '→' + row.judge_label
            if pattern not in by_pattern:
                by_pattern[pattern] = {'id': k, 'route': group_name, 'large_label': row.large_label,
                    'small_label': row.small_label, 'judge_label': row.judge_label,
                    'text': blind[k]['text'], 'quote': j.loc[k, 'quote'], 'rationale': j.loc[k, 'rationale']}
        examples.extend(list(by_pattern.values())[:6])
    save(OUT / 'examples.json', examples)
    result = {'model': MODEL, 'selected_n': len(selection), 'completed_n': len(j),
              'disagreement': {'n': len(dis), 'judge_labels': dis.judge_label.value_counts().to_dict(),
                               'matches_large': int(dis.judge_label.eq(dis.large_label).sum()),
                               'matches_small': int(dis.judge_label.eq(dis.small_label).sum()), 'transitions': transitions},
              'agreement_audit': {'n': len(audit), 'frame_n': 1306,
                                  'different_three_way_label': int(audit.audit_differs.sum()),
                                  'different_yes_indicator': int((known_audit.judge_label.eq('yes') != known_audit.large_label.eq('yes')).sum()),
                                  'undeterminable_n': int(audit.judge_label.eq('undeterminable').sum()),
                                  'transitions': audit_transitions},
              'combined_unresolved_n': int(unresolved.sum()), 'variants': variants,
              'audit_extrapolated_judge_sensitivity': ht_metrics,
              'interval_scope': '2000 matched composition-block bootstrap draws within task; fixed labels and fixed audit; excludes judge uncertainty and audit-extrapolation sampling uncertainty.',
              'api': {'requests': len(usage), 'usage': {k: sum(x.get('usage', {}).get(k, 0) for x in usage) for k in ['prompt_tokens', 'completion_tokens', 'total_tokens']},
                      'estimated_cost_usd': sum(x.get('estimated_cost_usd', 0) for x in usage)},
              'scope': 'LLM adjudication and agreement audit; not human validation; no manuscript changes.'}
    save(OUT / 'results.json', result)
    rows = []
    for model, scopes in variants.items():
        for scope, rec in scopes.items():
            for metric, stat in rec.items():
                rows.append({'coding': model, 'scope': scope, 'metric': metric, 'estimate': stat['estimate'], 'ci_low': stat['ci'][0], 'ci_high': stat['ci'][1]})
    pd.DataFrame(rows).to_csv(OUT / 'estimates.csv', index=False)
    print(json.dumps({k: v for k, v in result.items() if k not in ['variants', 'audit_extrapolated_judge_sensitivity', 'interval_scope']}, ensure_ascii=False, indent=2))
    print('POOLED', json.dumps({name: {k: v for k, v in scopes['pooled_population'].items() if k in ['baseline', 'stateful', 'difference', 'cue_stateful_rate', 'cue_fraction_of_increase']} for name, scopes in variants.items()}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['prepare', 'code', 'analyze'])
    p.add_argument('--limit', type=int, default=0)
    args = p.parse_args()
    if args.command == 'prepare':
        prepare()
    elif args.command == 'code':
        asyncio.run(code(args.limit))
    else:
        analyze()
