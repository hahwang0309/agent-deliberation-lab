"""Summarize existing N3 estimates/draws by domain; no model/API calls or manuscript edits."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1];B=R/'docs/research';OUT=B/'domain-convergence-comparison-20261025';OUT.mkdir(exist_ok=True)
BASE=R/'data/study1/results/exploratory';label_path=R/'data/study1/results/by-topic/a1r_by_item.csv'
names=pd.read_csv(label_path).query("model == 'claude'")[['item','domain']].set_index('item');names['domain']=names.domain.str.replace('America in One Room: ','',regex=False).str.replace(' policy','',regex=False)
domains=['Environment','Economy','Immigration','Health','Foreign'];korean={'Environment':'환경','Economy':'경제','Immigration':'이민','Health':'보건','Foreign':'외교'}
paths=[label_path];rows=[];contrasts=[];points={};draws={};items_out=[]
spec={'human':{'within':'delib_group_sd_drop','pooled_delib':'delib_sd_drop','pooled_control':'control_sd_drop','net':'did_sd_drop'}}
for model in ['claude','gemini','mistral']:
 spec[model]={'ordinary':'sd_drop|A-baseline','stateful':'sd_drop|A-stateful','reanswer':'sd_drop|C-reanswer','materials':'sd_drop|B-materials','ordinary_net':'sd_drop|A-baseline - C-reanswer','stateful_net':'sd_drop|A-stateful - C-reanswer','added_rules':'sd_drop|A-stateful - A-baseline'}
def record(model,metric,domain,point,rep,n):
 lo,hi=np.quantile(rep,[.025,.975]);return dict(model=model,metric=metric,domain=domain,n_policies=n,estimate=float(point),ci_low=float(lo),ci_high=float(hi))
for model,metrics in spec.items():
 stem='n3_human' if model=='human' else 'n3_ai';tp=BASE/model/(stem+'_items.csv');zp=BASE/model/(stem+'_replicates.npz');paths += [tp,zp]
 t=pd.read_csv(tp).set_index('item');z=np.load(zp);items=list(z['items']);assert len(items)==30 and set(items)==set(names.index)
 for metric,key in metrics.items():
  assert np.allclose(z[key].shape,(2000,30));points[model,metric]={};draws[model,metric]={}
  for domain in domains:
   ix=[j for j,item in enumerate(items) if names.loc[item,'domain']==domain];its=[items[j] for j in ix]
   value=t.loc[its,key].mean();rep=z[key][:,ix].mean(axis=1)
   points[model,metric][domain]=value;draws[model,metric][domain]=rep;rows.append(record(model,metric,domain,value,rep,len(ix)))
  for item in items:items_out.append(dict(model=model,metric=metric,item=item,domain=names.loc[item,'domain'],estimate=float(t.loc[item,key])))
 for metric in metrics:
  value=points[model,metric]['Environment']-points[model,metric]['Economy'];rep=draws[model,metric]['Environment']-draws[model,metric]['Economy']
  contrasts.append(record(model,metric,'Environment minus Economy',value,rep,15))
# Independent identities and agreement with native room-level exports / AI block summaries.
hnative=pd.read_csv(B/'consensus-representation/source-data/human-native-groups.csv')
ht=pd.read_csv(BASE/'human/n3_human_items.csv').set_index('item')
hroom=hnative.assign(delta=hnative.pre_sd-hnative.post_sd).groupby('item').delta.mean()
assert np.allclose(hroom.sort_index(),ht.delib_group_sd_drop.sort_index(),atol=1e-10)
paths.append(B/'consensus-representation/source-data/human-native-groups.csv')
for model in ['claude','gemini','mistral']:
 for domain in domains:
  assert np.isclose(points[model,'stateful'][domain]-points[model,'ordinary'][domain],points[model,'added_rules'][domain])
  assert np.isclose(points[model,'stateful'][domain]-points[model,'reanswer'][domain],points[model,'stateful_net'][domain])
 tp=BASE/model/'a1r_blocks.csv';paths.append(tp);blocks=pd.read_csv(tp);t=pd.read_csv(BASE/model/'n3_ai_items.csv').set_index('item')
 for lab in ['A-baseline','A-stateful']:
  q=blocks[blocks.label.eq(lab)].groupby('item').sd_drop.mean();assert np.allclose(q.sort_index(),t['sd_drop|'+lab].sort_index())
pd.DataFrame(rows).to_csv(OUT/'domain-summary.csv',index=False);pd.DataFrame(contrasts).to_csv(OUT/'environment-economy-contrasts.csv',index=False);pd.DataFrame(items_out).to_csv(OUT/'item-estimates.csv',index=False)

def val(model,metric,domain,ci=False):
 x=next(q for q in rows if q['model']==model and q['metric']==metric and q['domain']==domain)
 return f"{x['estimate']:.3f} [{x['ci_low']:.3f}, {x['ci_high']:.3f}]" if ci else f"{x['estimate']:.3f}"
lines=['# 분야별 의견 수렴 비교 · 2026-10-25','','기존 N3의 30개 정책별 추정값과 2,000회 재표집 결과를 분야별로 요약했다. 원고는 수정하지 않았다. AI Agents는 주모델 Claude를 뜻한다.','','## 1. 한 토론 안에서 의견 차이가 줄어든 정도','','응답 점수(0–10)의 토론 전 표준편차에서 토론 후 표준편차를 뺀 값이다. 양수일수록 의견 차이가 많이 줄었다. 정책별로 각 토론의 감소량을 같은 비중으로 평균한 뒤, 분야 안의 정책에 같은 비중을 주었다. 인간은 실제 방(6–16명), AI는 다섯 명 토론이다. 인간 값은 40개 방 안의 감소량 평균으로, 전체 인간 응답을 합쳐 계산한 값과 구분한다.','','| 분야(정책 수) | 인간 실제 토론방 | AI 일반 토론 | AI 상태 기반 토론 | 규칙 추가분: 상태 기반−일반 |','|---|---:|---:|---:|---:|']
for domain in domains:
 n=next(x['n_policies'] for x in rows if x['domain']==domain);lines.append(f"| {korean[domain]} ({n}) | {val('human','within',domain)} | {val('claude','ordinary',domain)} | {val('claude','stateful',domain)} | {val('claude','added_rules',domain)} |")
lines+=['','인간은 환경에서 감소량이 가장 작고 이민·경제에서 컸다. 주모델 상태 기반 토론에서는 환경의 감소량이 경제보다 큰 점추정이었고, 두 분야 모두 인간보다 컸다. 규칙 추가분도 주모델에서는 환경에서 더 컸다. 표의 토론 전후 감소량 자체는 토론만의 인과효과로 해석하지 않는다.','','## 2. 비교 조건보다 더 줄어든 정도','','아래는 본문 2.2.7 및 N4의 대비를 그대로 분야별로 요약한 값이다. 인간은 행사 참여−비참여, AI는 토론−혼자 재응답이다. 인간 N3의 이 대비는 전체 숙의군·통제군 응답을 각각 합쳐 계산한 SD의 감소량을 사용하고, AI는 토론 안의 감소량을 평균한다. 따라서 비교 처치뿐 아니라 집계 수준도 달라, 아래 수치의 인간−AI 차이를 같은 효과의 우열로 해석하지 않는다. 분야 안의 패턴과 각 연구 내 비교를 읽기 위한 보조표다.','','| 분야 | 인간 행사 참여−비참여 | AI 일반−재응답 | AI 상태 기반−재응답 |','|---|---:|---:|---:|']
for domain in domains:lines.append(f"| {korean[domain]} | {val('human','net',domain)} | {val('claude','ordinary_net',domain)} | {val('claude','stateful_net',domain)} |")
lines+=['','## 3. 환경과 경제의 차이 및 모델별 재현','','아래 값은 환경−경제이며, 같은 재표집 반복 안에서 차이를 계산한 95% 구간이다.','','| 대상·지표 | 환경−경제 [95% 구간] |','|---|---:|']
for model,metric,label in [('human','within','인간 실제 방의 감소량'),('claude','ordinary','AI Agents 일반 토론 감소량'),('claude','stateful','AI Agents 상태 기반 감소량'),('claude','added_rules','Claude 규칙 추가분'),('gemini','added_rules','Gemini 규칙 추가분'),('mistral','added_rules','Mistral 규칙 추가분')]:
 x=next(q for q in contrasts if q['model']==model and q['metric']==metric);lines.append(f"| {label} | {x['estimate']:.3f} [{x['ci_low']:.3f}, {x['ci_high']:.3f}] |")
lines+=['','인간의 경제−환경 감소량 차이는 0.274 [0.180, 0.371]다. Claude의 규칙 추가분은 환경이 경제보다 0.274 [0.083, 0.466]점 더 크다. 다만 Claude 상태 기반 조건 자체의 환경−경제 차이는 구간이 0을 포함한다. Gemini·Mistral에서는 규칙 추가분의 분야 차이가 뚜렷하지 않아, 주모델 패턴을 세 모델 공통 현상으로 쓰지 않는다.','','## 4. 계산과 해석 범위','','- 정책 목록·분야·모델은 기존 자료를 사용했다. 환경 8·경제 7·이민 5·보건 6·외교 4개로 총 30개다.','- 구간은 기존 재표집 행에서 분야 내 정책 열을 평균한 분포의 2.5·97.5 백분위다. 인간은 실제 방 군집과 통제 응답자 재표집, AI는 정책 내 대응 토론 블록 재표집을 따랐다.','- 이 구간은 선택된 정책을 고정한 자료 표집 변동을 나타낸다. 각 분야의 모든 정책으로 일반화하는 구간이 아니며, AI의 같은 인물 설정 재사용 의존성을 모두 반영하지는 못한다. 다중비교 보정한 확증 검정은 아니다.','- 인간 행사에는 자료·전문가 패널 등이 포함되고 토론 인원·구성이 AI와 다르므로 인간−AI 비교는 기술적이다.','- 기존 인간 N3의 방별 평균을 실제 인간 방 자료에서 독립 계산해 일치를 확인했다. AI 조건별 정책 평균을 기존 블록 자료에서 독립 계산해 대조했고, 상태 기반−일반 및 토론−재응답 산술 항등식을 확인했다.','- 토론별 평균 결론의 분산(2.2.6), 정책 사이의 수렴 효과 분산(2.2.7), 분야 평균 수렴 효과(이번 표)는 서로 다른 지표다.','','## 5. 원고 반영에 대한 판단 자료','','2.2.7에는 정책에 따라 효과가 다르다는 기존 결과와 함께 분야별 기술 비교를 넣을 수 있다. 인간에서 수렴이 작았던 환경 분야에서 주모델 AI의 수렴이 크고 규칙 추가분도 컸다는 관찰이 후보 문장이다. 다만 환경−경제 순위가 세 모델에서 모두 반대로 나타났다는 주장이나, 각 분야 전반에 대한 일반화는 현재 결과보다 강하다. 2.2.6의 토론별 결론 분산과 섞지 않고, 인간·AI의 집계 수준을 맞춘 첫 표를 주 비교로 사용하는 편이 낫다.','','[분야별 전체 수치·95% 구간](domain-summary.csv) · [환경−경제 대비](environment-economy-contrasts.csv) · [정책별 입력 추정값](item-estimates.csv) · [입력 해시·검증](verification.json) · [재현 코드](../../../scripts/summarize_domain_convergence.py)','']
(OUT/'Report.md').write_text('\n'.join(lines))
ver={'date':'2026-10-25','status':'post-hoc domain summaries; manuscript unchanged','inputs':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'checks':{'n_policies':30,'human_room_level_verified':True,'ai_block_level_verified':True,'paired_contrast_identities_verified':True,'bootstrap_draws':2000,'all_models_included':True}}
(OUT/'verification.json').write_text(json.dumps(ver,ensure_ascii=False,indent=2)+'\n')
print(pd.DataFrame(rows).query("model=='human' and metric=='within' or model=='claude' and metric in ['ordinary','stateful','added_rules']")[['model','metric','domain','estimate','ci_low','ci_high']].round(3).to_string(index=False))
