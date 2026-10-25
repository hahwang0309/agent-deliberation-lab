"""Review a candidate central finding using archived outcomes; no API or DB writes."""
import os
os.environ.setdefault('MPLCONFIGDIR', '/private/tmp/group-disagreement-matplotlib')
from pathlib import Path
import hashlib
import json
import sqlite3
import sys
import numpy as np
import pandas as pd
import yaml
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.analysis.group_disagreement import paired_groups,decompose,item_bootstrap
OUT=ROOT/'docs/research/novelty-review'
for name in ['figures','tables','source-data']:(OUT/name).mkdir(parents=True,exist_ok=True)
ARMS=['A-baseline','A-stateful']; METRICS=['within','between','total','between_share','between_unbiased']
NBOOT=10000; SEED=20261019
manifest=[]; result={}; allrows=[]; audit={}; auxrows=[]

def capture(path):
 manifest.append(dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))

def verify_db(a,db):
 con=sqlite3.connect(f'file:{db.resolve()}?mode=ro',uri=True)
 ids=set(a.discussion_id)
 observed={}
 for did,p,it,phase,score in con.execute('select discussion_id,participant,item_id,phase,score from survey_responses'):
  if did in ids:
   key=(did,p,it,phase)
   if key in observed:raise ValueError('Duplicate DB response')
   observed[key]=score
 run_models=set();statuses=set()
 for did,status,info in con.execute('select id,status,run_info from discussions'):
  if did in ids:
   statuses.add(status)
   llm=json.loads(info)[-1]['llm']['participants']
   run_models.update(v['model'] for v in llm.values())
 for row in a.itertuples(index=False):
  for phase in ['pre','post']:
   actual=observed[(row.discussion_id,row.participant,row.item_id,phase)]
   expected=getattr(row,phase)
   if pd.isna(expected):assert actual is None
   else:assert actual==expected,(row.discussion_id,phase)
 assert statuses=={'completed'}
 con.close()
 return dict(agent_rows=len(a),survey_values_checked=2*len(a),runs=len(ids),models=sorted(run_models),db_mode='read-only')

def contrast_frame(t):
 wide=t.pivot(index='item',columns='label',values=METRICS)
 return pd.DataFrame({m:wide[m]['A-stateful']-wide[m]['A-baseline'] for m in METRICS})

def composition(a):
 """Item-centered group mean association, controlling no-seed mean, equal item weights."""
 g=a.groupby(['item_id','block','label']).agg(pre=('pre','mean'),post=('post','mean'),D=('D','mean'),nD=('D','count')).reset_index()
 good=g[g.nD==5].groupby('block').label.nunique();g=g[g.block.isin(good[good==2].index)]
 terms=[]
 for item,q in g.groupby('item_id'):
  labs=[]
  for lab in ARMS:
   z=q[q.label==lab];z=z[['pre','D','post']]-z[['pre','D','post']].mean()
   x=z[['pre','D']].to_numpy();y=z.post.to_numpy()
   labs.append((x.T@x/len(x),x.T@y/len(x)))
  terms.append(labs)
 xx=np.array([[v[0] for v in t] for t in terms]);xy=np.array([[v[1] for v in t] for t in terms])
 fit=np.linalg.solve(xx.mean(axis=0),xy.mean(axis=0)[...,None])[...,0]
 rng=np.random.default_rng(SEED);idx=rng.integers(len(terms),size=(NBOOT,len(terms)))
 boot=np.linalg.solve(xx[idx].mean(axis=1),xy[idx].mean(axis=1)[...,None])[...,0]
 names=['initial_mean','default_mean'];output={'n_groups':int(g.block.nunique())}
 for armno,lab in enumerate(ARMS):
  output[lab]={name:dict(estimate=float(fit[armno,j]),ci=np.quantile(boot[:,armno,j],[.025,.975]).tolist()) for j,name in enumerate(names)}
 diff=boot[:,1,:]-boot[:,0,:]
 output['rule_minus_baseline']={name:dict(estimate=float(fit[1,j]-fit[0,j]),ci=np.quantile(diff[:,j],[.025,.975]).tolist()) for j,name in enumerate(names)}
 return output

for model in ['claude','gemini','mistral']:
 path=ROOT/f'data/study1/results/exploratory/{model}/a1r_agents.csv';capture(path)
 a=pd.read_csv(path)
 audit[model]=verify_db(a,ROOT/f'data/study1/{model}.db')
 planpaths=[ROOT/f'data/study1/plans/a1r-{part}-{model}.yaml' for part in ['dev','locked']]
 plans=[yaml.safe_load(p.read_text()) for p in planpaths]
 for p in planpaths:capture(p)
 locked={t['survey']['items'][0]['id'] for t in plans[1]['topics']}
 # Verify the party mix in archived agent rows, for all primary discussion arms.
 primary=paired_groups(a,ARMS)
 mix=primary.groupby(['block','label']).party.apply(lambda x:tuple(sorted(x.astype(int))))
 assert all(v==(1,1,2,2,3) for v in mix)
 t=decompose(primary);pre=decompose(primary,'pre');diff=contrast_frame(t)
 allrows.extend(t.assign(model=model).to_dict('records'))
 primary.to_csv(OUT/f'source-data/{model}-paired-outcomes.csv',index=False)
 estimates=item_bootstrap(diff,METRICS,NBOOT,SEED)
 # Paired block resampling: policy items fixed, original number of groups retained.
 boot=np.zeros((2000,2,3));rng=np.random.default_rng(SEED)
 for item,g in primary.groupby('item_id'):
  arr=[]
  for lab in ARMS:
   arr.append(np.stack([q.sort_values('participant').post.to_numpy() for _,q in g[g.label==lab].groupby('block')]))
  x=np.stack(arr,axis=1);ix=rng.integers(len(x),size=(2000,len(x)));draw=x[ix]
  w=draw.var(axis=3).mean(axis=1);b=draw.mean(axis=3).var(axis=1)
  boot[:,:,0]+=w/len(diff);boot[:,:,1]+=b/len(diff);boot[:,:,2]+=(w+b)/len(diff)
 block_ci={m:dict(estimate=estimates[m]['estimate'],ci=np.quantile(boot[:,1,j]-boot[:,0,j],[.025,.975]).tolist()) for j,m in enumerate(METRICS[:3])}
 four=paired_groups(a,['A-baseline','A-stateful','B-materials','C-reanswer'])
 fourtable=decompose(four);fourdiff=contrast_frame(fourtable[fourtable.label.isin(ARMS)])
 subsets={}
 for subset,idx in [('dev',~diff.index.isin(locked)),('locked',diff.index.isin(locked))]:
  sub=diff.loc[idx];subsets[subset]={'n_items':len(sub),'contrasts':item_bootstrap(sub,METRICS,NBOOT,SEED)}
 counts={'within_negative':int((diff.within<0).sum()),'between_positive':int((diff['between']>0).sum()),'both':int(((diff.within<0)&(diff['between']>0)).sum()),'n_items':len(diff)}
 loo=diff.apply(lambda s:pd.Series([(s.sum()-v)/(len(s)-1) for v in s])).agg(['min','max']).to_dict()
 result[model]=dict(n_groups=int(primary.block.nunique()),levels=t.groupby('label')[METRICS].mean().to_dict('index'),pre=pre.groupby('label')[METRICS].mean().to_dict('index'),contrasts=estimates,fixed_item_block_bootstrap=block_ci,subsets=subsets,sign_counts=counts,leave_one_item_out=loo,composition=composition(primary),four_arm_complete=dict(n_groups=int(four.block.nunique()),levels=fourtable.groupby('label')[METRICS].mean().to_dict('index'),contrasts=item_bootstrap(fourdiff,METRICS,NBOOT,SEED)))
 auxrows.extend(fourtable.assign(model=model).to_dict('records'))
 print(model,json.dumps({'contrasts':estimates,'composition':result[model]['composition'],'sign_counts':counts,'locked':subsets['locked']['contrasts']},ensure_ascii=False),flush=True)

summary=dict(status='Post-hoc exploratory candidate review; selected after seeing preliminary point estimates',date='2026-10-19',n_boot=NBOOT,seed=SEED,estimand='Equal-weight mean across 30 policy items; population within-group variance and variance of five-member group means',primary_comparison='Rules added minus baseline discussion; same members and seeded scores',topic_bootstrap='30 items resampled jointly across arms, within and between components; persona cross-item dependence not modeled',fixed_item_bootstrap='2000 paired five-member blocks resampled within each of 30 fixed items',caution='Between means includes group composition and stochastic dialogue variation; no repeat at identical group composition in this policy design',shared_analyzer='All three participant-model conditions use the same Claude analyzer',results=result,raw_db_audit=audit)
(OUT/'source-data/results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
pd.DataFrame(allrows).to_csv(OUT/'source-data/item-variance-components.csv',index=False)
pd.DataFrame(auxrows).to_csv(OUT/'source-data/four-arm-item-variance.csv',index=False)
capture(ROOT/'docs/research/figures/study1-figures.html')
(OUT/'source-data/input-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

def fmt(v):return f"{v['estimate']:+.3f} [{v['ci'][0]:+.3f}, {v['ci'][1]:+.3f}]"
table='| 모델 | 집단 안 분산 변화 | 집단 평균 사이 분산 변화 | 전체 분산 변화 |\n|---|---|---|---|\n'
for model,r in result.items():table+='| '+model+' | '+' | '.join(fmt(r['contrasts'][k]) for k in ['within','between','total'])+' |\n'
(OUT/'tables/rule-contrast.md').write_text(table)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
fig,axs=plt.subplots(1,2,figsize=(11,4.5));names=list(result)
for ax,metric,title in zip(axs,['within','between'],['a  Disagreement within each discussion','b  Differences between discussion means']):
 for y,model in enumerate(names):
  v=result[model]['contrasts'][metric];e=v['estimate'];l,h=v['ci']
  ax.errorbar(e,y,xerr=[[e-l],[h-e]],fmt='o',color='#2776bd',capsize=4)
 ax.axvline(0,color='#666',ls='--');ax.set(yticks=range(3),yticklabels=[n.title() for n in names],ylim=(2.6,-.6),xlabel='Rules added minus baseline (squared score points)',title=title)
fig.suptitle('Adding rules: closer opinions inside groups, more varied group conclusions',fontsize=13)
fig.text(.5,.025,'Same 0-10 policy scale, five-member groups, 30 items. Lines: 95% item-bootstrap intervals.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.08,1,.92))
for ext in ['png','pdf']:fig.savefig(OUT/f'figures/within-and-between.{ext}',dpi=220)
plt.close(fig)
