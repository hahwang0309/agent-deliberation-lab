"""Build the adjudicated Supplementary Figure 2 from preserved labels; no API calls."""
from pathlib import Path
import os,json,hashlib
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/manuscript-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd

R=Path(__file__).resolve().parents[1];O=R/'docs/research/position-change-adjudication'
r=json.loads((O/'results.json').read_text());v=r['variants']['glm_disagreement_combined'];f=pd.read_csv(O/'combined-labels.csv')
f['yes']=f.combined_label.eq('yes').astype(int)
pairs=f.pivot(index=['study','pair_id','block','stratum','weight'],columns='arm',values='yes').reset_index()
strata=['none','closing','moved','direct'];names=['No change cue','Closing only','Movement feedback','Explicit change request']
rng=np.random.default_rng(20261026);totals=[];draws=[]
for _,g in pairs.groupby('study'):
 matrix=[]
 for _,block in g.groupby('block'):
  vec=[block.weight.sum()]
  for cue in strata:
   q=block[block.stratum.eq(cue)];vec.extend([q.weight.sum(),(q.weight*q.stateful).sum()])
  matrix.append(vec)
 mat=np.array(matrix);totals.append(mat.sum(axis=0));draws.append(rng.multinomial(len(mat),np.full(len(mat),1/len(mat)),size=2000)@mat)
total=sum(totals);boot=sum(draws);records=[]
for i,cue in enumerate(strata):
 den,num=total[1+2*i:3+2*i];bd,bn=boot[:,1+2*i:3+2*i].T
 records.append({'cue':cue,'population_share':float(den/total[0]),'joint_contribution':float(num/total[0]),'conditional_rate':{'estimate':float(num/den),'ci':np.quantile(bn/bd,[.025,.975]).tolist()}})
assert np.isclose(sum(x['joint_contribution']for x in records),v['pooled_population']['stateful']['estimate'])
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
fig,ax=plt.subplots(1,3,figsize=(14.2,5.2),gridspec_kw={'width_ratios':[1.05,.9,1.25]})
for i,scope in enumerate(['wason','a1r','pooled_population']):
 for arm,off,col in [('baseline',-.12,'#2776bd'),('stateful',.12,'#d85a24')]:
  z=v[scope][arm];est=z['estimate'];lo,hi=z['ci'];ax[0].errorbar(est,i+off,xerr=[[est-lo],[hi-est]],fmt='o',color=col,capsize=3,label=('Ordinary'if arm=='baseline'else'Stateful')if i==0 else None)
ax[0].set(yticks=range(3),yticklabels=['Logic','Policy','All utterances'],xlim=(0,.6),ylim=(2.6,-.6),xlabel='Change-mention prevalence',title='a  Matched discussion comparison');ax[0].legend(frameon=False,loc='lower right',fontsize=9)
colors=['#557d99','#8db7a0','#d8a25d','#a77fa1'];bottom=0
for rec,name,col in zip(records,names,colors):
 value=rec['joint_contribution'];ax[1].bar(.2,value,bottom=bottom,width=.42,color=col,label=name)
 if value>.035:ax[1].text(.2,bottom+value/2,f'{100*value:.1f} pp',ha='center',va='center',fontsize=9,color='white'if col=='#557d99'else'#222')
 bottom+=value
ax[1].text(.2,bottom+.014,f'{100*bottom:.1f}%',ha='center',weight='bold');ax[1].set(xticks=[.2],xticklabels=['Stateful'],ylim=(0,.42),xlim=(-.4,.8),ylabel='Contribution to all-utterance prevalence',title='b  Composition of mentions');ax[1].legend(frameon=False,loc='upper left',bbox_to_anchor=(-.13,-.16),ncol=2,fontsize=8)
for i,rec in enumerate(records):
 z=rec['conditional_rate'];est=z['estimate'];lo,hi=z['ci'];ax[2].errorbar(est,i,xerr=[[est-lo],[hi-est]],fmt='o',color=colors[i],capsize=3)
ax[2].set(yticks=range(4),yticklabels=['No change\ncue','Closing\nonly','Movement\nfeedback','Explicit change\nrequest'],xlim=(0,1),ylim=(3.5,-.5),xlabel='Within-category change-mention rate',title='c  Mentions after current cues')
for a in ax:a.xaxis.set_major_formatter(PercentFormatter(1))
# Panel b uses percentages on the vertical rather than horizontal axis.
from matplotlib.ticker import ScalarFormatter
ax[1].xaxis.set_major_formatter(ScalarFormatter());ax[1].set_xticks([.2],['Stateful']);ax[1].yaxis.set_major_formatter(PercentFormatter(1))
fig.text(.5,.025,'Post-hoc primary-model analysis; disagreements adjudicated by GLM-5.3, agreed labels retained. Fixed-label paired-block 95% intervals.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.11,1,1),w_pad=2)
for ext in['png','pdf']:fig.savefig(O/f'comparison-and-decomposition.{ext}',dpi=200)
plt.close(fig)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
(O/'figure-source-data.json').write_text(json.dumps({'scope':'Adjudicated Supplementary Figure 2; fixed labels and paired composition-block resampling','estimates':v,'cue_categories':records,'inputs':{str(p.relative_to(R)):sha(p)for p in[O/'results.json',O/'combined-labels.csv',Path(__file__)]}},ensure_ascii=False,indent=2)+'\n')
print('Adjudicated supplementary PNG/PDF and traceable source data saved.')
