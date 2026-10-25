"""Data-only check of outcome variation under ordinary and stateful discussion."""
from pathlib import Path
import os,json,hashlib,sys
import pandas as pd,numpy as np
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/consensus-representation-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1];O=R/'docs/research/consensus-representation/ordinary-stateful-check';O.mkdir(exist_ok=True)
sys.path.insert(0,str(R))
from src.analysis.group_disagreement import paired_groups
q=pd.read_csv(R/'docs/research/consensus-representation/outcome-variability/discussion-outcomes.csv');saved=json.loads((R/'docs/research/consensus-representation/source-data/results.json').read_text());models=['claude','gemini','mistral'];arms=['A-baseline','A-stateful'];rows=[]
for (model,item,arm),g in q.groupby(['model','item','label']):
 c=g[g.consensus];rows.append(dict(model=model,item=item,label=arm,n_discussions=len(g),n_consensus=len(c),consensus_rate=len(c)/len(g),final_mean_min=g.post_mean.min(),final_mean_max=g.post_mean.max(),final_mean_range=g.post_mean.max()-g.post_mean.min(),final_mean_variance=g.post_mean.var(ddof=1),distinct_final_means=g.post_mean.nunique(),both_sides_of_5=bool(g.post_mean.lt(5).any()and g.post_mean.gt(5).any()),
 agreement_mean_min=c.post_mean.min()if len(c)else np.nan,agreement_mean_max=c.post_mean.max()if len(c)else np.nan,agreement_mean_range=c.post_mean.max()-c.post_mean.min()if len(c)>=2 else np.nan,agreement_mean_variance=c.post_mean.var(ddof=1)if len(c)>=2 else np.nan,distinct_agreement_means=c.post_mean.nunique(),agreement_both_sides_of_5=bool(c.post_mean.lt(5).any()and c.post_mean.gt(5).any())))
t=pd.DataFrame(rows);assert len(t)==180
summary=[]
for (m,a),g in t.groupby(['model','label']):
 summary.append(dict(model=m,label=a,n_items=len(g),all_outcomes_differ_items=int(g.distinct_final_means.gt(1).sum()),all_both_sides_items=int(g.both_sides_of_5.sum()),at_least_two_agreements_items=int(g.n_consensus.ge(2).sum()),different_agreement_means_items=int((g.n_consensus.ge(2)&g.distinct_agreement_means.gt(1)).sum()),agreement_both_sides_items=int(g.agreement_both_sides_of_5.sum()),mean_item_final_mean_range=g.final_mean_range.mean(),mean_item_final_mean_variance=g.final_mean_variance.mean(),mean_item_agreement_rate=g.consensus_rate.mean()))
u=pd.DataFrame(summary)
# Independent check of point estimates against raw paired agent rows.
for m in models:
 a=paired_groups(pd.read_csv(R/f'data/study1/results/exploratory/{m}/a1r_agents.csv'),arms)
 for arm in arms:
  for item,g in a[a.label.eq(arm)].groupby('item_id'):
   means=g.groupby('block').post.mean();agreement=g.groupby('block').post.std(ddof=0).le(1);z=t[t.model.eq(m)&t.label.eq(arm)&t['item'].eq(item)].iloc[0]
   assert len(means)==z.n_discussions and agreement.sum()==z.n_consensus
   assert np.isclose(means.var(ddof=1),z.final_mean_variance)
   assert np.isclose(means.max()-means.min(),z.final_mean_range)
   assert int((means.lt(5).any()and means.gt(5).any()))==z.both_sides_of_5
  z=u[u.model.eq(m)&u.label.eq(arm)].iloc[0];original=saved['models'][m]['levels'][arm]['item_bootstrap']
  assert np.isclose(z.mean_item_agreement_rate,original['post_consensus']['estimate'])
  assert np.isclose(z.mean_item_final_mean_variance,original['post_between_unbiased']['estimate'])
t.to_csv(O/'item-outcomes.csv',index=False);u.to_csv(O/'model-summary.csv',index=False)
# Only the distribution display changes; no manuscript or original analysis outputs are edited.
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
fig,axs=plt.subplots(1,3,figsize=(13,4.5),sharex=True,sharey=True)
for ax,item,title in zip(axs,['Q2C','Q3C','Q5F'],['Aid to Central America','Emissions taxes / market incentives','Public health-insurance buy-in']):
 for arm,y,color in [('A-baseline',1,'#2776bd'),('A-stateful',0,'#d85a24')]:
  g=q[q.model.eq('claude')&q['item'].eq(item)&q.label.eq(arm)].sort_values('block')
  for off,(_,r)in zip(np.linspace(-.18,.18,len(g)),g.iterrows()):ax.scatter(r.post_mean,y+off,s=40,facecolors=color if r.consensus else 'none',edgecolors=color,lw=1)
  ax.text(.02,y+.26,f'{int(g.consensus.sum())}/{len(g)} agreement',transform=ax.get_yaxis_transform(),fontsize=9,color=color)
 ax.axvline(5,ls='--',color='#aaaaaa',lw=.8);ax.set(title=item+' | '+title,xlabel='Final discussion mean (0 oppose / 10 favor)',xlim=(-.4,10.4),ylim=(-.5,1.6),yticks=[0,1],yticklabels=['Stateful','Ordinary'],xticks=[0,2,4,5,6,8,10]);ax.grid(axis='x',alpha=.12)
fig.suptitle('Both ordinary and stateful discussions can reach different conclusions on the same policy',fontsize=13)
fig.text(.5,.025,'Claude: one point per discussion; filled points meet final within-discussion SD <= 1, hollow points do not.\nSame compositions paired across conditions; agreement subsets differ. Vertical offsets only prevent overlap.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.15,1,.93),w_pad=2)
for ext in ['png','pdf']:fig.savefig(O/f'ordinary-and-stateful-outcomes.{ext}',dpi=200)
plt.close(fig)
def table(head,rows):return '| '+' | '.join(head)+' |\n|'+'|'.join('---'for _ in head)+'|\n'+'\n'.join('| '+' | '.join(str(z)for z in row)+' |'for row in rows)+'\n'
def f(z):return f"{z['estimate']:.3f} [{z['ci'][0]:.3f}, {z['ci'][1]:.3f}]"
s='''# 일반 토론도 서로 다른 결론에 도달하는가? — 데이터 확인

2026-10-21. 저자의 지적에 따라 일반 토론을 명시적 기준으로 다시 확인했다. **원고·수정 계획·체크리스트 문구는 이번 점검에서 바꾸지 않았다.** 기존 공통 구성의 일반/상태 기반 자료를 사용한 추가 기술 점검이다.

**확인 결과:** 일반 토론에서도 같은 정책의 서로 다른 토론들은 같은 결론에 도달하지 않았다. 세 모델·두 조건 모두 30문항 각각에서 토론별 최종 평균이 둘 이상이었다. 합의한 토론만 보더라도 일반 토론에서 서로 다른 합의점이 존재했다. 따라서 ‘상태 기반에서만 결론이 달라진다’는 해석은 맞지 않는다.

서로 다른 결론이 있다는 사실과, 그 차이가 조건 간 얼마나 커졌는지는 별개다. 전체 토론 최종 평균의 문항별 분산을 평균하면 상태 기반에서 세 모델 모두 더 컸다. 이는 일반 토론의 변동이 없었다는 뜻이 아니라 **이미 있던 변동이 평균적으로 더 커졌다**는 결과다. 모든 문항이 같은 폭으로 커졌다는 뜻도 아니다.

## 1. 전체 토론 결론의 차이와 합의율

30문항 동일 가중치다. 분산은 문항 안 토론별 최종 평균에 G−1 분모를 사용했다. 점수 제곱 단위이며, 합의율은 SD≤1을 충족한 토론 비율의 문항 평균이다.

'''
rows=[]
for m in models:
 b=saved['models'][m]['levels'][arms[0]]['item_bootstrap'];a=saved['models'][m]['levels'][arms[1]]['item_bootstrap'];d=saved['models'][m]['rules_minus_baseline']['item_bootstrap']['post_between_unbiased']
 rows.append([m.title(),f"{100*b['post_consensus']['estimate']:.1f}% → {100*a['post_consensus']['estimate']:.1f}%",f"{b['post_between_unbiased']['estimate']:.3f}",f"{a['post_between_unbiased']['estimate']:.3f}",f(d)])
s+=table(['모델','합의율: 일반→상태 기반','일반: 결론 분산','상태 기반: 결론 분산','분산 차이 [95% 구간]'],rows)
s+='''
- **관찰:** 일반 토론의 분산부터 0보다 컸다. 상태 기반−일반의 분산 차이는 세 모델에서 양수이며 5,000회 문항 짝 재표집 구간도 0보다 컸다. 구간은 기존 추가 분석의 저장값을 그대로 사용했다.
- **해석:** ‘일반은 공통 결론, 상태 기반은 다른 결론’이라는 대비가 아니라, 두 조건 모두 토론별 결론 차이가 존재하는 가운데 상태 기반의 평균적인 퍼짐이 더 컸다.
- **수치 범위:** 이 표의 G−1 분산은 기존 본문 Fig.5의 G 분모 분산과 다르다. 43.1%는 문항 동일 가중치이며 기존 집단 동일 가중 합의율 43.5%를 수정한 값이 아니다.

## 2. 차이가 단지 소수점 수준인가?

토론 평균이 척도 중간인 5점 미만과 초과에 각각 나타나는 문항도 계산했다. 이는 평균 점수 위치를 분류한 기술 지표이며 개별 구성원이 모두 찬성·반대한다는 뜻은 아니다.

'''
s+=table(['모델·조건','토론별 평균이 서로 다른 문항','평균이 5점 아래·위에 각각 있는 문항','문항별 최댓값−최솟값의 평균'],[[r.model.title()+' '+('일반'if r.label==arms[0]else'상태 기반'),str(r.all_outcomes_differ_items)+'/30',str(r.all_both_sides_items)+'/30',f'{r.mean_item_final_mean_range:.2f}점']for r in u.itertuples()])
s+='''
- **관찰:** 일반 토론에서도 양쪽 방향의 평균이 나온 문항은 Claude 20개, Gemini 27개, Mistral 22개였다. 문항별 최종 평균 범위의 평균도 각각 3.71·4.39·3.64점이었다.
- **해석:** 일반 토론의 결론 차이가 단순히 완전 동일 여부의 문제가 아니라 정책 방향 차이까지 포함함을 보여준다. 중간점 양쪽에 있는 문항 수와 분산은 서로 다른 지표라 조건별 증가 방향이 항상 같을 필요는 없다.

## 3. 합의한 토론만 보아도 일반 토론의 합의점은 다른가?

합의 토론이 2개 이상인 문항에서만 합의점의 서로 다름을 판단했다. 0개이면 합의점이 없고 1개이면 토론 사이 합의점 변동을 평가하지 않는다.

'''
s+=table(['모델·조건','합의 토론 ≥2개인 문항','그중 서로 다른 합의점이 있는 문항','합의점이 5점 아래·위에 각각 있는 문항'],[[r.model.title()+' '+('일반'if r.label==arms[0]else'상태 기반'),str(r.at_least_two_agreements_items)+'/30',str(r.different_agreement_means_items)+'/'+str(r.at_least_two_agreements_items),str(r.agreement_both_sides_items)+'/30']for r in u.itertuples()])
s+='''
- **관찰:** Claude 일반 토론에서는 합의 토론이 두 개 이상인 20문항 모두 합의점이 서로 달랐다. 그중 5문항에서는 5점 미만과 초과의 합의점이 함께 있었다. Mistral 일반 토론도 각각 15문항과 3문항이었다. Gemini 일반 토론은 합의 토론이 두 개 이상인 문항이 1개뿐이었다.
- **해석:** 합의점의 다양성은 상태 기반 조건에서만 생긴 현상이 아니다. 다만 조건별 합의 토론 수와 구성은 다르므로 이 표의 문항 수나 범위를 상태 기반 규칙이 합의점 분산을 늘렸다는 독립 효과 추정으로 사용하지 않는다. 전체 토론의 분산 비교와 구별한다.

## 4. 앞서 고른 세 정책을 두 조건에서 나란히 보기

![일반 토론과 상태 기반 토론의 실제 결론](ordinary-and-stateful-outcomes.png)

- **가로축:** 토론 하나의 최종 평균 점수, 0=반대·10=찬성. 회색 5점 점선은 척도 중간이다.
- **세로축:** 위는 일반 토론, 아래는 상태 기반 토론. 같은 정책의 각 행에는 동일한 16개 구성이 대응된다. 점의 세로 위치를 조금 벌린 것은 겹침을 피하기 위해서다.
- **점:** 한 점은 토론 하나다. 파란색은 일반, 주황색은 상태 기반이다. 채운 점은 내부 합의 SD≤1, 빈 점은 미충족이다. 채운 점들의 가로 분포가 합의점 분포다.
- **관찰:** 일반 토론의 채운 점들도 모두 한 위치에 모이지 않는다. 원조에서는 일반 토론부터 반대·찬성 양쪽 합의점이 나타난다. 탄소세 일반 토론은 합의가 한 번뿐이어서 합의점의 안정성을 평가할 수 없다.
- **해석:** 합의율, 모든 토론의 결론 분포, 합의한 토론만의 합의점 분포를 함께 보여줘야 두 조건의 공통점과 차이가 드러난다.

'''
rows=[]
for item,ko in [('Q2C','중미 원조'),('Q3C','탄소세·시장 유인'),('Q5F','공공보험 구매 허용')]:
 row=[item+' '+ko]
 for arm in arms:
  r=t[t.model.eq('claude')&t['item'].eq(item)&t.label.eq(arm)].iloc[0]
  desc=f'{int(r.n_consensus)}/{int(r.n_discussions)}; '
  if r.n_consensus==1:desc+=f'{r.agreement_mean_min:.1f}점 한 사례'
  else:desc+=f'{r.agreement_mean_min:.1f}–{r.agreement_mean_max:.1f}점'
  row.append(desc)
 rows.append(row)
s+=table(['정책','일반: 합의 수/토론 수; 합의점','상태 기반: 합의 수/토론 수; 합의점'],rows)
s+='''
## 5. 데이터 확인 후의 판단

원래 계획 문장은 일반 토론도 토론마다 결론이 다르다는 사실을 명시하지 않아 오해의 여지가 있다. 데이터상 핵심은 **두 조건 모두 결론 변동이 있고, 상태 기반에서는 일반보다 내부 합의율과 전체 토론 결론의 평균 분산이 함께 커졌다는 것**이다. 합의한 토론만의 분산 증가까지 세 모델 공통 결과로 확장하지 않는다.

이번 점검은 문구 수정 여부를 판단할 자료이며 원고·수정 계획·체크리스트는 아직 바꾸지 않았다. 만약 반영한다면 ‘두 조건의 공통점→규칙 추가 후의 차이’ 순서로 서술하고, 앞의 나란한 그림·표를 근거로 연결하는 것이 자료에 맞는다.

[문항별 180행](item-outcomes.csv) · [모델·조건별 집계](model-summary.csv) · [그림 PDF](ordinary-and-stateful-outcomes.pdf) · [검증 기록](verification.json)
'''
(O/'README.md').write_text(s)
inputs=[Path(__file__),R/'docs/research/consensus-representation/outcome-variability/discussion-outcomes.csv',R/'docs/research/consensus-representation/source-data/results.json',R/'src/analysis/group_disagreement.py']+[R/f'data/study1/results/exploratory/{m}/a1r_agents.csv'for m in models]
(O/'verification.json').write_text(json.dumps({'date':'2026-10-21','status':'passed','raw_paired_agent_points':'all 180 item-model-condition counts, variances, ranges and side-of-midpoint flags checked','saved_aggregate_estimates':'agreement and sample between-discussion variances match existing results.json','scope':'No manuscript/plan/checklist changes; all-discussion variability distinguished from conditional agreement-endpoint variability','input_hashes':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in inputs}},ensure_ascii=False,indent=2)+'\n')
print(u.to_string(index=False));print('Saved explicit ordinary/stateful comparison; manuscript, plan and checklist unchanged.')
