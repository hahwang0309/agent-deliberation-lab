"""Validate independently completed human-review JSONs and report agreement/accuracy.

python scripts/summarize_human_validation.py --a <A.json> --b <B.json> \
    --final <adjudicated.json> --out <new-output-directory>
No LLM calls, no source database writes. Incomplete submissions fail explicitly.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'docs/research/human-validation/coordinator'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def validate(payload, packet, expected_coder=None):
    errors = []
    if payload.get('packet_id') != packet['packet_id']:
        errors.append('packet_id mismatch')
    if payload.get('codebook_version') != packet['codebook_version']:
        errors.append('codebook_version mismatch')
    if expected_coder and payload.get('coder_id') != expected_coder:
        errors.append('coder_id mismatch')
    records = payload.get('records', {})
    allowed = {c['case_id'] for c in packet['cases']}
    if set(records) - allowed:
        errors.append('unknown case IDs')
    for c in packet['cases']:
        if c['split'] != 'main':
            continue
        cid = c['case_id']
        r = records.get(cid, {})
        if r.get('review_status') != 'completed':
            errors.append(f'{cid}: not completed')
        if not str(r.get('rationale', '')).strip():
            errors.append(f'{cid}: missing rationale')
        labels = r.get('labels', {})
        for k, values in packet['schema'][c['task']].items():
            value = labels.get(k)
            if values == 'integer_list':
                if not isinstance(value, list) or any(type(s) is not int or s not in c['available_seqs'] for s in value):
                    errors.append(f'{cid}.{k}: invalid transcript sequence list')
            elif value not in values:
                errors.append(f'{cid}.{k}: invalid or missing label')
        if c['task'] == 'device':
            if (not c['instruction']) != (labels.get('instruction_followed') == 'none'):
                errors.append(f'{cid}: instruction_followed none inconsistent with instruction')
        if c['task'] == 'evidence':
            ref = labels.get('references_argument')
            if ref == 'yes':
                if not labels.get('argument_seqs') or labels.get('argument_source') == 'none':
                    errors.append(f'{cid}: reference=yes needs sequence and source')
                if any(labels.get(k) == 'none' for k in ['relevant', 'supports', 'rebutted']):
                    errors.append(f'{cid}: reference=yes cannot have conditional none')
            elif ref in ['no', 'undeterminable']:
                if labels.get('argument_seqs') or labels.get('argument_source') != 'none' or any(labels.get(k) != 'none' for k in ['relevant', 'supports', 'rebutted']):
                    errors.append(f'{cid}: no identified reference needs source/conditional none and empty seqs')
                if labels.get('rebuttal_resolved') != 'undeterminable':
                    errors.append(f'{cid}: no identified reference needs rebuttal_resolved=undeterminable')
            if ref == 'yes' and labels.get('rebutted') == 'no' and labels.get('rebuttal_resolved') != 'not_rebutted':
                errors.append(f'{cid}: no rebuttal needs not_rebutted')
            if ref == 'yes' and labels.get('rebutted') == 'yes' and labels.get('rebuttal_resolved') == 'not_rebutted':
                errors.append(f'{cid}: rebuttal=yes conflicts with not_rebutted')
            if ref == 'yes' and labels.get('rebutted') == 'undeterminable' and labels.get('rebuttal_resolved') != 'undeterminable':
                errors.append(f'{cid}: unknown rebuttal needs resolution undeterminable')
    return errors


def metrics(pairs, expected_categories=()):
    """Pairs are reference, prediction, design weight; None means missing prediction."""
    all_n = len(pairs)
    complete = [(a, b, w) for a, b, w in pairs if b is not None and b != '']
    n = len(complete)
    if not n:
        return {'n_total': all_n, 'n_valid': 0, 'n_missing_prediction': all_n}
    categories = sorted(set(expected_categories) | {str(x) for a, b, _ in complete for x in [a, b]})
    result = {'n_total': all_n, 'n_valid': n, 'n_missing_prediction': all_n-n,
              'confusion_matrix': {a: {b: sum(x == a and y == b for x, y, _ in complete) for b in categories} for a in categories}}
    for name, weighted in [('unweighted', False), ('source_pool_weighted', True)]:
        p = [(a, b, w if weighted else 1) for a, b, w in complete]
        total = sum(w for _, _, w in p)
        po = sum(w for a, b, w in p if a == b) / total
        pe = sum(sum(w for a, _, w in p if a == k) * sum(w for _, b, w in p if b == k) for k in categories) / total**2
        by_label = {}
        for k in categories:
            tp = sum(w for a, b, w in p if a == b == k)
            true = sum(w for a, _, w in p if a == k)
            pred = sum(w for _, b, w in p if b == k)
            by_label[k] = {'precision': tp/pred if pred else None, 'recall': tp/true if true else None,
                           'n_reference': sum(a == k for a, _, _ in p), 'n_prediction': sum(b == k for _, b, _ in p)}
        result[name] = {'exact_agreement': po, 'kappa': (po-pe)/(1-pe) if pe < 1 else None, 'by_label': by_label}
    return result


def target_combined(v):
    return 'task_content' if v in ['solution', 'reasoning'] else v


def analyze(a, b, final, packet, mapping):
    cases = [c for c in packet['cases'] if c['split'] == 'main']
    report = {'status': 'human-completed inputs', 'n_main': len(cases), 'human_agreement_before_adjudication': {}, 'machine_vs_adjudicated': {}, 'by_condition': {},
              'notes': ['Human agreement uses independent pre-adjudication labels.',
                        'Weights refer only to each frozen source pool; never all AI utterances.',
                        'Precision/recall with no relevant cases are null, not zero or perfect.',
                        'Point estimates only. Cluster-aware uncertainty remains to be calculated before final inferential reporting.',
                        'Device sampling unit is category × utterance; duplicate physical utterances can occur across categories.',
                        'Layer3 conditional fields are evaluated only on human reference=yes; resolution only on human rebutted=yes.',
                        'Standalone solution/reasoning statistics are diagnostic; combined task_content is the manuscript inference label.']}
    disputed = []
    for task in packet['schema']:
        rows = [c for c in cases if c['task'] == task]
        fields = list(packet['schema'][task])
        if task == 'utterance':
            fields += ['target_combined']
        for field in fields:
            if field == 'argument_seqs':
                # Exact sequence-list equality is not a semantic validity score.
                continue
            hp, mp, sp = [], [], []
            by_condition = defaultdict(lambda: {'human': [], 'primary': [], 'secondary': []})
            categories = ['task_content', 'agree', 'disagree', 'moderation', 'none'] if field == 'target_combined' else packet['schema'][task][field]
            for c in rows:
                cid = c['case_id']; m = mapping[cid]
                get = lambda lab: target_combined(lab.get('target')) if field == 'target_combined' else lab.get(field)
                av, bv, fv = [get(z['records'][cid]['labels']) for z in [a, b, final]]
                weight = m['sampling']['weight']
                if task == 'device' and field == 'instruction_followed' and not c['instruction']:
                    continue
                hp.append((av, bv, weight))
                condition = m['source']['label']
                by_condition[condition]['human'].append((av, bv, weight))
                if task == 'evidence' and field != 'references_argument':
                    if final['records'][cid]['labels']['references_argument'] != 'yes':
                        continue
                    if field == 'rebuttal_resolved' and final['records'][cid]['labels']['rebutted'] != 'yes':
                        continue
                for dst, source in [(mp, 'primary'), (sp, 'secondary')]:
                    pred = get(m[source]) if m[source] else None
                    dst.append((fv, pred, weight))
                    by_condition[condition][source].append((fv, pred, weight))
            report['human_agreement_before_adjudication'][task+'.'+field] = metrics(hp, categories)
            report['machine_vs_adjudicated'][task+'.'+field] = {'primary': metrics(mp, categories), 'secondary': metrics(sp, categories)}
            report['by_condition'][task+'.'+field] = {condition: {name: metrics(pairs, categories) for name,pairs in values.items()} for condition,values in by_condition.items()}
        for c in rows:
            cid = c['case_id']; al = a['records'][cid]['labels']; bl = b['records'][cid]['labels']
            fields = [k for k in packet['schema'][task] if (sorted(al[k]) if k == 'argument_seqs' else al[k]) != (sorted(bl[k]) if k == 'argument_seqs' else bl[k])]
            if fields:
                disputed.append({'case_id': cid, 'fields': fields, 'a': al, 'b': bl,
                                 'final': final['records'][cid]['labels'], 'decision_basis': final['records'][cid].get('decision_basis', '')})
    report['n_disputed_cases'] = len(disputed)
    return report, disputed


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--a', required=True); p.add_argument('--b', required=True)
    p.add_argument('--final', required=True); p.add_argument('--out', required=True)
    args = p.parse_args()
    packet = read(PACK / 'packet.json')
    a, b, final = [read(x) for x in [args.a, args.b, args.final]]
    errors = []
    for label, payload, coder in [('A', a, 'A'), ('B', b, 'B'), ('final', final, 'ADJ')]:
        errors.extend(label+': '+e for e in validate(payload, packet, coder))
    if not str(final.get('adjudicator_id', '')).strip():
        errors.append('final: adjudicator_id missing')
    if errors:
        raise SystemExit('\n'.join(errors[:30])+f'\nTotal errors: {len(errors)}. No results generated.')
    mapping = {m['case_id']: m for m in read(PACK / 'case-map-and-machine-labels.json')}
    report, disputes = analyze(a, b, final, packet, mapping)
    for r in disputes:
        if not r['decision_basis'].strip():
            errors.append(r['case_id']+': missing adjudication decision_basis')
    if errors:
        raise SystemExit('\n'.join(errors)+'\nNo results generated.')
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    for name, data in [('metrics.json', report), ('disagreements.json', disputes)]:
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 사람 검증 결과 요약', '', f'본 검증 {len([c for c in packet["cases"] if c["split"]=="main"])}건; 독립 판정 불일치 사례 {len(disputes)}건.', '',
             '아래는 자동 집계한 점추정치다. 군집을 고려한 신뢰구간, 오류 사례의 해석, 원고 반영 결정은 결과 보고서에 추가한다.', '',
             '| 항목 | 사람 간 일치율 | 사람 간 κ | 주 자동 코더와 최종 사람 판정의 일치율 | 유효 표본 |', '|---|---:|---:|---:|---:|']
    for field, h in report['human_agreement_before_adjudication'].items():
        m = report['machine_vs_adjudicated'][field]['primary']
        fmt = lambda x: '산출 불가' if x is None else f'{x:.3f}'
        lines.append(f'| {field} | {fmt(h.get("unweighted",{}).get("exact_agreement"))} | {fmt(h.get("unweighted",{}).get("kappa"))} | {fmt(m.get("unweighted",{}).get("exact_agreement"))} | {m["n_valid"]} |')
    lines += ['', '라벨별 정밀도·재현율·분모·혼동행렬과 원 표집틀 가중치는 metrics.json 참조. 층3 조건부 항목은 사람이 실제 참조 논거를 확인한 사례만 평가한다.', '',
              '연습 사례는 모든 수치에서 제외했다. 원자료 누락과 판정 불가를 숨기지 말고 별도 보고한다.']
    (out / 'Summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(f'Results written: {out}')


if __name__ == '__main__':
    main()
