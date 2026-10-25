"""Additional descriptive post-hoc check: both parties' adjustment inside each room."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from src.analysis import humans
from src.analysis.group_disagreement import paired_groups
O=R/'docs/research/consensus-representation';S=O/'source-data';B=5000;SEED=20261021;PANELS=200
items=pd.read_csv(R/'data/study1/results/exploratory/human/n3_human_items.csv').item.tolist()
ix=np.random.default_rng(SEED).integers(len(items),size=(B,len(items)))
def measures(pre,post,party):
 pre=np.atleast_2d(pre);post=np.atleast_2d(post);party=np.broadcast_to(np.atleast_2d(party),pre.shape)
 d=party=='1';r=party=='2';valid=d.any(axis=1)&r.any(axis=1)
 def avg(a,mask):return np.divide((a*mask).sum(axis=1),mask.sum(axis=1),out=np.zeros(a.shape[0]),where=mask.sum(axis=1)>0)
 d0,r0,d1,r1=avg(pre,d),avg(pre,r),avg(post,d),avg(post,r)
 gap0=d0-r0;gap1=d1-r1;hasgap=valid&(gap0!=0);con=post.std(axis=1)<=1
 both=hasgap&((d1-d0)*np.sign(r0-d0)>0)&((r1-r0)*np.sign(d0-r0)>0)
 same=hasgap&(np.sign(gap1)==np.sign(gap0));tie=hasgap&(gap1==0);flip=hasgap&(gap1*gap0<0)
 return {'consensus':con.astype(float),'initial_party_gap_present':hasgap.astype(float),
 'mutual_party_approach':both.astype(float),'mutual_party_approach_and_consensus':(both&con).astype(float),
 'party_order_retained':same.astype(float),'party_order_tied':tie.astype(float),'party_order_reversed':flip.astype(float),
 'initial_party_gap_and_consensus':(hasgap&con).astype(float),'party_order_retained_and_consensus':(same&con).astype(float),
 'party_order_tied_and_consensus':(tie&con).astype(float),'party_order_reversed_and_consensus':(flip&con).astype(float)}
def rec(p,d):
 d=np.asarray(d);f=d[np.isfinite(d)];return {'estimate':float(p),'ci':np.quantile(f,[.025,.975]).tolist(),'valid_bootstrap_draws':len(f)}
def package(t):
 t=t.set_index('item').reindex(items);out={c:rec(t[c].mean(),t[c].to_numpy()[ix].mean(axis=1))for c in t}
 for name,num,den in [('mutual_among_consensus','mutual_party_approach_and_consensus','consensus'),('order_retained_among_consensus','party_order_retained_and_consensus','initial_party_gap_and_consensus'),('order_tied_among_consensus','party_order_tied_and_consensus','initial_party_gap_and_consensus'),('order_reversed_among_consensus','party_order_reversed_and_consensus','initial_party_gap_and_consensus')]:
  n=t[num].to_numpy();d=t[den].to_numpy();bd=d[ix].mean(axis=1);bn=n[ix].mean(axis=1);dd=np.divide(bn,bd,out=np.full_like(bn,np.nan),where=bd>0);out[name]=rec(n.mean()/d.mean(),dd)
 return t,out
h=humans.a1r_delegates(str(R/'data/raw/a1r/dataset.tab'),items,'1');h['party']=h.party.astype(str)
native=[];panels=[];rng=np.random.default_rng(SEED)
for (group,item),g in h.groupby(['group','item']):
 pre=g.pre.to_numpy(float);post=g.post.to_numpy(float);party=g.party.to_numpy()
 native.append({'item':item,'group':group,**{k:float(v[0])for k,v in measures(pre,post,party).items()}})
 if not all((party==p).sum()>=n for p,n in [('1',2),('2',2),('3',1)]):continue
 idx=np.concatenate([np.stack([rng.choice(np.flatnonzero(party==p),n,replace=False)for _ in range(PANELS)])for p,n in [('1',2),('2',2),('3',1)]],axis=1)
 panels.append({'item':item,'group':group,**{k:float(v.mean())for k,v in measures(pre[idx],post[idx],party[idx]).items()}})
out={'date':'2026-10-21','status':'Post-hoc extension after inspecting pooled party profiles; no new P values','definition':'Party ordering refers to the two party means inside the same room. Ties and reversals are separated. Mutual approach means both party means move toward the other party initial mean. It does not require stopping before crossing.','human':{},'models':{}}
for label,rows in [('native',native),('balanced5',panels)]:
 df=pd.DataFrame(rows);df.to_csv(S/f'human-{label}-room-party-metrics.csv',index=False);t=df.drop(columns='group').groupby('item').mean().reset_index();_,summary=package(t);out['human'][label]=summary
for model in ['claude','gemini','mistral']:
 a=paired_groups(pd.read_csv(R/f'data/study1/results/exploratory/{model}/a1r_agents.csv'),['A-baseline','A-stateful']);records=[];out['models'][model]={};tabs={}
 for arm in ['A-baseline','A-stateful']:
  for (item,block),g in a[a.label==arm].groupby(['item_id','block']):
   records.append({'item':item,'block':block,'label':arm,**{k:float(v[0])for k,v in measures(g.pre.to_numpy(float),g.post.to_numpy(float),g.party.astype(str).to_numpy()).items()}})
  df=pd.DataFrame([r for r in records if r['label']==arm]);t=df.drop(columns=['block','label']).groupby('item').mean().reset_index();tabs[arm],out['models'][model][arm]=package(t)
 pd.DataFrame(records).to_csv(S/f'{model}-room-party-metrics.csv',index=False)
 diff=tabs['A-stateful']-tabs['A-baseline'];out['models'][model]['rules_minus_baseline']={k:rec(diff[k].mean(),diff[k].to_numpy()[ix].mean(axis=1))for k in diff}
(S/'group-party-adjustment.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
inputs=[Path(__file__),R/'data/raw/a1r/dataset.tab',R/'src/analysis/humans.py',R/'src/cases/a1r.py']+[R/f'data/study1/results/exploratory/{m}/a1r_agents.csv'for m in ['claude','gemini','mistral']]
(S/'group-party-input-manifest.json').write_text(json.dumps({str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in inputs},ensure_ascii=False,indent=2)+'\n')
print('Saved within-room party adjustment and ordering, with paired item intervals.')
