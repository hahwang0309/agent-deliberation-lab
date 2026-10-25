"""Render matched recoding results and a descriptive cue decomposition, without API calls."""
from pathlib import Path
import hashlib,json,os
import numpy as np
import pandas as pd
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/position-change-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

R=Path(__file__).resolve().parents[1];B=R/'docs/research';O=B/'position-change-mentions'
M=['mistral-large-2512','mistral-small-2603'];N=['자동 코더 1','자동 코더 2']
SCOPES={'wason':'논리 과제','a1r':'정책토론','pooled_population':'전체 발언 모집단 가중치','equal_task':'두 과제 동일 가중치'}
H={'none':'입장 변화 특정 안내 없음','closing':'마무리 요청만 있음','moved':'입장 이동 안내','direct':'명시적 변화 진술 지시'}
def pct(v):return f"{100*v:.1f}%"
def interval(r,pp=False):return f"{100*r['estimate']:+.1f}"if pp else pct(r['estimate'])
def cell(r,pp=False):
    if pp:return f"{100*r['estimate']:+.1f} [{100*r['ci'][0]:+.1f}, {100*r['ci'][1]:+.1f}]"
    return f"{100*r['estimate']:.1f}% [{100*r['ci'][0]:.1f}, {100*r['ci'][1]:.1f}]"

d=json.loads((O/'results.json').read_text());est=d['estimates'];dec=d['decomposition']
strict_table=['| 자동 코더 | 기준 | 일반 토론 | 상태 기반 토론 | 차이(%포인트) |','|---|---|---:|---:|---:|']
for model,name in zip(M,N):
    r=d['maintenance_strict_sensitivity'][model]['pooled_population']
    strict_table.append(f"| {name} | 명시적 입장 유지 표현이 있는 발언을 모두 비변화로 처리 | {cell(r['baseline'])} | {cell(r['stateful'])} | {cell(r['difference'],True)} |")
strict_cues=['| 자동 코더 | 안내 유형 | 보수적 변화 언급률 | 전체 발언에서의 몫(%포인트) |','|---|---|---:|---:|']
for model,name in zip(M,N):
    f=pd.read_csv(O/f'classified-{model}.csv');f=f[f.arm.eq('stateful')]
    for h,label in H.items():
        g=f[f.stratum.eq(h)];rate=float(np.average(g.yes_strict,weights=g.weight));share=float(g.weight.sum()/f.weight.sum())
        strict_cues.append(f"| {name} | {label} | {pct(rate)} | {100*rate*share:.2f} |")


table=['| 자동 코더 | 분석 범위 | 일반 토론 | 상태 기반 토론 | 차이(%포인트) |','|---|---|---:|---:|---:|']
for model,name in zip(M,N):
    for scope,label in SCOPES.items():
        r=est[model][scope];table.append(f"| {name} | {label} | {cell(r['baseline'])} | {cell(r['stateful'])} | {cell(r['difference'],True)} |")
decomp=['| 자동 코더 | 상태 기반 발언의 안내 유형 | 해당 유형의 실제 비중 | 해당 유형 안의 변화 언급률 | 전체 발언 비율에 더하는 몫(%포인트) | 전체 변화 언급 중 차지하는 몫 |','|---|---|---:|---:|---:|---:|']
diffrows=[]
for model,name in zip(M,N):
    for h,label in H.items():
        r=dec[model]['pooled_population'][h]
        decomp.append(f"| {name} | {label} | {pct(r['population_share']['estimate'])} | {cell(r['stateful_rate'])} | {100*r['stateful_joint']['estimate']:.2f} | {pct(r['fraction_of_stateful_mentions']['estimate'])} |")
        diffrows.append(dict(model=model,exposure=h,population_share=r['population_share']['estimate'],baseline_rate=r['baseline_rate']['estimate'],stateful_rate=r['stateful_rate']['estimate'],stateful_joint=r['stateful_joint']['estimate'],difference_contribution=r['difference_contribution']['estimate'],fraction_of_stateful_mentions=r['fraction_of_stateful_mentions']['estimate']))
pd.DataFrame(diffrows).to_csv(O/'pooled-decomposition.csv',index=False)
difference_table=['| 상태 기반 안내 유형으로 나눈 발언쌍 | 같은 진행 위치의 일반 발언 언급률 | 상태 기반 언급률 | 전체 조건 차이에 해당하는 몫(%포인트) |','|---|---:|---:|---:|']
for h,label in H.items():
    r=dec[M[0]]['pooled_population'][h]
    difference_table.append(f"| {label} | {pct(r['baseline_rate']['estimate'])} | {pct(r['stateful_rate']['estimate'])} | {cell(r['difference_contribution'],True)} |")


first=est[M[0]]['pooled_population'];direct=dec[M[0]]['pooled_population']['direct'];none=dec[M[0]]['pooled_population']['none'];moved=dec[M[0]]['pooled_population']['moved']
history=pd.read_csv(O/'cue-history-sensitivity.csv')
history_table=['| 자동 코더 | 현재 특정 안내가 없는 발언의 과거 이력 | 표집 발언 수 | 변화 명시 건수 | 가중 변화 언급률 |','|---|---|---:|---:|---:|']
for model,name in zip(M,N):
    for row in history[history.model.eq(model)&history.study.eq('pooled_population')&history.arm.eq('stateful')].itertuples():
        label='본인에게 이전 변화 안내도 없었음'if not row.prior_own_any_cue else '본인에게 이전 변화 안내는 있었음'
        history_table.append(f"| {name} | {label} | {row.n} | {row.n_yes} | {pct(row.weighted_rate)} |")

report=f'''# 일반 토론과 상태 기반 토론의 입장 변화 언급 비교

분석일: 2026-10-24. 주모델 AI Agents의 기존 토론에서 같은 기준으로 발언을 뽑아 새로 분류했다. 모든 비율은 **발언의 비율**이며 참가자·토론의 비율이 아니다. 측정한 것은 자신의 입장이 바뀌었다고 명시한 발언이며, 실제 판단 변화는 별도 지표다.

## 보고할 세 가지 결과

| 보고할 내용 | 자동 코더 1 | 자동 코더 2 |
|---|---:|---:|
| 1. 일반 토론보다 변화 언급이 얼마나 늘었나 | 12.7%→31.8%; +19.0%포인트 | 13.4%→29.4%; +16.0%포인트 |
| 2. 전체 상태 기반 변화 언급 중 지시가 있는 발언에서 나온 비중 | 40.9% | 47.9% |
| ↳ 현재 발언에 두 지시가 모두 없었던 비중 | 59.1% | 52.1% |
| 3. 지시가 있는 발언 중 실제로 변화를 언급한 비율 | 46.2% | 50.2% |
| ↳ 입장 이동 안내 뒤 | 42.1% | 46.5% |
| ↳ 명시적 변화 진술 지시 뒤 | 92.8% | 92.5% |

지시는 입장 이동 안내와 명시적 변화 진술 지시를 합친 것이다. 두 번째 행의 분모는 전체 상태 기반 변화 언급이고, 세 번째 질문의 분모는 지시가 있는 상태 기반 발언이다. 두 지시는 전체 상태 기반 발언의 28.1%에 있었다. 현재 발언에 두 지시가 없는 범주에는 마무리 설명 요청만 있는 발언도 포함한다. 지시의 발생 자체가 토론 상태에 따라 정해지므로, 두 번째 비율은 지시가 원인으로 만들어낸 변화량이 아니라 지시가 있는 발언에서 관찰된 비중이다. 측정 대상은 실제 판단 변화가 아닌 입장 변화의 명시적 언급이다.

## 같은 기준으로 비교한 전체 변화 언급률

원 논리 과제 471개 구성과 정책 416개 구성을 사용했다. 두 조건에서 같은 초기 구성·같은 토론 내 발언 순서를 짝지었다. 토론 규칙이 발언 배분을 바꾸므로, 짝의 발언자가 항상 같은 사람인 것은 아니다. 원 논리 과제 7,625개·정책 10,400개 발언쌍의 모집단에서 안내 유형별로 발언쌍을 추출했다. 조건마다 800개, 총 1,600개 발언을 두 코더가 각각 분류했다.

가중치는 각 과제×유형의 실제 발언 수/추출 수다. 직접 지시가 드물어 충분히 추출했지만 전체 비율을 계산할 때는 실제 빈도로 되돌렸다. 전체 발언 수치는 원 표집틀의 발언 수 비중으로 합쳤다. 별도 민감도 수치에서는 논리·정책에 각각 50%를 주었다. 대괄호는 같은 구성의 토론쌍을 유지한 블록 재표집 2,000회의 95% 구간이다. 반복 인물 설정의 모든 교차 의존성을 해결한 구간은 아니다.

'''+ '\n'.join(table)+f'''

두 코더는 {M[0]}와 {M[1]}이다. 토론 조건, 프로그램 지시, 안내 유형, 원 자료 식별자는 가렸다. 최종 분류에는 대상 발언 자체만 제시해 앞선 대화를 대상 발언으로 잘못 인용하는 문제를 줄였다. ‘변화를 명시함’은 yes, 암시만 있거나 확신 정도만 달라진 경우는 partial, 변화 언급이 없거나 입장 유지라고 말한 경우는 no로 분류했다. 본 표는 yes만 센 결과다. yes+partial 민감도는 [분해 CSV](exposure-decomposition.csv)에 있다.

## 지시 없는 변화 언급과 안내 뒤의 변화 언급

다음 네 범주는 서로 겹치지 않도록 직접 지시 → 이동 안내 → 마무리 요청 → 세 안내 없음의 순서로 분류했다. 직접 지시와 마무리 요청이 함께 들어간 발언은 직접 지시에 포함된다.

- **입장 변화 특정 안내 없음:** 해당 발언의 프롬프트에 아래 세 종류가 없다. 다른 숙의 규칙이나 이전 발언에서 받은 안내까지 없다는 뜻은 아니다.
- **마무리 요청만 있음:** 최종 입장과 어떤 논거가 의견을 움직였거나 움직이지 못했는지 설명하도록 요청한다. 두 토론 조건에 모두 있는 요청이다.
- **입장 이동 안내:** ‘지난 발언 이후 입장이 움직였으니 발언에 반영하라’는 안내가 있다.
- **명시적 변화 진술 지시:** ‘입장이 전환됐으니 생각을 바꿨다고 분명히 말하고 근거를 설명하라’는 지시가 있다.

'''+ '\n'.join(decomp)+f'''

**표 읽는 예:** ‘전체 발언 비율에 더하는 몫’은 해당 유형의 실제 비중×그 유형 안의 언급률이다. 네 행을 더하면 상태 기반 전체 언급률이 된다. 직접 지시의 조건부 언급률이 높아도 지시 자체가 드물면 전체에서 차지하는 몫은 작을 수 있다. 단순 입장 이동 안내의 경우 그 몫은 {100*moved['stateful_joint']['estimate']:.2f}%포인트였다(자동 코더 1).

여기서 ‘몫’은 관찰된 비율의 분해다. 안내는 토론 상황에 따라 발생했으므로, 해당 안내가 그만큼의 변화를 **원인으로 만들어냈다**는 추정은 아니다. 특정 안내가 없는 발언의 변화 언급도 상태 기반 규칙 전체의 영향이나 이전 안내의 영향을 받을 수 있다. 이전에 같은 에이전트가 변화 안내를 받았는지 나눈 민감도는 [안내 이력 비교](cue-history-sensitivity.csv)에 보존했다.

### 현재 안내와 이전 안내를 더 구분하면

현재 입장 변화 특정 안내가 없는 발언을, 같은 에이전트가 이전에 변화 안내·마무리 요청을 받은 적이 있는지 다시 나눴다. 아래는 전체 발언 모집단 가중치의 조건부 기술값이다. 표집 발언 수와 단순 변화 건수를 함께 보였으며, 비율은 층별 추출을 보정한 가중값이다.

'''+ '\n'.join(history_table)+f'''

이전 본인 안내가 없더라도 다른 참가자의 발언·다른 숙의 규칙의 영향은 받을 수 있으므로 ‘모든 지시가 없는 자발적 변화’로 확대하지 않는다.

## 두 조건 차이를 발언 유형으로 나누면

다음은 자동 코더 1의 결과다. 상태 기반 발언의 안내 유형을 기준으로 짝의 일반 발언도 같은 행에 넣었다. 마지막 열은 해당 유형의 실제 비중×짝 발언의 언급률 차이이며, 네 행의 합이 전체 일반–상태 기반 차이다. 분해한 차이를 특정 안내의 독립적 인과효과로 해석하지 않는다.

'''+ '\n'.join(difference_table)+f'''

## 기존 93.7%를 어디에 놓아야 하는가

기존 93.7%는 직접 지시를 받은 발언만 따로 뽑은 표본에서 자신의 입장 변화를 명시한 비율인 **281/300건**이다. 전체 상태 기반 발언의 변화 언급률이 아니다. 같은 기존 표본에서 변화의 근거 설명 등까지 포함한 별도 지시 이행 항목의 yes는 **278/300건, 92.7%**였다.

새 분석에서는 조건과 지시를 가린 재분류로 전체 비율과 유형별 비율을 먼저 제시하고, 기존 93.7%는 안내 이행을 확인한 별도 표본의 결과로 뒤에 설명한다. 기존 표본과 새 표본은 과제·반복 범위·표집 방식·코더에게 제공한 정보가 달라, 기존 93.7%를 새 직접 지시 비율로 그대로 곱하지 않는다.

기존 일반 토론의 9.6%도 일반 응답 발언만의 과제 혼합 표본에서 유효 291개 중 28개를 센 값이다. 새 분석은 두 조건의 동일한 표집틀에 마무리 발언까지 포함하고 과제 가중치를 맞췄으므로, 새 일반 토론 비율을 함께 사용한다.

## 그래프와 해석

![같은 기준의 변화 언급 비교와 안내 유형별 분해](comparison-and-decomposition.png)

- **a:** 가로축은 논리·정책·전체 발언 모집단 가중치, 세로축은 전체 발언 중 입장 변화 명시 비율이다. 파랑은 일반, 주황은 상태 기반이며 원과 삼각형은 자동 코더 1·2다. 선은 95% 구간이다.
- **b:** 자동 코더별 상태 기반 전체 비율을 네 안내 유형의 몫으로 나눴다. 각 색 구간의 높이는 전체 발언에서 해당 유형의 변화 언급이 차지하는 비율이며, 네 높이의 합이 전체 비율이다.
- **c:** 각 안내 유형 안에서 변화 언급이 얼마나 나타났는지 보여 준다. 이 조건부 비율과 b의 전체 몫은 분모가 다르다.

[벡터 PDF](comparison-and-decomposition.pdf) · [수치 결과](results.json) · [추출 계획·가중치](protocol.json) · [표본 메타데이터](sample-metadata.csv) · [분해 표 CSV](pooled-decomposition.csv)

## 명시적 입장 유지 표현을 보수적으로 처리하면

원문 점검에서 ‘입장은 바뀌지 않았다’는 표현과 확신 변화가 함께 있을 때, 자동 코더가 yes나 partial로 판정한 사례가 확인됐다. 원래 판정은 수정하지 않고, 두 조건 전체에 같은 규칙을 적용한 민감도를 추가했다. 자신의 입장이 변하지 않았다는 명시적 표현을 포함한 159개 대상 발언을 모두 비변화로 간주하는 보수적 기준이다. 일부 문장에는 유지와 부분 변화가 함께 있을 수 있어 이 기준은 사람 조정 판정이나 정답 라벨을 대신하지 않는다.

'''+ '\n'.join(strict_table)+'\n\n'+ '\n'.join(strict_cues)+f'''

이 표는 전체 발언 모집단 가중치 요약이다. 원 판정과 이 보수적 민감도를 함께 제시하며, 정확한 최종 비율은 사람 검증 뒤 보강한다. [표현 기준과 대상 ID](maintenance-audit-candidates.json)는 조건·코더 결과와 별개로 전체 대상 문장에서 추출했다.

## 분류 일치와 검증 범위

두 코더의 yes 대 나머지 일치율은 {pct(d['coder_agreement']['yes_vs_not_agreement'])}, κ={d['coder_agreement']['yes_vs_not_kappa']:.3f}였다. 두 모델은 같은 공급자 계열이며, 이 일치는 실제 사람 판정에 대한 정확도 검증을 대신하지 않는다. 사람 검증은 `<추후 작성 필요>`다.

표본·분류 기준은 최종 처리 전 고정했다. 문맥을 포함한 시험 분류에서 인용 근거가 섞여, 대상 발언만 제시하고 원문 인용을 검증하는 방식으로 바꾼 뒤 최종 표본 전체를 다시 분류했다. 시험 결과는 별도 보관했고 최종 수치에 섞지 않았다. API 속도 제한·형식 또는 인용 오류는 저장된 성공 결과를 유지한 채 미완료 항목만 재시도했다. 인용문 끝의 따옴표 등 형식만 달라 실패한 경우에는 판정 라벨을 바꾸지 않고 원문과 연속으로 일치하는 구간만 근거로 보존했다. 원래 인용과 원문 일치 구간은 별도 기록했다.
'''
(O/'README.md').write_text(report)

# Supplementary Table 13 holds the same estimates and decomposition; no duplicate inference.
si='''# Supplementary Table 13. 동일 기준 발언 표집의 입장 변화 언급 <a id="supplementary-table-13"></a>

주모델 기존 발언을 조건마다 800개씩 추출해, 토론 조건과 지시를 가린 두 코더로 재분류한 사후 탐색 분석이다. 아래 비율은 입장 변화를 명시한 발언의 비율이다. 과제·유형별 역추출확률 가중치를 적용했다. 전체는 모집단 발언 수의 비중으로 합쳤고 두 과제 동일 가중치도 별도로 보고했다. 구간은 대응 블록 재표집 2,000회의 95% 구간이다.

## A. 일반·상태 기반 토론의 동일 기준 비교

'''+ '\n'.join(table)+'''

## B. 상태 기반 전체 비율의 안내 유형별 분해

'''+ '\n'.join(decomp)+'''

직접 지시·이동 안내·마무리 요청·세 안내 없음의 우선순위로 겹치지 않게 나눴다. ‘특정 안내 없음’은 현재 발언에 세 종류가 없다는 뜻이며, 다른 숙의 규칙이나 과거 안내까지 없는 것은 아니다. 마지막에서 두 번째 열 네 값을 더하면 해당 코더의 전체 변화 언급률이다. 이는 관찰된 비율의 분해이며 지시의 독립적인 인과효과 추정이 아니다.

기존 직접 지시 표본의 변화 명시 93.7%(281/300)와 전체 지시 이행 판정 92.7%(278/300)는 별도 지표다. 기존 수치와 새 조건부 비율은 표집과 코더 정보가 달라 구분한다. 원문 근거·표본·원자료 해시·코더별 모든 판정은 [분석 보고서와 기록](../position-change-mentions/README.md)에 연결했다. 사람 검증: `<추후 작성 필요>`.

## Supplementary Fig. 2. 전체 비교와 안내 유형별 분해

![발언의 변화 언급 비교](../position-change-mentions/comparison-and-decomposition.png)

**English legend.** Post-hoc instruction-blind recoding of primary-model utterances. Panel a shows explicit own-position-change mention prevalence under ordinary and stateful discussion, separately for original reasoning and policy tasks and with population utterance weights for the summary. Circles and triangles identify Mistral Large and Small coders. Bars in b partition total stateful prevalence into mutually exclusive current-prompt cue categories. Panel c shows prevalence conditional on each category. Error bars are 95% matched-block bootstrap intervals. Cue categories prioritize explicit change instructions, movement feedback, closing requests and no change-specific cue. Conditional rates and joint prevalence contributions have different denominators. Cue occurrence was not randomized; the decomposition is descriptive. Human validation is pending.

[표 수치·분해 CSV](../position-change-mentions/pooled-decomposition.csv)
'''
legacy=[]
for file,model in [('devices_large.csv',M[0]),('devices_small.csv',M[1])]:
    source=R/'data/study1/results/exploratory/coding'/file
    f=pd.read_csv(source)
    for device,column in [('respond_challenge','addresses_specific_claim'),('mediate','names_disagreement_between_others'),('devils_advocate','objects_to_shared_view'),('switched','states_position_change')]:
        g=f[f.device.eq(device)].dropna(subset=[column,'instruction_followed'])
        legacy.append(dict(coder=model,device=device,valid_n=len(g),behaviour_yes=int(g[column].eq('yes').sum()),behaviour_rate=float(g[column].eq('yes').mean()),full_instruction_yes=int(g.instruction_followed.eq('yes').sum()),full_instruction_rate=float(g.instruction_followed.eq('yes').mean())))
pd.DataFrame(legacy).to_csv(O/'legacy-instruction-checks.csv',index=False)
legacy_table=['| 자동 코더 | 요청 유형 | 유효 발언 수 | 해당 행동 명시 | 전체 지시 이행 판정 |','|---|---|---:|---:|---:|']
labels={'respond_challenge':'반박에 응답','mediate':'불일치 정리·중재','devils_advocate':'반대 관점 검토','switched':'입장 변화 명시'}
for row in legacy:
    legacy_table.append(f"| {N[M.index(row['coder'])]} | {labels[row['device']]} | {row['valid_n']} | {row['behaviour_yes']} ({pct(row['behaviour_rate'])}) | {row['full_instruction_yes']} ({pct(row['full_instruction_rate'])}) |")
si=si.replace('## Supplementary Fig. 2.', '## C. 기존 지시 대상 발언만의 수행 점검\n\n'+ '\n'.join(legacy_table)+'\n\n요청을 받은 발언만을 뽑은 기존 표본이다. 전체 발언 비율 또는 A의 동일 기준 비교와 구분한다. 두 코더는 지시 문구를 볼 수 있었으며, 새 분류는 지시를 가렸다. 원 분류 자료를 새로 재계산했으며 기존 수치는 변경하지 않았다.\n\n## Supplementary Fig. 2.')
si=si.replace('## Supplementary Fig. 2.', '## D. 명시적 유지 표현을 모두 비변화로 처리한 민감도\n\n'+ '\n'.join(strict_table)+'\n\n'+ '\n'.join(strict_cues)+'\n\n원 자동 판정은 보존했다. 전체 대상에서 명시적 자기 입장 유지 표현이 있는 159개 발언을 모두 비변화로 처리한 보수적 점검이며, 사람 조정 판정은 아니다.\n\n## Supplementary Fig. 2.')
(B/'supplementary-information/PositionChangeMentions.md').write_text(si)

# Figure layout and data are created only from the completed two-coder output.
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
fig,axes=plt.subplots(1,3,figsize=(18,5.7),gridspec_kw={'width_ratios':[1.2,.8,1.2]});a,b,c=axes
colors={'baseline':'#2776bd','stateful':'#d85a24'}
for j,model in enumerate(M):
    for arm,offset in [('baseline',-.12),('stateful',.12)]:
        for x,scope in enumerate(['wason','a1r','pooled_population']):
            r=est[model][scope][arm];v=r['estimate'];lo,hi=r['ci']
            a.errorbar(x+offset+(j-.5)*.04,v,yerr=[[v-lo],[hi-v]],fmt=['o','^'][j],color=colors[arm],capsize=3,label=f'{arm.title()}, coder {j+1}'if x==0 else None)
a.set(xticks=range(3),xticklabels=['Logic','Policy','All utterances\npopulation weights'],ylabel='Share of all utterances',title='a  Matched-sample comparison');a.yaxis.set_major_formatter(PercentFormatter(1));a.legend(frameon=False,fontsize=8)
cue_colors=['#637e96','#c3a96f','#6eb19a','#b7767e'];names=['No change cue','Closing request','Movement feedback','Explicit change instruction']
bottom=np.zeros(2)
for h,color,name in zip(H,cue_colors,names):
    values=np.array([dec[model]['pooled_population'][h]['stateful_joint']['estimate']for model in M]);b.bar(range(2),values,bottom=bottom,color=color,label=name);bottom+=values
b.set(xticks=range(2),xticklabels=['Coder 1','Coder 2'],ylabel='Contribution to all-utterance share',title='b  Stateful prevalence components');b.yaxis.set_major_formatter(PercentFormatter(1));b.legend(frameon=False,fontsize=8,loc='upper left',bbox_to_anchor=(0,-.14))
for j,model in enumerate(M):
    for x,h in enumerate(H):
        r=dec[model]['pooled_population'][h]['stateful_rate'];v=r['estimate'];lo,hi=r['ci'];c.errorbar(x+(j-.5)*.1,v,yerr=[[v-lo],[hi-v]],fmt=['o','^'][j],color=['#2776bd','#d85a24'][j],capsize=3,label=f'Coder {j+1}'if x==0 else None)
c.set(xticks=range(4),xticklabels=['No change\ncue','Closing\nonly','Movement\nfeedback','Explicit\ninstruction'],ylabel='Mention rate within cue category',title='c  Conditional stateful rates',ylim=(0,1.04));c.yaxis.set_major_formatter(PercentFormatter(1));c.legend(frameon=False,fontsize=8)
fig.suptitle('Explicit position-change mentions: matched rates and descriptive cue decomposition',fontsize=13)
fig.tight_layout(rect=(0,.03,1,.94),w_pad=3)
for ext in ['png','pdf']:fig.savefig(O/f'comparison-and-decomposition.{ext}',dpi=220)
plt.close(fig)

# Preserve quantitative records and all classification outputs in a separate provenance manifest.
inputs=[O/'protocol.json',O/'sample-metadata.csv',O/'coding-system.txt',O/'results.json',*[O/f'coded-{model}.jsonl'for model in M],R/'scripts/analyze_position_change_mentions.py',R/'scripts/finalize_position_change_quotes.py',O/'maintenance-audit-candidates.json',O/'quote-source-span-resolutions.json',Path(__file__)]
outputs=[O/'README.md',O/'pooled-decomposition.csv',O/'legacy-instruction-checks.csv',O/'comparison-and-decomposition.png',O/'comparison-and-decomposition.pdf',B/'supplementary-information/PositionChangeMentions.md']
hashes=lambda paths:{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths}
(O/'output-manifest.json').write_text(json.dumps({'date':'2026-10-24','inputs':hashes(inputs),'outputs':hashes(outputs)},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'report':str(O/'README.md'),'coders':M,'primary_pooled_population':first,'direct_population_share':direct['population_share']['estimate'],'direct_contribution':direct['stateful_joint']['estimate']},ensure_ascii=False))
