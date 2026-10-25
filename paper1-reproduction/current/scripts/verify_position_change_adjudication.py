from pathlib import Path
from collections import Counter
import json,hashlib,random,re,sys
import pandas as pd
import numpy as np
R=Path.cwd();O=R/'docs/research/position-change-adjudication';S=R/'docs/research/position-change-mentions'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=json.loads((O/'protocol.json').read_text());r=json.loads((O/'results.json').read_text())
a=pd.read_csv(S/'classified-mistral-large-2512.csv').set_index('id');b=pd.read_csv(S/'classified-mistral-small-2603.csv').set_index('id');sel=pd.read_csv(O/'selection.csv').set_index('id');f=pd.read_csv(O/'combined-labels.csv').set_index('id');j=pd.read_csv(O/'judgments.csv',keep_default_na=False).set_index('id');blind={x['id']:x for x in map(json.loads,(O/'blind-inputs.jsonl').read_text().splitlines())}
assert len(j)==454 and not j.index.duplicated().any() and set(j.index)==set(sel.index)==set(blind)
assert all(set(x)=={'id','speaker','text'}for x in blind.values())
assert all(sha(R/name)==h for name,h in p['source_sha256'].items())
protected_match=all(sha(R/name)==h for name,h in p['protected_manuscript_sha256'].items())
after_revision='--after-manuscript-revision' in sys.argv
if not after_revision:assert protected_match, 'Historical pre-application manuscript changed; use --after-manuscript-revision for current arithmetic audit'
AUDIT=R/'docs/research/submission-preparation' if after_revision else O
assert all(sha(O/name)==h for name,h in p['frozen_files'].items())
dis=set(a.index[a.label!=b.reindex(a.index).label]);agr=sorted(set(a.index)-dis)
assert set(sel.index[sel.route.eq('disagreement')])==dis and len(dis)==294
assert set(random.Random(20261025).sample(agr,160))==set(sel.index[sel.route.eq('agreement_audit')])
assert f.index.is_unique and set(f.index)==set(a.index)
assert all(f.loc[k,'combined_label']==j.loc[k,'label']for k in dis)
assert all(f.loc[k,'combined_label']==a.loc[k,'label']for k in agr)
assert not f.combined_label.isna().any()
norm=lambda s:re.sub(r'\s+',' ',s).strip()
for k,row in j.iterrows():
 assert row.label in ['yes','partial','no','undeterminable']
 assert row.rationale.strip()
 assert hashlib.sha256(blind[k]['text'].encode()).hexdigest()==row.text_sha256
 if row.label in ['yes','partial']:assert row.quote.strip()
 if row.quote:assert norm(row.quote)in norm(blind[k]['text'])and len(row.quote.split())<=25
# Independent weighted means and cue decomposition, avoiding the paired/bootstrap helper.
for key,col in [('mistral_large','large_label'),('mistral_small','small_label'),('glm_disagreement_combined','combined_label')]:
 v=r['variants'][key]['pooled_population'];rates={arm:float(np.average(g[col].eq('yes'),weights=g.weight))for arm,g in f.groupby('arm')}
 assert np.isclose(rates['baseline'],v['baseline']['estimate'],atol=1e-12)
 assert np.isclose(rates['stateful'],v['stateful']['estimate'],atol=1e-12)
 assert np.isclose(rates['stateful']-rates['baseline'],v['difference']['estimate'],atol=1e-12)
 pair=f.reset_index().pivot(index=['study','pair_id','block','stratum','weight'],columns='arm',values=col).reset_index()
 pair['delta']=pair.stateful.eq('yes').astype(int)-pair.baseline.eq('yes').astype(int)
 withcue=pair.stratum.isin(['direct','moved']);contrib=(pair.loc[withcue,'weight']*pair.loc[withcue,'delta']).sum()/pair.weight.sum()
 assert np.isclose(contrib/(rates['stateful']-rates['baseline']),v['cue_fraction_of_increase']['estimate'],atol=1e-12)
 state=f[f.arm.eq('stateful')&f.stratum.isin(['direct','moved'])]
 assert np.isclose(np.average(state[col].eq('yes'),weights=state.weight),v['cue_stateful_rate']['estimate'],atol=1e-12)
# Independently reconstruct two-phase judge totals using inclusion probabilities.
for arm,g in f.groupby('arm'):
 judge_dis=g.loc[g.index.intersection(dis)]
 agree=g.loc[g.index.intersection(agr)]
 aud=g.loc[g.index.intersection(sel.index[sel.route.eq('agreement_audit')])]
 total=(judge_dis.weight*judge_dis.judge_label.eq('yes')).sum()+(agree.weight*agree.large_label.eq('yes')).sum()
 total+=(aud.weight*(aud.judge_label.eq('yes').astype(int)-aud.large_label.eq('yes').astype(int))/(160/1306)).sum()
 assert np.isclose(total/g.weight.sum(),r['audit_extrapolated_judge_sensitivity']['pooled_population'][arm],atol=1e-12)
# Original published estimates must be reproduced, not silently changed by refactoring.
old=json.loads((S/'results.json').read_text())
for key,model in [('mistral_large','mistral-large-2512'),('mistral_small','mistral-small-2603')]:
 for scope in ['wason','a1r','pooled_population']:
  for metric in ['baseline','stateful','difference']:
   assert np.isclose(old['estimates'][model][scope][metric]['estimate'],r['variants'][key][scope][metric]['estimate'],atol=1e-12)
usage=[json.loads(s)for s in(O/'requests.jsonl').read_text().splitlines()]
assert len(usage)<90 and r['api']['estimated_cost_usd']<5
assert np.isclose(sum(x.get('usage',{}).get('prompt_tokens',0)*1.4/1e6+x.get('usage',{}).get('completion_tokens',0)*4.4/1e6 for x in usage),r['api']['estimated_cost_usd'])
# Extract raw label fluctuations seen only because format validation required retries.
rawlabels={}
for file in (O/'raw').glob('*.json'):
 raw=json.loads(file.read_text());content=raw['choices'][0]['message'].get('content')
 if isinstance(content,list):content=''.join(x.get('text','')for x in content if isinstance(x,dict)and x.get('type')=='text')
 if not content:continue
 try:items=json.loads(content).get('items',[])
 except (ValueError,AttributeError):continue
 for x in items:
  if x.get('id')in blind and x.get('label')in ['yes','partial','no','undeterminable']:
   rawlabels.setdefault(x['id'],[]).append({'request':file.stem,'label':x['label']})
retried={k:v for k,v in rawlabels.items()if len(v)>1};varied={k:v for k,v in retried.items()if len({x['label']for x in v})>1}
(AUDIT/'format-retry-diagnostics.json').write_text(json.dumps({'note':'Opportunistic diagnostic from format retries, not a random reliability study. Accepted labels remain unchanged.','retried_target_n':len(retried),'targets_with_label_variation_n':len(varied),'varied_targets':varied},ensure_ascii=False,indent=2)+'\n')
# Frozen-label bounds for these observed retry variations; no new model calls.
fl=f.combined_label.eq('yes').astype(int);fu=fl.copy()
for k,v in varied.items():
 if k in dis:
  fl.loc[k]=int(all(x['label']=='yes'for x in v));fu.loc[k]=int(any(x['label']=='yes'for x in v))
variation={}
for arm,g in f.groupby('arm'):
 variation[arm]={'min':float(np.average(fl.loc[g.index],weights=g.weight)),'max':float(np.average(fu.loc[g.index],weights=g.weight))}
variation['difference']={'min':variation['stateful']['min']-variation['baseline']['max'],'max':variation['stateful']['max']-variation['baseline']['min']}
V={'date':'2026-10-25','selected_n':454,'accepted_n':454,'missing':0,'duplicate_ids':0,'all_accepted_quotes_exact_target_spans':True,'api_input_fields':['id','speaker','text'],'source_hashes_unchanged':True,'protected_manuscript_hashes_unchanged':protected_match,'historical_protection_check_applicable':not after_revision,'frozen_sample_reproduced':True,'combined_label_rule_checked_for_all_1600':True,'weighted_rates_and_cue_decomposition_independently_recomputed':True,'original_coder_estimates_reproduced':True,'audit_extrapolation_independently_recomputed':True,'cost_guard_satisfied':True,'estimated_cost_usd':r['api']['estimated_cost_usd'],'opportunistic_retry_label_variation':{'retried_targets':len(retried),'varied_targets':len(varied),'combined_rate_bounds':variation},'scope':'Evidence spans and arithmetic/provenance checks, not human-reference semantic validation.','artifact_sha256':{p.name:sha(p)for p in [O/'protocol.json',O/'results.json',O/'judgments.csv',O/'combined-labels.csv',O/'estimates.csv']}}
(AUDIT/('adjudication-verification.json' if after_revision else 'Verification.json')).write_text(json.dumps(V,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in V.items()if k not in ['artifact_sha256','scope','api_input_fields']},ensure_ascii=False,indent=2))
