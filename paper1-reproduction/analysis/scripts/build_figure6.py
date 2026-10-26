"""Render Figure 6 from archived discussion outcomes; no fitting or API calls."""
from pathlib import Path
import json,hashlib,sys,os,zipfile
import pandas as pd
R=Path(__file__).resolve().parents[1];B=R/'docs/research';O=B/'manuscript-figures';S=B/'supplementary-information'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def table(cols,rows):return '\n'.join(['| '+' | '.join(cols)+' |','|'+'|'.join(['---']*len(cols))+'|']+['| '+' | '.join(map(str,row))+' |'for row in rows])+'\n'
summary=B/'consensus-representation/ordinary-stateful-check/model-summary.csv';item=B/'consensus-representation/ordinary-stateful-check/item-outcomes.csv';outcomes=B/'consensus-representation/outcome-variability/discussion-outcomes.csv';res=B/'consensus-representation/source-data/results.json'
u=pd.read_csv(summary);q=pd.read_csv(outcomes);d=json.loads(res.read_text());models=['claude','gemini','mistral'];arms=['A-baseline','A-stateful']
if '--tables-only' not in sys.argv:
 os.environ.setdefault('MPLCONFIGDIR','/private/tmp/manuscript-revision-mpl')
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
 fig,axs=plt.subplots(1,3,figsize=(13,4.3),sharex=True,sharey=True)
 chosen=[]
 for ax,policy,title,letter in zip(axs,['Q2C','Q3C','Q5F'],['Aid to Central America','Emissions tax / market incentives','Public health-insurance buy-in'],'abc'):
  for arm,y,col in zip(arms,[1,0],['#2776bd','#d85a24']):
   g=q[q.model.eq('claude')&q['item'].eq(policy)&q.label.eq(arm)].sort_values('block').copy();assert len(g)==16
   chosen.append(g)
   import numpy as np
   for off,row in zip(np.linspace(-.17,.17,len(g)),g.itertuples()):ax.scatter(row.post_mean,y+off,s=60,facecolor=col if row.consensus else 'white',edgecolor=col,linewidth=1.3)
  ax.axvline(5,color='#999',ls='--',lw=.8);ax.set(xlim=(-.35,10.35),ylim=(-.45,1.45),xticks=[0,2,4,6,8,10],yticks=[0,1],yticklabels=['Stateful','Ordinary'],xlabel='Final discussion mean (0 oppose; 10 favour)',title=f'{letter}  {policy}: {title}')
  ax.tick_params(axis='y',labelleft=True)
 fig.text(.5,.035,'Each point: one discussion. Filled: within-discussion SD <= 1; open: SD > 1. Vertical offsets separate overlapping points.',ha='center',fontsize=10)
 fig.tight_layout(rect=(0,.10,1,1),w_pad=2.0)
 for ext in ['png','pdf']:fig.savefig(O/f'figure6.{ext}',dpi=220)
 plt.close(fig)
 pd.concat(chosen).to_csv(O/'figure6-source-data.csv',index=False)
 (O/'figure6-manifest.json').write_text(json.dumps({'date':'2026-10-21','inputs':{str(p.relative_to(R)):sha(p)for p in [outcomes,Path(__file__).resolve()]},'n_points':96,'outputs':{str(p.relative_to(R)):sha(p)for p in [O/'figure6.png',O/'figure6.pdf',O/'figure6-source-data.csv']}},indent=2)+'\n')
