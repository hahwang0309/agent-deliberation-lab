"""Build manuscript-planning figures/tables from saved Study 1 estimates.

No statistical models are refitted. Original uncertainty intervals are preserved.
Run: MPLCONFIGDIR=/private/tmp/rq-matplotlib .venv/bin/python scripts/build_research_question_artifacts.py
"""
from pathlib import Path
import hashlib
import json
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import PercentFormatter

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "data/study1/results"
OUT = ROOT / "docs/research/rq-artifacts"
for folder in ("figures", "tables", "source-data"):
    (OUT / folder).mkdir(parents=True, exist_ok=True)
MODELS = {"claude": "claude-haiku-4-5-20251001", "gemini": "gemini-3.5-flash-lite", "mistral": "mistral-small-2603"}
SHORT = {"claude": "Claude", "gemini": "Gemini", "mistral": "Mistral"}
COL = {"human": "#7b7b7b", "A-baseline": "#2776bd", "A-stateful": "#d85a24", "B-materials": "#23856a", "C-reanswer": "#a97700"}
MCOL = {"claude": "#2776bd", "gemini": "#8064a2", "mistral": "#23856a"}
ARMS = ["C-reanswer", "B-materials", "A-baseline", "A-stateful"]
ANAME = {"C-reanswer": "Re-answer", "B-materials": "Materials", "A-baseline": "Baseline", "A-stateful": "Stateful"}
CACHE, ROWS = {}, {1: [], 2: [], 3: []}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 12,
    "axes.labelsize": 10, "legend.fontsize": 8, "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": 1, "lines.linewidth": 1.5, "pdf.fonttype": 42, "savefig.facecolor": "white"})


def load(rel):
    if rel not in CACHE:
        CACHE[rel] = json.loads((RES / rel).read_text())
    return CACHE[rel]


def ex(model, name):
    return f"exploratory/{model}/{name}.json"


def reg(model):
    return f"results-{MODELS[model]}.json"


def get(rq, rel, path, label, n=None, analysis="exploratory", unit="", scale=1):
    value = load(rel)
    for key in path:
        value = value[key]
    if "estimate" not in value and "rho" in value:
        value = {**value, "estimate": value["rho"]}
    if "estimate" not in value and "spearman" in value:
        value = {**value, "estimate": value["spearman"]}
    rec = {"metric": label, "estimate": value["estimate"], "ci": value.get("ci"),
           "n": n if n is not None else value.get("n"), "unit": unit, "display_scale": scale,
           "analysis": analysis, "source": str((RES / rel).relative_to(ROOT)), "json_path": path,
           "original_record": value}
    if rec["ci"] is not None:
        assert rec["ci"][0] <= rec["estimate"] <= rec["ci"][1], rec
    ROWS[rq].append(rec)
    return rec


def dot(ax, x, y, rec, color, marker="o", horizontal=False, label=None):
    est = rec["estimate"] * rec["display_scale"]
    ci = rec["ci"]
    err = None if ci is None else np.array([[est-ci[0]*rec["display_scale"]], [ci[1]*rec["display_scale"]-est]])
    ax.errorbar(est if horizontal else x, y if horizontal else est,
        xerr=err if horizontal else None, yerr=None if horizontal else err,
        fmt=marker, color=color, capsize=3, markersize=6, linewidth=1.2, label=label)


def setup(title):
    fig, axes = plt.subplots(2, 2, figsize=(12.8, 9.2))
    fig.subplots_adjust(left=.10, right=.97, top=.88, bottom=.13, hspace=.57, wspace=.40)
    fig.suptitle(title, fontsize=17, fontweight="bold", x=.10, ha="left", y=.975)
    for ax in axes.flat:
        ax.grid(axis="x", alpha=.16)
        ax.set_axisbelow(True)
    return fig, axes.flat


def save(fig, stem, note):
    fig.text(.10, .052, note, ha="left", va="top", fontsize=9, linespacing=1.5)
    for suffix in ("png", "pdf"):
        fig.savefig(OUT / "figures" / f"{stem}.{suffix}", dpi=220)
    plt.close(fig)


def fmt(rec, decimals=2, percent=False):
    scale = 100 if percent else rec["display_scale"]
    tail = "%" if percent else ""
    if rec["ci"] is None:
        return f'{rec["estimate"]*scale:.{decimals}f}{tail} (CI not estimated)'
    lo, hi = rec["ci"]
    return f'{rec["estimate"]*scale:.{decimals}f}{tail} [{lo*scale:.{decimals}f}, {hi*scale:.{decimals}f}]'


from research_question_explanations import ITEM_NOTES, COMMON_GUIDE, ANSWERS


def item_notes(key):
    return "\n".join(f"- **{kind}:** {text}" for kind, text in ITEM_NOTES[key]) + "\n"


def table(name, title, headers, rows, notes):
    content = f"#### {title}\n\n| " + " | ".join(headers) + " |\n|" + "|".join("---" for _ in headers) + "|\n"
    content += "\n".join("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    content += "\n\n" + item_notes(name) + "\n<details>\n<summary>표본과 분석 방법 · 집필용 세부사항</summary>\n\n" + notes + "\n\n</details>\n"
    (OUT / "tables" / name).write_text(content)
    return content


# RQ1: initial-answer dependence, temporal process, minority direction, item alignment.
n0 = load(ex("claude", "n0"))
n9 = load(ex("claude", "n9"))
fig, (a,b,c,d) = setup("RQ1  How do agent and human deliberation differ?")
rq1table = []
for arm, color, label, marker in [("human",COL["human"],"Human","s"), ("ai_baseline",COL["A-baseline"],"Claude baseline","o"), ("ai_stateful",COL["A-stateful"],"Claude stateful","^")]:
    vals=[]
    for x,k in enumerate(["0","1","2+"]):
        row=get(1,ex("claude","n0"),["rates",arm,k],f"accuracy, k={k}, {label}",n=f'{n0["blocks_by_k"][k]} groups',unit="proportion")
        dot(a,x,0,row,color,marker); vals.append(row["estimate"])
    a.plot(range(3),vals,color=color,label=label)
a.set(title="a  Initial solvers and final accuracy",xlabel="Initially correct members (k)",ylabel="Post-discussion individual accuracy",xticks=range(3),xticklabels=["0","1","2+"],ylim=(0,1.06))
a.yaxis.set_major_formatter(PercentFormatter(1)); a.legend(frameon=False,loc="lower right")
timekeys=["0.00-0.25","0.25-0.50","0.50-0.75","0.75-1.01"]
for arm,label,marker in [("human","Human","s"),("A-baseline","Claude baseline","o"),("A-stateful","Claude stateful","^")]:
    path=["human"] if arm=="human" else ["ai",arm]
    v=n9["human"] if arm=="human" else n9["ai"][arm]
    vals=[]
    for x,t in enumerate(timekeys):
        row=get(1,ex("claude","n9"),path+[f"share_t_{t}"],f"answer changes in quarter {x+1}, {label}",n=f'{v["n_events"]} events / {v["n_groups"]} groups',unit="proportion")
        dot(b,x,0,row,COL[arm],marker); vals.append(row["estimate"])
    b.plot(range(4),vals,color=COL[arm],label=label)
b.set(title="b  When answers change",xlabel="Quarter of discussion (message count)",ylabel="Share of all answer changes",xticks=range(4),xticklabels=["1st","2nd","3rd","4th"],ylim=(0,.95))
b.yaxis.set_major_formatter(PercentFormatter(1));b.legend(frameon=False)
s3=load(ex("claude","s3"))
minor=[]
for i,arm in enumerate(["human","C-reanswer","A-baseline","A-stateful"]):
    path=["human","delib_small_group"] if arm=="human" else ["ai",arm]
    v=s3["human"]["delib_small_group"] if arm=="human" else s3["ai"][arm]
    row=get(1,ex("claude","s3"),path+["share_toward_5-11"],f"outlier movement toward others, {arm}",n=f'{v["n_5-11"]} agent/person-item records',unit="proportion")
    dot(c,0,i,row,COL[arm],horizontal=True);minor.append(row)
c.set(title="c  Initially distant members move toward others",yticks=range(4),yticklabels=["Human","Re-answer only","Claude baseline","Claude stateful"],xlabel="Share moving toward others (initial distance >= 5)",xlim=(.45,1.01))
c.invert_yaxis();c.xaxis.set_major_formatter(PercentFormatter(1))
for i,m in enumerate(MODELS):
    for arm,off,marker in [("A-baseline",-.12,"o"),("A-stateful",.12,"^")]:
        row=get(1,ex(m,"n4"),["indicators","sd_drop","spearman_human_did_vs_ai",arm+" - C-reanswer"],f"human-AI item-response rank correlation, {m}, {arm}",n="30 policy items",unit="Spearman rho")
        dot(d,0,i+off,row,COL[arm],marker,horizontal=True,label=ANAME[arm] if i==0 else None)
d.axvline(0,color="#555555",ls="--",lw=1)
d.set(title="d  Do the same policy items respond?",yticks=range(3),yticklabels=list(SHORT.values()),xlabel="Human-AI rank correlation of SD reduction",xlim=(-.72,.72));d.invert_yaxis();d.legend(frameon=False,loc="lower right")
save(fig,"rq1_process_and_outcomes","a-c: Claude is the primary model; d: Gemini and Mistral are replications. Whiskers: original 95% intervals.\nHuman comparisons are references with different discussion settings. Panel b shows quarters, not first utterances.")

for title,rel,paths,ns,percent in [
    ("Individual accuracy when k = 0",ex("claude","n0"),[["rates",x,"0"] for x in ["human","ai_baseline","ai_stateful"]],"338 initially all-wrong groups",True),
    ("Answer changes in first quarter",ex("claude","n9"),[["human","share_t_0.00-0.25"],["ai","A-baseline","share_t_0.00-0.25"],["ai","A-stateful","share_t_0.00-0.25"]],"Human 466; baseline 470; stateful 466 groups",True),
    ("Changes per participant",ex("claude","n9"),[["human","changes_per_participant"],["ai","A-baseline","changes_per_participant"],["ai","A-stateful","changes_per_participant"]],"Human 1,517; AI 1,525 participants per engine",False),
    ("Wrong-to-correct share of changes",ex("claude","n9"),[["human","share_wrong_to_correct"],["ai","A-baseline","share_wrong_to_correct"],["ai","A-stateful","share_wrong_to_correct"]],"Human 5,288; baseline 1,534; stateful 1,578 events",True),
    ("Question/probing utterances",ex("claude","n10"),[["by_sample","comparison","human_same_groups","probing"],["by_sample","comparison","conditions","A-baseline","probing"],["by_sample","comparison","conditions","A-stateful","probing"]],"68 matched groups; AI coded by GLM",True),
    ("Outlier movement toward others",ex("claude","s3"),[["human","delib_small_group","share_toward_5-11"],["ai","A-baseline","share_toward_5-11"],["ai","A-stateful","share_toward_5-11"]],"Human 2,351; AI 475 person/agent-item records",True),
    ("Democrat movement toward Republicans (points)",ex("claude","e6"),[["human","delib","toward_other_D"],["ai","A-baseline","toward_other_D"],["ai","A-stateful","toward_other_D"]],"Human 40 groups; AI 398 mixed-party blocks",False),
    ("Republican movement toward Democrats (points)",ex("claude","e6"),[["human","delib","toward_other_R"],["ai","A-baseline","toward_other_R"],["ai","A-stateful","toward_other_R"]],"Human 40 groups; AI 398 mixed-party blocks",False),
]:
    vals=[get(1,rel,path,title,n=ns) for path in paths]
    rq1table.append([title]+[fmt(v,1 if percent else 2,percent) for v in vals]+[ns])
t1=table("rq1_core_comparisons.md","Table RQ1. Core human-agent comparisons (estimate [95% interval])",["Measure","Human reference","Claude baseline","Claude stateful","Sample / unit"],rq1table,
    "All rows are exploratory summaries; the initial-solver contrast also has a separate registered H1 test. "
    "Human uncertainty resamples groups; AI uncertainty resamples groups/blocks as recorded in the source JSON. "
    "Party movement is in 0-10 scale points, not a probability. Probing is an LLM-coded descriptive estimate; human validation is pending.")
crossrows=[]
for pair in ["claude vs gemini","claude vs mistral","gemini vs mistral"]:
    vals=[get(1,"exploratory/s2_cross_model.json",[key,pair],f"cross-model {key} {pair}",n="30 items",unit="Spearman rho") for key in ["D","post_A-baseline","post_A-stateful"]]
    crossrows.append([pair]+[f"{v['estimate']:.3f}" for v in vals]+["30 policy items; CI not estimated"])
crosscontent=table("rq1_replication_and_references.md","Table RQ1b. Cross-model policy-position similarity",["Model pair","Default D: rho","Post baseline: rho","Post stateful: rho","Sample / uncertainty"],crossrows,
    "Exploratory correlations of item means. Higher rank correlation does not establish equality of positions, independence of models, or accuracy.")
refrows=[]
for coder in ['evidence_glm','evidence_sonnet']:
    for arm in ['A-baseline','A-stateful']:
        vals=[get(1,ex('claude','l3'),['coders',coder,'by_label',arm,'key',key],f"{coder} {arm} {key}",unit="proportion") for key in ['references','peer_given_ref']]
        refrows.append([coder,ANAME[arm],fmt(vals[0],1,True),fmt(vals[1],1,True),str(vals[0]['n'])])
crosscontent+='\n'+table("rq1_argument_references.md","Table RQ1c. Post-discussion reasons reference discussion arguments",["Coder","Claude engine","Any argument reference","Peer reference given a reference","Coded reasons"],refrows,
    "Exploratory LLM coding, estimates [95% block-bootstrap interval]. A 100% observed rate is a ceiling in this coded sample, not proof of perfect reasoning or a causal effect of peers. Human validation is pending.")
t1+='\n'+crosscontent

# RQ2: controls, default/group association, argument quality, direction split.
fig,(a,b,c,d)=setup("RQ2  What does discussion add, and what moves agents?")
for i,arm in enumerate(ARMS):
    row=get(2,ex("claude","n2b"),["ai","mean_abs_move",arm],f"mean absolute change, {arm}",n="416 blocks x 5 agents; 30 items",unit="0-10 score points")
    dot(a,i,0,row,COL[arm])
a.set(title="a  Position change with and without discussion",xticks=range(4),xticklabels=[ANAME[x] for x in ARMS],ylabel="Mean absolute position change (0-10 points)",ylim=(0,2.2))
for i,coef in enumerate(["beta","gamma"]):
    for arm,off,mk in [("A-baseline",-.10,"o"),("A-stateful",.10,"^")]:
        row=get(2,ex("claude","n1"),["models",arm,coef],f"{coef}, {arm}",n="2,080 agent-item observations; 416 blocks",unit="coefficient",analysis="registered H2c baseline / exploratory stateful refit")
        dot(b,0,i+off,row,COL[arm],mk,True,label=ANAME[arm] if i==0 else None)
b.set(title="b  Associations with default and group",yticks=[0,1],yticklabels=["Model default (beta)","Group prior mean (gamma)"],xlabel="Change per point of initial distance",xlim=(0,.65));b.invert_yaxis();b.legend(frameon=False,loc="lower right")
for i,m in enumerate(MODELS):
    for code,off,mk,lab in [("H3a",-.12,"o","Argument quality"),("H3b",.12,"s","Social support")]:
        row=get(2,reg(m),["hypotheses",code],f"{m}, {code}",n="384 runs; 32 argument sets",analysis="registered",unit="0-100 score points")
        dot(c,0,i+off,row,MCOL[m],mk,True)
c.axvline(0,color="#555555",ls="--",lw=1)
c.set(title="c  Quality (circle) and support (square)",yticks=range(3),yticklabels=list(SHORT.values()),xlabel="Baseline-engine contrast (0-100 points)",xlim=(-3,6.1));c.invert_yaxis()
S4_SOURCE=str(ROOT / 'docs/research/robustness/source-data/s4-display.json')
splits=[("aligned","Aligned with default"),("opposing","Opposing default")]
for i,(split,lab) in enumerate(splits):
    for key,off,mk,col in [("q",-.12,"o",COL["A-baseline"]),("sup",.12,"s",COL["A-stateful"])]:
        row=get(2,S4_SOURCE,["by_split",split,"model_delta_c",key],f"{split}, {key}",n="15 sets / 360 runs",unit="0-100 score points")
        dot(d,0,i+off,row,col,mk,True,label="Quality" if key=="q" and i==0 else "Support" if i==0 else None)
d.axvline(0,color="#555555",ls="--",lw=1)
d.set(title="d  Argument direction relative to default",yticks=range(2),yticklabels=[x[1] for x in splits],xlabel="Re-answer-adjusted contrast (0-100 points)",xlim=(-3,5.5));d.invert_yaxis();d.legend(frameon=False,loc="lower right")
save(fig,"rq2_controls_and_drivers","a-b,d: Claude; c: primary model and two replications. Whiskers: original 95% intervals (bootstrap or model CI).\nA mean shift is not the same as within-group agreement. Interval overlap with zero alone does not establish equivalence.")
rq2rows=[]
for arm in ARMS:
    move=get(2,ex("claude","n2b"),["ai","mean_abs_move",arm],f"table movement {arm}",n="416 blocks / 2,080 agent-items",unit="points")
    agreement=get(2,ex("claude","n2b"),["ai","consensus_sd",arm],f"table agreement {arm}",n="416 blocks / 30 items",unit="proportion")
    corr=get(2,ex("claude","n12"),[f"1-B {arm}","corr_toward_D"],f"table default association {arm}",n="2,080 agent-items",unit="Pearson r")
    rq2rows.append([ANAME[arm],fmt(move),fmt(agreement,1,True),fmt(corr),"416 blocks; 30 items"])
contrast=get(2,ex("claude","n2b"),["ai","consensus_sd","A-baseline - B-materials"],"paired baseline-minus-materials agreement contrast",n="416 paired blocks / 30 items",unit="percentage points",scale=100)
t2=table("rq2_controls_and_drivers.md","Table RQ2. Change, agreement, and default association (Claude)",["Condition","Absolute change (0-10 points)","Agreement: post SD <= 1","Correlation with D - pre","Sample"],rq2rows,
    "Values are estimates [95% intervals]. Movement and agreement intervals: item > block bootstrap; correlation intervals: block bootstrap. "
    "All are exploratory summaries. Agreement is a group-item outcome; default association is an agent-item relationship. "
    f"Paired baseline-minus-materials agreement contrast: {fmt(contrast,1)} percentage points (95% bootstrap interval).")
rq2effectrows=[]
for m in MODELS:
    dat=load(reg(m))
    for code,lab in [("H3a","Argument quality"),("H3b","Social support")]:
        rec=get(2,reg(m),["hypotheses",code],f"table {m} {code}",analysis="registered",n="384 runs; 32 sets")
        p=dat['families']['reference_holm'][code]['p_holm']
        rq2effectrows.append([SHORT[m],lab,fmt(rec),f"{p:.3g}","Registered; baseline engine"])
for split,lab in splits:
    for key,klabel in [("q","Quality"),("sup","Support")]:
        rec=get(2,S4_SOURCE,["by_split",split,"model_delta_c",key],f"table split {split} {key}",n="15 sets / 360 runs")
        rq2effectrows.append(["Claude",f"{klabel}: {lab}",fmt(rec),"Not multiplicity-adjusted", "Exploratory; both engines"])
rec=get(2,S4_SOURCE,['joint','sup:aligned'],'Direct aligned-minus-opposing support interaction',n='30 sets / 720 runs',unit='0-100 score points')
rq2effectrows.append(['Claude','Support effect: aligned minus opposing',fmt(rec),f"{load(S4_SOURCE)['joint']['sup:aligned']['p_holm']:.3g}",'Post-hoc interaction; Holm across 4 direction terms'])
t2+= "\n"+table("rq2_quality_and_support.md","Table RQ2b. Argument quality and social support (0-100 points)",["Model","Contrast","Estimate [95% CI]","Holm P / status","Analysis"],rq2effectrows,
    "H3 estimates are baseline-engine contrasts. Updated S4 excludes two neutral-default sets (D=50), retaining 15 aligned and 15 strictly opposing sets. The original 17-set nonaligned fit is preserved in the raw exploratory JSON. "
    "The direct interaction adds a topic intercept to the full quality × support × engine × alignment model; four direction-related interaction tests are Holm-adjusted. Aligned and joint fits are singular; these remain post-hoc sensitivity evidence.")
resolve=load(ex("claude","n12"))["1-A B-resolve"]["seeded_wrong_stay_wrong"]
extra2=f"**보충:** 토론 없는 논리 과제 재응답에서 초기 오답의 교정 비율은 {1-resolve['estimate']:.1%} [{1-resolve['ci'][1]:.1%}, {1-resolve['ci'][0]:.1%}]다. 이는 저장된 ‘오답 유지’ 추정량을 1에서 뺀 값이며, 토론의 추가 기여와 구분한다. 정책 재응답 변화와 기본 입장까지 거리의 상관은 위 표에 제시했다.\n"
ROWS[2].append({"metric":"Correction of seeded wrong answers without discussion", "estimate":1-resolve['estimate'],"ci":[1-resolve['ci'][1],1-resolve['ci'][0]],"source":str((RES/ex("claude","n12")).relative_to(ROOT)),"json_path":["1-A B-resolve","seeded_wrong_stay_wrong"],"transform":"1 - estimate; [1 - upper, 1 - lower]","n":"471 groups; 1,525 agents, restricted to initially wrong agents for rate","analysis":"exploratory"})

# RQ3: observed behaviours, accuracy, convergence, human distance.
fig,(a,b,c,d)=setup("RQ3  Do human-inspired rules change behaviour and outcomes?")
dev=load(ex("claude","n6b"))
device_rows=[]
for i,(key,label) in enumerate([("respond_challenge","Reply to a claim"),("mediate","Describe disagreement"),("devils_advocate","Object to shared view"),("switched","State position change")]):
    item=dev['coders']['devices_large']['by_device'][key]['device_item']
    for coder,control,off,col,mk in [("devices_large",True,-.13,COL['human'],"o"),("devices_large",False,.08,COL['A-stateful'],"o"),("devices_small",False,.22,"#222222","D")]:
        arm="control" if control else key
        v=dev['coders'][coder]['by_device'][arm]
        rate=v['items'][item]['yes']
        row={"metric":f"{coder}, {arm}, {item}","estimate":rate,"ci":None,"n":v['n'],"unit":"proportion","display_scale":1,"analysis":"exploratory LLM coding", "source":str((RES/ex("claude","n6b")).relative_to(ROOT)),"json_path":["coders",coder,"by_device",arm,"items",item,"yes"]}
        ROWS[3].append(row);dot(a,0,i+off,row,col,mk,True,label=("No instruction (coder 1)" if control else "Instructed (coder 1)" if coder=='devices_large' else "Instructed (coder 2)") if i==0 else None)
    primary=dev['coders']['devices_large']['by_device'][key]
    control=dev['coders']['devices_large']['by_device']['control']
    ROWS[3].append({"metric":f"instruction-following, {key}","estimate":primary['instruction_followed']['yes'],"ci":None,"n":primary['n'],"unit":"proportion","analysis":"exploratory LLM coding","source":str((RES/ex("claude","n6b")).relative_to(ROOT)),"json_path":["coders","devices_large","by_device",key,"instruction_followed","yes"]})
    device_rows.append([label,f"{control['items'][item]['yes']:.1%} (n={control['n']})",f"{primary['items'][item]['yes']:.1%} (n={primary['n']})",f"{primary['instruction_followed']['yes']:.1%}"])
a.set(title="a  Instructed behaviours appear in text",yticks=range(4),yticklabels=["Reply to\na claim","Describe\ndisagreement","Object to\nshared view","State position\nchange"],xlabel="Observed yes rate (not instruction-following score)",xlim=(0,1.05));a.invert_yaxis();a.xaxis.set_major_formatter(PercentFormatter(1));a.legend(frameon=False,loc="lower left",bbox_to_anchor=(0,-.36),ncol=2,fontsize=8)
for ax,code,title,xlabel,scale in [(b,"E1","b  Accuracy change on the logic task","Stateful - baseline (percentage points)",100),(c,"E3","c  Additional within-group convergence","Extra SD reduction (0-10 score points)",1),(d,"H5","d  Distance from human opinion","Change in human distance (negative = closer)",1)]:
    for i,m in enumerate(MODELS):
        v=load(reg(m))['hypotheses'][code]
        n=f"{v['n']} observations" if 'n' in v else "22 locked policy items"
        row=get(3,reg(m),['hypotheses',code],f"{m} {code}",n=n,unit=xlabel,analysis="registered primary" if m=='claude' else "registered replication",scale=scale)
        dot(ax,0,i,row,MCOL[m],"o" if m=='claude' else "s",True)
    ax.axvline(0,color="#555555",ls="--",lw=1);ax.set(title=title,xlabel=xlabel,yticks=range(3),yticklabels=list(SHORT.values()));ax.invert_yaxis()
save(fig,"rq3_rules_and_consequences","a: Claude utterances; two independent LLM coders. Descriptive rates, no intervals estimated; human validation pending.\nb-d: registered estimates with original 95% CIs; Claude primary, other models replications. Effects have different units.")
rq3rows=[]
for code,lab,unit in [("E1","Logic accuracy","percentage points"),("E2","Absolute policy movement","0-10 points"),("E3","Policy SD reduction","0-10 points"),("E4","Quality x engine","0-100 points"),("E5","Support x engine","0-100 points"),("H5","Distance to human opinion","distance units")]:
    vals=[]
    for m in MODELS:
        rec=get(3,reg(m),['hypotheses',code],f"table {m} {code}",analysis="registered",unit=unit,scale=100 if code=='E1' else 1)
        vals.append(fmt(rec,3 if code=='H5' else 2))
    v=load(reg('claude'))['hypotheses'][code]
    n={"E1":"942 runs; 471 matched groups","E2":"416 paired blocks; 30 items","E3":"416 paired blocks; 30 items","E4":"768 runs; 32 argument sets","E5":"768 runs; 32 argument sets","H5":"22 locked items; 1,760 agent-items per engine"}[code]
    rq3rows.append([code+": "+lab,unit]+vals+[n])
t3=table("rq3_registered_effects.md","Table RQ3. Registered engine contrasts (stateful - baseline)",["Outcome","Units","Claude primary","Gemini replication","Mistral replication","Claude sample"],rq3rows,
    "Estimates [original 95% CI]. E4/E5 are interaction contrasts, not main effects. E1/E2/E3/E4/E5 use model-based intervals; "
    "H5 uses its registered bootstrap and the 22-item locked set. Intervals are not multiplicity-adjusted; the registered tests use their original families. "
    "E1 uses one baseline replicate, unlike exploratory summaries pooling three. Mistral E2/E3 have 415 blocks after an exclusion; others have 416.")
t3+='\n'+table("rq3_device_validation.md","Table RQ3b. Observed behaviour and instruction-following are distinct",["Behaviour","No instruction: observed yes","Instructed: observed yes","Instructed: instruction-following yes"],device_rows,
    "Claude utterances; primary coder Mistral Large. Original design sampled 300 per stratum; valid n differs after coder failures. "
    "The same control stratum is reused across behaviours. These are descriptive coded rates with no estimated intervals, not causal effects of individual devices.")
more3=[]
for arm,lab in [('base','Baseline'),('state','Stateful')]:
    rec=get(3,ex('claude','n2a'),['rates',arm,'unanimous_wrong','all'],f"wrong unanimity {lab}",n="471 groups; baseline averages 3 replicates")
    more3.append(f"{lab}: {fmt(rec,1,True)}")
extra3="**추가 관찰 · 모두 같은 오답을 낸 집단:** "+"; ".join(more3)+". 일반 토론 3회 평균과 규칙 토론 1회를 비교한 집단별 오답 만장일치 비율이다. 이는 첫 일반 토론 반복만 쓰는 등록 E1과 비교 범위가 다르다.\n\n"
for arm in ['baseline','stateful']:
    rec=get(3,ex('claude','n7'),['participants',arm,'corr_xfinal_post'],f"engine-survey correlation {arm}",n="2,080 agent-items; 416 blocks")
    extra3+=f"**엔진 상태–별도 사후 설문 상관({arm}):** {fmt(rec)}. 토론 중 엔진이 기록한 최종 입장과, 토론 뒤 별도로 물어본 답이 얼마나 함께 움직이는지를 뜻한다. 1에 가까운 상관은 엔진이 기록한 입장이 높은 에이전트일수록 사후 설문 점수도 높은 경향이 강하다는 의미다. 별도 호출이지만 같은 대화의 영향을 받은 응답이다.\n\n"


def imageblock(stem, alt):
    folder=OUT/'figures'
    return f"![{alt}]({folder/stem}.png)\n\n" + item_notes(stem) + f"\n[Vector PDF]({folder/stem}.pdf) · [Plotted values and source records]({OUT/'source-data'/(stem[:3]+'_values.json')})\n\n"


GRAPH_METHODS = {
    1: "a는 471개 원집단을 초기 정답자 수로 나눈다(k=0: 338, k=1: 112, k≥2: 21). b의 사분기는 실제 시간이 아니라 발언 순서로 나눈다. c는 다른 구성원의 토론 전 평균이 있는 방향으로 점수가 바뀌었는지를 센다. c의 인간은 실제 소집단, AI는 5명 집단이며, 같은 사람·에이전트의 여러 문항 응답을 포함한다. d는 정책 30문항의 비교다. 구간은 a·b 집단, c AI 블록/인간 소집단, d 기존 인간·AI 재표집 결과에서 가져왔다. AI 카드 선택 추출이 가능한 Claude 발언은 68.1%다. 문항별 재표집 구간에는 페르소나의 교차 의존이 반영되지 않는다.",
    2: "a는 416블록·30문항이며 문항→블록 재표집 구간을 쓴다. b는 2,080개 에이전트×문항 관측의 회귀계수이며 모형 구간을 쓴다. c는 모델별 32세트·384실행의 등록 분석이다. d는 2026-10-20 중립 두 세트를 제외한 같은 방향15·반대 방향15세트(각360실행)의 재분석이다. 같은 방향 및 직접 상호작용 모형은 singular fit이다. 직접 방향 차이는 아래 표와 강건성 보고서에 제시한다. b의 상태 기반 재적합과 d는 탐색이다.",
    3: "a의 첫 평가 모델은 Mistral Large, 둘째는 Mistral Small이다. 논리·정책 과제에서 지시 종류별로 뽑은 표본이므로 전체 토론 발언 발생률과 구분한다. 평가 성공 발언 수는 첫 모델 288~300개/지시 종류, 무지시 291개이며, 둘째는 종류별 300개다. a에는 새 구간을 추정하지 않았다. 사람 검증은 아직 진행 전이다. b는 등록 E1의 한 기준선 반복과 상태 기반을 비교하고, c는 E3의 30문항(Claude·Gemini 416블록, Mistral 415블록)을 비교한다. d는 H5의 잠금 22문항이다. b·c는 기존 모형 구간, d는 등록 재표집 구간이며 모두 95%다.",
}
FIGURE_SPECS = {
    1: ('rq1_process_and_outcomes', 'RQ1: 사람과 AI의 답 찾기·의견 변화 과정'),
    2: ('rq2_controls_and_drivers', 'RQ2: 재응답·토론·기본 입장·논거·지지자 수'),
    3: ('rq3_rules_and_consequences', 'RQ3: 규칙 도입에 따른 발언·정답률·의견 접근·인간 거리 변화'),
}
TABLE_LINKS = {
    1: [('인간 비교 표', 'rq1_core_comparisons.md'), ('모델 간 유사성 표', 'rq1_replication_and_references.md'), ('논거 참조 표', 'rq1_argument_references.md')],
    2: [('통제 조건 표', 'rq2_controls_and_drivers.md'), ('논증 질·지지 표', 'rq2_quality_and_support.md')],
    3: [('등록 효과 표', 'rq3_registered_effects.md'), ('장치 수행 표', 'rq3_device_validation.md')],
}
blocks = {}
for rq, table_text in [(1, t1), (2, t2), (3, t3)]:
    stem, alt = FIGURE_SPECS[rq]
    links = ' · '.join(f'[{label}]({OUT / "tables" / filename})' for label, filename in TABLE_LINKS[rq])
    methods = f'<details>\n<summary>표본과 분석 방법 · 집필용 세부사항</summary>\n\n{GRAPH_METHODS[rq]}\n\n</details>\n\n'
    blocks[rq] = imageblock(stem, alt) + methods + table_text + '\n' + links + '\n\n'
    if rq == 2:
        blocks[rq] += extra2 + '\n'
    if rq == 3:
        blocks[rq] += extra3
    blocks[rq] += '**이 연구질문에 대한 답:** ' + ANSWERS[rq] + '\n'
    party_evidence = ROOT/'docs/research/party-dispersion/rq-evidence.md'
    if rq == 1 and party_evidence.exists():
        blocks[rq] += '\n' + party_evidence.read_text()
doc=ROOT/'docs/research/ResearchQuestions.md'
text=doc.read_text()
guide = "<!-- BEGIN READING GUIDE -->\n\n" + COMMON_GUIDE + "<!-- END READING GUIDE -->\n\n"
pattern = r'<!-- BEGIN READING GUIDE -->.*?<!-- END READING GUIDE -->\n*'
if re.search(pattern, text, flags=re.S):
    text = re.sub(pattern, lambda _: guide, text, flags=re.S)
else:
    text = text.replace('## 세부 연구질문', guide + '## 세부 연구질문', 1)
for rq,next_heading in [(1,'### RQ2.'),(2,'### RQ3.'),(3,'## 세 질문을 종합해 도출할 함의')]:
    block=f"<!-- BEGIN RQ{rq} EVIDENCE -->\n\n"+blocks[rq]+f"\n<!-- END RQ{rq} EVIDENCE -->\n\n"
    pattern=rf'<!-- BEGIN RQ{rq} EVIDENCE -->.*?<!-- END RQ{rq} EVIDENCE -->\n*'
    if re.search(pattern,text,flags=re.S):text=re.sub(pattern,lambda _:block,text,flags=re.S)
    else:
        index=text.index(next_heading);text=text[:index]+block+text[index:]
doc.write_text(text)
for rq,rows in ROWS.items():
    (OUT/'source-data'/f'rq{rq}_values.json').write_text(json.dumps({"generated_for":"ResearchQuestions.md","checked_date_kst":"2026-10-20","note":"Original estimates, not a statistical reanalysis. Rows may repeat a value displayed in both a figure and table.","records":rows},ensure_ascii=False,indent=2)+'\n')
(OUT/'source-data/input-snapshot.json').write_text(json.dumps(CACHE,ensure_ascii=False,indent=2)+'\n')
manifest=[{"path":str((RES/rel).relative_to(ROOT)),"sha256":hashlib.sha256((RES/rel).read_bytes()).hexdigest()} for rel in sorted(CACHE)]
(OUT/'source-data/input-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(OUT/'figures/observations-and-interpretations.md').write_text(
    "# 그림별 핵심 관찰과 해석\n\n" + COMMON_GUIDE + "\n".join(
        f"## {key}\n\n" + item_notes(key)
        for key in ["rq1_process_and_outcomes", "rq2_controls_and_drivers", "rq3_rules_and_consequences"]
    )
)
readme='''# 연구질문별 그림·표

수치 원자료: 기존 등록·탐색 결과 및 2026-10-20 S4 강건성 재분석. 표시 검토: 2026-10-20. 이 표시 도구는 저장된 추정값과 구간을 읽으며 자체적으로 모형을 적합하지 않는다. S4 중립 제외와 직접 상호작용 계산은 별도 강건성 분석에 기록했다.

- `figures/`: 질문별 4패널 PNG와 편집 가능한 벡터 PDF, 총 3개 그림. `observations-and-interpretations.md`에 그림별 관찰·해석 불릿도 보관한다.
- `tables/`: 본문에 삽입한 영문 표의 별도 Markdown 원본, 총 7개 표. 각 표 바로 밑에 한국어 관찰·해석 불릿을 포함한다.
- `source-data/rq*_values.json`: 실제 표시 수치·구간·단위·분석 구분·표본·원본 JSON 경로. 그림과 표에 공통인 값은 중복 기록될 수 있다.
- `source-data/input-snapshot.json`: 사용한 집계 JSON 입력 보관본. 개인정보가 있는 원시 전사는 포함하지 않는다.
- `source-data/input-manifest.json`: 원본 집계 파일의 SHA-256 기록.

재생성: 저장소 루트에서 `MPLCONFIGDIR=/private/tmp/rq-matplotlib .venv/bin/python scripts/build_research_question_artifacts.py`. `ResearchQuestions.md`의 표시 블록도 갱신한다. 입력 원본은 저장소의 기존 `data/study1/results/`에 있어야 한다. 표시 블록 수동 수정은 재생성 시 덮어쓴다. 쉬운 읽기 설명은 `scripts/research_question_explanations.py`에서 관리하며 본문·표·그림별 설명 문서에 함께 반영한다.

## 해석·재현 주의

Claude가 주 모델이고 Gemini·Mistral은 재현이다. 등록 대비와 탐색 요약을 혼합한 새 검정 가족을 만들지 않는다. 그림은 기존 95% 구간을 표시하며, 등록 검정의 다중비교 보정과 구간은 별개다. RQ2b 표에 H3의 원래 Holm 보정 P값을 함께 보였다. 특이 적합과 코더 실패·미완료 사람 검증을 문서에 표시했다.

RQ1의 k=0 정확도는 N0의 전체 개인 정답률(Claude 기준선 95.9%)이다. N9의 ‘초기 오답자가 최종 정답인 비율’(약 97%)과 계산 대상이 다르다. 시간 패널은 토론 첫 사분기를 뜻하며 ‘첫 발언’으로 바꾸어 읽지 않는다. 정당 상대 방향 이동은 점수 이동량이며 비율이 아니다. H5 Gemini 재현에서는 인간 거리가 감소하므로 전 모델 무효과로 일반화하지 않는다.

논문 최종 Figure 번호와 배치는 아직 확정하지 않았다. 이 묶음은 연구질문에 대한 근거를 확인하는 집필용 자료다.
'''
(OUT/'README.md').write_text(readme)
print(f"Created 3 figures (PNG/PDF), 7 tables, source records; updated {doc}")
