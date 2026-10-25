"""Build five manuscript-layout figures from archived estimates, without refitting."""
import hashlib,json,os,shutil
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/manuscript-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import PercentFormatter, FuncFormatter
import numpy as np

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'docs/research';OUT=BASE/'manuscript-figures'
MODELS=['claude','gemini','mistral'];NAMES=[m.title()for m in MODELS]
COL=['#777777','#2776bd','#d85a24'];CACHE={};RECORDS={str(i):[]for i in range(1,6)}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold','pdf.fonttype':42})


def get(fig,path,keys,label,transform=None):
    rel=str(path);p=(BASE/path).resolve()
    if rel not in CACHE:CACHE[rel]=json.loads(p.read_text())
    v=CACHE[rel]
    for k in keys:v=v[k]
    original=v
    if transform=='one_minus':v={**v,'estimate':1-v['estimate'],'ci':[1-v['ci'][1],1-v['ci'][0]]}
    if transform=='sum_solution_reasoning':v={'estimate':v['solution']['estimate']+v['reasoning']['estimate'],'ci':None}
    RECORDS[str(fig)].append({'metric':label,'source':str(p.relative_to(ROOT)),'json_path':keys,'transform':transform,'record':v})
    return v


def rq(fig,rq,metric,transform=None):
    path=f'rq-artifacts/source-data/rq{rq}_values.json'
    p=BASE/path
    if path not in CACHE:CACHE[path]=json.loads(p.read_text())
    rows=CACHE[path]['records'];idx=next(i for i,r in enumerate(rows)if r['metric']==metric)
    return get(fig,path,['records',idx],metric,transform)


def point(ax,r,x,y,color,marker='o',horizontal=False,label=None):
    v=r['estimate'];ci=r.get('ci');err=None if ci is None else [[v-ci[0]],[ci[1]-v]]
    ax.errorbar(v if horizontal else x,y if horizontal else v,xerr=err if horizontal else None,yerr=None if horizontal else err,fmt=marker,color=color,capsize=3,label=label)


def save(fig,n):
    for ext in ['png','pdf']:fig.savefig(OUT/f'figure{n}.{ext}',dpi=220)
    plt.close(fig)


def figure4():
    fig,axes=plt.subplots(2,2,figsize=(12.8,9));a,b,c,d=axes.flat
    for i,scope in enumerate(['wason','a1r','pooled_population']):
        for arm,offset,color in [('baseline',-.13,'#2776bd'),('stateful',.13,'#d85a24')]:
            value=get(4,'position-change-adjudication/results.json',['variants','glm_disagreement_combined',scope,arm],f'{scope}, GLM-adjudicated, {arm}: explicit position-change mention')
            point(a,value,0,i+offset,color,'o',True,label='Ordinary' if arm=='baseline' and i==0 else 'Stateful' if i==0 else None)
    a.set(yticks=range(3),yticklabels=['Logic','Policy','All utterances'],xlabel='Share of all utterances (weighted)',title='a  Explicit position-change mentions',xlim=(0,1));a.set_ylim(3.6,-.5);a.xaxis.set_major_formatter(PercentFormatter(1));a.legend(frameon=False,fontsize=8,loc='lower left')
    for ax,key,title,xlabel in [(b,'E1','b  Reasoning accuracy','Stateful minus ordinary (percentage points)'),(c,'E3','c  Policy convergence','Additional SD decrease (0-10 points)'),(d,'H5','d  Distance from human responses','Change in Wasserstein distance')]:
        for i,m in enumerate(MODELS):point(ax,rq(4,3,f'{m} {key}'),0,i,['#2776bd','#23856a','#d85a24'][i],['o','s','^'][i],True)
        ax.axvline(0,color='#666',ls='--');ax.set(yticks=range(3),yticklabels=NAMES,xlabel=xlabel,title=title);ax.invert_yaxis()
    b.xaxis.set_major_formatter(FuncFormatter(lambda value, pos: f"{100*value:g}"))
    fig.text(.5,.025,'a: GLM-adjudicated disagreements; agreed labels retained; fixed-label paired-block 95% intervals. b-d: registered contrasts.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.05,1,1),h_pad=3,w_pad=3);save(fig,4)


def main():
    OUT.mkdir(exist_ok=True)
    fig,ax=plt.subplots(figsize=(12,7));ax.set(xlim=(0,12),ylim=(0,7));ax.axis('off')
    def box(x,y,w,h,title,text,color='#edf4f8'):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.12',facecolor=color,edgecolor='#7894a5'))
        ax.text(x+.15,y+h-.27,title,weight='bold',va='top',fontsize=12);ax.text(x+.15,y+h-.72,text,va='top',fontsize=10,linespacing=1.6)
    box(.25,4.65,3.5,1.6,'1-A  Reasoning','471 human groups / 1,525 members\nMatched initial card selections\nOriginal and variant tasks')
    box(4.25,4.65,3.5,1.6,'1-B  Policy deliberation','30 items: 8 development + 22 evaluation\nFive-agent mixed-party groups\n2 D / 2 R / 1 Independent')
    box(8.25,4.65,3.5,1.6,'1-C  Argument response','16 topics / 32 target-side sets\nQuality x support x discussion rules\nThree repetitions per cell')
    box(.4,2.2,5.2,1.4,'Compare conditions','Ordinary discussion / stateful discussion\nIndependent re-answer / materials / no-seed response',color='#eef5ee')
    box(6.3,2.2,5.2,1.4,'Measure different outcomes','Accuracy / agreement / human response fidelity\nArgument response / process / opinion distributions',color='#fff1e6')
    for x in [2,6,10]:ax.annotate('',xy=(6,3.95),xytext=(x,4.5),arrowprops={'arrowstyle':'->','color':'#7894a5'})
    ax.annotate('',xy=(6,1.85),xytext=(6,2.5),arrowprops={'arrowstyle':'->','color':'#7894a5'})
    ax.text(6,1.55,'Three participant-model families; one shared Claude utterance analyzer',ha='center',weight='bold')
    ax.text(6,1.05,'18,209 completed runs / 18,210 planned; analysis units differ across outcomes',ha='center')
    ax.text(6,.55,'Registered comparisons + explicitly labeled post-hoc analyses; automated coding checks reported separately',ha='center',fontsize=9,color='#6c553b')
    fig.tight_layout();save(fig,1)
    RECORDS['1']=[{'source':'docs/research/MethodsDraft.md','type':'Study-design schematic; no statistical estimates'}]

    fig,axes=plt.subplots(2,2,figsize=(12.8,9));a,b,c,d=axes.flat
    labels=['Human','Claude baseline','Claude stateful']
    for j,label in enumerate(labels):
        for i,k in enumerate(['0','1','2+']):
            r=rq(2,1,f'accuracy, k={k}, {label}');point(a,r,i+(j-1)*.1,0,COL[j],marker=['o','s','^'][j],label=label.replace('Claude baseline','AI Agents ordinary').replace('Claude stateful','AI Agents stateful') if i==0 else None)
    a.set(xticks=range(3),xticklabels=['0','1','2+'],xlabel='Initially correct members (k)',ylabel='Final individual accuracy',title='a  Dependence on initial correct answers');a.yaxis.set_major_formatter(PercentFormatter(1));a.legend(frameon=False,fontsize=8)
    for j,label in enumerate(labels):
        r=[rq(2,1,f'answer changes in quarter {q}, {label}')for q in range(1,5)]
        b.plot(range(1,5),[v['estimate']for v in r],marker=['o','s','^'][j],color=COL[j],label=label)
        for i,v in enumerate(r):point(b,v,i+1,0,COL[j],marker=['o','s','^'][j])
    b.set(xticks=range(1,5),xlabel='Quarter of utterance sequence',ylabel='Share of answer-change events',title='b  Timing of changes');b.yaxis.set_major_formatter(PercentFormatter(1))
    for i,(key,label,color)in enumerate([('human','Human','#777777'),('C-reanswer','Re-answer','#a97700'),('A-baseline','Ordinary','#2776bd'),('A-stateful','Stateful','#d85a24')]):
        point(c,rq(2,1,'outlier movement toward others, '+key,'one_minus'),i,0,color)
    c.set(xticks=range(4),xticklabels=['Human','Re-answer','Ordinary','Stateful'],ylabel='Maintained or moved away',title='c  Persistence of initially distant opinions');c.yaxis.set_major_formatter(PercentFormatter(1))
    path='../../data/study1/results/exploratory/claude/n10.json'
    # Path is relative to docs/research; resolve it for portable provenance.
    for j,(keys,label)in enumerate([(['by_sample','comparison','human_same_groups'],'Human'),(['by_sample','comparison','conditions','A-baseline'],'Ordinary'),(['by_sample','comparison','conditions','A-stateful'],'Stateful')]):
        r=get(2,path,keys+['probing'],label+' probing');point(d,r,0+(j-1)*.18,0,COL[j],marker=['o','s','^'][j],label=label)
        for x,target in [(1,'solution'),(2,'reasoning')]:
            r=get(2,path,keys+[target],label+' '+target);point(d,r,x+(j-1)*.18,0,COL[j],marker=['o','s','^'][j])
    d.set(xticks=[0,1,2],xticklabels=['Questions','Answer only','Reasoning'],ylabel='Share of utterances',title='d  Utterance functions');d.yaxis.set_major_formatter(PercentFormatter(1));d.legend(frameon=False,fontsize=8)
    fig.text(.5,.025,'b: extracted card selections; c: policy responses initially >=5 points from others. d: original automated labels; adjudication sensitivity in Supplementary Information.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.05,1,1),h_pad=3,w_pad=3);save(fig,2)

    fig,axes=plt.subplots(2,2,figsize=(12.8,9));a,b,c,d=axes.flat
    arms=['C-reanswer','B-materials','A-baseline','A-stateful']
    for i,arm in enumerate(arms):point(a,rq(3,2,'table agreement '+arm),i,0,['#a97700','#23856a','#2776bd','#d85a24'][i])
    a.set(xticks=range(4),xticklabels=['Re-answer','Materials','Ordinary','Stateful'],ylabel='Post-discussion SD <= 1',title='a  Agreement (equal discussion weights)');a.yaxis.set_major_formatter(PercentFormatter(1))
    for i,key in enumerate(['beta','gamma']):
        for arm,offset,color,marker in [('A-baseline',-.1,'#2776bd','o'),('A-stateful',.1,'#d85a24','^')]:point(b,rq(3,2,key+', '+arm),0,i+offset,color,marker,True,label=('Ordinary' if arm=='A-baseline' else 'Stateful') if i==0 else None)
    b.set(yticks=[0,1],yticklabels=['Model default','Group initial mean'],xlabel='Movement coefficient',title='b  Default and initial-group associations');b.invert_yaxis();b.legend(frameon=False,fontsize=8)
    for i,key in enumerate(['weak','strong']):point(c,get(3,'argument-quality-response/source-data/results.json',['estimates',key],key+' quality rating'),i,0,'#2776bd')
    c.set(xticks=[0,1],xticklabels=['Weak','Strong'],ylabel='Standalone quality rating (0-1)',title='c  Same-model argument evaluation',ylim=(0,.65))
    for i,key in enumerate(['baseline','stateful']):point(d,get(3,'argument-quality-response/source-data/results.json',['estimates',key],key+' strong-minus-weak response'),0,i,['#2776bd','#d85a24'][i],horizontal=True)
    d.axvspan(-5,5,color='#dddddd',alpha=.35,zorder=0);d.axvline(-5,color='#666',ls=':');d.axvline(5,color='#666',ls=':');d.axvline(0,color='#666',ls='--');d.set(xlim=(-6,6),yticks=[0,1],yticklabels=['Ordinary','Stateful'],xlabel='Strong-minus-weak stance change (0-100 points)',title='d  Argument quality during discussion');d.invert_yaxis()
    fig.text(.5,.025,'Claude. Quality ratings and discussion are distinct tasks. Whiskers: 95% intervals. Shaded band: -5 to +5 points (effect-size benchmark).',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.05,1,1),h_pad=3,w_pad=3);save(fig,3)

    figure4()

    fig=plt.figure(figsize=(12.8,11));grid=fig.add_gridspec(3,2,height_ratios=[.6,1,1.25]);ah=fig.add_subplot(grid[0,0]);bh=fig.add_subplot(grid[0,1]);a=fig.add_subplot(grid[1,0],sharex=ah);b=fig.add_subplot(grid[1,1],sharex=bh);c=fig.add_subplot(grid[2,0]);d=fig.add_subplot(grid[2,1])
    party='party-dispersion/source-data/results.json'
    for i,m in enumerate(['human']+MODELS):
        contrast='deliberation - control'if m=='human'else'A-baseline - B-materials'
        keys=['results',m,'contrasts',contrast];gap=ah if m=='human'else a;spread=bh if m=='human'else b;y=0 if m=='human'else i-1
        point(gap,get(5,party,keys+['party_gap'],m+' party gap'),0,y,'#777777'if m=='human'else'#2776bd',horizontal=True)
        for key,off,color,marker,label in [('sd_dem',-.1,'#2776bd','o','Democratic'),('sd_rep',.1,'#d85a24','^','Republican')]:point(spread,get(5,party,keys+[key],m+' '+key),0,y+off,color,marker,True,label=label if m=='human'else None)
    for ax,title,labels in [(ah,'a(i)  Human: event - control',['Human']),(bh,'b(i)  Human: event - control',['Human']),(a,'a(ii)  AI: discussion - materials',NAMES),(b,'b(ii)  AI: discussion - materials',NAMES)]:
        ax.axvline(0,color='#666',ls='--');ax.set(yticks=range(len(labels)),yticklabels=labels,title=title,ylim=(len(labels)-.5,-.5))
    ah.set_xlabel('Change in between-party gap (0-10 points)');a.set_xlabel('Change in between-party gap (0-10 points)')
    bh.set_xlabel('Change in within-party SD (0-10 points)');b.set_xlabel('Change in within-party SD (0-10 points)');bh.legend(frameon=False,fontsize=8,loc='lower left')
    original='novelty-review/source-data/results.json'
    for i,m in enumerate(MODELS):
        for key,off,color,marker,label in [('within',-.12,'#2776bd','o','Within group'),('between',.12,'#d85a24','^','Between group means')]:point(c,get(5,original,['results',m,'contrasts',key],m+' '+key),0,i+off,color,marker,horizontal=True,label=label.replace('Claude baseline','AI Agents ordinary').replace('Claude stateful','AI Agents stateful') if i==0 else None)
        point(d,get(5,original,['results',m,'composition','rule_minus_baseline','initial_mean'],m+' original initial-mean association'),0,i-.1,'#2776bd',horizontal=True,label='Item bootstrap'if i==0 else None)
        point(d,get(5,f'robustness/source-data/{m}-persona.json',['initial_mean_association_delta','coefficients','pre_centered'],m+' repeated-persona initial-mean association'),0,i+.1,'#d85a24','^',True,label='Repeated-persona model'if i==0 else None)
    c.axvline(0,color='#666',ls='--');c.set(yticks=range(3),yticklabels=NAMES,xlabel='Stateful minus ordinary (squared score points)',title='c  Within and between discussion groups');c.invert_yaxis();c.legend(frameon=False,fontsize=8)
    d.axvline(0,color='#666',ls='--');d.set(yticks=range(3),yticklabels=NAMES,xlabel='Additional initial-mean coefficient',title='d  Initial-group and final-group means');d.invert_yaxis();d.legend(frameon=False,fontsize=8)
    fig.text(.5,.018,'a-b: distinct contrasts on shared units. c-d: post-hoc stateful minus ordinary. Mistral within-variance sensitivity: see supplement.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.045,1,1),h_pad=3,w_pad=3);save(fig,5)
    (OUT/'source-data.json').write_text(json.dumps({'status':'Manuscript layout draft; automated coding checks completed; final author review pending','figures':RECORDS},ensure_ascii=False,indent=2)+'\n')
    manifest={str((BASE/p).resolve().relative_to(ROOT)):hashlib.sha256((BASE/p).read_bytes()).hexdigest()for p in CACHE}
    for path in ['docs/research/MethodsDraft.md','scripts/build_manuscript_figures.py']:
        manifest[path]=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    (OUT/'input-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    import subprocess,sys
    subprocess.run([sys.executable,str(ROOT/'scripts/build_manuscript_revision_additions.py'),'--figure-only'],check=True)
    print('Six manuscript-layout PNG/PDF figures and traceable values written.')


if __name__=='__main__':
    import sys
    if '--figure4-only'in sys.argv:
        saved=json.loads((OUT/'source-data.json').read_text())
        figure4();saved['figures']['4']=RECORDS['4']
        (OUT/'source-data.json').write_text(json.dumps(saved,ensure_ascii=False,indent=2)+'\n')
        manifest=json.loads((OUT/'input-manifest.json').read_text())
        for source in CACHE:
            p=(BASE/source).resolve();manifest[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
        manifest['scripts/build_manuscript_figures.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        manifest['docs/research/MethodsDraft.md']=hashlib.sha256((BASE/'MethodsDraft.md').read_bytes()).hexdigest()
        (OUT/'input-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        print('Figure 4a replaced by matched blind recoding; b-d estimates unchanged; other figures untouched.')
    else:main()

