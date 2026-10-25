"""Independently verify matched coding, weighted estimates, decomposition and rendered values."""
from pathlib import Path
import hashlib,json,re
import numpy as np
import pandas as pd

R=Path(__file__).resolve().parents[1];B=R/'docs/research';O=B/'position-change-mentions'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
protocol=json.loads((O/'protocol.json').read_text());meta=pd.read_csv(O/'sample-metadata.csv')
for name,h in protocol['inputs'].items():assert sha(R/name)==h,name
for name,h in protocol['frozen_files'].items():assert sha(O/name)==h,name
assert len(meta)==1600 and meta.id.nunique()==1600 and meta.pair_id.nunique()==800
assert meta.groupby('pair_id').arm.nunique().eq(2).all()
assert meta.groupby('pair_id').weight.nunique().eq(1).all()
assert meta.groupby(['study','stratum','arm']).size().eq(100).all()
population=pd.read_csv(O/'population-strata.csv').set_index(['study','stratum'])['n']
for key,g in meta.groupby(['study','stratum','arm']):
    assert np.isclose(g.weight.sum(),population.loc[key[:2]])
    assert g.ordinal.nunique()>1
inputs={x['id']:x for x in map(json.loads,(O/'blind-inputs.jsonl').read_text().splitlines())}
for row in meta.itertuples():assert hashlib.sha256(inputs[row.id]['text'].encode()).hexdigest()==row.text_sha256

result=json.loads((O/'results.json').read_text());rec=[]
for model in protocol['models']:
    coded=pd.DataFrame([json.loads(x)for x in (O/f'coded-{model}.jsonl').read_text().splitlines()])
    assert len(coded)==1600 and coded.id.nunique()==1600 and set(coded.id)==set(meta.id)
    assert coded.label.isin(['yes','partial','no']).all()
    normalize=lambda x:re.sub(r'\s+',' ',x).strip()
    for row in coded.itertuples():
        if row.label!='no':assert row.quote and normalize(row.quote)in normalize(inputs[row.id]['text']),row.id
    f=meta.merge(coded,on='id',validate='one_to_one');f['y']=f.label.eq('yes').astype(int)
    tasks={}
    for study,g in f.groupby('study'):
        task={}
        for arm,h in g.groupby('arm'):
            task[arm]=np.average(h.y,weights=h.weight)
            expected=result['estimates'][model][study][arm]
            assert np.isclose(task[arm],expected['estimate'])
            assert expected['ci'][0]<=expected['estimate']<=expected['ci'][1]
        tasks[study]=task
        assert np.isclose(task['stateful']-task['baseline'],result['estimates'][model][study]['difference']['estimate'])
    for arm in ['baseline','stateful']:
        expected=np.mean([v[arm]for v in tasks.values()]);assert np.isclose(expected,result['estimates'][model]['equal_task'][arm]['estimate'])
    for arm,h in f.groupby('arm'):
        pooled=float(np.average(h.y,weights=h.weight))
        assert np.isclose(pooled,result['estimates'][model]['pooled_population'][arm]['estimate'])
    for category in ['none','closing','moved','direct']:
        h=f[f.arm.eq('stateful')&f.stratum.eq(category)];total=f[f.arm.eq('stateful')].weight.sum()
        joint=float((h.weight*h.y).sum()/total);pop=float(h.weight.sum()/total)
        expected=result['decomposition'][model]['pooled_population'][category]
        assert np.isclose(joint,expected['stateful_joint']['estimate'])
        assert np.isclose(pop,expected['population_share']['estimate'])
    denied=set(json.loads((O/'maintenance-audit-candidates.json').read_text())['ids'])
    for arm,h in f.groupby('arm'):
        strict=h.y.where(~h.id.isin(denied),0)
        assert np.isclose(np.average(strict,weights=h.weight),result['maintenance_strict_sensitivity'][model]['pooled_population'][arm]['estimate'])
    # Independently standardize each utterance weight to one half for each task/arm.
    f['standard_weight']=f.weight/f.groupby(['study','arm']).weight.transform('sum')/2
    for category in ['none','closing','moved','direct']:
        h=f[f.arm.eq('stateful')&f.stratum.eq(category)];pop=h.standard_weight.sum();joint=(h.standard_weight*h.y).sum()
        rate=joint/pop
        expected=result['decomposition'][model]['equal_task'][category]
        assert np.isclose(pop,expected['population_share']['estimate'])
        assert np.isclose(joint,expected['stateful_joint']['estimate'])
        assert np.isclose(rate,expected['stateful_rate']['estimate'])
        b=f[f.arm.eq('baseline')&f.stratum.eq(category)]
        diff=joint-(b.standard_weight*b.y).sum()
        assert np.isclose(diff,expected['difference_contribution']['estimate'])
        rec.append((model,category,float(pop),float(rate),float(joint)))
    terms=result['decomposition'][model]['equal_task']
    assert np.isclose(sum(v['stateful_joint']['estimate']for v in terms.values()),result['estimates'][model]['equal_task']['stateful']['estimate'])
    assert np.isclose(sum(v['difference_contribution']['estimate']for v in terms.values()),result['estimates'][model]['equal_task']['difference']['estimate'])
legacy=pd.read_csv(O/'legacy-instruction-checks.csv')
r=legacy[legacy.coder.eq(protocol['models'][0])&legacy.device.eq('switched')].iloc[0]
assert r.valid_n==300 and r.behaviour_yes==281 and r.full_instruction_yes==278
for key in ['inputs','outputs']:
    for name,h in json.loads((O/'output-manifest.json').read_text())[key].items():assert sha(R/name)==h,name
for name in ['README.md','../supplementary-information/PositionChangeMentions.md']:
    p=(O/name).resolve()
    for link in re.findall(r'\]\(([^)]+)\)',p.read_text()):
        if not link.startswith(('http:','https:','#')):assert (p.parent/link.split('#')[0]).exists(),link
checks={'date':'2026-10-24','status':'passed; descriptive automatic coding, human validation pending',
        'paired_sample':'800 pairs, 1600 targets, 8 exposure-by-task strata with exactly matched arm selection',
        'source_hashes':'unchanged utterance data and read-only original DB',
        'accepted_labels':'1600 unique final labels per coder; no missing targets',
        'quote_evidence':'all yes/partial evidence checked against target text, not context',
        'weighted_estimates':'both tasks and equal-task summary recomputed independently',
        'decomposition':'four disjoint cue contributions sum to all-utterance prevalence and matched difference',
        'legacy_937':'281/300 explicit-change mention; 278/300 full instruction-following, separately preserved',
        'coders':protocol['models'],'coder_agreement':result['coder_agreement'],
        'causal_scope':'observed cue decomposition; not independent causal attribution to cues'}
(O/'verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n');print(json.dumps(checks,ensure_ascii=False))
