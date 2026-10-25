"""Post-hoc robustness functions; registered estimators and outputs stay unchanged."""
import warnings
import numpy as np
import pandas as pd
from scipy.stats import t
import statsmodels.api as sm
from statsmodels.regression.mixed_linear_model import VCSpec

ARMS = ['A-baseline', 'A-stateful']


def group_frame(agents):
    """Paired group functionals; memberships refer to original respondent-row IDs."""
    a = agents[agents.label.isin(ARMS)].copy()
    if a.groupby(['block', 'label']).size().ne(5).any():
        raise ValueError('Need paired complete five-member groups')
    if a.groupby(['block', 'label']).persona.nunique().ne(5).any():
        raise ValueError('Repeated persona inside a group')
    g = a.groupby(['item_id', 'block', 'label']).agg(
        pre=('pre','mean'), D=('D','mean'), nD=('D','count'),
        mean=('post','mean'), within=('post',lambda s: s.var(ddof=0))).reset_index()
    g['between'] = (g['mean']-g.groupby(['item_id','label'])['mean'].transform('mean'))**2
    wide=g.pivot(index=['item_id','block'],columns='label',values=['pre','D','nD','mean','within','between'])
    if wide[['pre','mean','within','between']].isna().any().any():
        raise ValueError('Missing paired group outcome')
    if not np.allclose(wide['pre'][ARMS[0]],wide['pre'][ARMS[1]]) or not np.allclose(wide['D'][ARMS[0]],wide['D'][ARMS[1]]):
        raise ValueError('Predictor mismatch across arms')
    out=pd.DataFrame(index=wide.index)
    out['complete_D']=wide['nD'].eq(5).all(axis=1)
    for metric in ['mean','within','between']:
        out[metric+'_delta']=wide[metric][ARMS[1]]-wide[metric][ARMS[0]]
        for arm in ARMS:
            out[metric+'_'+arm]=wide[metric][arm]
    out['pre']=wide['pre'][ARMS[0]];out['D']=wide['D'][ARMS[0]]
    for k in ['pre','D']:
        out[k+'_centered']=out[k]-out[k].groupby(level='item_id').transform('mean')
    membership = a[a.label==ARMS[0]].pivot_table(index=['item_id','block'],columns='persona',values='pre',aggfunc='size',fill_value=0).reindex(out.index).fillna(0)/5
    if not np.allclose(membership.sum(axis=1),1):
        raise ValueError('Invalid membership weights')
    return out, membership


def membership_fit(frame, membership, outcome, predictors=(), maxiter=400):
    """y=Xb + item intercept + mean of five persona effects + group error (REML).

    This is a Gaussian working-model sensitivity, not a replacement registered fit.
    Each profile has one shared effect wherever it appears, across items/groups.
    """
    x=np.column_stack([np.ones(len(frame))]+[frame[c].to_numpy() for c in predictors])
    item=pd.get_dummies(frame.index.get_level_values('item_id')).to_numpy(dtype=float)
    mm=membership.to_numpy(dtype=float)
    vc=VCSpec(['item','persona'],[[list(map(str,range(item.shape[1])))], [list(map(str,membership.columns))]],[[item],[mm]])
    model=sm.MixedLM(frame[outcome].to_numpy(),x,np.ones(len(frame)),exog_vc=vc)
    fits=[];failures=[]
    for method in ['lbfgs','powell','bfgs']:
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                fit=model.fit(reml=True,method=method,maxiter=maxiter,disp=False)
                _=fit.bse_fe;_=fit.llf
            fits.append((fit,method,list(dict.fromkeys(str(w.message) for w in caught))))
        except (np.linalg.LinAlgError,ValueError,FloatingPointError) as e:
            failures.append({'method':method,'error':f'{type(e).__name__}: {e}'})
    valid=[v for v in fits if v[0].converged and np.isfinite(v[0].fe_params).all() and np.isfinite(v[0].bse_fe).all() and np.isfinite(v[0].llf)]
    if not valid:
        raise RuntimeError('No converged finite multiple-membership fit')
    # Check a common high-likelihood start when boundary components make solvers differ.
    start=max(valid,key=lambda z:z[0].llf)[0].params
    for optimizer in ['lbfgs','bfgs']:
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                refined=model.fit(start_params=start,reml=True,method=optimizer,maxiter=maxiter,disp=False)
                _=refined.bse_fe;_=refined.llf
            fits.append((refined,optimizer+'_refined',list(dict.fromkeys(str(w.message)for w in caught))))
        except (np.linalg.LinAlgError,ValueError,FloatingPointError) as e:
            failures.append({'method':optimizer+'_refined','error':f'{type(e).__name__}: {e}'})
    valid=[v for v in fits if v[0].converged and np.isfinite(v[0].fe_params).all() and np.isfinite(v[0].bse_fe).all() and np.isfinite(v[0].llf)]
    fit,method,msgs=max(valid,key=lambda z:z[0].llf)
    df=frame.index.get_level_values('item_id').nunique()-1
    q=t.ppf(.975,df)
    names=['intercept']+list(predictors)
    return {'n_groups':len(frame),'n_items':df+1,'n_personas':membership.shape[1],
            'method':'Gaussian REML multiple-membership sensitivity; t interval with items-1 df',
            'formula':f'{outcome} ~ '+ ' + '.join(['1']+list(predictors))+' + item_RE + mean(five persona_RE) + group_error',
            'coefficients':{name:{'estimate':float(v),'se':float(se),'ci':[float(v-q*se),float(v+q*se)]} for name,v,se in zip(names,fit.fe_params,fit.bse_fe)},
            'variance_components':dict(zip(vc.names,map(float,fit.vcomp))), 'residual_variance':float(fit.scale),
            'optimizer':method,'converged':bool(fit.converged),'warnings':msgs,
            'optimizer_failures':failures,
            'optimizer_checks':[{'method':m,'converged':bool(f.converged),'loglik':float(f.llf),'coefficients':list(map(float,f.fe_params)),
                                 'fixed_effect_se':list(map(float,f.bse_fe)),'warnings':w}for f,m,w in fits],
            'optimizer_interval_envelope':{name:[float(min(f.fe_params[j]-q*f.bse_fe[j] for f,_,_ in valid)),
                                                 float(max(f.fe_params[j]+q*f.bse_fe[j] for f,_,_ in valid))]for j,name in enumerate(names)},
            'inference_scope':'Working-model sensitivity, not a distribution-free guarantee; GLM/mixed estimates can differ from equal-item descriptive means.'}


def deletion_influence(frame, membership):
    """Remove all groups containing each profile; recompute both variances by item."""
    items=frame.index.get_level_values('item_id').to_numpy()
    records=[]
    for persona in membership.columns:
        keep=membership[persona].to_numpy()==0
        w=[];b=[]
        for item in np.unique(items):
            sub=frame.iloc[np.flatnonzero(keep & (items==item))]
            if len(sub)<2:
                raise ValueError('Deletion leaves fewer than two groups for an item')
            w.append(sub.within_delta.mean())
            b.append(sub['mean_'+ARMS[1]].var(ddof=0)-sub['mean_'+ARMS[0]].var(ddof=0))
        records.append({'persona':int(persona),'removed_groups':int((~keep).sum()),'within':float(np.mean(w)),'between':float(np.mean(b))})
    return pd.DataFrame(records)


def h1_risk_bootstrap(human, ai, n_boot=10000, seed=20261020):
    """Participant-weighted risk gains, matched human/AI group bootstrap within k."""
    h=human.groupby(['block','k']).correct.agg(['sum','count']).rename(columns={'sum':'h_sum','count':'h_n'})
    z=ai.groupby(['block','k']).correct.agg(['sum','count']).rename(columns={'sum':'a_sum','count':'a_n'})
    both=h.join(z,how='inner').reset_index()
    rng=np.random.default_rng(seed)
    point={};boot={}
    for k,g in both.groupby('k'):
        x=g[['h_sum','h_n','a_sum','a_n']].to_numpy()
        p=x.sum(axis=0);point[k]={'human':float(p[0]/p[1]),'ai':float(p[2]/p[3]),'n_groups':len(g),'human_n':int(p[1]),'ai_n':int(p[3])}
        sums=x[rng.integers(len(x),size=(n_boot,len(x)))].sum(axis=1)
        boot[k]=np.column_stack([sums[:,0]/sums[:,1],sums[:,2]/sums[:,3]])
    if not {'0','1'}<=point.keys():
        raise ValueError('Need k=0 and k=1')
    gains=boot['1']-boot['0'];delta=gains[:,1]-gains[:,0]
    estimates={}
    for name,j in [('human_gain',0),('ai_gain',1)]:
        col='human' if j==0 else 'ai'
        estimates[name]={'estimate':point['1'][col]-point['0'][col],'ci':np.quantile(gains[:,j],[.025,.975]).tolist()}
    estimates['ai_minus_human_gain']={'estimate':estimates['ai_gain']['estimate']-estimates['human_gain']['estimate'],'ci':np.quantile(delta,[.025,.975]).tolist()}
    return {'cells':point,'contrasts':estimates,'n_boot':n_boot,'resampling':'Original groups, independently within k strata, human and all AI repetitions kept together','scale':'probability difference, not registered conditional log odds','group_size_adjusted':False}


def direction_topic_bootstrap(frame,n_boot=10000,seed=20261020):
    """Paired topic contrasts; retain both sides, quality, support, engines and reps."""
    d=frame[frame.direction!='neutral']
    terms=['sup:aligned','q:aligned','sup:eng:aligned','q:eng:aligned']
    rows=[]
    for topic,g in d.groupby('topic'):
        if len(g)!=48 or g.groupby(['q','sup','eng','aligned']).size().nunique()!=1:
            raise ValueError('Direction bootstrap requires balanced 48-trial topics')
        rows.append([float((g.delta_c*np.prod([g[c].to_numpy()for c in term.split(':')],axis=0)).mean()*4**len(term.split(':')))for term in terms])
    x=np.asarray(rows);rng=np.random.default_rng(seed)
    draws=x[rng.integers(len(x),size=(n_boot,len(x)))].mean(axis=1)
    return {'n_topics':len(x),'n_boot':n_boot,'seed':seed,'resampling':'Policy topic, both argument sides and all experimental cells jointly retained',
            'contrasts':{term:{'estimate':float(x[:,j].mean()),'ci':np.quantile(draws[:,j],[.025,.975]).tolist()}for j,term in enumerate(terms)}}
