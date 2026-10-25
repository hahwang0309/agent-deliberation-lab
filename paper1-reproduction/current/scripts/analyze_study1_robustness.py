"""Targeted post-hoc robustness checks on archived data; no API calls or DB writes."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('VECLIB_MAXIMUM_THREADS','1')
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.analysis.group_disagreement import paired_groups
from src.analysis.humans import delidata_individuals
from src.analysis.robustness import group_frame,membership_fit,deletion_influence,h1_risk_bootstrap,direction_topic_bootstrap
from src.analysis import mixed
from src.analysis.study1 import holm

OUT=ROOT/'docs/research/robustness'
SOURCE=OUT/'source-data'
MODELS=['claude','gemini','mistral']
SEED=20261020


def write(name,data):
    (SOURCE/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def plain(x):
    return json.loads(json.dumps(x,default=lambda z: z.item() if isinstance(z,np.generic) else str(z)))


def h1_data(model,human):
    con=sqlite3.connect(f'file:{ROOT/f"data/study1/{model}.db"}?mode=ro',uri=True)
    meta=human.drop_duplicates('block').set_index('block')
    rows=[]
    query="""select d.id,d.config,r.correct from discussions d join survey_responses r on d.id=r.discussion_id
      where d.status='completed' and r.phase='post' and r.correct is not null
      and json_extract(d.config,'$.experiment.label')='A-baseline'
      and json_extract(d.config,'$.experiment.topic_key') like 'deli-%'"""
    for did,cfg,c in con.execute(query):
        e=json.loads(cfg)['experiment'];key=e['topic_key'];m=meta.loc[key]
        rows.append(dict(block=key,run=f"{key}#r{e['replicate']}",card_set=m['card_set'],group_size=int(m['group_size']),k=m['k'],ai=1,correct=int(c)))
    con.close()
    ai=pd.DataFrame(rows)
    hum=human[human.block.isin(ai.block)].assign(ai=0,run=lambda x:x.block+'#h')
    both=pd.concat([hum,ai],ignore_index=True)
    both['k1']=(both.k=='1').astype(int);both['k2p']=(both.k=='2+').astype(int)
    return ai,both


def h1(model,human,nboot):
    ai,both=h1_data(model,human)
    path=SOURCE/f'{model}-h1-observations.csv';both.to_csv(path,index=False)
    csv_r=SOURCE/f'{model}-h1-model-diagnostics.json'
    proc=subprocess.run(['Rscript',str(ROOT/'scripts/diagnose_h1.R'),str(path),str(csv_r)],text=True,capture_output=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr[-2000:])
    # Adjusted probability-scale sensitivity, with original group clustering.
    fit=smf.ols('correct ~ k1 + k2p + ai + k1:ai + k2p:ai + group_size',both).fit(cov_type='cluster',cov_kwds={'groups':both.block,'use_correction':True},use_t=True)
    term='k1:ai'
    result={'probability_scale':h1_risk_bootstrap(human,ai,nboot,SEED),
            'size_adjusted_linear_probability':{'estimate':float(fit.params[term]),'ci':fit.conf_int().loc[term].tolist(),'p':float(fit.pvalues[term]),'n':len(both),'n_clusters':both.block.nunique(),'formula':fit.model.formula,'note':'Post-hoc linear probability interaction, not registered conditional log-odds estimand'},
            'diagnostics':json.loads(csv_r.read_text())}
    write(f'{model}-h1.json',plain(result))
    print(model,'H1',json.dumps(result['probability_scale']['contrasts']),flush=True)
    return result


def persona(model):
    raw=pd.read_csv(ROOT/f'data/study1/results/exploratory/{model}/a1r_agents.csv')
    agents=paired_groups(raw,['A-baseline','A-stateful'])
    f,m=group_frame(agents)
    f.to_csv(SOURCE/f'{model}-group-functionals.csv')
    m.to_csv(SOURCE/f'{model}-membership-weights.csv')
    res={}
    for outcome in ['within_delta','between_delta']:
        res[outcome]=membership_fit(f,m,outcome)
        print(model,outcome,res[outcome]['coefficients'],flush=True)
    cf=f[f.complete_D].copy()
    for k in ['pre','D']:
        cf[k+'_centered']=cf[k]-cf[k].groupby(level='item_id').transform('mean')
    res['initial_mean_association_delta']=membership_fit(cf,m.reindex(cf.index),'mean_delta',['pre_centered','D_centered'])
    influences=deletion_influence(f,m)
    influences.to_csv(SOURCE/f'{model}-leave-persona-out.csv',index=False)
    res['leave_persona_out']={'n_deletions':len(influences),'within_min_max':[float(influences.within.min()),float(influences.within.max())],
                             'between_min_max':[float(influences.between.min()),float(influences.between.max())],
                             'max_removed_groups':int(influences.removed_groups.max()),'interpretation':'Point-estimate influence only, not uncertainty correction'}
    counts=(m>0).sum(axis=0)
    res['reuse']={'n_personas':m.shape[1],'n_groups':len(m),'n_reused_personas':int((counts>1).sum()),'max_groups_per_persona':int(counts.max())}
    write(f'{model}-persona.json',res)
    return res


def s4():
    d=pd.read_csv(ROOT/'docs/research/argument-quality-response/source-data/discussion-outcomes.csv')
    old=json.loads((ROOT/'data/study1/results/exploratory/claude/s4.json').read_text())
    dhat=old['d_hat']
    # Read archived no-discussion change, retaining all repetitions.
    con=sqlite3.connect(f'file:{ROOT/"data/study1/claude.db"}?mode=ro',uri=True)
    controls=[]
    for did,cfg in con.execute("select id,config from discussions where status='completed' and json_extract(config,'$.experiment.label')='C-reanswer' and json_extract(config,'$.experiment.topic_key') like 'argq%'"):
        e=json.loads(cfg)['experiment'];values=dict(con.execute('select phase,score from survey_responses where discussion_id=?',(did,)))
        assert set(values)=={'pre','post'} and all(v is not None for v in values.values())
        controls.append({'set':e['topic_key'],'delta':(-1 if e['topic_key'].endswith('-pro')else 1)*(values['post']-values['pre'])})
    con.close()
    pd.DataFrame(controls).to_csv(SOURCE/'s4-reanswer-controls.csv',index=False)
    cdelta=pd.DataFrame(controls).groupby('set').delta.mean()
    assert len(controls)==96 and len(cdelta)==32 and len(d)==768
    d['set']=d.topic_key;d['q']=np.where(d.quality=='strong',.5,-.5);d['sup']=np.where(d.support=='majority',.5,-.5);d['eng']=np.where(d.engine=='stateful',.5,-.5)
    d['side']=np.where(d['set'].str.endswith('-pro'),.5,-.5);d['D']=d.topic.map(dhat)
    d['delta_c']=d.delta-d['set'].map(cdelta)
    d['direction']=np.where(d.D==50,'neutral',np.where(np.where(d.side>0,d.D<50,d.D>50),'aligned','opposing'))
    d['aligned']=np.where(d.direction=='aligned',.5,-.5)
    d.to_csv(SOURCE/'s4-direction-observations.csv',index=False)
    res={'counts':d.groupby('direction').agg(n=('delta','size'),n_sets=('set','nunique')).to_dict('index'),
         'neutral_sets':sorted(d.loc[d.direction=='neutral','set'].unique()),'models':{},'cell_contrasts':{}}
    for name,sub in [('aligned',d[d.direction=='aligned']),('opposing',d[d.direction=='opposing'])]:
        res['models'][name]=mixed.fit(sub.rename(columns={'delta_c':'y'}),'y ~ q * sup * eng + side + (1 + q | set)')
    nd=d[d.direction!='neutral'].copy()
    joint=mixed.fit(nd.rename(columns={'delta_c':'y'}),'y ~ q * sup * eng * aligned + side + (1 + q | set) + (1 | topic)')
    res['models']['joint_no_neutral']=joint
    terms=['sup:aligned','q:aligned','sup:eng:aligned','q:eng:aligned']
    res['direct_direction_tests']={t:joint['coefficients'][t]for t in terms}
    res['direction_tests_holm']=holm({t:res['direct_direction_tests'][t]['p']for t in terms})
    res['topic_bootstrap']=direction_topic_bootstrap(nd)
    for term in terms:
        if not np.isclose(res['topic_bootstrap']['contrasts'][term]['estimate'],res['direct_direction_tests'][term]['estimate'],atol=1e-10):
            raise ValueError('Balanced direct contrast differs from mixed-model coefficient')
    for name,sub in [('aligned',d[d.direction=='aligned']),('opposing',d[d.direction=='opposing'])]:
        for factor in ['sup','q']:
            for eng,ss in sub.groupby('engine'):
                res['cell_contrasts'][name+'_'+factor+'_'+eng]=float(ss.loc[ss[factor]>0,'delta_c'].mean()-ss.loc[ss[factor]<0,'delta_c'].mean())
    write('s4.json',res)
    print('S4 direct interactions',json.dumps(res['direct_direction_tests']),flush=True)
    return res


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--part',choices=['all','h1','persona','s4','manifest'],default='all');p.add_argument('--bootstrap',type=int,default=10000);args=p.parse_args()
    SOURCE.mkdir(parents=True,exist_ok=True)
    human=delidata_individuals(str(ROOT/'data/raw/delidata'))
    if args.part in ['all','h1']:
        for model in MODELS:h1(model,human,args.bootstrap)
    if args.part in ['all','persona']:
        for model in MODELS:persona(model)
    if args.part in ['all','s4']:s4()
    files=[ROOT/f'data/study1/results/exploratory/{m}/a1r_agents.csv'for m in MODELS]
    files += [ROOT/'data/study1/results/exploratory/claude/s4.json',ROOT/'docs/research/argument-quality-response/source-data/discussion-outcomes.csv',ROOT/'src/analysis/robustness.py',Path(__file__),ROOT/'scripts/diagnose_h1.R']
    files += list((ROOT/'data/study1/results').glob('results-*.json'))
    files += [ROOT/'docs/research/novelty-review/source-data/results.json',ROOT/'scripts/report_study1_robustness.py']
    manifest={'date':'2026-10-20','status':'Post-hoc targeted robustness; registered outputs unchanged','seed':SEED,'bootstrap':args.bootstrap,'db_access':'read-only','files':[{'path':str(x.relative_to(ROOT)),'sha256':hashlib.sha256(x.read_bytes()).hexdigest()}for x in files]}
    # Hash the exact extracted observations, plus the raw human inputs.
    manifest['extracted_files']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in SOURCE.glob('*.csv')}
    manifest['human_inputs']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in (ROOT/'data/raw/delidata').glob('*.tsv')}
    manifest['software']={'python':sys.version,'packages':{p:importlib.metadata.version(p)for p in ['numpy','pandas','scipy','statsmodels']}}
    manifest['software']['R']=subprocess.run(['Rscript','-e','cat(R.version.string,"; lme4 ",as.character(packageVersion("lme4")),"; lmerTest ",as.character(packageVersion("lmerTest")),sep="")'],capture_output=True,text=True,check=True).stdout
    manifest['raw_databases']=[]
    for model in MODELS:
        db=ROOT/f'data/study1/{model}.db';h=hashlib.sha256()
        with db.open('rb')as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        manifest['raw_databases'].append({'path':str(db.relative_to(ROOT)),'sha256':h.hexdigest(),'access':'read-only'})
    write('manifest.json',manifest)


if __name__=='__main__':main()
