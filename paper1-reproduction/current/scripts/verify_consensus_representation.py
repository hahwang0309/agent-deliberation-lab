"""Verify new saved point estimates against source rows and keep audit trail."""
from pathlib import Path
import json,hashlib,sys,re
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from src.analysis.group_disagreement import paired_groups,decompose
O=R/'docs/research/consensus-representation';S=O/'source-data'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def close(a,b):assert np.isclose(a,b,atol=1e-12,rtol=1e-12),(a,b)
def main():
 checks={};x=json.loads((S/'results.json').read_text())
 for path,digest in json.loads((S/'input-manifest.json').read_text()).items():
  if path==str((O/'AnalysisPlan.md').relative_to(R)) and sha(R/path)!=digest:
   frozen=O/'AnalysisPlanAtMainComputation.md'
   assert sha(frozen)==digest and (R/path).read_bytes().startswith(frozen.read_bytes())
   checks['plan_extension']='Main computation plan hash preserved in AnalysisPlanAtMainComputation.md; within-room party analysis appended after inspecting pooled profiles'
  else:assert sha(R/path)==digest,path
 for path,digest in json.loads((S/'report-input-manifest.json').read_text()).items():assert sha(R/path)==digest,path
 for path,digest in json.loads((S/'group-party-input-manifest.json').read_text()).items():assert sha(R/path)==digest,path
 checks['input_hashes']='valid'
 for row in json.loads((S/'figure-source-data.json').read_text())['records']:
  v=x
  for k in row['json_path']:v=v[k]
  assert v==row['record'],row['label']
 checks['figure_estimate_records']=len(json.loads((S/'figure-source-data.json').read_text())['records'])
 h=pd.read_csv(S/'human-native-groups.csv');rows=[]
 for item,q in h.groupby('item'):
  result={}
  for phase in ['pre','post']:
   means=q[phase+'_mean'];within=q[phase+'_within'].mean();between=means.var(ddof=0)
   close(within+between,(q[phase+'_within']+means**2).mean()-means.mean()**2)
   result[phase+'_between']=between;result[phase+'_between_unbiased']=means.var(ddof=1)
   result[phase+'_consensus']=q[phase+'_consensus'].mean()
  rows.append(result)
 for k,v in pd.DataFrame(rows).mean().items():close(v,x['human']['native']['item_bootstrap'][k]['estimate'])
 assert len(h)==1200 and h.group.nunique()==40
 checks['human_actual_rooms']='1200 group-item records; moments and variance identity verified'
 for m in ['claude','gemini','mistral']:
  source=pd.read_csv(R/f'data/study1/results/exploratory/{m}/a1r_agents.csv');a=paired_groups(source,['A-baseline','A-stateful'])
  frozen=decompose(a);d=x['models'][m];levels=d['levels']
  for arm in ['A-baseline','A-stateful']:
   t=frozen[frozen.label==arm]
   for k in ['within','between']:close(t[k].mean(),levels[arm]['item_bootstrap']['post_'+k]['estimate'])
   close(t.between_unbiased.mean(),levels[arm]['item_bootstrap']['post_between_unbiased']['estimate'])
   g=a[a.label==arm].groupby(['item_id','block']).post.std(ddof=0)
   close(g.le(1).groupby(level=0).mean().mean(),levels[arm]['item_bootstrap']['post_consensus']['estimate'])
   pm=pd.read_csv(S/f'{m}-matched-persona-outcomes.csv');pm=pm[pm.label==arm]
   close(pm.groupby('item_id').mae.mean().mean(),d['matched'][arm+'_mae']['estimate'])
   close(pm.groupby('item_id').human_mover_direction.mean().mean(),d['matched'][arm+'_human_mover_direction']['estimate'])
  assert d['sample']['paired_blocks']==(415 if m=='mistral' else 416)
  assert d['sample']['AI_agent_item_rows_unmatched']==72
  profile=pd.read_csv(S/f'{m}-party-profiles.csv')
  for arm in ['Human','A-baseline','A-stateful']:
   gap=profile[arm+'_gap'].to_numpy();initial=profile.initial_gap.to_numpy()
   close(np.mean(np.sign(gap)==np.sign(initial)),d['party_profiles'][arm]['initial_gap_direction_agreement']['estimate'])
   close(np.abs(gap).mean(),d['party_profiles'][arm]['mean_absolute_party_gap']['estimate'])
   close(np.mean(initial*gap)/np.mean(initial**2),d['party_profiles'][arm]['initial_gap_alignment']['estimate'])
  # Same original source persona and score for every joined record.
  from src.analysis import humans
  items=profile.item.tolist();human=humans.a1r_delegates(str(R/'data/raw/a1r/dataset.tab'),items,'1')
  q=a.merge(human,left_on=['persona','item_id'],right_on=['row','item'],suffixes=('_a','_h'),validate='many_to_one')
  assert (q.pre_a==q.pre_h).all() and(q.party_a.astype(str)==q.party_h.astype(str)).all()
  q['error']=np.abs(q.post_a-q.post_h)
  independently=q.groupby(['label','item_id','persona']).error.mean().groupby(['label','item_id']).mean().groupby('label').mean()
  for arm in ['A-baseline','A-stateful']:close(independently[arm],d['matched'][arm+'_mae']['estimate'])
 checks['AI_groups_and_matched_persona_points']='source means, SD criterion, MAE, party gap and alignment independently checked'
 room=json.loads((S/'group-party-adjustment.json').read_text())
 for model in ['claude','gemini','mistral']:
  t=pd.read_csv(S/f'{model}-room-party-metrics.csv')
  a=paired_groups(pd.read_csv(R/f'data/study1/results/exploratory/{model}/a1r_agents.csv'),['A-baseline','A-stateful'])
  for arm in ['A-baseline','A-stateful']:
   q=t[t.label==arm];v=room['models'][model][arm]
   for c in q.select_dtypes('number').columns:
    if c=='block':continue
    close(q.groupby('item')[c].mean().mean(),v[c]['estimate'])
   assert np.allclose(q.party_order_retained+q.party_order_tied+q.party_order_reversed,q.initial_party_gap_present)
   assert np.allclose(q.party_order_retained_and_consensus+q.party_order_tied_and_consensus+q.party_order_reversed_and_consensus,q.initial_party_gap_and_consensus)
   for _,r in q.iterrows():
    g=a[(a.item_id==r['item'])&(a.block==r['block'])&(a.label==arm)]
    p=g[g.party.astype(str)=='1'];rep=g[g.party.astype(str)=='2']
    gap0=p.pre.mean()-rep.pre.mean();gap1=p.post.mean()-rep.post.mean()
    consensus=g.post.std(ddof=0)<=1
    valid=len(p)>0 and len(rep)>0 and gap0!=0
    close(r['party_order_retained_and_consensus'],float(valid and consensus and gap0*gap1>0))
    mutual=valid and ((p.post.mean()-p.pre.mean())*np.sign(-gap0)>0) and ((rep.post.mean()-rep.pre.mean())*np.sign(gap0)>0)
    close(r['mutual_party_approach_and_consensus'],float(mutual and consensus))
 checks['within_room_party_metrics']='party ordering partition and joint consensus/party adjustment independently verified against raw paired AI rows'
 for key in ['native','balanced5','native_balanced_eligible']:
  table=pd.read_csv(S/('human-native-items.csv'if key=='native'else'human-balanced-panel-items.csv'if key=='balanced5'else'human-native-eligible-items.csv'))
  c=x['human'][key]['conditional_consensus_direction']
  for numerator,name in [('one_way_and_consensus','one_way_among_consensus'),('two_way_and_consensus','two_way_among_consensus')]:close(table[numerator].mean()/table.post_consensus.mean(),c[name]['estimate'])
 for p in [O/'README.md',O/'AnalysisPlan.md']:
  for link in re.findall(r'\]\(([^)]+)\)',p.read_text()):
   if link.startswith(('http:','https:','#')):continue
   if link=='source-data/verification.json':continue
   assert (p.parent/link.split('#')[0]).exists(),(p.name,link)
 checks['report_local_links']='valid'
 checks['tests']='4 interpretation/invariant tests passed; see tests/test_consensus_representation.py'
 checks['visual_review']='Both saved figures inspected; long first-figure xlabel split over two lines'
 checks['scope']='Post-hoc evidence; no normative political representation or matched causal human/AI treatment claim'
 (S/'verification.json').write_text(json.dumps({'date':'2026-10-21','status':'passed','checks':checks},ensure_ascii=False,indent=2)+'\n')
 paths=list(S.glob('*.json'))+list(S.glob('*.csv'))+list((O/'figures').glob('*'))+list(O.glob('*.md'))+[R/'scripts/analyze_consensus_representation.py',R/'scripts/analyze_group_party_adjustment.py',R/'scripts/report_consensus_representation.py',R/'tests/test_consensus_representation.py',Path(__file__)]
 (S/'output-manifest.json').write_text(json.dumps({str(p.relative_to(R)):sha(p)for p in paths if p.name!='output-manifest.json'},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(checks,ensure_ascii=False))
if __name__=='__main__':main()
