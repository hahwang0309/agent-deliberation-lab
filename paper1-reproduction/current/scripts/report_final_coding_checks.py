"""Summarize completed supplemental judgments without replacing primary results."""
import json,sys
from pathlib import Path
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from src.analysis.coding import human_labels,n10_summary

def main():
 p=R/'docs/research/submission-preparation/coding-finalization'
 kinds=['utterance','evidence','device']
 for k in kinds:assert (p/(k+'-summary.json')).exists(),k
 out={'scope':'post-hoc automated coding robustness; original primary estimates preserved','domains':{k:json.loads((p/(k+'-summary.json')).read_text()) for k in kinds}}
 u=pd.read_csv(p/'utterance-combined.csv')
 composition=n10_summary(human_labels(str(R/'data/raw/delidata')),u,2000,2026)
 (p/'utterance-composition.json').write_text(json.dumps(composition,ensure_ascii=False,indent=2))
 c=composition['by_sample']['comparison'];out['utterance_group_equal_means']={lab:{f:c['conditions'][lab][f]['estimate'] for f in ['probing','solution','reasoning','disagree']} for lab in ['A-baseline','A-stateful']}
 out['utterance_original_glm_missing']=129
 e=pd.read_csv(p/'evidence-combined.csv');out['evidence']={}
 for lab,g in e.groupby('label'):
  ref=g.references_argument.eq('yes')
  out['evidence'][lab]={'n':len(g),'referencing_n':int(ref.sum()),'peer_or_both_n':int((ref&g.argument_source.isin(['peer','both'])).sum()),'peer_or_both_share_given_reference':float(g.loc[ref,'argument_source'].isin(['peer','both']).mean()),'undeterminable_by_field':{k:int(g[k].eq('undeterminable').sum()) for k in ['references_argument','relevant','supports','rebutted','rebuttal_resolved']}}
 d=pd.read_csv(p/'device-combined.csv');out['devices']={}
 for dev,g in d.groupby('device'):
  out['devices'][dev]={'n':len(g),'instruction_followed_yes':float(g.instruction_followed.eq('yes').mean()),'states_position_change_yes':float(g.states_position_change.eq('yes').mean())}
 # Report audit differences field by field, not just the union across categories.
 out['agreement_audits']={}
 for kind in kinds:
  pairs=json.loads((p/(kind+'-initial-pairs.json')).read_text())
  sel=pd.read_csv(p/(kind+'-selection.csv'))
  judged={x['id']:x['labels'] for x in [json.loads(t) for t in (p/(kind+'-judge.jsonl')).read_text().splitlines()]}
  ids=sel.loc[sel.route.eq('agreement_audit'),'id'].tolist()
  fields=list(next(iter(pairs.values()))['first'])
  out['agreement_audits'][kind]={'n':len(ids),'per_field_difference_n':{f:sum(judged[i][f]!=pairs[i]['first'][f] for i in ids) for f in fields}}
 out['settings']={'initial_small_temperature':0,'judge_temperature':0,'judge_reasoning_effort':'high for every valid judge result','output_budget':'initial 4000 device/8000 utterance; missing-output retries and evidence12000','technical_changes':'unsupported none requests returned400 without labels; malformed or duplicate ids were retried, retaining every valid prior output'}
 # Report label perturbations on audit samples; never overwrite original agreed labels.
 out['audit_note']='Agreement audit differences are observed model disagreement, not human error rates. Main sensitivity retains initial complete agreements.'
 out['estimated_cost_undiscounted_usd']=sum(x.get('estimated_cost_usd',0) for x in [json.loads(s) for s in (p/'requests.jsonl').read_text().splitlines()])
 out['cost_note']='Conservative list-price estimate; early real-time Small calls used GLM prices as an upper bound. Batch/cached discounts not credited; interrupted requests may have unrecorded charges. Not a billing receipt.'
 (p/'results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 records=[]
 for lab,values in out['utterance_group_equal_means'].items():
  for metric,v in values.items():records.append({'domain':'utterance','condition':lab,'metric':metric,'estimate':v,'denominator':'equal weight to 68 source groups'})
 for lab,vals in out['evidence'].items():
  records.append({'domain':'evidence','condition':lab,'metric':'peer_or_both_given_reference','estimate':vals['peer_or_both_share_given_reference'],'denominator':vals['referencing_n']})
 pd.DataFrame(records).to_csv(p/'robustness-estimates.csv',index=False)
 print(json.dumps({k:out[k] for k in ['utterance_group_equal_means','evidence','devices','estimated_cost_undiscounted_usd']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
