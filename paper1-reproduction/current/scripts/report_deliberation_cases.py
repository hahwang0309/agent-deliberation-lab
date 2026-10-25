"""Three illustrative within-item contrast cases with exact utterance evidence."""
from pathlib import Path
import os,json,hashlib
import numpy as np,pandas as pd
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/deliberation-cases-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1];O=R/'docs/research/deliberation-case-studies';T=O/'transcripts';F=O/'figures'
PAIRS=[('Q2C','중미 빈곤·폭력 완화를 위한 원조','Aid to Central America','Q2C-g11','Q2C-g08'),('Q3C','탄소배출 감축을 위한 세금·시장 유인','Taxes / market incentives for emissions','Q3C-g10','Q3C-g08'),('Q5F','누구나 Medicare형 공공보험 구매 허용','Public health-insurance buy-in','Q5F-g07','Q5F-g05')]
def load(stem,arm='stateful'):return json.loads((T/(stem+'-'+arm+'.json')).read_text())
def tab(head,rows):return '| '+' | '.join(head)+' |\n|'+'|'.join('---'for _ in head)+'|\n'+'\n'.join('| '+' | '.join(str(v)for v in row)+' |'for row in rows)+'\n'
def metric(d):
 q=pd.DataFrame(d['participants']);return dict(initial_mean=q.pre.mean(),final_mean=q.post.mean(),initial_sd=q.pre.std(ddof=0),final_sd=q.post.std(ddof=0),consensus=bool(q.post.std(ddof=0)<=1))
E=[
('Q2C-g11',19,'Reese',"I've moved toward undecided because I can't actually answer your core challenge.",'강한 찬성자도 효과 입증 요구에 답하기 어렵다고 인정한다. 이후 최종 설문에서는 3점으로 응답했다.'),
('Q2C-g11',20,'Finley',"safer spending on a small scale isn't the same as effective spending on the scale the problem requires.",'감독으로 지출 위험을 줄여도 국가 전체 규모의 문제를 해결할 효과가 생긴 것은 아니라는 논거다.'),
('Q2C-g08',19,'Drew','the uncertainty becomes manageable rather than disqualifying.','불확실성을 사업 포기의 이유 대신 측정·수정 가능한 위험으로 해석한다.'),
('Q2C-g08',23,'Taylor',"The accountability mechanisms Drew and I discussed—exit metrics, conditional funding tranches, documented benchmarks",'조건부 지급과 중단 기준을 논의했지만, 이를 집행할 정치적 의지가 남은 쟁점이라고 말한다.'),
('Q3C-g10',12,'Blake',"people don't have the luxury of waiting for a quarterly check",'에너지 비용은 먼저 오르는데 환급은 나중에 온다는 부담의 시간차를 받아들인다.'),
('Q3C-g10',24,'Taylor',"I can't support this tax proposal without concrete details on the dividend amounts",'환급액과 대체 수단이 구체화되지 않은 원안에는 찬성하기 어렵다고 결론짓는다.'),
('Q3C-g08',18,'Noel',"funded separately, not competing for the same revenue pool?",'탄소세와 별도 재원의 인프라 투자를 병행하는 조합을 제안한다.'),
('Q3C-g08',25,'Kendall',"What actually changed my mind was Noel's framing of a parallel approach",'본인은 병행 설계 논거 때문에 반대 쪽에서 찬성 쪽으로 바뀌었다고 설명한다.'),
('Q5F-g07',15,'Finley',"both of them are defending versions of the proposal that don't quite exist yet",'토론 중 설계된 대안과 원래 정책 문안이 다르다는 문제를 제기한다.'),
('Q5F-g07',24,'Morgan',"I genuinely don't know, and the materials don't help.",'의료기관 보호 장치를 붙인 뒤에도 비용 절감 효과가 남는지 판단하지 못한다고 말한다.'),
('Q5F-g05',17,'Harper',"Start smaller—open it to people in specific age groups or geographic areas",'특정 인구·지역부터 시범 도입하고 공급자 참여와 대기시간을 확인하는 대안을 제안한다.'),
('Q5F-g05',21,'Casey',"that's a different proposal than what's on the table",'단계적 도입과 안전장치는 원안과 다른 정책이라는 점을 직접 지적한다. 최종 점수는 5점이다.')]
evidence=[]
for stem,seq,speaker,quote,ko in E:
 d=load(stem);r=next(r for r in d['messages']if r['seq']==seq);assert r['speaker']==speaker and quote in r['content'],(stem,seq,quote)
 evidence.append(dict(stem=stem,discussion_id=d['discussion_id'],seq=seq,speaker=speaker,quote=quote,Korean_paraphrase=ko,quote_char_start=r['content'].index(quote),quote_char_end=r['content'].index(quote)+len(quote)))
(O/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
rows=[];participants=[]
for _,_,_,lo,hi in PAIRS:
 for stem in [lo,hi]:
  for arm in ['baseline','stateful']:
   d=load(stem,arm);rows.append(dict(stem=stem,label=arm,discussion_id=d['discussion_id'],**metric(d)))
   for p in d['participants']:participants.append(dict(stem=stem,label=arm,discussion_id=d['discussion_id'],**p))
pd.DataFrame(rows).to_csv(O/'discussion-metrics.csv',index=False);pd.DataFrame(participants).to_csv(O/'participant-scores.csv',index=False)
# Point-to-point lines join assigned initial and final survey scores within a single stateful discussion.
colors={1:'#286bb6',2:'#bd4b3d',3:'#777777'};markers={1:'o',2:'s',3:'^'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axs=plt.subplots(3,2,figsize=(12,12),sharey=True)
for i,(item,ko,en,lo,hi)in enumerate(PAIRS):
 for j,stem in enumerate([lo,hi]):
  ax=axs[i,j];d=load(stem);p=pd.DataFrame(d['participants']).sort_values(['party','participant']);m=metric(d)
  for off,(_,r)in zip(np.linspace(-.07,.07,5),p.iterrows()):ax.plot([off,1+off],[r.pre,r.post],color=colors[int(r.party)],marker=markers[int(r.party)],alpha=.85,ms=7,lw=1.6)
  ax.axhline(5,ls='--',color='#999999',lw=.8);ax.set(xticks=[0,1],xticklabels=['Assigned initial','Final survey'],xlim=(-.23,1.3),ylim=(-.3,10.4),yticks=[0,2,4,5,6,8,10],ylabel='Policy score: 0 oppose / 10 favor'if j==0 else'')
  ax.set_title(item+' | '+en+'\n'+stem+f" | mean {m['initial_mean']:.1f} -> {m['final_mean']:.1f}; final SD {m['final_sd']:.2f}",loc='left',fontsize=10);ax.grid(axis='y',alpha=.13)
handles=[plt.Line2D([],[],color=colors[p],marker=markers[p],label=lab)for p,lab in [(1,'Democratic role'),(2,'Republican role'),(3,'Independent role')]]
fig.legend(handles=handles,loc='lower center',ncol=3,frameon=False,bbox_to_anchor=(.5,.042))
fig.suptitle('Three policy items: internal agreement can end at different conclusions',fontsize=15)
fig.text(.5,.016,'Claude stateful discussions. Each line = one agent. Initial = assigned source-human score; final = post-discussion survey.\nAgreement criterion: within-discussion population SD <= 1. Horizontal offsets separate overlapping points; no confidence intervals.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.09,1,.95),h_pad=3,w_pad=2)
for ext in ['png','pdf']:fig.savefig(F/f'agent-score-trajectories.{ext}',dpi=180)
plt.close(fig)
summary=[['중미 원조','3.0 / 0.63','8.0 / 0.63','감독해도 규모에 맞는 효과가 입증되지 않음 ↔ 조건부 지급·중단 기준을 붙여 시도'],['탄소세·시장 유인','2.0 / 0.63','7.6 / 0.49','가계 비용은 즉시, 환급·대안은 불확실 ↔ 완만한 탄소세와 별도 재원 인프라 동시 추진'],['공공보험 구매 허용','3.6 / 0.49','6.8 / 0.98','공급자 보호가 경쟁·비용 절감을 무너뜨릴 수 있음 ↔ 시범 도입·접근성 점검 후 확대']]
s='''# 합의의 방향보다 논거와 조건을 함께 봐야 하는 세 토론 사례

선정·원문 검토: 2026-10-21. **Claude 상태 기반 토론 3개 정책 × 두 토론 = 6개 토론**을 설명용 사례로 골랐다. 각 토론의 일반 토론 대응 실행도 보존해 총 12개 원문을 연결했다. 새 시뮬레이션이나 API는 실행하지 않았다.

**공통 관찰:** 같은 정책에서 두 토론 모두 수치상 내부 합의(SD≤1)에 도달했지만, 한 토론은 반대 쪽·다른 토론은 찬성 쪽 평균으로 모였다. 중요한 차이는 단순히 서로 다른 위험을 언급했다는 데 있지 않다. 비슷한 위험을 인정한 뒤, 그 위험을 **원안에 찬성할 수 없는 이유**로 삼는지, **조건을 붙여 시도할 수 있는 이유**로 삼는지가 달랐다. 아래 발언 연결과 사후 설명은 이 분기를 검토할 구체적 자료다.

## 1. 세 사례 개요

값은 최종 평균 / 구성원 SD다. 평균은 정책 방향, SD는 같은 토론 안 의견의 가까움을 나타낸다. 0은 반대, 10은 찬성이고 5는 중간이다. 낮은 평균과 높은 평균은 서로 다른 구성의 토론이다.

'''+tab(['정책','낮은 평균의 합의','높은 평균의 합의','결론을 가른 논거의 초점'],summary)+'''
- **관찰:** 여섯 토론 모두 최종 SD≤1이지만 서로 다른 정책 방향으로 모였다. 집단 내부 수렴과 토론 사이 결론 차이가 함께 나타나는 실제 사례다.
- **해석:** 최종 점수만 전달하면 무엇을 전제로 합의했는지 놓친다. 원안의 위험·효과를 해석하는 기준과 토론 중 제안된 수정 조건을 함께 제공할 필요가 있다.

## 2. 개인 점수 변화

![각 토론의 초기 입장과 최종 점수](figures/agent-score-trajectories.png)

[PDF](figures/agent-score-trajectories.pdf) · [개인별 점수](participant-scores.csv)

- **가로축:** 왼쪽은 원 인간 응답에서 가져와 부여한 초기 입장, 오른쪽은 토론 후 설문 응답이다. 토론 중간 시점들은 그리지 않았다. 에이전트에는 초기 점수를 찬반 표현으로 전달했으므로 왼쪽이 별도 AI 사전 설문에서 측정한 점수라는 뜻은 아니다.
- **세로축:** 정책 점수 0–10. 0은 반대, 10은 찬성이다. 5점 점선은 척도 중간이다.
- **선·색·모양:** 선 하나는 한 에이전트다. 파랑 원은 민주당 역할, 빨강 네모는 공화당 역할, 회색 삼각형은 무당층 역할이다. 겹침을 줄이기 위해 가로 위치만 조금 벌렸다. 선은 초기·최종 두 점을 연결한 것이며 실제 변화 시점이나 발언별 경로를 나타내지 않는다.
- **패널:** 같은 행이 같은 정책이다. 왼쪽과 오른쪽은 서로 다른 구성의 토론이므로 초기 점수도 다르다. 제목의 mean은 평균, SD는 구성원 점수의 표준편차이며 오차막대나 추정 불확실성 구간이 아니다.
- **관찰:** 초기의 상반된 개인 점수가 가까워지는 경로와 이미 찬성자가 많은 구성에서 입장이 정리되는 경로가 함께 있다. 같은 정당 역할도 처음부터 같은 점수를 가진 것은 아니다.
- **해석:** 토론별 초기 구성을 함께 보여줘야 결론 차이를 이해할 수 있다. 이 사례만으로 논거의 효과를 초기 구성 효과에서 분리하지 않는다.

'''
texts=[
('Q2C','원조 효과가 입증돼야 하는가, 감독하며 시도할 수 있는가?',
 '양쪽 모두 부패·감독·정치적 의지의 문제를 인정한다. 낮은 평균 토론에서는 감독이 가능한 소규모 사업이라도 국가 전체의 폭력·이주 문제를 해결할 규모가 되지 않는다는 반론이 최종 이유에 반복된다. 높은 평균 토론에서는 불확실성을 탈락 사유로 삼는 대신, 조건부 지급·성과 지표·실패 시 중단으로 관리할 수 있다고 해석한다.',
 '인간에게 제시할 자료는 원조 찬반 한 숫자보다 ‘규모에 맞는 효과를 어떻게 입증할 것인가’와 ‘감독·중단 조건 아래 어디까지 시도할 것인가’라는 두 정책 경로다.'),
('Q3C','탄소 가격을 먼저 올릴 것인가, 전환 부담을 줄이는 조건을 붙일 것인가?',
 '양쪽 모두 에너지 가격 상승과 대체 수단·환급 사이의 시간차가 취약 가계에 부담이 된다는 점을 인정한다. 낮은 평균 토론에서는 구체적 보호책의 부재 때문에 원안을 지지하기 어렵다고 정리한다. 높은 평균 토론에서는 완만하고 예측 가능한 탄소세와 별도 재원의 인프라 투자를 병행하는 대안이 등장하고, 반대하던 참여자가 이를 자신의 입장 변화 이유로 지목한다.',
 '이 사례는 무엇을 지지했는지의 조건이 중요함을 보여준다. 높은 점수의 이유에는 탄소세 단독이 아니라 점진 도입·별도 재원·동시 인프라라는 정책 조합이 포함된다.'),
('Q5F','안전장치를 붙여도 원안의 비용 절감 논리가 유지되는가?',
 '양쪽 모두 의료기관 참여·지불 수준·농촌 접근성 위험을 논의하고 보완책을 제안한다. 낮은 평균 토론에서는 지불 하한과 지역별 조정이 필요하다면 당초의 경쟁·비용 절감 논리가 바뀐다고 판단한다. 높은 평균 토론에서는 특정 지역·인구의 시범 도입과 공급자 참여·대기시간 점검을 거친 확대를 지지할 조건으로 제시한다.',
 '특히 높은 평균 토론의 Casey는 단계적 도입이 원안과 다른 제안이라고 말하고, 최종 5점으로 남는다. SD≤1의 수치상 합의는 모든 사람이 원안에 같은 이유로 찬성했다는 뜻이 아니다. 대안과 그 조건을 점수와 분리해 전달해야 한다.')]
for idx,((item,ko,en,lo,hi),(_,title,description,meaning))in enumerate(zip(PAIRS,texts),1):
 s+=f'## {idx+2}. 사례 {idx} — {ko}\n\n**초점: {title}**\n\n'+description+'\n\n'
 details=[]
 for stem in [lo,hi]:
  for e in [r for r in evidence if r['stem']==stem]:details.append([stem+' · '+str(e['seq'])+'번 '+e['speaker'],'“'+e['quote']+'”',e['Korean_paraphrase'],f"[발언 원문](transcripts/{stem}-stateful.md)"])
 s+=tab(['토론·발언','영문 원문 발췌','한국어 설명·해석','확인'],details)
 s+='\n- **관찰:** '+description+'\n- **해석:** '+meaning+'\n\n'
 s+='**같은 구성의 일반 토론과 비교한 점수:**\n\n'
 rows=[]
 for stem in [lo,hi]:
  b,t=metric(load(stem,'baseline')),metric(load(stem));rows.append([stem,f"{t['initial_mean']:.1f}",f"{b['final_mean']:.1f} / {b['final_sd']:.2f}",f"{t['final_mean']:.1f} / {t['final_sd']:.2f}",f"[일반](transcripts/{stem}-baseline.md) · [상태 기반](transcripts/{stem}-stateful.md)"])
 s+=tab(['토론 구성','초기 평균','일반 토론 최종 평균 / SD','상태 기반 최종 평균 / SD','원문'],rows)
 s+='\n- **관찰:** 일반·상태 기반은 각 행에서 같은 구성원·초기 점수의 별도 실행이다. 열은 시간 순서가 아니다.\n- **해석:** 이 표는 선택한 사례의 대응 비교이며 전체 처치 효과 추정은 기존 전체 표본 결과를 사용한다.\n\n'
context=pd.read_csv(R/'docs/research/human-ai-topic-variation/topic-metrics.csv')
s+='## 6. 해당 주제의 전체 토론 맥락\n\n선택한 여섯 토론의 비율 대신, 각 주제의 전체 상태 기반 토론과 인간 5명 표준화 패널을 함께 제시한다. 인간 패널은 원래 큰 방에서 토론한 사람들의 응답을 2민주·2공화·1무당층으로 추출한 측정이며 실제 다섯 명 토론 처치가 아니다.\n\n'
context_rows=[]
for item,ko,_,_,_ in PAIRS:
 r=context[context.model.eq('claude')&context.label.eq('A-stateful')&context['item'].eq(item)].iloc[0]
 context_rows.append([item+' '+ko,f'{r.panel_post_consensus*100:.1f}%',f'{int(r.n_consensus)}/{int(r.n_discussions)} ({r.consensus_rate*100:.1f}%)'])
s+=tab(['정책','인간 5명 패널 합의율','Claude 상태 기반 전체 합의 수 / 토론 수'],context_rows)
s+='\n- **관찰:** 세 주제 모두 상태 기반 AI의 내부 합의율이 인간 5명 측정 패널보다 높았다.\n- **해석:** 이는 해당 실험 자료의 비교다. 사례의 논거 분기는 질적 설명으로, 합의 빈도는 이 전체 토론 집계로 구별해서 읽는다.\n\n'
s+='''## 7. 이 사례들이 뒷받침하는 논지

> 상태 기반 토론은 서로 다른 초기 구성을 가진 에이전트들이 각 토론 안에서 가까운 점수에 도달하도록 할 수 있다. 그러나 같은 정책의 토론이라도 불확실성을 어떻게 해석하고 어떤 보완 조건을 받아들이는지에 따라 결론은 달라졌다. 따라서 최종 합의점을 단일한 정책 답으로 전달하기보다, 대립한 논거·채택한 전제·수정된 정책 조건·남은 쟁점을 함께 제공하는 방식이 적합하다.

이는 대안과 근거를 만들어 인간이 검토할 수 있다는 **가능성을 보여주는 사례**다. 논거의 사실성·정책 실행 가능성이나 실제 인간 숙의의 질 향상은 이 사례 선정으로 검증한 성과가 아니다.

## 8. 선정·근거·검증 범위

- Claude 주 분석에서 최종 수치상 합의가 서로 다른 방향으로 나타난 세 정책을 목적 표집했다. 기존 문항별 결과를 보고 선정했으므로 빈도·대표성을 추정하는 표본이 아니다. 해당 주제의 모든 토론 분포는 [주제별 분포 자료](../consensus-representation/OutcomeVariabilityAndPartyMovement.md)에 있다.
- 모든 토론은 민주당 2명·공화당 2명·무당층 1명의 구성이나 인물·초기 점수는 다르다. 공공보험의 낮은 평균 토론은 초기 양당 평균 차이가 0.5점으로 작다. 정당이 다르다는 것과 평균 입장이 크게 다르다는 것은 구분한다.
- 발언 인용은 실제 messages의 seq·speaker·문자 위치와 대조했다. 한국어 설명은 원문의 번역·요약과 연구자의 해석이며, 독립적인 사람 코딩 결과는 아니다. 대화에서 나온 비용·효과·현황 주장을 검증된 정책 사실로 제시하지 않는다.
- 원문 중 자신의 입장이 바뀌었다는 말은 에이전트의 설명으로 인용했다. 해당 논거가 이동을 일으킨 독립적인 인과효과를 추정하지 않았다. 실제 점수 변화는 초기 부여값과 최종 설문으로 확인했다.
- 수치상 합의 SD≤1은 내용상 완전한 동의·동일한 정책 대안·같은 이유의 공유와 다르다. 공공보험 높은 평균 토론에는 최종 5점의 유보자가 포함된다. 낮은 평균 토론에서도 발언의 유보 표현과 최종 3–4점이 함께 나타난다.
- 원자료 DB는 읽기 전용으로 열었고 덮어쓰지 않았다. 인물 이름은 시뮬레이션의 에이전트 이름이다. 각 원문에 discussion_id와 전체 발언·최종 설문 이유를 붙였다.

[발언 증거와 문자 위치](evidence.json) · [12개 토론 측정값](discussion-metrics.csv) · [60개 개인 점수](participant-scores.csv) · [검증 기록](verification.json)
'''
(O/'README.md').write_text(s)
print('Saved Korean report, evidence excerpts, paired discussion tables, and six-panel PNG/PDF figure.')
