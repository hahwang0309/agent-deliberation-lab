"""Calculate and report post-hoc within-party policy dispersion; no model/API calls."""
import os
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/party-dispersion-matplotlib")

from pathlib import Path
import hashlib
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis import humans
from src.analysis.party_dispersion import ARMS, METRICS, analyze_ai, analyze_human

OUT = ROOT / "docs/research/party-dispersion"
for folder in ["figures", "tables", "source-data"]:
    (OUT/folder).mkdir(parents=True, exist_ok=True)
NBOOT, SEED = 2000, 20261019
items_path = ROOT/"data/study1/results/exploratory/human/n3_human_items.csv"
items = pd.read_csv(items_path)["item"].tolist()
raw_path = ROOT/"data/raw/a1r/dataset.tab"
inputs = [items_path, raw_path]
results, item_records = {}, []
for i, model in enumerate(["claude", "gemini", "mistral"]):
    path = ROOT/f"data/study1/results/exploratory/{model}/a1r_agents.csv"
    inputs.append(path)
    result, records = analyze_ai(pd.read_csv(path, dtype={"party": str}), items, NBOOT, SEED+i)
    results[model] = result
    item_records.extend({"model": model, **r} for r in records)
    print(model, {k:v for k,v in result["sample"].items() if k!="by_item"}, flush=True)
delib = humans.a1r_delegates(str(raw_path), items, "1")
control = humans.a1r_delegates(str(raw_path), items, "0")
result, records = analyze_human(delib, control, items, NBOOT, SEED+3)
results["human"] = result
item_records.extend({"model": "human", **r} for r in records)

analysis = {
    "date_kst": "2026-10-19", "status": "Post-hoc exploratory analysis; specified after inspecting preliminary point estimates",
    "target": "Equal-weight mean over the same fixed 30 items; within each item pool each party across discussion groups",
    "party_codes": {"1": "Democratic", "2": "Republican"},
    "exclusions": "Independents and other party codes excluded; pre/post paired; AI agent records complete in all four conditions",
    "sd_definition": "population SD ddof=0; post minus pre; positive is more dispersion",
    "party_gap_definition": "absolute difference of item-level Democratic and Republican means; post minus pre; negative is closer",
    "variance_identity": "total variance = weighted within-party variance + p_D * p_R * (mean_D - mean_R)^2",
    "confidence_intervals": "2000 percentile cluster bootstrap draws; items held fixed; no new P values or multiple-testing claims",
    "ai_dependency": "Same whole blocks resampled across all conditions within item; cross-block/cross-item persona dependence not preserved",
    "human_dependency": "All records of a discussion group resampled together; control all records of a participant resampled together",
    "seed": SEED, "results": results,
}
(OUT/"source-data/results.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2)+"\n")
(OUT/"source-data/item-estimates.json").write_text(json.dumps(item_records, ensure_ascii=False, indent=2)+"\n")
(OUT/"source-data/input-manifest.json").write_text(json.dumps([
    {"path":str(p.relative_to(ROOT)), "sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs
], indent=2)+"\n")

def f(record):
    lo, hi = record["ci"]
    return f'{record["estimate"]:+.3f} [{lo:+.3f}, {hi:+.3f}]'


def mdtable(title, headers, rows):
    text = f"### {title}\n\n| " + " | ".join(headers) + " |\n|" + "|".join("---" for _ in headers) + "|\n"
    return text + "\n".join("| "+" | ".join(row)+" |" for row in rows)+"\n\n"


names = {"claude":"Claude", "gemini":"Gemini", "mistral":"Mistral", "human":"Human"}
armnames = {"C-reanswer":"Re-answer", "B-materials":"Materials only", "A-baseline":"Baseline discussion", "A-stateful":"Stateful discussion", "control":"Control", "deliberation":"Deliberation event"}
contrast_keys = ["A-baseline - B-materials", "A-baseline - C-reanswer", "A-stateful - A-baseline"]
contrast_names = ["Discussion minus materials only", "Discussion minus re-answer", "Stateful minus baseline discussion"]
tables = []
for key, label in zip(contrast_keys, contrast_names):
    rows=[]
    for model in ["claude","gemini","mistral"]:
        vals=results[model]["contrasts"][key]
        rows.append([names[model]]+[f(vals[m]) for m in METRICS[:3]])
    if key == contrast_keys[0]:
        vals=results['human']['contrasts']['deliberation - control']
        rows.append(['Human event minus control']+[f(vals[m]) for m in METRICS[:3]])
    tables.append(mdtable(label, ['Model / comparison','Within Democrats: SD change','Within Republicans: SD change','Between parties: gap change'],rows))
contrast_table="".join(tables)
(OUT/'tables/contrasts.md').write_text(contrast_table)
levelrows=[]
for model in ['human','claude','gemini','mistral']:
    for arm, vals in results[model]['levels'].items():
        row=[names[model],armnames[arm]]
        for metric in METRICS[:3]:
            v=vals[metric]
            row.append(f"{v['pre']['estimate']:.3f} → {v['post']['estimate']:.3f}")
        levelrows.append(row)
level_table=mdtable('Pre → post: item-averaged levels', ['Model','Condition','Democratic SD','Republican SD','Party mean gap'],levelrows)
(OUT/'tables/pre-post-levels.md').write_text(level_table)

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
def plot(key, filename, title, human=False):
    ms=['claude','gemini','mistral']+(['human'] if human else [])
    fig, axes=plt.subplots(1,3,figsize=(13.5,4.9))
    fig.subplots_adjust(left=.14,right=.98,top=.77,bottom=.25,wspace=.37)
    fig.suptitle(title,x=.14,ha='left',y=.95,fontsize=15,fontweight='bold')
    for ax,metric,color,heading in zip(axes,METRICS[:3],['#2776bd','#d85a24','#8064a2'],['a  Spread within Democrats','b  Spread within Republicans','c  Gap between party means']):
        for y,model in enumerate(ms):
            k='deliberation - control' if model=='human' else key
            v=results[model]['contrasts'][k][metric];est=v['estimate'];lo,hi=v['ci']
            ax.errorbar(est,y,xerr=[[est-lo],[hi-est]],fmt='o' if model=='claude' else 's',color=color,capsize=3,markersize=6)
        ax.axvline(0,color='#555555',ls='--',lw=1)
        ax.set_yticks(range(len(ms)));ax.set_yticklabels([names[m]+(' (event-control)' if m=='human' else '') for m in ms])
        ax.set_ylim(len(ms)-.6,-.4);ax.set_title(heading,fontsize=11,pad=12)
        ax.set_xlabel('Difference in SD change\npositive = more within-party spread' if metric!='party_gap' else 'Difference in gap change\nnegative = closer party means',fontsize=9)
        ax.grid(axis='x',alpha=.15)
    fig.text(.14,.10,'Unit: 0-10 policy-score points. Points: estimates; whiskers: 95% cluster-bootstrap intervals.\nEach party is pooled across discussions within each item; equal average over 30 fixed items.\nClaude primary; Gemini/Mistral replications. Human contrast covers the full deliberation event.',fontsize=9,va='top')
    for ext in ['png','pdf']:fig.savefig(OUT/'figures'/f'{filename}.{ext}',dpi=220,facecolor='white')
    plt.close(fig)
plot(contrast_keys[0],'discussion_effect','Discussion: party means and within-party opinion spread',True)
plot(contrast_keys[2],'rule_effect','Adding rules: party means and within-party opinion spread')

def img(stem,label):
    return f'![{label}]({OUT/"figures"/(stem+".png")})\n\n[Vector PDF]({OUT/"figures"/(stem+".pdf")})\n\n'

main=results['claude']['contrasts'][contrast_keys[0]]
rule=results['claude']['contrasts'][contrast_keys[2]]
claude_levels=results['claude']['levels']
core=f'''## 핵심 결과: Claude

- **토론 전후:** 기준선 토론에서 민주당 내부 SD는 {claude_levels['A-baseline']['sd_dem']['pre']['estimate']:.2f}→{claude_levels['A-baseline']['sd_dem']['post']['estimate']:.2f}, 공화당 내부 SD는 {claude_levels['A-baseline']['sd_rep']['pre']['estimate']:.2f}→{claude_levels['A-baseline']['sd_rep']['post']['estimate']:.2f}로 줄었다. 양당 평균의 간격도 {claude_levels['A-baseline']['party_gap']['pre']['estimate']:.2f}→{claude_levels['A-baseline']['party_gap']['post']['estimate']:.2f}로 줄었다.
- **자료만 읽은 조건과 비교:** 토론 조건의 민주당 내부 SD는 {f(main['sd_dem'])}점, 공화당 내부 SD는 {f(main['sd_rep'])}점 더 크다. 양당 평균 간격 변화의 조건 차이는 {f(main['party_gap'])}점이다. 즉 토론 조건의 양당 간격이 약 {abs(main['party_gap']['estimate']):.2f}점 더 작다.
- **해석:** Claude에서 자료를 읽은 뒤 토론까지 하면, 자료만 읽을 때보다 양당의 평균 입장은 가까워지면서 각 정당 안의 의견은 더 넓게 분포한다. 두 조건 모두 처음보다 당내 의견 차이는 줄지만, 토론 조건은 그 다양성을 더 많이 남긴다.
- **규칙의 추가 영향:** 기준선 토론에 규칙을 넣으면 민주당 SD 차이는 {f(rule['sd_dem'])}, 공화당 SD 차이는 {f(rule['sd_rep'])}, 양당 간격 차이는 {f(rule['party_gap'])}이다. 양당 평균 접근과 정당 내부 의견 변화는 따로 살펴야 한다.

'''
reading='''## 지표를 읽는 법

- **정당 내부 SD:** 같은 문항에 답한 민주당끼리, 공화당끼리 점수가 얼마나 다른지다. SD=0은 모두 같은 점수이고 클수록 서로 다른 의견이 많다. 서로 다른 토론 소집단에 속한 같은 정당의 응답도 모아서 계산했다.
- **양당 간격:** 같은 문항의 민주당 평균 점수와 공화당 평균 점수의 절댓값 차이다. 예를 들어 민주당 3점·공화당 7점이면 간격은 4점이다.
- **전후 변화:** 나중 값−처음 값이다. 당내 SD의 음수는 의견이 모였다는 뜻이고, 양당 간격의 음수는 두 정당 평균이 가까워졌다는 뜻이다.
- **조건 차이:** 각 조건의 전후 변화끼리 뺀다. AI의 ‘토론−자료만’은 같은 자료를 읽은 상태에서 토론이 추가된 차이를 본다. ‘상태 기반−기준선’은 이미 토론하는 상황에서 규칙을 추가한 차이다.
- **인간 비교:** 숙의 행사 참여군의 전후 변화에서 비참여 통제군의 전후 변화를 뺀다. 이는 자료·전문가 패널 등을 포함한 행사 전체의 변화다.
- **계산 범위:** 30개 정책 문항마다 계산한 뒤 문항을 똑같이 가중해 평균했다. 무당파·기타 응답은 이번 양당 비교에서 제외했다. 앞의 토론 소집단별 양당 격차와 달리, 이번 간격은 문항별로 같은 정당의 응답을 모두 모은 평균 사이의 간격이다.

'''
figure_reading='''- **세로축:** Claude·Gemini·Mistral과 인간 비교다.
- **a·b 가로축:** 정당 내부 SD 변화의 조건 차이다. 오른쪽 양수는 비교 조건보다 당내 의견이 더 넓고, 왼쪽 음수는 더 모였다는 뜻이다.
- **c 가로축:** 양당 평균 간격 변화의 조건 차이다. 왼쪽 음수는 비교 조건보다 양당이 더 가까워졌다는 뜻이다.
- **점과 선:** 점은 추정값, 선은 95% 구간이다. 선이 0의 한쪽에 있으면 그 방향의 차이가 비교적 뚜렷하다.

'''
metadata='''## 분석 방법과 범위

이번 질문을 받은 뒤 추가한 **사후 탐색 분석**이다. 예비 점추정값을 본 뒤 아래 재표집 방법을 정했으며 등록 분석을 대체하지 않는다.

정책 척도는 0~10, SD는 모집단 정의(ddof=0)다. 개인별 사전·사후가 모두 있는 응답을 쓰고, AI는 네 조건에 공통으로 유효한 에이전트×문항만 남겼다. 같은 정당의 응답을 문항별로 합쳐 정당 평균·SD를 계산했으므로 토론 소집단 사이의 차이도 정당 내부 분포에 포함된다.

구간은 2,000회 군집 재표집으로 계산했다. AI는 문항 안에서 같은 토론 블록을 네 조건에 함께 재표집했다. 인간 숙의군은 토론 소집단을, 통제군은 참가자를 재표집하고 그 집단/참가자의 모든 문항 응답을 함께 옮겼다. 문항 30개는 고정했다. 따라서 구간은 이 문항 집합에서의 불확실성을 나타낸다. AI의 동일 페르소나가 여러 블록·문항에 반복 등장하는 의존은 블록 재표집이 전부 반영하지 못한다.

새 유의성 검정은 추가하지 않았고, 추정값과 95% 구간을 보고한다. 집계 JSON에는 검산용으로 전체 분산 = 정당 내부 분산 + 정당 사이 분산의 분해도 저장했다.

재생성: `OPENBLAS_NUM_THREADS=1 .venv/bin/python scripts/analyze_party_dispersion.py`. 원자료가 있어야 실행할 수 있다. 원자료는 복사·공개하지 않고 입력 파일 해시와 집계 결과를 보관했다.

'''
sample_rows=[]
for model in ['claude','gemini','mistral']:
    v=results[model]['sample']
    sample_rows.append([names[model],str(v['blocks']),str(v['agent_item_records_per_condition']),str(v['distinct_personas']),str(v['excluded_condition_rows_for_pairing'])])
sample_table=mdtable('AI complete-case sample',['Model','Blocks','D/R agent-item records per condition','Distinct D/R personas','Excluded condition rows'],sample_rows)
h=results['human']['sample']
human_sample=f"인간 숙의군: 양당 응답자 {h['deliberation']['people']}명, {h['deliberation']['clusters']}개 소집단. 인간 통제군: 양당 응답자 {h['control']['people']}명.\n\n"
rule_reading=figure_reading.replace('Claude·Gemini·Mistral과 인간 비교다.', 'Claude·Gemini·Mistral 세 모델이다.')
cross_reading='''## 모델별·인간 결과의 해석

- **Claude:** 자료만 읽는 조건보다 토론 조건에서 양당 평균은 가까워지고, 각 정당 내부의 점수는 더 넓게 분포한다. 재응답 조건과 비교해도 방향이 같다.
- **Gemini:** 자료만 대비 기준선 토론은 양당 간격을 0.353점 더 벌린다. 당내 SD 차이는 두 정당 모두 구간이 0을 포함한다. 여기에 규칙을 넣으면 양당 간격은 기준선보다 1.638점 줄고 당내 SD 차이는 뚜렷하지 않다.
- **Mistral:** 자료만 대비 기준선 토론은 양당 간격과 두 정당 내부의 SD를 모두 줄인다. 반면 이미 토론하는 상태에서 규칙을 추가하면, 양당 간격은 더 줄면서 두 정당 내부 SD는 커진다.
- **인간:** 행사 참여군−통제군에서 양당 간격은 0.797점 줄었다. 민주당 SD 변화 차이 −0.045점, 공화당 +0.027점은 모두 구간이 0을 포함한다. 인간 숙의의 뚜렷한 변화는 양당 평균의 접근이며, 당내 의견의 폭은 큰 방향 변화가 확인되지 않았다.

'''
report='# 정책 토론: 정당 내부의 의견 차이와 양당 간격\n\n작성·계산: 2026-10-19 (한국시간).\n\n'+reading+core+'## 그림 1. 토론은 무엇을 더하는가?\n\n'+img('discussion_effect','토론−자료만의 정당 내부 SD 및 양당 간격 차이')+figure_reading+tables[0]+'## 그림 2. 숙의 규칙은 무엇을 더하는가?\n\n'+img('rule_effect','상태 기반−기준선 토론의 정당 내부 SD 및 양당 간격 차이')+rule_reading+tables[2]+cross_reading+'## 재응답 조건 대비\n\n'+tables[1]+level_table+sample_table+human_sample+metadata
(OUT/'README.md').write_text(report)
snippet='''#### 추가 분석. 양당은 가까워지면서 정당 내부 의견은 다양해지는가?

각 정책 문항에서 민주당 응답은 민주당끼리, 공화당 응답은 공화당끼리 모아 계산한 사후 탐색 분석이다. 서로 다른 토론 소집단의 같은 정당 응답도 함께 포함한다. SD는 정당 내부 점수의 퍼짐이고, party gap은 양당 평균 점수의 간격이다.

'''+img('discussion_effect','정당 내부의 의견 차이와 양당 간격: 토론−자료만')+figure_reading+tables[0]+core+f'[전후 수치·규칙 개입·계산 방법을 포함한 전체 결과]({OUT/"README.md"})\n\n'
(OUT/'rq-evidence.md').write_text(snippet)
print('Human sample:', results['human']['sample'], flush=True)
for model in results:
    k='deliberation - control' if model=='human' else contrast_keys[0]
    print(model,k,{m:results[model]['contrasts'][k][m] for m in METRICS[:3]},flush=True)
print('Report:', OUT/'README.md', flush=True)
