"""Post-hoc item-level human disagreement / AI agreement and outcome variation."""
from pathlib import Path
import os,json,hashlib
import numpy as np
import pandas as pd
from scipy.stats import rankdata
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/consensus-representation-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1];O=R/'docs/research/human-ai-topic-variation';S=R/'docs/research/consensus-representation'
B=5000;SEED=20261021;models=['claude','gemini','mistral'];arms=['A-baseline','A-stateful']
human=pd.read_csv(S/'source-data/human-native-items.csv').rename(columns=lambda c:'human_'+c if c!='item'else c)
panel=pd.read_csv(S/'source-data/human-balanced-panel-items.csv').rename(columns=lambda c:'panel_'+c if c!='item'else c)
out=pd.read_csv(S/'outcome-variability/item-outcome-summary.csv');discussion=pd.read_csv(S/'outcome-variability/discussion-outcomes.csv')
extra=[]
for (model,item,label),g in discussion.groupby(['model','item','label']):
 c=g[g.consensus];extra.append(dict(model=model,item=item,label=label,agreement_only_sd=c.post_mean.std(ddof=1)if len(c)>=4 else np.nan))
out=out.merge(pd.DataFrame(extra),on=['model','item','label'],validate='one_to_one').merge(human,on='item',validate='many_to_one').merge(panel,on='item',validate='many_to_one')
domains={'Q2':'Immigration','Q3':'Environment','Q4':'Economy','Q5':'Health','Q6':'Foreign policy'}
out['domain']=out['item'].str[:2].map(domains);out['final_mean_iqr']=out.final_mean_q75-out.final_mean_q25
assert len(out)==180 and out['item'].nunique()==30 and out.domain.notna().all()
def corr(a,b):
 a=a-a.mean(axis=-1,keepdims=True);b=b-b.mean(axis=-1,keepdims=True)
 den=np.sqrt((a*a).sum(axis=-1)*(b*b).sum(axis=-1))
 return np.divide((a*b).sum(axis=-1),den,out=np.full_like(den,np.nan),where=den>0)
def rho(x,y):return float(corr(rankdata(np.asarray(x,float)),rankdata(np.asarray(y,float))))
def partial(x,y,z):
 a=rankdata(np.asarray(x,float));b=rankdata(np.asarray(y,float));z=np.column_stack([np.ones(len(a))]+[rankdata(np.asarray(c,float))for c in z])
 return float(corr(a-z@np.linalg.lstsq(z,a,rcond=None)[0],b-z@np.linalg.lstsq(z,b,rcond=None)[0]))
def stats(q,x,y):
 q=q.dropna(subset=[x,y]);a=q[x].to_numpy(float);b=q[y].to_numpy(float);n=len(q)
 if n<4 or np.ptp(a)==0 or np.ptp(b)==0:return dict(n=n,rho=None,ci=None)
 idx=np.random.default_rng(SEED).integers(n,size=(B,n));boot=corr(rankdata(a[idx],axis=1),rankdata(b[idx],axis=1));finite=boot[np.isfinite(boot)]
 loo=[rho(np.delete(a,k),np.delete(b,k))for k in range(n)]
 return dict(n=n,rho=rho(a,b),ci=np.quantile(finite,[.025,.975]).tolist(),valid_bootstrap_draws=len(finite),leave_one_item_out=[float(np.nanmin(loo)),float(np.nanmax(loo))],
  leave_one_domain_out={d:rho(q[q.domain!=d][x],q[q.domain!=d][y])for d in sorted(q.domain.unique())},
  partial_initial_composition_and_count=partial(a,b,[q.initial_mean_sd,q.n_discussions]),partial_human_initial_disagreement=partial(a,b,[q.human_pre_sd]))
results={'date':'2026-10-21','status':'Post-hoc exploratory item associations; no P values','B':B,'seed':SEED,'by_model':{},'condition_changes':{}}
for m in models:
 results['by_model'][m]={}
 for arm in arms:
  q=out[(out.model==m)&(out.label==arm)].sort_values('item');results['by_model'][m][arm]={}
  for predictor in ['human_post_sd','panel_post_sd','panel_post_consensus','human_post_party_gap']:
   results['by_model'][m][arm][predictor]={target:stats(q,predictor,target)for target in ['consensus_rate','final_mean_sd','final_mean_iqr','agreement_only_sd']}
 b=out[(out.model==m)&(out.label==arms[0])].set_index('item');s=out[(out.model==m)&(out.label==arms[1])].set_index('item');q=s.copy()
 for k in ['consensus_rate','final_mean_sd']:q[k]=s[k]-b[k]
 results['condition_changes'][m]={k:stats(q.reset_index(),'human_post_sd',k)for k in ['consensus_rate','final_mean_sd']}
out.to_csv(O/'topic-metrics.csv',index=False)
(O/'associations.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axs=plt.subplots(2,3,figsize=(14,8),sharex=True)
colors=dict(zip(domains.values(),['#555555','#13866c','#3775b6','#b67812','#a34490']))
for j,m in enumerate(models):
 q=out[(out.model==m)&(out.label==arms[1])]
 for i,(target,label)in enumerate([('consensus_rate','AI within-discussion agreement rate'),('final_mean_sd','SD between AI final discussion means')]):
  ax=axs[i,j]
  annotations={'Q4F':(4,6),'Q2C':(4,5),'Q3A':(-15,13),'Q6F':(-28,-13),'Q5A':(-25,16),'Q4H':(4,23)}
  for _,r in q.iterrows():
   ax.scatter(r.human_post_sd,r[target],s=40,color=colors[r.domain],alpha=.85)
   if r['item'] in annotations:ax.annotate(r['item'],(r.human_post_sd,r[target]),xytext=annotations[r['item']],textcoords='offset points',fontsize=8)
  z=results['by_model'][m][arms[1]]['human_post_sd'][target];ax.set_title(m.title()+' | rho = '+f"{z['rho']:.2f}")
  ax.set_ylabel(label if j==0 else '');ax.grid(alpha=.12)
  if i==0:ax.set_ylim(-.04,1.05)
  else:ax.set_xlabel('Human post-discussion disagreement\n(mean within-room SD)')
handles=[plt.Line2D([],[],marker='o',ls='',color=c,label=d)for d,c in colors.items()]
fig.legend(handles=handles,loc='lower center',ncol=5,frameon=False)
fig.suptitle('Do human disagreement and AI agreement / outcome variation track the same policy items?',fontsize=14)
fig.tight_layout(rect=(0,.06,1,.95),w_pad=2,h_pad=3)
for ext in ['png','pdf']:fig.savefig(O/f'human-ai-topic-associations.{ext}',dpi=200)
plt.close(fig)
inputs=[Path(__file__),O/'AnalysisPlan.md',S/'source-data/human-native-items.csv',S/'source-data/human-balanced-panel-items.csv',S/'outcome-variability/item-outcome-summary.csv',S/'outcome-variability/discussion-outcomes.csv']
(O/'input-manifest.json').write_text(json.dumps({str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in inputs},indent=2)+'\n')
for m in models:
 for a in arms:
  z=results['by_model'][m][a]['human_post_sd'];print(m,a,{k:{s:v for s,v in z[k].items()if s in ['rho','ci','partial_initial_composition_and_count','partial_human_initial_disagreement']}for k in ['consensus_rate','final_mean_sd']})
print('Saved 180 topic-condition-model rows, primary/sensitivity rank associations, and scatter figure.')
