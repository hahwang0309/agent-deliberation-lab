"""Post-hoc human/AI consensus, group conclusions and representation checks.

Reads archived outcomes and existing human survey pairs; no API calls or DB writes.
See docs/research/consensus-representation/AnalysisPlan.md for estimands and limits.
"""
from pathlib import Path
import os,sys,json,hashlib
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/consensus-representation-mpl')
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import humans
from src.analysis.group_disagreement import paired_groups
OUT=ROOT/'docs/research/consensus-representation';S=OUT/'source-data'
ARMS=['A-baseline','A-stateful'];MODELS=['claude','gemini','mistral']
BOOT=5000;PANELS=200;SEED=20261021
ITEMS=pd.read_csv(ROOT/'data/study1/results/exploratory/human/n3_human_items.csv').item.tolist()


def stats_group(pre,post,weights=None,D=None):
    """Equal group weight or supplied bootstrap counts; last axis is group.

    pre/post dicts contain per-group moments, not independent member rows.
    """
    size=len(pre['mean']);w=np.ones((1,size)) if weights is None else np.atleast_2d(weights)
    n_drawn=w.sum(axis=1)
    w=w/n_drawn[:,None]
    def avg(v):
        v=np.asarray(v);valid=np.isfinite(v)
        return (w[:,valid]@v[valid])/w[:,valid].sum(axis=1)

    vx=avg(pre['mean']**2)-avg(pre['mean'])**2
    cov=avg(pre['mean']*post['mean'])-avg(pre['mean'])*avg(post['mean'])
    out={}
    for phase,d in [('pre',pre),('post',post)]:
        for name in ['within','sd','consensus','range_consensus','party_gap']:
            out[phase+'_'+name]=avg(d[name])
        out[phase+'_between']=np.maximum(0,avg(d['mean']**2)-avg(d['mean'])**2)
        out[phase+'_between_unbiased']=out[phase+'_between']*n_drawn/(n_drawn-1)
    out['sd_drop']=out['pre_sd']-out['post_sd']
    out['between_change']=out['post_between']-out['pre_between']
    out['group_mean_distance_from_initial']=avg(np.abs(post['mean']-pre['mean']))
    out['_initial_variance']=vx;out['_initial_final_covariance']=cov
    for k in ['one_way','all_moving_one_way','two_way_and_consensus','one_way_and_consensus','individual_initial_distance','individual_default_distance','group_default_distance']:
        if k in post:out[k]=avg(post[k])
    return {k:v[0]if weights is None else v for k,v in out.items()}


def moments(pre,post,party,D=None):
    """Arrays groups x members; compute matched pre/post moments."""
    output=[]
    for a in [pre,post]:
        var=a.var(axis=1);d={'mean':a.mean(axis=1),'within':var,'sd':np.sqrt(var),'consensus':(np.sqrt(var)<=1).astype(float),'range_consensus':(np.ptp(a,axis=1)<=2).astype(float)}
        dem=np.where(party=='1',a,np.nan);rep=np.where(party=='2',a,np.nan)
        with np.errstate(invalid='ignore'):d['party_gap']=np.abs(np.nanmean(dem,axis=1)-np.nanmean(rep,axis=1))
        # Some actual human rooms lack one party. Gap is handled separately there.
        output.append(d)
    delta=post-pre
    output[1]['one_way']=(((delta>=0).all(axis=1)|(delta<=0).all(axis=1))&(delta!=0).any(axis=1)).astype(float)
    output[1]['all_moving_one_way']=((delta>0).all(axis=1)|(delta<0).all(axis=1)).astype(float)
    output[1]['one_way_and_consensus']=output[1]['one_way']*output[1]['consensus']
    output[1]['two_way_and_consensus']=((delta>0).any(axis=1)&(delta<0).any(axis=1)).astype(float)*output[1]['consensus']
    output[1]['individual_initial_distance']=np.abs(delta).mean(axis=1)
    if D is not None:
        output[1]['individual_default_distance']=np.where(np.isfinite(D).all(axis=1),np.nanmean(np.abs(post-D),axis=1),np.nan)
        output[1]['group_default_distance']=np.where(np.isfinite(D).all(axis=1),np.abs(post.mean(axis=1)-np.nanmean(D,axis=1)),np.nan)
    return output


def record(point,draws):
    draws=np.asarray(draws);finite=draws[np.isfinite(draws)]
    return {'estimate':float(point),'ci':np.quantile(finite,[.025,.975]).tolist()if len(finite) else None,'valid_bootstrap_draws':int(len(finite))}


def item_summary(table,indices):
    """Equal policy-item weight, paired indices across conditions and metrics."""
    x=table.reindex(ITEMS).to_numpy(float)
    if not np.isfinite(x).all():raise ValueError('Nonfinite item metric')
    draws=x[indices].mean(axis=1);point=x.mean(axis=0)
    return {k:record(point[j],draws[:,j])for j,k in enumerate(table.columns)}



def conditional_consensus(table,indices):
    out={};t=table.reindex(ITEMS);den=t.post_consensus.to_numpy()
    for name in ['one_way_and_consensus','two_way_and_consensus']:
        num=t[name].to_numpy();bd=den[indices].mean(axis=1);bn=num[indices].mean(axis=1)
        boot=np.divide(bn,bd,out=np.full_like(bn,np.nan),where=bd>0)
        out[name.replace('_and_consensus','_among_consensus')]=record(num.mean()/den.mean(),boot)
    return out

def shape_summary(table,indices):
    """Ratio/slope/correlation estimands: recompute after each item resample."""
    z=table.reindex(ITEMS)
    out={}
    for arm in ['Human']+ARMS:
        initial=z['initial_gap'].to_numpy();final=z[arm+'_gap'].to_numpy()
        def slope(a,b):return np.mean(a*b,axis=-1)/np.mean(a*a,axis=-1)
        out[arm]={
          'initial_gap_alignment':record(slope(initial,final),slope(initial[indices],final[indices])),
          'mean_absolute_party_gap':record(np.abs(final).mean(),np.abs(final[indices]).mean(axis=1)),
          'initial_gap_direction_agreement':record((np.sign(initial)==np.sign(final)).mean(),(np.sign(initial[indices])==np.sign(final[indices])).mean(axis=1)),
        }
        selected=np.abs(initial)>=1
        out[arm]['n_items_initial_gap_ge_1']=int(selected.sum())
        out[arm]['initial_gap_direction_agreement_ge_1']={'estimate':float((np.sign(initial[selected])==np.sign(final[selected])).mean())}
        # Pearson correlation across policies; undefined constant draws omitted.
        a=initial[indices];b=final[indices];ac=a-a.mean(axis=1,keepdims=True);bc=b-b.mean(axis=1,keepdims=True)
        corr=(ac*bc).sum(axis=1)/np.sqrt((ac*ac).sum(axis=1)*(bc*bc).sum(axis=1))
        out[arm]['initial_gap_correlation']=record(np.corrcoef(initial,final)[0,1],corr)
        if arm!='Human':
            err=np.abs(final-z.Human_gap.to_numpy())
            out[arm]['distance_from_human_final_party_gap']=record(err.mean(),err[indices].mean(axis=1))
    # Direct paired comparison; not inference from overlap of separate CIs.
    initial=z.initial_gap.to_numpy();base=z[ARMS[0]+'_gap'].to_numpy();state=z[ARMS[1]+'_gap'].to_numpy()
    b=np.mean(initial*base)/np.mean(initial**2);t=np.mean(initial*state)/np.mean(initial**2)
    bd=np.mean(initial[indices]*base[indices],axis=1)/np.mean(initial[indices]**2,axis=1)
    td=np.mean(initial[indices]*state[indices],axis=1)/np.mean(initial[indices]**2,axis=1)
    out['rules_minus_baseline']={'initial_gap_alignment':record(t-b,td-bd)}
    return out


def human_tables(h):
    rows=[];panelrows=[];panels={};native={};rng=np.random.default_rng(SEED)
    for (grp,item),g in h.groupby(['group','item']):
        pre=g.pre.to_numpy(float);post=g.post.to_numpy(float);party=g.party.astype(str).to_numpy()
        mi=[]
        for a in [pre,post]:
            var=a.var();gap=abs(a[party=='1'].mean()-a[party=='2'].mean())if (party=='1').any()and(party=='2').any()else np.nan
            mi.append({'mean':a.mean(),'within':var,'sd':np.sqrt(var),'consensus':float(np.sqrt(var)<=1),'range_consensus':float(np.ptp(a)<=2),'party_gap':gap})
        delta=post-pre;mi[1]['one_way']=float(((delta>=0).all()or(delta<=0).all())and(delta!=0).any());mi[1]['all_moving_one_way']=float((delta>0).all()or(delta<0).all());mi[1]['individual_initial_distance']=float(np.abs(delta).mean())
        mi[1]['one_way_and_consensus']=mi[1]['one_way']*mi[1]['consensus'];mi[1]['two_way_and_consensus']=float((delta>0).any()and(delta<0).any())*mi[1]['consensus']
        native[(str(grp),item)]=mi
        rows.append({'group':str(grp),'item':item,'n':len(g),**{phase+'_'+k:float(v)for phase,m in zip(['pre','post'],mi)for k,v in m.items()}})
        if not all((party==p).sum()>=n for p,n in [('1',2),('2',2),('3',1)]):continue
        indices=np.concatenate([np.stack([rng.choice(np.flatnonzero(party==p),n,replace=False)for _ in range(PANELS)])for p,n in [('1',2),('2',2),('3',1)]],axis=1)
        samplepart=np.take(party,indices);m=moments(pre[indices],post[indices],samplepart)
        panels[(str(grp),item)]=m
        panelrows.append({'group':str(grp),'item':item,**{phase+'_'+k:float(np.mean(v))for phase,d in zip(['pre','post'],m)for k,v in d.items()}})
    groups=sorted(h.group.astype(str).unique());gid={g:i for i,g in enumerate(groups)}
    rng=np.random.default_rng(SEED+1);weights=rng.multinomial(len(groups),np.ones(len(groups))/len(groups),size=BOOT)
    native_item=[];native_draw=[];panel_item=[];panel_draw=[];eligible=[];eligible_item=[];eligible_draw=[]
    for item in ITEMS:
        keys=[k for k in native if k[1]==item];pre={k:np.array([native[key][0][k]for key in keys])for k in native[keys[0]][0]};post={k:np.array([native[key][1][k]for key in keys])for k in native[keys[0]][1]}
        z=stats_group(pre,post);native_item.append({'item':item,**z});native_draw.append(stats_group(pre,post,weights[:,[gid[k[0]]for k in keys]]))
        pkeys=[k for k in panels if k[1]==item];eligible.append({'item':item,'groups':len(pkeys)})
        epre={k:np.array([native[key][0][k]for key in pkeys])for k in native[pkeys[0]][0]}
        epost={k:np.array([native[key][1][k]for key in pkeys])for k in native[pkeys[0]][1]}
        eligible_item.append({'item':item,**stats_group(epre,epost)})
        eligible_draw.append(stats_group(epre,epost,weights[:,[gid[k[0]]for k in pkeys]]))

        w=weights[:,[gid[k[0]]for k in pkeys]].astype(float);n_drawn=w.sum(axis=1);w/=n_drawn[:,None]
        pdct={};ddct={}
        for j,phase in enumerate(['pre','post']):
            # Each panel replication has one five-person measurement per actual room.
            data={k:np.stack([panels[key][j][k]for key in pkeys],axis=1)for k in panels[pkeys[0]][j]}
            for name in ['within','sd','consensus','range_consensus','party_gap']:
                pdct[phase+'_'+name]=float(data[name].mean());ddct[phase+'_'+name]=w@data[name].mean(axis=0)
            means=data['mean'];pdct[phase+'_between']=float(means.var(axis=1).mean())
            ddct[phase+'_between']=w@(means**2).mean(axis=0)-((w@means.T)**2).mean(axis=1)
            pdct[phase+'_between_unbiased']=pdct[phase+'_between']*len(pkeys)/(len(pkeys)-1)
            ddct[phase+'_between_unbiased']=ddct[phase+'_between']*n_drawn/(n_drawn-1)
        x=np.stack([panels[k][0]['mean']for k in pkeys],axis=1);y=np.stack([panels[k][1]['mean']for k in pkeys],axis=1)
        pdct['_initial_variance']=float(x.var(axis=1).mean());pdct['_initial_final_covariance']=float(((x-x.mean(axis=1,keepdims=True))*(y-y.mean(axis=1,keepdims=True))).mean())
        ddct['_initial_variance']=w@(x*x).mean(axis=0)-((w@x.T)**2).mean(axis=1)
        ddct['_initial_final_covariance']=w@(x*y).mean(axis=0)-((w@x.T)*(w@y.T)).mean(axis=1)
        pdct['group_mean_distance_from_initial']=float(np.abs(y-x).mean());ddct['group_mean_distance_from_initial']=w@np.abs(y-x).mean(axis=0)
        pdct['sd_drop']=pdct['pre_sd']-pdct['post_sd'];ddct['sd_drop']=ddct['pre_sd']-ddct['post_sd']
        pdct['between_change']=pdct['post_between']-pdct['pre_between'];ddct['between_change']=ddct['post_between']-ddct['pre_between']
        for name in ['one_way','all_moving_one_way','two_way_and_consensus','one_way_and_consensus','individual_initial_distance']:
            vals=np.array([panels[k][1][name].mean()for k in pkeys]);pdct[name]=float(vals.mean());ddct[name]=w@vals
        panel_item.append({'item':item,**pdct});panel_draw.append(ddct)
    pd.DataFrame(rows).to_csv(S/'human-native-groups.csv',index=False);pd.DataFrame(panelrows).to_csv(S/'human-balanced-panel-groups.csv',index=False)
    def collapse(items,draws):
        frame=pd.DataFrame(items).set_index('item');res={k:record(frame[k].mean(),np.stack([d[k]for d in draws]).mean(axis=0))for k in frame if not k.startswith('_')}
        b=frame._initial_final_covariance.mean()/frame._initial_variance.mean();boot=np.stack([d['_initial_final_covariance']for d in draws]).mean(axis=0)/np.stack([d['_initial_variance']for d in draws]).mean(axis=0)
        res['initial_final_mean_slope']=record(b,boot)
        return frame,res
    nf,ns=collapse(native_item,native_draw);pf,ps=collapse(panel_item,panel_draw);ef,es=collapse(eligible_item,eligible_draw)
    nf.to_csv(S/'human-native-items.csv');pf.to_csv(S/'human-balanced-panel-items.csv');ef.to_csv(S/'human-native-eligible-items.csv')
    return {'native':(nf,ns),'balanced5':(pf,ps),'native_balanced_eligible':(ef,es)}, {'rows':len(h),'people':h.row.nunique(),'groups':h.group.nunique(),'group_item_records':len(rows),'min_valid_members':int(pd.DataFrame(rows).n.min()),'max_valid_members':int(pd.DataFrame(rows).n.max()),'balanced_eligible_group_items':len(panelrows),'balanced_by_item':eligible,'n_panels':PANELS}


def matched_tables(a,h,indices,model):
    # Same original human, same item, same seeded score; repeated AI contexts collapsed per persona.
    q=a.merge(h,left_on=['persona','item_id'],right_on=['row','item'],suffixes=('_ai','_h'),validate='many_to_one')
    assert np.allclose(q.pre_ai,q.pre_h);assert (q.party_ai.astype(str)==q.party_h.astype(str)).all()
    q['delta_ai']=q.post_ai-q.pre_ai;q['delta_h']=q.post_h-q.pre_h
    q['mae']=np.abs(q.delta_ai-q.delta_h);q['sign_agreement']=(np.sign(q.delta_ai)==np.sign(q.delta_h)).astype(float)
    q['human_mover_direction']=np.where(np.abs(q.delta_h)>=1,(np.sign(q.delta_ai)==np.sign(q.delta_h)).astype(float),np.nan)
    cols=['mae','sign_agreement','human_mover_direction','delta_ai','delta_h','pre_ai','post_ai','post_h','D']
    persona=q.groupby(['label','item_id','persona','party_ai','group'])[cols].mean().reset_index()
    persona.to_csv(S/f'{model}-matched-persona-outcomes.csv',index=False)
    rows=[];profile=[]
    for item in ITEMS:
        group=persona[persona.item_id==item];row={'item':item};pp={'item':item}
        for arm in ARMS:
            v=group[group.label==arm]
            for key in ['mae','sign_agreement','human_mover_direction']:row[arm+'_'+key]=float(v[key].mean())
            for party in [1,2]:
                t=v[v.party_ai.astype(int)==party]
                row[f'{arm}_mae_party{party}']=float(t.mae.mean())
                row[f'{arm}_sign_party{party}']=float(t.human_mover_direction.mean())
            by=v[v.party_ai.astype(int).isin([1,2])].groupby('party_ai')[['delta_ai','delta_h','pre_ai','post_ai','post_h']].mean()
            by.index=by.index.astype(int);err=np.abs(by.delta_ai-by.delta_h)
            row[arm+'_party_shift_mae']=float(err.mean())
            selected=by.delta_h.abs()>=.5
            row[arm+'_party_mover_count']=int(selected.sum())
            row[arm+'_party_mover_hits']=int((np.sign(by.loc[selected,'delta_ai'])==np.sign(by.loc[selected,'delta_h'])).sum())

            for party in [1,2]:
                row[f'{arm}_party{party}_shift']=float(by.loc[party,'delta_ai']);row[f'Human_party{party}_shift']=float(by.loc[party,'delta_h'])
            pp[arm+'_gap']=float(by.loc[1,'post_ai']-by.loc[2,'post_ai'])
            pp['initial_gap']=float(by.loc[1,'pre_ai']-by.loc[2,'pre_ai']);pp['Human_gap']=float(by.loc[1,'post_h']-by.loc[2,'post_h'])
        for k in ['mae','sign_agreement','human_mover_direction','mae_party1','mae_party2','sign_party1','sign_party2','party_shift_mae']:
            row['rules_minus_baseline_'+k]=row[ARMS[1]+'_'+k]-row[ARMS[0]+'_'+k]
        rows.append(row);profile.append(pp)
    table=pd.DataFrame(rows).set_index('item');pframe=pd.DataFrame(profile).set_index('item')
    table.to_csv(S/f'{model}-matched-item-metrics.csv');pframe.to_csv(S/f'{model}-party-profiles.csv')
    summ=item_summary(table,indices);shape=shape_summary(pframe,indices)
    directional={}
    for arm in ARMS:
        num=table.reindex(ITEMS)[arm+'_party_mover_hits'].to_numpy();den=table.reindex(ITEMS)[arm+'_party_mover_count'].to_numpy()
        directional[arm]=record(num.sum()/den.sum(),num[indices].sum(axis=1)/den[indices].sum(axis=1))
        directional[arm]['n_party_item_cells']=int(den.sum())
    directional['rules_minus_baseline']=record(directional[ARMS[1]]['estimate']-directional[ARMS[0]]['estimate'],
      (table[ARMS[1]+'_party_mover_hits'].to_numpy()[indices].sum(axis=1)/table[ARMS[1]+'_party_mover_count'].to_numpy()[indices].sum(axis=1))-
      (table[ARMS[0]+'_party_mover_hits'].to_numpy()[indices].sum(axis=1)/table[ARMS[0]+'_party_mover_count'].to_numpy()[indices].sum(axis=1)))
    diff=np.abs(pframe[ARMS[1]+'_gap'].to_numpy()-pframe.Human_gap.to_numpy())-np.abs(pframe[ARMS[0]+'_gap'].to_numpy()-pframe.Human_gap.to_numpy())
    shape['rules_minus_baseline']['distance_from_human_final_party_gap']=record(diff.mean(),diff[indices].mean(axis=1))

    # Joint source-human-room reweighting carries the same persona into both AI arms.
    rng=np.random.default_rng(SEED+10);groups=sorted(h.group.unique());mp={g:i for i,g in enumerate(groups)}
    weights=rng.multinomial(len(groups),np.ones(len(groups))/len(groups),size=BOOT)
    numerator={};denom={};moving_num={};moving_den={}
    for arm in ARMS:
        mae=np.zeros(BOOT);sgn=np.zeros(BOOT);cnt=0
        for item in ITEMS:
            v=persona[(persona.label==arm)&(persona.item_id==item)];ix=v.group.map(mp).to_numpy()
            w=weights[:,ix];den=w.sum(axis=1)
            mae+=(w@v.mae.to_numpy())/den/len(ITEMS)
            valid=v.human_mover_direction.notna().to_numpy();sgn+=(w[:,valid]@v.human_mover_direction.to_numpy()[valid])/w[:,valid].sum(axis=1)/len(ITEMS)
        numerator[arm]=mae;moving_num[arm]=sgn
    cluster={k:record(summ['rules_minus_baseline_'+k]['estimate'],arr)for k,arr in [('mae',numerator[ARMS[1]]-numerator[ARMS[0]]),('human_mover_direction',moving_num[ARMS[1]]-moving_num[ARMS[0]])]}
    return {'matched':summ,'party_cell_movement_direction':directional,'party_profiles':shape,'source_human_room_cluster_contrasts':cluster,'sample':{'AI_agent_item_rows_joined':len(q),'AI_agent_item_rows_unmatched':len(a)-len(q),'unique_persona_item_pairs':int(persona[['item_id','persona']].drop_duplicates().shape[0]),'distinct_people':int(persona.persona.nunique()),'rows_by_arm':q.groupby('label').size().to_dict(),'human_moving_persona_items':int(persona[persona.label==ARMS[0]].human_mover_direction.notna().sum())}}


def main():
    S.mkdir(parents=True,exist_ok=True);(OUT/'figures').mkdir(exist_ok=True)
    h=humans.a1r_delegates(str(ROOT/'data/raw/a1r/dataset.tab'),ITEMS,'1');h['party']=h.party.astype(str)
    humansets,hsample=human_tables(h)
    rng=np.random.default_rng(SEED);indices=rng.integers(len(ITEMS),size=(BOOT,len(ITEMS)))
    out={'date':'2026-10-21','status':'Post-hoc exploratory; user hypothesis after prior analyses','n_boot':BOOT,'seed':SEED,'human_sample':hsample,'human':{},'models':{},'interpretation_limits':['Descriptive outcome comparisons, different human/AI environments and group construction','Human balanced panels are measurements from original larger discussion rooms, not new 5-person discussions','Topic bootstrap holds observed membership fixed; AI block bootstrap does not solve cross-block persona dependence','Initial-group mean dependence is not the same as party representation','No causal isolation of party identity or individual deliberation mechanisms']}
    for label,(frame,cluster)in humansets.items():
        summ=item_summary(frame.drop(columns=[c for c in frame if c.startswith('_')]),indices)
        xx=frame._initial_variance.to_numpy();xy=frame._initial_final_covariance.to_numpy()
        summ['initial_final_mean_slope']=record(xy.mean()/xx.mean(),xy[indices].mean(axis=1)/xx[indices].mean(axis=1))
        out['human'][label]={'item_bootstrap':summ,'actual_room_cluster_bootstrap':cluster,'conditional_consensus_direction':conditional_consensus(frame,indices)}
    inputs=[ROOT/'data/raw/a1r/dataset.tab',ROOT/'data/study1/results/exploratory/human/n3_human_items.csv',ROOT/'src/analysis/humans.py',ROOT/'src/cases/a1r.py',Path(__file__),OUT/'AnalysisPlan.md']
    allitems=[]
    for model in MODELS:
        path=ROOT/f'data/study1/results/exploratory/{model}/a1r_agents.csv';inputs.append(path)
        source=pd.read_csv(path);a=paired_groups(source,ARMS);a['party']=a.party.astype(str)
        rows=[];draws={arm:[]for arm in ARMS}
        for item in ITEMS:
            g=a[a.item_id==item];blocks=sorted(g.block.unique());arrays=[]
            for arm in ARMS:
                q=g[g.label==arm].sort_values(['block','participant']);assert q.groupby('block').size().eq(5).all()
                arrays.append({k:q[k].to_numpy().reshape(-1,5)for k in ['pre','post','party','D']})
            rng=np.random.default_rng(SEED+ITEMS.index(item));w=rng.multinomial(len(blocks),np.ones(len(blocks))/len(blocks),size=BOOT)
            for arm,arr in zip(ARMS,arrays):
                pre,post=moments(arr['pre'].astype(float),arr['post'].astype(float),arr['party'],arr['D'].astype(float))
                # Mistral has one missing D; default-only metrics use complete groups.
                nD=int(np.isfinite(arr['D']).all(axis=1).sum())
                point=stats_group(pre,post);sampled=stats_group(pre,post,w)
                rows.append({'item':item,'label':arm,'n_groups':len(blocks),'n_complete_D_groups':nD,**point});draws[arm].append(sampled)
        tab=pd.DataFrame(rows);tab.to_csv(S/f'{model}-group-item-metrics.csv',index=False);allitems.extend(tab.assign(model=model).to_dict('records'))
        mr={'sample':{'paired_blocks':int(a.block.nunique()),'agent_item_rows_per_arm':int(len(a)/2)},'levels':{},'rules_minus_baseline':{},'human_comparisons':{}}
        cols=[k for k in rows[0]if k not in ['item','label','n_groups','n_complete_D_groups']and not k.startswith('_')]
        for arm in ARMS:
            frame=tab[tab.label==arm].set_index('item');summ=item_summary(frame[cols],indices)
            xx=frame.reindex(ITEMS)._initial_variance.to_numpy();xy=frame.reindex(ITEMS)._initial_final_covariance.to_numpy()
            summ['initial_final_mean_slope']=record(xy.mean()/xx.mean(),xy[indices].mean(axis=1)/xx[indices].mean(axis=1))
            cluster={k:record(frame[k].mean(),np.stack([x[k]for x in draws[arm]]).mean(axis=0))for k in cols}
            cluster['initial_final_mean_slope']=record(summ['initial_final_mean_slope']['estimate'],np.stack([x['_initial_final_covariance']for x in draws[arm]]).mean(axis=0)/np.stack([x['_initial_variance']for x in draws[arm]]).mean(axis=0))
            mr['levels'][arm]={'item_bootstrap':summ,'paired_block_bootstrap_fixed_items':cluster,'conditional_consensus_direction':conditional_consensus(frame,indices)}
            mr['human_comparisons'][arm]={}
            for human,(hf,_)in humansets.items():
                shared=[k for k in cols if k in hf and k!='party_gap']
                diff=frame.reindex(ITEMS)[shared]-hf.reindex(ITEMS)[shared]
                mr['human_comparisons'][arm][human]=item_summary(diff,indices)
        base=tab[tab.label==ARMS[0]].set_index('item');state=tab[tab.label==ARMS[1]].set_index('item')
        mr['rules_minus_baseline']['item_bootstrap']=item_summary(state[cols]-base[cols],indices)
        mr['rules_minus_baseline']['paired_block_bootstrap_fixed_items']={k:record((state[k]-base[k]).mean(),np.stack([x[k]for x in draws[ARMS[1]]]).mean(axis=0)-np.stack([x[k]for x in draws[ARMS[0]]]).mean(axis=0))for k in cols}
        matched=matched_tables(a,h,indices,model);mr['sample'].update(matched.pop('sample'));mr.update(matched);out['models'][model]=mr
        print(model,json.dumps({'agreement':{arm:mr['levels'][arm]['item_bootstrap']['post_consensus']for arm in ARMS},'human_motion_MAE_delta':mr['matched']['rules_minus_baseline_mae'],'human_direction_delta':mr['matched']['rules_minus_baseline_human_mover_direction'],'party_gap_alignment':mr['party_profiles']['rules_minus_baseline'],'party_shift_MAE_delta':mr['matched']['rules_minus_baseline_party_shift_mae']},ensure_ascii=False),flush=True)
    (S/'results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (S/'input-manifest.json').write_text(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in inputs},ensure_ascii=False,indent=2)+'\n')
    print('Human group comparisons',json.dumps({k:{m:v['item_bootstrap'][m]for m in ['post_consensus','pre_between','post_between','between_change','initial_final_mean_slope']}for k,v in out['human'].items()},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
