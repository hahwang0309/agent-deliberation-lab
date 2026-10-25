"""Readable post-hoc report and scientific figures, entirely from saved estimates."""
from pathlib import Path
import json,hashlib,os
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/consensus-representation-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
R=Path(__file__).resolve().parents[1];O=R/'docs/research/consensus-representation';S=O/'source-data';F=O/'figures'
x=json.loads((S/'results.json').read_text());room=json.loads((S/'group-party-adjustment.json').read_text());MODELS=['claude','gemini','mistral'];ARMS=['A-baseline','A-stateful'];records=[]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold','pdf.fonttype':42})
def get(path,label):
 v=x
 for k in path:v=v[k]
 records.append({'label':label,'source':'docs/research/consensus-representation/source-data/results.json','json_path':path,'record':v})
 return v

def point(ax,r,y,color,marker='o',label=None):
 e=r['estimate'];ci=r.get('ci');ax.errorbar(e,y,xerr=[[e-ci[0]],[ci[1]-e]]if ci else None,fmt=marker,color=color,capsize=3,label=label)

def level(m,a,k):return get(['models',m,'levels',a,'item_bootstrap',k],m+' '+a+' '+k)
def fmt(v,scale=1,precision=3):
 e=v['estimate']*scale;l,h=[z*scale for z in v['ci']];return f'{e:.{precision}f} [{l:.{precision}f}, {h:.{precision}f}]'
def table(head,rows):return '| '+' | '.join(head)+' |\n|'+'|'.join('---'for _ in head)+'|\n'+'\n'.join('| '+' | '.join(str(v)for v in row)+' |'for row in rows)+'\n'
def save(fig,name):
 for ext in ['png','pdf']:fig.savefig(F/f'{name}.{ext}',dpi=220)
 plt.close(fig)

fig,axs=plt.subplots(1,2,figsize=(12.5,6.5));labels=['Human: actual rooms','Human: 5-person panels']+[m.title()for m in MODELS]
for ax,key,title,xlabel in [(axs[0],'post_consensus','a  How often are opinions close?','Agreement rate: final within-group SD <= 1'),(axs[1],'post_between_unbiased','b  How different are group conclusions?','Variance between final group means\n(score points squared)')]:
 for y,name in enumerate(['native','balanced5']):point(ax,get(['human',name,'item_bootstrap',key],name+' '+key),y,'#666666'if y==0 else'#222222','s'if y==0 else'D')
 for i,m in enumerate(MODELS,2):
  for arm,off,col,mark,name in [('A-baseline',-.12,'#2776bd','o','Ordinary discussion'),('A-stateful',.12,'#d85a24','^','Stateful discussion')]:point(ax,level(m,arm,key),i+off,col,mark,name if i==2 else None)
 ax.set(yticks=range(5),yticklabels=labels,title=title,xlabel=xlabel,ylim=(4.6,-.6));ax.grid(axis='x',alpha=.15)
axs[0].xaxis.set_major_formatter(PercentFormatter(1));axs[0].set_xlim(-.01,.56);axs[0].legend(frameon=False,loc='lower right',fontsize=9)
fig.text(.5,.035,'Equal weight across 30 items. Five-person human panels: 2 D / 2 R / 1 Independent drawn from original larger rooms.\nIntervals: paired item bootstrap. Panel b uses sample variance (group-count denominator G-1).',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.12,1,1),w_pad=3);save(fig,'consensus-and-conclusions')

fig,axes=plt.subplots(2,2,figsize=(12.5,9));a,b,c,d=axes.flat
for i,m in enumerate(MODELS):
 for arm,off,col,mark in [('A-baseline',-.1,'#2776bd','o'),('A-stateful',.1,'#d85a24','^')]:point(a,get(['models',m,'matched',arm+'_human_mover_direction'],m+' '+arm+' human direction'),i+off,col,mark)
 point(b,get(['models',m,'matched','rules_minus_baseline_mae'],m+' human movement error change'),i,'#2776bd')
 point(d,get(['models',m,'party_profiles','rules_minus_baseline','distance_from_human_final_party_gap'],m+' error in human final party gap change'),i,'#2776bd')
for ax,title,xlabel in [(a,'a  Direction of movement relative to the source human','Direction match among humans who changed their score'),(b,'b  Error in individual human movement','Change in absolute error (stateful - ordinary)'),(d,'d  Error in reproducing human party gaps','Change in absolute gap error (stateful - ordinary)')]:
 ax.set(yticks=range(3),yticklabels=[m.title()for m in MODELS],ylim=(2.6,-.6),title=title,xlabel=xlabel);ax.grid(axis='x',alpha=.15)
a.xaxis.set_major_formatter(PercentFormatter(1));a.set_xlim(.25,.75)
for ax in [b,d]:ax.axvline(0,color='#777',ls='--')
point(c,get(['models','claude','party_profiles','Human','mean_absolute_party_gap'],'Human matched party gap'),0,'#333','D')
for i,m in enumerate(MODELS,1):
 for arm,off,col,mark in [('A-baseline',-.1,'#2776bd','o'),('A-stateful',.1,'#d85a24','^')]:point(c,get(['models',m,'party_profiles',arm,'mean_absolute_party_gap'],m+' '+arm+' absolute party gap'),i+off,col,mark)
c.set(yticks=range(4),yticklabels=['Human (matched)']+[m.title()for m in MODELS],ylim=(3.6,-.6),title='c  How much difference remains between parties?',xlabel='Mean absolute Democratic-Republican gap (0-10 points)');c.grid(axis='x',alpha=.15)
fig.text(.5,.025,'Blue circles: ordinary discussion; orange triangles: stateful. Whiskers: paired item-bootstrap 95% intervals.\nHuman-room cluster sensitivity for individual movement is reported separately. Smaller error is closer to human outcomes.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.09,1,1),h_pad=3,w_pad=3);save(fig,'movement-and-party-positions')

head='''# 합의는 늘면서 초기·정당 관점도 보존되는가?

계산·검토: 2026-10-21. 저자의 질문에 따라 기존 설문 결과를 이용해 추가한 **사후 탐색 분석**이다. [계획](AnalysisPlan.md)은 새 지표 계산 전에 기록했고, 앞서 본 기존 합의율·이동 계수는 그 기록에 명시했다. 분석·보고는 새로운 실험이나 API 호출 없이 진행했다.

용어 구분·무작위 구성 설계·주제별 결론 분포와 민주당 방향 이동은 [추가 확인 문서](OutcomeVariabilityAndPartyMovement.md)에 정리했다. 토론 사이 결론 변동과 토론 안 정당 간 차이를 구별한다.

**결론은 부분적으로 지지되며 모델에 따라 다르다.** 세 모델의 상태 기반 토론은 높은 합의를 만들면서도 정당별 평균 입장의 상대적 방향을 모두 지우지는 않았다. 모델 기본 입장과의 거리가 커지고, 모두 같은 방향으로 움직이는 집단의 비율도 작아지는 양상이 있었다. 그러나 ‘일반 토론보다 개별 이동과 정당별 결과가 더 인간과 비슷해졌다’는 증거는 Gemini에서 가장 일관됐고, Claude·Mistral에서는 측정값과 불확실성 평가에 따라 달랐다. 집단별 결론 차이가 더 커졌다는 사실 자체를 정당 대표성의 증거로 삼을 수는 없다.

## 1. 합의율과 집단별 결론: 인간과 직접 비교

![합의율과 집단별 결론](figures/consensus-and-conclusions.png)

- **왼쪽 가로축:** 한 집단의 최종 정책 점수 표준편차가 1점 이하인 비율이다. 같은 집단 구성원의 점수가 가까우면 합의로 분류한다. 단위는 %다.
- **오른쪽 가로축:** 같은 문항을 토론한 집단들의 최종 평균이 얼마나 다른지다. 클수록 서로 다른 회의가 다른 결론을 냈다. 단위는 정책 점수의 제곱이다. 집단 수 차이를 고려해 통상적인 표본분산 분모 G−1을 사용했다.
- **세로축:** 인간 실제 토론방, 인간 다섯 명 표준화 패널, 세 AI 모델이다. 파란 원은 일반 토론, 주황 삼각형은 상태 기반 토론이다.
- **인간 다섯 명 패널:** 실제로 다섯 명끼리 새로 토론한 것이 아니라, 원래 더 큰 방에서 토론한 사람 중 민주당 2명·공화당 2명·무당층 1명의 응답을 추출한 측정이다. 방×문항 1,200개 중 이 구성이 가능한 981개를 사용했다.
- **핵심 관찰:** 상태 기반 토론의 합의율은 세 모델 모두 인간 다섯 명 패널보다 높았다. 집단별 최종 평균 차이는 Gemini에서 인간 패널보다 컸지만 Claude·Mistral에서는 뚜렷한 차이가 확인되지 않았다. 아래 표의 범위를 함께 읽어야 한다.

'''
rows=[]
for label,k in [('인간 실제 방','native'),('인간 5명 패널','balanced5')]:
 q=x['human'][k]['item_bootstrap'];rows.append([label,fmt(q['post_consensus'],100,1)+'%',fmt(q['pre_between_unbiased']),fmt(q['post_between_unbiased'])])
for m in MODELS:
 for arm in ARMS:
  q=x['models'][m]['levels'][arm]['item_bootstrap'];rows.append([m.title()+' '+('일반'if arm==ARMS[0]else'상태 기반'),fmt(q['post_consensus'],100,1)+'%',fmt(q['pre_between_unbiased']),fmt(q['post_between_unbiased'])])
text=head+table(['대상','합의율 [95% 구간]','초기 집단 평균 사이 분산','최종 집단 평균 사이 분산'],rows)
text+='\n**상태 기반 AI − 인간 5명 패널의 최종 평균 사이 분산 차이:**\n\n'+table(['모델','차이 [95% 구간]'],[[m.title(),fmt(x['models'][m]['human_comparisons'][ARMS[1]]['balanced5']['post_between_unbiased'])]for m in MODELS])
text+='''
**비교 기준을 구별해야 한다.** 인간 실제 방에서는 토론 전보다 토론 후에 집단 평균 사이 분산이 커졌다(1.00→1.44). 반면 세 AI 모델에서 공통으로 관찰된 것은 **일반 토론 후보다 상태 기반 토론 후의 집단 평균 사이 분산이 더 크다**는 결과다. 초기와 상태 기반 후를 비교한 점추정은 Claude 1.86→1.81, Gemini 1.86→2.69, Mistral 1.87→1.87로 다르다. Claude는 초기보다 약간 작고 Mistral은 거의 같으며, Gemini에서 커졌다. ‘AI도 모두 토론 전보다 집단 간 차이가 커졌다’고 묶어 서술하지 않는다.

**합의율과 집단 사이 차이는 다른 층위의 측정이다.** 가령 같은 문항에 대해 1번 방의 다섯 명이 모두 3점, 2번 방의 다섯 명이 모두 7점에 도달하면 두 방 모두 합의했지만 두 방의 결론은 다르다. 따라서 방 안 합의가 늘면서 방 사이 결론 차이가 더 클 수 있다. 위 분산은 문항마다 모든 방을 포함해 계산한 뒤 30문항을 평균했다. 합의하지 못한 주제나 방만 뽑은 결과가 아니다. 합의한 방만의 결론 분산이나 문항별 경로는 이 평균만으로 판단하지 않는다.

사람 수가 더 많은 실제 인간 방과 AI 다섯 명 방을 비교할 때와 인간 다섯 명 패널로 맞출 때도 결과가 달라진다. 인간과의 수치 비교에서는 그 표집틀을 함께 적는다.

기존 Claude 합의율 43.5%와 새 표의 43.1%가 다른 이유는 기존 N2b가 집단에 같은 가중치를, 이번 비교가 30문항에 같은 가중치를 주기 때문이다. 문항당 집단은 개발 8개·잠금 16개로 달랐다. 기존 인간 5명 합의율 약 5.6%는 정당 2/2/1 추출이 불가능한 방에서도 무작위 5명을 사용한 결과이며, 이번 엄격한 정당 혼합 패널의 5.4%와 표집틀이 다르다. 기존 결과는 그대로 보존했다.

## 2. 사람의 실제 이동과 더 비슷해졌는가?

이 절에서 인간과의 유사성은 비교 지표이며 성과의 우열 기준이 아니다. 가치 판단 문제에서는 인간의 입장 차이 유지와 낮은 합의율도 함께 나타날 수 있다. 인간과 닮은 이동, 합의의 양, 정당별 차이 보존, 도출한 대안의 가치는 서로 구별해서 평가해야 한다.

![개인 이동과 정당 입장](figures/movement-and-party-positions.png)

- **a 가로축:** 원래 대응시킨 인간이 점수를 바꾼 사람·문항에서, AI도 같은 방향으로 점수를 바꾼 비율이다. 인간이 높였을 때 AI도 높이면 일치, AI가 유지하거나 낮추면 불일치다. 실제 점수 변화량의 일치를 뜻하지 않는다.
- **b 가로축:** AI와 대응 인간의 점수 변화량 사이 절대 오차가 규칙 추가 후 얼마나 달라졌는지다. 음수이면 인간 변화량과 가까워졌고, 양수이면 멀어졌다. 0–10점 단위다.
- **c 가로축:** 같은 문항의 민주당·공화당 최종 평균 점수 차이의 절댓값이다. 낮으면 정당 평균이 가까워졌다. 인간 행은 Claude/Gemini 대응 표본이며 Mistral 인간 기준도 0.001점 이내로 같다.
- **d 가로축:** AI의 양당 격차가 인간 최종 양당 격차와 얼마나 다른지의 절대 오차 변화다. 음수는 인간 결과에 더 가까워졌다는 뜻이다.
- **핵심 관찰:** Gemini의 이동 방향과 정책별 정당 결과는 상태 기반 조건에서 인간에 더 가까워졌다. Claude는 개인 이동 방향이 일부 가까워지는 단서가 있지만 변화량 오차가 줄지 않았고, 양당 최종 간격은 인간보다 더 많이 압축되는 양상이었다. Mistral의 개인 이동이 인간과 더 유사해졌다는 결과는 뚜렷하지 않았다.

'''
rows=[]
for m in MODELS:
 q=x['models'][m];s=q['matched'];rows.append([m.title(),fmt(s[ARMS[0]+'_human_mover_direction'],100,1)+'%',fmt(s[ARMS[1]+'_human_mover_direction'],100,1)+'%',fmt(s['rules_minus_baseline_human_mover_direction'],100,2)+'%p',fmt(q['source_human_room_cluster_contrasts']['human_mover_direction'],100,2)+'%p',fmt(s['rules_minus_baseline_mae'])])
text+=table(['모델','인간 이동 방향 일치: 일반','상태 기반','변화: 문항 재표집','변화: 원 인간 방 재표집','개인 변화량 절대 오차 변화'],rows)
text+='''
Claude의 방향 일치율 증가는 문항 재표집 구간에는 0이 들어가고 원 인간 방 재표집 구간에서는 0보다 컸다. 표집 변동을 어떻게 평가하는지에 민감하므로 일관된 인간 유사성 증가로 해석하지 않는다. Gemini는 두 방식 모두 같은 양의 방향이었다. 세 모델 모두 개인 변화량 절대 오차가 줄었다는 뚜렷한 결과는 없었다.

같은 사람이 여러 AI 집단에 등장한 횟수로 그 사람의 인간 관측을 늘리지 않았다. 각 AI 맥락에서 오차·방향 일치 지표를 계산한 뒤 같은 원 인간 persona×문항 안에서 평균하고, 문항 안 persona에 같은 가중치를 주었다. Claude/Gemini는 조건별 2,044개의 유효 AI 사람×문항 기록을 인간과 연결했고, 중복을 합치면 1,863개 persona×문항이다. Mistral은 각각 2,039개·1,858개다. 각 조건의 36개 기록은 대응 인간의 유효 사후 응답이 없어 제외했다. 대응한 사람은 세 모델 모두 492명이다.

## 3. 정당 입장을 모두 잃은 합의인가?

문항별로 민주당과 공화당의 평균을 따로 계산했다. 개인 한 명이 정당을 얼마나 충실히 대표하는지, 실제 이해관계가 보존되는지를 직접 평가한 것은 아니다.

**세 모델의 두 토론 조건 모두 30문항에서 초기 양당 평균의 상대적 순서를 유지했다.** 처음 민주당 평균이 더 찬성한 문항은 나중에도 민주당 평균이 더 찬성했고, 반대 순서의 문항도 그 순서를 유지했다. 초기 양당 간격이 1점 이상인 28문항에서도 같았다. 즉 정당별 평균을 모았을 때의 차이가 완전히 사라지거나 뒤집힌 결과는 아니었다. 다만 간격의 크기는 상태 기반 조건에서 세 모델 모두 줄었다.

'''
rows=[]
for m in MODELS:
 q=x['models'][m];p=q['party_profiles'];rows.append([m.title(),fmt(p['Human']['mean_absolute_party_gap']),fmt(p[ARMS[0]]['mean_absolute_party_gap']),fmt(p[ARMS[1]]['mean_absolute_party_gap']),fmt(p['rules_minus_baseline']['distance_from_human_final_party_gap'])])
text+=table(['모델의 대응 표본','인간 최종 양당 간격','AI 일반','AI 상태 기반','인간 최종 간격과의 절대 오차 변화'],rows)
text+='''
‘양당 간격이 작아짐’ 자체는 합의와 함께 나타날 수 있다. 여기서는 간격을 많이 유지할수록 항상 좋다고 평가하지 않았다. 초기 정당 순서의 유지, 실제 인간의 이동과 간격, 집단 안의 합의와 여러 집단의 결론을 함께 비교했다.

**정책×정당별 평균 이동량을 인간과 비교한 절대 오차:**\n\n'''
text+=table(['모델','일반 토론','상태 기반','규칙 추가 변화 [95% 구간]'],[[m.title(),fmt(x['models'][m]['matched'][ARMS[0]+'_party_shift_mae']),fmt(x['models'][m]['matched'][ARMS[1]+'_party_shift_mae']),fmt(x['models'][m]['matched']['rules_minus_baseline_party_shift_mae'])]for m in MODELS])
text+='\n인간의 정당 평균이 0.5점 이상 움직인 정책×정당 44셀의 방향 일치(보조 기준):\n\n'+table(['모델','일반','상태 기반','차이 [95% 구간]'],[[m.title(),fmt(x['models'][m]['party_cell_movement_direction'][ARMS[0]],100,1)+'%',fmt(x['models'][m]['party_cell_movement_direction'][ARMS[1]],100,1)+'%',fmt(x['models'][m]['party_cell_movement_direction']['rules_minus_baseline'],100,1)+'%p']for m in MODELS])
text+='''
### 같은 토론방 안에서도 정당별 차이가 남았는가?

앞의 30문항 결과는 여러 방의 같은 정당 사람들을 모아 계산한 것이다. 이를 확인한 뒤 **각 방의 민주당 평균과 공화당 평균**을 따로 계산하는 추가 탐색을 했다. ‘순서 유지’는 예를 들어 처음 민주당 평균이 공화당 평균보다 높았으면, 마지막에도 더 높은 경우다. 양당이 가까워지되 서로의 위치가 뒤집히지 않은 합의도 포함한다. 처음 두 정당 평균이 같은 방은 순서 유지·동률·역전의 조건부 비교에서 제외했다.

'''
text+=table(['대상','합의한 방에서 정당 순서 유지 [95% 구간]','최종 양당 평균 동률','정당 순서 역전'],[[name,fmt(v['order_retained_among_consensus'],100,1)+'%',fmt(v['order_tied_among_consensus'],100,1)+'%',fmt(v['order_reversed_among_consensus'],100,1)+'%']for name,v in [('인간 5명 패널',room['human']['balanced5'])]+[(m.title()+' '+('일반'if a==ARMS[0]else'상태 기반'),room['models'][m][a])for m in MODELS for a in ARMS]])
text+='''
- **관찰:** 상태 기반 합의 집단에서 초기 정당 순서가 남는 비율은 Claude 81.3%, Gemini 72.7%, Mistral 70.7%였다. 합의는 개인 점수가 가까워졌다는 기준(SD≤1)이므로 작은 정당 차이가 함께 남을 수 있다.
- **해석:** 합의가 늘었다고 해서 양당 관점의 상대적 차이까지 모두 지워진 것은 아니다. 다만 상대적 순서가 남는 것과 실제 정당의 핵심 이해관계·양보 한계가 보존되는 것은 구별된다.

조건마다 합의한 방이 달라지는 영향을 함께 보기 위해, **전체 방 중 ‘합의에 도달하면서 초기 정당 순서도 유지한 방’의 비율**도 비교했다.

'''
text+=table(['모델','일반','상태 기반','증가 [95% 구간]'],[[m.title(),fmt(room['models'][m][ARMS[0]]['party_order_retained_and_consensus'],100,1)+'%',fmt(room['models'][m][ARMS[1]]['party_order_retained_and_consensus'],100,1)+'%',fmt(room['models'][m]['rules_minus_baseline']['party_order_retained_and_consensus'],100,1)+'%p']for m in MODELS])
text+='''
세 모델 모두 이 동시 발생 비율이 증가했고 문항 재표집 구간도 0보다 컸다. 이는 이번 질문에 가장 직접적인 결과다. ‘합의가 더 많다’와 ‘정당별 초기 차이가 남는다’가 서로 다른 집단에서만 관찰된 것이 아니라, **같은 집단에서 함께 나타나는 사례가 늘었다.**

## 4. 모델 공통 입장으로 한쪽 쏠림이 강해진 것인가?

D는 같은 인물 설정에서 초기 점수를 따로 주지 않고 물었을 때의 기본 입장이다. 사후 응답과 D의 거리가 클수록 공통 기본 입장에 덜 가까운 결과이며, 그 자체로 정치적 대표성이 높다는 뜻은 아니다. ‘같은 방향 이동’은 한 방에서 점수를 올린 사람과 내린 사람이 섞이지 않고 모두 같은 방향으로 움직인 경우다. 점수 유지자는 허용하되 최소 한 명은 움직여야 한다.

'''
rows=[]
for m in MODELS:
 q=x['models'][m];b=q['levels'][ARMS[0]]['item_bootstrap'];t=q['levels'][ARMS[1]]['item_bootstrap'];c=q['rules_minus_baseline']['item_bootstrap'];rows.append([m.title(),fmt(b['individual_default_distance']),fmt(t['individual_default_distance']),fmt(c['individual_default_distance']),fmt(b['one_way'],100,1)+'% → '+fmt(t['one_way'],100,1)+'%',fmt(c['group_mean_distance_from_initial'])])
text+=table(['모델','개인 사후−D 거리: 일반','상태 기반','거리 증가 [95% 구간]','한 방 같은 방향 이동: 일반→상태 기반','집단 평균의 초기 평균까지 거리 변화'],rows)
text+='''
- **관찰:** 세 모델 모두 상태 기반 조건의 사후 입장이 D에서 더 멀었다. 한 방의 같은 방향 이동 비율은 감소했고 Claude·Mistral의 구간은 0보다 작았다. 공통 모델 응답으로 일괄 이동한다는 설명은 이 결과와 잘 맞지 않는다.
- **해석:** 상태 기반은 같은 방 안에서 서로 다른 방향의 조정을 동반하면서 합의를 늘릴 수 있다. 그러나 자기 정당 관점의 지속이나 인간과 같은 이동은 앞의 별도 지표로 확인해야 한다.
- **앞선 질문의 확인:** 집단 초기 평균과 최종 평균의 연결이 강해진 것이 초기 평균까지의 거리가 줄었다는 뜻은 아니다. Claude에서는 그 거리 변화가 거의 없고, Gemini는 오히려 커졌으며, Mistral에서는 작아졌다.

### 합의는 어떤 이동으로 만들어졌는가?

합의한 방만 남겨 구성원 중 점수를 높인 사람과 낮춘 사람이 함께 있는지 계산했다. 이런 **양방향 개인 이동**은 양쪽 정당이 각각 움직였다는 뜻과 다르다. 같은 정당 안에서도 서로 반대로 움직일 수 있으므로, 민주당 평균과 공화당 평균이 **서로의 초기 입장을 향해 둘 다 움직였는지**도 별도로 확인했다.

'''
text+=table(['대상','합의한 방 중 개인 양방향 이동','합의한 방 중 양당 평균 모두 상대 방향으로 이동'],[[name,fmt(v['two_way_among_consensus'],100,1)+'%',fmt(w['mutual_among_consensus'],100,1)+'%']for name,v,w in [('인간 5명 패널',x['human']['balanced5']['conditional_consensus_direction'],room['human']['balanced5'])]+[(m.title()+' '+('일반'if a==ARMS[0]else'상태 기반'),x['models'][m]['levels'][a]['conditional_consensus_direction'],room['models'][m][a])for m in MODELS for a in ARMS]])
text+='''
- **관찰:** Claude 상태 기반 합의 집단의 73.4%에서는 개인별 증가·감소 이동이 함께 있었다. 양당 평균이 모두 상대의 초기 입장을 향해 움직인 합의는 29.0%였다. Mistral은 각각 81.0%와 36.9%, Gemini는 50.0%와 11.9%였다.
- **해석:** 합의 가운데는 서로 다른 방향의 조정을 동반하는 경우가 있다. 그러나 양당 모두의 이동은 전체 합의 중 일부다. 한쪽 정당의 유지와 다른 쪽 이동 등 나머지 경로도 함께 존재한다. ‘상대 방향 이동’은 최종 설문 점수 변화로 정의했으며, 상대를 지나쳐 이동한 경우도 포함한다.

전체 방에서 ‘양당이 모두 상대 방향으로 움직이면서 합의한 방’은 다음과 같다.

'''
text+=table(['모델','일반','상태 기반','증가 [95% 구간]'],[[m.title(),fmt(room['models'][m][ARMS[0]]['mutual_party_approach_and_consensus'],100,1)+'%',fmt(room['models'][m][ARMS[1]]['mutual_party_approach_and_consensus'],100,1)+'%',fmt(room['models'][m]['rules_minus_baseline']['mutual_party_approach_and_consensus'],100,1)+'%p']for m in MODELS])
text+='''
Claude·Mistral에서는 이 동시 발생 비율이 증가했고 구간이 0보다 컸다. Gemini는 점추정은 늘었으나 사례 수가 작아 구간에 0이 포함됐다. 합의 집단 안 비율만의 변화는 조건별 합의 집단의 구성도 반영하므로, 일반/상태 기반 짝을 유지한 이 전체 집단 기준 차이를 함께 제시했다.

## 5. 저자 가설의 현재 판단

| 가설의 구성 요소 | 판단 |
|---|---|
| 인간보다 합의가 많아지는가 | 세 모델의 상태 기반 조건에서 지지. 같은 0–10점·SD≤1 정의와 인간 5명 측정 표준화에서도 방향 유지. 일반 토론의 Gemini는 인간보다 낮았음. |
| 모든 정당 관점이 사라져 같은 입장으로 몰리는가 | 정당별 전체 평균의 상대적 순서는 두 조건·세 모델·30문항에서 유지. 같은 방 안에서도 합의와 초기 양당 순서 유지가 함께 일어나는 비율이 세 모델 모두 증가. 규칙 추가 후 D와의 거리도 커져 단순한 공통 기본 입장 쏠림 설명을 약화함. |
| 규칙이 개인을 더 인간처럼 움직이게 하는가 | Gemini에서 인간과의 방향 일치율 증가. Claude는 재표집 방식에 민감, Mistral은 뚜렷하지 않음. 개인 변화량의 인간 대비 오차는 세 모델 모두 뚜렷하게 줄지 않음. |
| 규칙이 정당별 결과를 더 인간처럼 만드는가 | Gemini에서 정당 평균 이동 오차와 최종 양당 간격 오차가 함께 줄어 가장 일관됨. Claude·Mistral은 인간 유사성이 일관되게 증가했다고 보기 어려움. |
| 인간보다 집단들이 더 다른 결론에 이르는가 | 5명·정당 혼합 표준화와 집단 수 분모를 맞추면 Gemini에서 더 큼. Claude·Mistral의 차이는 불확실. 인간 실제 방과의 단순 비교만으로 일반화하기 어려움. |
| 합의를 늘리면서 정책 대안 탐색의 가능성을 보이는가 | 가설의 가능성을 검토할 구체적 근거이며 특히 Gemini 사례가 부합. 실제 정치적 대표성·타협안 품질·실행 가능성·인간 의사결정 지원 성과는 이번 지표만으로 확정되지 않음. |

**원고에서 가능한 설명:** “상태 기반 규칙은 합의에 도달하면서 초기 양당 평균의 상대적 순서도 유지하는 집단의 비율을 세 모델 모두에서 높였다. 사후 입장은 모델 기본 응답에서 더 멀었으며, Gemini에서는 대응 인간의 이동 방향과 정당별 변화도 더 유사해졌다. 이 결합은 합의를 늘리는 현상을 단순한 정당 관점의 소거로 설명하기 어렵게 하지만, 인간 유사성의 변화는 모델과 지표에 따라 달랐다.”

이번 결과는 추가 탐색 자료로 따로 보존했으며, 기존 초록·본문의 결론은 자동으로 교체하지 않았다.

## 6. 방법·자료·검증

- 인간 분석 입력은 522명·40개 실제 방·14,431개 유효 사람×문항 응답이다. 문항별 방의 유효 인원은 6–16명이다. 사전·사후가 함께 유효한 응답을 사용했다.
- AI 일반/상태 기반은 같은 구성원·초기 점수의 짝만 사용했다. Claude/Gemini 416쌍, Mistral 415쌍이다. 개인별 D 거리에서는 D가 완전한 집단을 사용하여 Mistral은 414쌍이다.
- 문항별로 먼저 지표를 계산한 뒤 30문항에 같은 가중치를 주었다. 주 구간은 같은 문항을 모든 조건·지표에 함께 재표집한 5,000회 백분위 95% 구간이다. 이는 관측한 인물·방의 구성을 고정한 문항 간 변동을 나타낸다. 별도로 인간의 실제 토론방을 모든 문항과 함께 재표집하고, AI의 두 조건은 문항 안에서 같은 블록을 재표집한 민감도를 보존했다.
- 개인 이동의 원 인간 방 재표집은 각 인간과 그 사람에서 유래한 두 AI 조건을 함께 가중했다. AI 방들이 여러 원 인간 방의 인물을 혼합하므로 전체 교차 의존성을 완전히 모델링한 결과는 아니다. 여러 지표를 탐색했으며 새 p값·확증 주장은 제시하지 않았다.
- 인간 행사와 AI 실험은 토론 환경·자료·집단 크기와 구성이 달랐다. 인간 5명 패널은 원래 큰 방에서 토론한 사람들의 응답을 표준화한 것이며 실제 5명 토론 처치를 뜻하지 않는다. 이 비교를 같은 처치 효과로 해석하지 않았다.
- 같은 원 인간 persona와 초기 점수·정당 코드가 연결됐는지 전수 확인했다. 기존 등록·탐색 자료는 덮어쓰지 않았다. 과정 코딩의 사람 검증이 끝났다는 뜻도 아니다.

[방법 계획](AnalysisPlan.md) · [전체 추정·95% 구간·표본](source-data/results.json) · [방 안 양당 이동·순서](source-data/group-party-adjustment.json) · [입력 해시](source-data/input-manifest.json) · [검증 기록](source-data/verification.json)

재현: `OPENBLAS_NUM_THREADS=1 .venv/bin/python scripts/analyze_consensus_representation.py`, 이어서 `scripts/analyze_group_party_adjustment.py`, `scripts/report_consensus_representation.py`, `scripts/verify_consensus_representation.py`. 원 인간 자료가 로컬에 있어야 한다. 원자료를 이 보고서에 재배포하지 않았다.
'''
(O/'README.md').write_text(text)
(S/'figure-source-data.json').write_text(json.dumps({'figures':'consensus-and-conclusions; movement-and-party-positions','records':records},ensure_ascii=False,indent=2)+'\n')
(S/'report-input-manifest.json').write_text(json.dumps({str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [S/'results.json',S/'group-party-adjustment.json',Path(__file__)]},ensure_ascii=False,indent=2)+'\n')
print('Readable report, two PNG/PDF figures and',len(records),'traceable plot records written.')
