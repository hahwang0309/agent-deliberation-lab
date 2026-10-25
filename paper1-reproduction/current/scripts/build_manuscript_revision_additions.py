"""Render existing outcome records into manuscript/SI additions; no model fitting or API calls."""
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
if '--figure-only' not in sys.argv:
 rows=[]
 for m in models:
  a=u[u.model.eq(m)&u.label.eq(arms[0])].iloc[0];b=u[u.model.eq(m)&u.label.eq(arms[1])].iloc[0];v=d['models'][m]['rules_minus_baseline']['item_bootstrap']['post_between_unbiased']
  rows.append([m.title(),f'{100*a.mean_item_agreement_rate:.1f}% → {100*b.mean_item_agreement_rate:.1f}%',f'{a.mean_item_final_mean_variance:.3f} → {b.mean_item_final_mean_variance:.3f}',f'{v["estimate"]:+.3f} [{v["ci"][0]:.3f}, {v["ci"][1]:.3f}]'])
 addition='\n\n## 내부 합의와 전체 토론 결론의 분포 — 추가 사후 비교\n'
 addition+='\n30문항 동일 가중치, 공통 구성의 첫 반복이다. 아래 분산은 합의 여부와 관계없이 모든 토론 최종 평균에 분모 G−1을 사용했다. 위 Fig.5 분산 분해의 G 분모 수치와 구별한다. 합의율은 다섯 사후 점수의 모집단 SD≤1을 충족한 토론 비율이다.\n\n'+table(['모델','합의율: 일반 → 상태 기반','전체 토론 평균 분산: 일반 → 상태 기반','분산 차이 [95% 문항 재표집 구간]'],rows)
 addition+='\n- **관찰:** 두 조건 모두 결론 분산이 0보다 크고, 규칙 추가 후 내부 합의율과 전체 토론 결론 분산이 세 모델 모두 증가했다.\n- **해석:** 같은 방에서 가까워지는 것과 여러 방이 같은 결론을 내는 것은 별개다. 합의한 방만의 합의점 분산 효과와 구별한다.\n- **비교 범위:** 엄격한 정당 혼합 인간 5명 응답 패널 합의율은 5.4%다. 실제 큰 방에서 숙의한 응답을 추출했으며 실제 다섯 명 처치가 아니다. 기존 N2b의 Claude 상태 기반 43.5%는 토론 동일 가중치, 아래 비교의 43.1%는 문항 동일 가중치다.\n\n[Supplementary Table 6](supplementary-information/AnalysisDetails.md#supplementary-table-6) · [두 조건 점 분포: Fig.6](manuscript-figures/figure6.pdf).\n'
 p=B/'Table2.md';s=p.read_text().split('\n\n## 내부 합의와 전체 토론 결론의 분포')[0];p.write_text(s+addition)
 si='''# Supplementary Methods·Discussion·Tables 6–8 — 추가 분포 비교

2026-10-21. 국문 보충자료의 추가 부품이다. 본문 Results 2.4–2.5·2.8과 Methods 4.7에서 직접 인용한다. 새 확증 검정이나 최종 영문 SI PDF로 표시하지 않는다.

## Supplementary Methods — 측정과 표집

한 토론은 다섯 명, 초기 역할은 민주당2·공화당2·무당층1이다. 조건 사이 동일 인물·초기 점수의 짝만 사용했다. 합의는 다섯 사후 점수의 모집단 SD(ddof=0)≤1이다. 모든 토론의 최종 평균과 합의한 토론만의 평균 분포를 따로 계산했다. 표6 분산은 각 문항 안 G−1 분모, Fig.5는 G 분모 분산 분해다. 30문항에 동일 가중치를 주었다. 기존 등록·탐색의 가중치와 추정량은 보존했다. 추가 추정 구간은 문항 짝 재표집 5,000회이며 원 인간 방 재표집 민감도와 다르다. 세부 코드·표집·해시·전체 추정은 아래 원 자료 링크에 보존했다. 문항당8/16토론과 합의 토론 수가 달라 분포 모양을 확정 분포족으로 분류하지 않았다. 구성·생성 변동은 동일 구성 반복이 없어 분리하지 않았다.

<a id="supplementary-table-6"></a>
## Supplementary Table 6. 일반·상태 기반의 합의와 토론별 결론

'''+table(['모델','합의율: 일반 → 상태 기반','전체 평균 분산: 일반 → 상태 기반','분산 차이 [95% 구간]'],rows)
 si+='\n각 문항에서 토론별 최종 평균은 두 조건·세 모델 모두 둘 이상이었다. 합의 토론이 두 개 이상인 문항에서만 합의점의 차이를 평가했다. 아래 마지막 열은 평균이5미만·5초과인 합의가 모두 있는 문항 수다.\n\n'
 si+=table(['모델·조건','평균이5양쪽에 있는 문항','합의토론≥2인 문항','그중 합의점이 다른 문항','합의점이5양쪽인 문항'],[[r.model.title()+' '+('일반'if r.label==arms[0]else'상태 기반'),f'{r.all_both_sides_items}/30',f'{r.at_least_two_agreements_items}/30',f'{r.different_agreement_means_items}/{r.at_least_two_agreements_items}',f'{r.agreement_both_sides_items}/30']for r in u.itertuples()])
 si+='''
- **관찰:** 일반 토론에도 서로 다른 방향의 합의점이 있다. 규칙 추가 후 모든 토론의 평균 분산은 커졌다.
- **해석:** 합의 발생과 끝점의 분포를 따로 읽어야 한다. 조건마다 합의 토론의 수·구성이 달라 이 조건부 문항 수 자체를 합의점 분산의 개입 효과로 쓰지 않는다.
- **원자료:** [180개 문항·모델·조건 행](../consensus-representation/ordinary-stateful-check/item-outcomes.csv), [모델별 요약](../consensus-representation/ordinary-stateful-check/model-summary.csv), [개별 토론](../consensus-representation/outcome-variability/discussion-outcomes.csv), [인간 패널과 구간·방법](../consensus-representation/README.md).

<a id="supplementary-table-7"></a>
## Supplementary Table 7. 정당 차이가 남은 합의와 기본 응답·인간 이동

'''
 # Reuse exactly the already source-verified tables, maintaining full intervals.
 raw=(B/'consensus-representation/README.md').read_text()
 def take_table(fragment):
  start=raw.index(fragment);lines=raw[start:].splitlines();out=[]
  for line in lines:
   if line.startswith('|'):out.append(line)
   elif out:break
  return '\n'.join(out)+'\n'
 si+=take_table('| 모델 | 일반 | 상태 기반 | 증가 [95% 구간] |')
 si+='\n위 표는 전체 방 중 합의와 초기 양당 평균의 상대 순서 유지가 함께 나타난 비율이다. 초기 동률은 순서 유지로 세지 않았다. 실제 이해관계 대변 여부와 구별한다.\n\n'+take_table('| 모델 | 개인 사후−D 거리: 일반 |')
 si+='\nD는 별도 초기 점수 없이 응답한 기본 입장이다. 양수의 거리 변화는 D에서 멀어졌다는 뜻이다. 같은 방향 이동은 유지자를 허용하되 최소 한 명이 이동하고 증가·감소가 함께 없는 경우다.\n\n'+take_table('| 모델 | 인간 이동 방향 일치: 일반 |')
 si+='''
- **관찰:** 초기 정당 순서가 남은 합의의 전체 발생 비율과 D와의 거리는 세 모델 모두 증가했다. 대응 인간의 이동 방향과 가까워지는 변화는 Gemini에서 두 재표집 방식 모두 확인됐지만 다른 모델에서는 일관되지 않았다.
- **해석:** 합의와 작은 정당 차이가 함께 존재한다. D로의 단순 복귀만으로 모든 합의를 설명하기 어렵지만 실제 대표성 확보나 전 모델 인간 유사성 증가와는 구별된다.
- **방법·추가표:** [조건부 분모·양당 이동·반복 인물 처리](../consensus-representation/README.md), [기계 판독 추정](../consensus-representation/source-data/results.json), [같은 방 양당 조정](../consensus-representation/source-data/group-party-adjustment.json).

<a id="supplementary-table-8"></a>
## Supplementary Table 8. 인간의 주제별 의견 차이와 AI 반응

'''
 topic_records=json.loads((B/'human-ai-topic-variation/associations.json').read_text())
 def association_cell(model,metric):
  record=topic_records['by_model'][model]['A-stateful']['human_post_sd'][metric]
  if record['rho'] is None:return f"해당 문항{record['n']}개; 산출 불가"
  low,high=record['ci'];return f"n={record['n']}; ρ={record['rho']:+.3f} [{low:.3f}, {high:.3f}]"
 si+=table(['비교: 인간 실제 방 평균 사후SD ↔ AI 상태 기반 지표','Claude','Gemini','Mistral'],[[label,*[association_cell(model,metric)for model in models]]for metric,label in [('consensus_rate','내부 합의율'),('final_mean_sd','전체 토론 최종 평균SD'),('agreement_only_sd','합의점SD; 합의 방≥4인 문항만')]])
 si+='''
- **관찰:** 모든 방 최종 평균SD와의 상관 구간은 세 모델 모두0을 포함한다. 인간 초기SD를 고려하면 합의율 관계는 약해진다. 엄격한 인간 합의율은0–7.5%로 낮아 연속적인 사후SD를 주 비교 지표로 사용했다.
- **해석:** 인간의 갈등이 클수록 AI 결론도 더 퍼진다는 일관된 관계는 확인되지 않았다. Gemini 합의점 분석은 표본 부족으로 산출하지 않았으며0상관으로 표시하지 않는다.
- **전체 추정·구간·민감도·반례:** [인간–AI 주제별 비교](../human-ai-topic-variation/README.md). 원래 인간SD 지표를 더 유리한 상관의 지표로 교체하지 않았다.

## Supplementary Discussion — 합의의 양과 내용

표6의 합의율은 방 안 가까움을, 전체 평균 분산은 방들 사이 차이를 측정한다. Fig.6은 세 정책에서 두 조건의 전체 점과 합의한 점을 함께 보여준다. 사례의 조건부 타협은 [Supplementary Fig.1·Tables3–5](CaseStudies.md)에 있는 개별 발언·사후 이유와 연결한다. 이 자료는 어떤 가정과 조건 아래 다른 결론이 나오는지 검토할 근거이며, 모든 논거의 사실성·정책 실행 가능성이나 인간 숙의 지원 효과를 측정한 것은 아니다. 과정 코딩의 사람 검증 결과는 `<추후 작성 필요>`다.
'''
 (S/'AnalysisDetails.md').write_text(si)
 # CSV exports for each new SI display: retain exact numeric data, no embedded rounding-only data.
 (S/'source-data').mkdir(exist_ok=True)
 u.to_csv(S/'source-data/Supplementary-Table-6.csv',index=False)
 # Flatten original numeric records into independent extractable source tables.
 def flatten(v,path=()):
  if isinstance(v,dict):
   for k,x in v.items():yield from flatten(x,path+(str(k),))
  elif isinstance(v,list):
   for i,x in enumerate(v):yield from flatten(x,path+(str(i),))
  else:yield {'json_path':'.'.join(path),'value':v}
 party=R/'docs/research/consensus-representation/source-data/group-party-adjustment.json'
 topic=R/'docs/research/human-ai-topic-variation/associations.json'
 pd.DataFrame([*flatten(d),*flatten(json.loads(party.read_text()),('group_party',))]).to_csv(S/'source-data/Supplementary-Table-7.csv',index=False)
 pd.DataFrame(flatten(json.loads(topic.read_text()))).to_csv(S/'source-data/Supplementary-Table-8.csv',index=False)
 # Do not add new exports into the older case-only zip; separate named source package.
 import shutil
 shutil.copyfile(O/'figure6-source-data.csv',S/'source-data/Main-Figure-6.csv')
 with zipfile.ZipFile(S/'files/Outcome-Source-Data.zip','w',compression=zipfile.ZIP_DEFLATED)as z:
  for path in [O/'figure6-source-data.csv',summary,item,outcomes,res,party,topic,*[S/f'source-data/Supplementary-Table-{i}.csv' for i in [6,7,8]]]:
   z.write(path,str(path.relative_to(B)))
 manifest={'date':'2026-10-21','inputs':{str(p.relative_to(R)):sha(p)for p in [summary,item,outcomes,res,party,topic,B/'consensus-representation/README.md',B/'human-ai-topic-variation/README.md',Path(__file__).resolve()]},'outputs':{str(p.relative_to(R)):sha(p)for p in [S/'AnalysisDetails.md',S/'files/Outcome-Source-Data.zip',*[S/f'source-data/Supplementary-Table-{i}.csv' for i in [6,7,8]],B/'Table2.md']}}
 (S/'outcome-additions-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Rendered manuscript outcome additions from archived records; no new inference.')
