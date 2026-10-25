"""Descriptive policy outcome distributions; no distribution fitting or new simulations."""
from pathlib import Path
import os,sys,json,hashlib,textwrap
import numpy as np
import pandas as pd
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/consensus-representation-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import yaml
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from src.analysis.group_disagreement import paired_groups
O=R/'docs/research/consensus-representation/outcome-variability';O.mkdir(exist_ok=True)
arms=['A-baseline','A-stateful'];allrows=[];summaries=[];movement=[];texts={}
for path in ['data/cases/a1r_dev.yaml','data/cases/a1r_locked.yaml']:
 for topic in yaml.safe_load((R/path).read_text())['topics']:
  for it in topic['survey']['items']:texts[it['id']]=it['text'].removeprefix('Proposal: ')
for model in ['claude','gemini','mistral']:
 a=paired_groups(pd.read_csv(R/f'data/study1/results/exploratory/{model}/a1r_agents.csv'),arms)
 assert (a.replicate==0).all(), 'Inspect repetition design before interpreting outcomes'
 rows=[]
 for (item,block,arm),g in a.groupby(['item_id','block','label']):
  d=g[g.party.astype(str)=='1'];r=g[g.party.astype(str)=='2']
  d0,r0,d1,r1=d.pre.mean(),r.pre.mean(),d.post.mean(),r.post.mean()
  gap=d0-r0;post=g.post.mean();sd=g.post.std(ddof=0)
  row=dict(model=model,item=item,proposal=texts[item],block=block,label=arm,pre_mean=g.pre.mean(),post_mean=post,post_sd=sd,consensus=sd<=1,
   initial_D=d0,initial_R=r0,final_D=d1,final_R=r1,initial_gap=gap,
   D_toward_R=(d1-d0)*np.sign(-gap) if gap!=0 else np.nan,
   R_toward_D=(r1-r0)*np.sign(gap) if gap!=0 else np.nan,
   D_anchor_closer=abs(post-d0)<abs(post-r0),R_anchor_closer=abs(post-d0)>abs(post-r0))
  rows.append(row)
 t=pd.DataFrame(rows);allrows.extend(rows)
 for (item,arm),q in t.groupby(['item','label']):
  c=q[q.consensus];summaries.append(dict(model=model,item=item,proposal=texts[item],label=arm,n_discussions=len(q),n_consensus=len(c),consensus_rate=len(c)/len(q),
   initial_mean_sd=q.pre_mean.std(ddof=1),final_mean_sd=q.post_mean.std(ddof=1),final_mean_min=q.post_mean.min(),final_mean_max=q.post_mean.max(),final_mean_q25=q.post_mean.quantile(.25),final_mean_median=q.post_mean.median(),final_mean_q75=q.post_mean.quantile(.75),
   consensus_mean_min=c.post_mean.min(),consensus_mean_max=c.post_mean.max(),consensus_mean_median=c.post_mean.median()))
 for arm,q in t.groupby('label'):
  eligible=q[q.initial_gap.abs()>=1].copy()
  for party in ['D','R']:
   eligible[party+'_anchor_closer_and_consensus']=eligible[party+'_anchor_closer']&eligible.consensus
  v=eligible.groupby('item')[['D_anchor_closer','R_anchor_closer','D_anchor_closer_and_consensus','R_anchor_closer_and_consensus','consensus']].mean().mean()
  movement.append(dict(model=model,label=arm,n_initial_gap_at_least_1=len(eligible),**v.to_dict(),
   D_anchor_closer_given_consensus=v.D_anchor_closer_and_consensus/v.consensus,
   R_anchor_closer_given_consensus=v.R_anchor_closer_and_consensus/v.consensus))
 # All observations shown. Filled points = within-discussion agreement; hollow = other discussions.
 fig,axs=plt.subplots(6,5,figsize=(19,20),sharex=True,sharey=True)
 for ax,item in zip(axs.flat,sorted(t.item.unique())):
  q=t[t.item==item];base=q[q.label==arms[0]].sort_values('block');state=q[q.label==arms[1]].sort_values('block')
  assert base.block.tolist()==state.block.tolist() and np.allclose(base.pre_mean,state.pre_mean)
  jitter=np.linspace(-.15,.15,len(base))
  ax.scatter(base.pre_mean,0+jitter,s=15,color='#888888',alpha=.7)
  for y,frame,color in [(1,base,'#2776bd'),(2,state,'#d85a24')]:
   for j,(_,row) in enumerate(frame.iterrows()):ax.scatter(row.post_mean,y+jitter[j],s=23,facecolors=color if row.consensus else 'none',edgecolors=color,linewidth=.9)
  n0=int(base.consensus.sum());n1=int(state.consensus.sum())
  title=item+' | '+textwrap.fill(texts[item],46)+'\nagreement: '+str(n0)+'/'+str(len(base))+' ordinary; '+str(n1)+'/'+str(len(state))+' stateful'
  ax.set_title(title,fontsize=8,loc='left');ax.set(xlim=(-.3,10.3),ylim=(2.4,-.4),yticks=[0,1,2],yticklabels=['Initial','Ordinary','Stateful'],xticks=[0,5,10]);ax.tick_params(labelsize=8);ax.grid(axis='x',alpha=.15)
 fig.suptitle(model.title()+': discussion outcomes for each policy item',fontsize=17,y=.995)
 fig.text(.5,.008,'Horizontal axis: mean policy score (0 = oppose; 10 = favor). Each point is one discussion. Filled final points meet SD <= 1.\nDifferent initial compositions; one run per composition. These are empirical outcomes, not fitted predictive distributions.',ha='center',fontsize=11)
 fig.tight_layout(rect=(0,.04,1,.98),h_pad=2)
 for ext in ['png','pdf']:fig.savefig(O/f'{model}-item-outcomes.{ext}',dpi=150)
 plt.close(fig)
pd.DataFrame(allrows).to_csv(O/'discussion-outcomes.csv',index=False)
pd.DataFrame(summaries).to_csv(O/'item-outcome-summary.csv',index=False)
pd.DataFrame(movement).to_csv(O/'party-anchor-proximity.csv',index=False)
# Check every saved agreement count and final-outcome quantile independently against saved discussion rows.
g=pd.read_csv(O/'discussion-outcomes.csv');s=pd.read_csv(O/'item-outcome-summary.csv')
for _,row in s.iterrows():
 q=g[(g.model==row.model)&(g.item==row['item'])&(g.label==row.label)]
 assert len(q)==row.n_discussions and int((q.post_sd<=1).sum())==row.n_consensus
 assert np.isclose(q.post_mean.median(),row.final_mean_median)
inputs=[Path(__file__),R/'src/analysis/group_disagreement.py',R/'src/cases/a1r.py',R/'data/cases/a1r_dev.yaml',R/'data/cases/a1r_locked.yaml']+[R/f'data/study1/results/exploratory/{m}/{name}'for m in ['claude','gemini','mistral']for name in ['a1r_agents.csv','e6.json']]
(O/'input-manifest.json').write_text(json.dumps({str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in inputs},indent=2)+'\n')
print(pd.DataFrame(movement).to_string(index=False))
print('Saved 3 model figures, individual discussion data and 180 item-condition summaries; counts and medians verified.')
