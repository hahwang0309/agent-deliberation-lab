"""Build the case-study component of Supplementary Information and data packages."""
from pathlib import Path
import os,json,zipfile,hashlib
import pandas as pd,numpy as np
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/deliberation-cases-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1];B=R/'docs/research';O=B/'supplementary-information';C=B/'deliberation-case-studies';T=C/'transcripts'
pairs=[('Q2C','중미 빈곤·폭력 완화를 위한 원조','Aid to Central America','Q2C-g11','Q2C-g08'),('Q3C','배출 감축을 위한 세금·시장 유인','Emissions taxes / market incentives','Q3C-g10','Q3C-g08'),('Q5F','Medicare형 공공보험 구매 허용','Public health-insurance buy-in','Q5F-g07','Q5F-g05')]
def tab(head,rows):return '| '+' | '.join(head)+' |\n|'+'|'.join('---'for _ in head)+'|\n'+'\n'.join('| '+' | '.join(str(v)for v in row)+' |'for row in rows)+'\n'
e=json.loads((C/'evidence.json').read_text());m=pd.read_csv(C/'discussion-metrics.csv');p=pd.read_csv(C/'participant-scores.csv')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':7,'pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
fig,axs=plt.subplots(3,2,figsize=(7.05,8.4),sharey=True);col={1:'#286bb6',2:'#bd4b3d',3:'#777777'};mark={1:'o',2:'s',3:'^'}
for i,(item,_,title,lo,hi)in enumerate(pairs):
 for j,stem in enumerate([lo,hi]):
  ax=axs[i,j];q=p[p.stem.eq(stem)&p.label.eq('stateful')].sort_values(['party','participant']);r=m[m.stem.eq(stem)&m.label.eq('stateful')].iloc[0]
  for offset,(_,v)in zip(np.linspace(-.07,.07,5),q.iterrows()):ax.plot([offset,1+offset],[v.pre,v.post],color=col[v.party],marker=mark[v.party],ms=4,lw=1,alpha=.85)
  ax.axhline(5,ls='--',color='#888888',lw=.6);ax.set(xticks=[0,1],xticklabels=['Assigned initial','Final survey'],xlim=(-.2,1.25),ylim=(-.4,10.4),yticks=[0,2,4,6,8,10],ylabel='Policy score (0-10)'if j==0 else'')
  ax.set_title(chr(97+2*i+j)+'  '+item+' '+title+'\n'+stem+f" | final mean {r.final_mean:.1f}; SD {r.final_sd:.2f}",loc='left',fontsize=7);ax.grid(axis='y',alpha=.12)
handles=[plt.Line2D([],[],color=col[k],marker=mark[k],ms=4,label=l)for k,l in [(1,'Democratic role'),(2,'Republican role'),(3,'Independent role')]]
fig.legend(handles=handles,loc='lower center',ncol=3,frameon=False,fontsize=7)
fig.tight_layout(rect=(0,.05,1,1),h_pad=2,w_pad=1.5)
for ext in ['pdf','png']:fig.savefig(O/'figures'/f'supplementary-figure-1.{ext}',dpi=240)
plt.close(fig)
caption="""Assigned initial and final survey positions in six illustrative Claude stateful discussions. Panels a and b concern aid to Central America (Q2C); c and d concern taxes or market incentives for emissions reductions (Q3C); e and f concern a Medicare-like public insurance buy-in (Q5F). Each line joins two scores for one agent; it is not an utterance-level trajectory. Blue circles denote Democratic roles, red squares Republican roles, and grey triangles Independent roles. Each discussion contains five agents (two Democratic, two Republican and one Independent); 30 agent records are displayed, without assuming 30 distinct source personas. Initial scores derive from assigned source-human responses, conveyed to agents as verbal stance categories; final scores come from post-discussion surveys. Scores range from zero (oppose) to ten (favour). The dashed line marks the scale midpoint. Horizontal offsets separate overlapping points. SD denotes population standard deviation across the five final scores, with divisor five. All six displayed discussions satisfy the descriptive agreement criterion SD <= 1. No confidence intervals or inferential tests are shown. The two discussions per item have different initial compositions and were purposefully selected for contrasting final positions; they are not an estimate of outcome frequencies or a comparison holding initial composition fixed. Full transcripts and matched ordinary discussions are provided in Supplementary Data 1. Numerical data are provided in the Source Data file."""
assert len(caption.split())<=350
# Source Data: one extractable file per figure/table, kept separate from full transcript data.
p[p.label.eq('stateful')].to_csv(O/'source-data/Supplementary-Figure-1.csv',index=False)
for index,(item,ko,_,lo,hi)in enumerate(pairs,3):
 pd.DataFrame([v for v in e if v['stem']in [lo,hi]]).to_csv(O/f'source-data/Supplementary-Table-{index}.csv',index=False)
with zipfile.ZipFile(O/'files/Case-Source-Data.zip','w',compression=zipfile.ZIP_DEFLATED)as z:
 for name in ['Supplementary-Figure-1.csv',*[f'Supplementary-Table-{i}.csv'for i in [3,4,5]]]:
  path=O/'source-data'/name;z.write(path,path.name)
with zipfile.ZipFile(O/'files/Supplementary-Data-1.zip','w',compression=zipfile.ZIP_DEFLATED)as z:
 for path in sorted(T.glob('*')):z.write(path,'transcripts/'+path.name)
 for name in ['discussion-metrics.csv','participant-scores.csv','evidence.json']:z.write(C/name,name)
 z.writestr('README.txt','Supplementary Data 1: Full AI discussion transcripts and survey responses for three illustrative policy contrasts. Includes six stateful discussions and their six matched ordinary discussions. Same-person/source-score matching applies within each ordinary/stateful pair; the two contrasted compositions per policy differ. The six stateful discussions were purposefully selected, not randomly sampled for a frequency estimate. Names are agent aliases. Exact utterance evidence is indexed by discussion_id, seq, speaker and character offsets. Initial values are assigned source-human scores, not independently measured AI pre-survey scores. Final values are separate post-discussion surveys. The dataset supports qualitative illustration; it does not validate policy factual claims or human deliberation benefits.\n')
s='''# Supplementary Information — case-study component

Adding deliberation rules increases policy convergence and differences between language model groups’ conclusions

国文作业原稿（한글 작업본）, 2026-10-21. 이번 파일은 논문 전체 보충자료 중 새 사례 분석 부품이다. 기존 Supplementary Tables 1–2와 다른 보충 방법·자료의 최종 합본, 영문화 및 PDF 편집은 남아 있다. 번호는 전체 원고의 기존 두 표 뒤에 배정했다. Results라는 별도 보충 절은 두지 않고, 본문 Results 2.8에 제시한 관찰의 상세 근거와 해석을 제공한다.

## Supplementary Fig. 1 | Initial and final positions in contrasting policy discussions

![Supplementary Fig. 1](figures/supplementary-figure-1.png)

'''+caption+'''

[Vector PDF](figures/supplementary-figure-1.pdf). [Source Data](source-data/Supplementary-Figure-1.csv).

## Supplementary Tables 3–5 | Exact utterance evidence for the three contrasts

각 표의 원문 발췌는 실제 토론에서 연속된 문자열이다. 한국어 해석은 저자의 사후 독해이며 독립 코더 판정이 아니다. 상세 위치는 discussion_id·seq·speaker 및 문자 위치로 연결된다. 토론 정책 주장 자체의 사실성 검증과는 구별한다. 범용 통계 검정·오차막대는 제시하지 않는다.

'''
for index,(item,ko,_,lo,hi)in enumerate(pairs,3):
 s+=f'### Supplementary Table {index} | {ko}의 대조 토론 근거\n\n'
 rows=[]
 for stem in [lo,hi]:
  r=m[m.stem.eq(stem)&m.label.eq('stateful')].iloc[0]
  for v in [v for v in e if v['stem']==stem]:rows.append([stem+f' · 최종 평균 {r.final_mean:.1f}, SD {r.final_sd:.2f}',str(v['seq'])+' · '+v['speaker'],v['quote'],v['Korean_paraphrase']])
 s+=tab(['토론·최종 점수','발언 번호·참여자','영문 원문 발췌','한국어 설명'],rows)
 s+=f'\n각 토론 n=5 에이전트, 표의 두 토론은 서로 다른 구성이다. SD는 다섯 최종 점수의 모집단 표준편차다. 발췌 수는 토론당 2곳으로 빈도 추정용 표본이 아니다. 전체 발언과 사후 설명은 Supplementary Data 1, 해당 표의 판독 가능한 데이터는 [Source Data](source-data/Supplementary-Table-{index}.csv)에 있다.\n\n'
s+='''## Supplementary Methods | Selection and traceability of illustrative discussions

사후 탐색으로 Claude 상태 기반 토론에서 같은 문항에 대해 최종 평균이 서로 다른 방향으로 모이고 SD≤1인 세 정책·두 토론씩을 목적 표집했다. 0은 반대, 10은 찬성이며 단위는 정책 점수다. 선택한 토론의 일반 토론 대응 실행도 보존해 12개 토론·60개 조건별 개인 응답을 연결했다. 일반·상태 기반은 같은 구성원·초기 점수의 별도 실행이며 시간적 전후 단계가 아니다. 서로 대조한 두 구성은 인물과 초기 점수가 다르다. 각 토론은 민주당 2·공화당 2·무당층 1로 구성됐다. 정치적 역할의 차이가 초기 점수 차이와 항상 일치하지는 않는다.

원 자료의 messages에서 발언 번호·이름·전체 내용과 최종 survey_responses의 점수·이유를 읽기 전용으로 추출했다. 정확한 발췌 문자열과 문자 위치를 원문과 대조했으며 모든 개인 최종 점수·평균·SD를 원자료로 검산했다. 초기 값은 원 인간 응답의 부여값이며 에이전트에는 다섯 구간의 찬반 표현으로 제시됐다. 토론 과정의 인과적 전환점은 추정하지 않았다. 검토한 발언과 사후 설명에서 제안·반론·수정 조건·입장 변화에 대한 자기 설명을 연결한 사례 독해다. 별도의 독립 인간 코딩 검증이 끝났다고 보고하지 않는다.

## Supplementary Discussion | Conditional agreement and the content of alternatives

중미 원조의 두 토론은 부패·감독·정치적 의지의 문제를 인정하면서도, 그 불확실성을 사업의 충분한 효과를 입증하지 못한 이유로 보거나 성과 측정·조건부 지급·중단 기준으로 관리하며 시도할 위험으로 보았다. 탄소세의 두 토론은 가계 부담과 보상·대체 수단 사이의 시간차를 공통으로 다뤘다. 낮은 평균 토론은 보호책의 구체성이 부족해 원안에 찬성하지 못했고, 높은 평균 토론에서는 점진적 탄소세와 별도 재원의 인프라 병행이 지지의 조건으로 제안됐다.

공공보험 토론에서도 의료기관 참여·지불 수준·접근성 위험이 공통 쟁점이었다. 낮은 평균 토론은 필요한 보호 장치가 경쟁·비용 절감이라는 원래 논리를 바꿀 수 있다고 봤다. 높은 평균 토론은 시범 도입과 공급자 참여·대기시간 점검을 거친 확대를 제안했다. 해당 토론의 한 참여자는 이것이 원안과 다르다고 지적하며 최종 5점으로 남았다. 따라서 수치상 합의는 모든 사람이 원안을 같은 이유로 지지했다는 뜻이 아니다.

이 사례는 최종 점수와 함께 논거·수정 조건·남은 쟁점을 제공할 필요를 설명한다. 대안의 사실성·실행 가능성이나 실제 인간 숙의 지원 성과를 검증한 자료는 아니다. 표집 비율·기제의 빈도·논거의 독립 인과효과도 이 사례만으로 추정하지 않는다. 전체 집단의 분산·합의에 관한 추정은 본문 Fig.3–5와 Results를 따른다.

## Supplementary Data 1 | Full transcripts and linked surveys for illustrative policy discussions

자료 설명: 세 정책의 상태 기반 토론 6개와 각각의 일반 토론 대응 실행 6개의 전체 발언·최종 설문 이유·정당 역할·초기 부여값·최종 점수 및 발언 근거 색인이다. 총 12개 토론·324개 메시지 행·60개 조건별 개인 점수를 담았다. 메시지 수에는 진행자의 발언이 포함된다. 이는 서로 다른 원 인간 60명을 뜻하지 않는다. ZIP 안 README에 파일과 해석 범위를 제시했다. 별도 데이터 파일의 제목·범례는 제출 시 커버레터에도 넣는다.

[Supplementary Data 1](files/Supplementary-Data-1.zip) · [사례 Source Data](files/Case-Source-Data.zip)
'''
s=s.replace('国文作业原稿（한글 작업본）','국문 작업 원고')
(O/'CaseStudies.md').write_text(s)
(O/'FileLegends.md').write_text('''# 별도 제출 파일의 제목과 범례 — 사례 분석

## Supplementary Data 1

**Title:** Full transcripts and linked surveys for illustrative policy discussions.

**Legend:** Complete transcripts, agent role assignments, assigned initial positions, post-discussion survey scores and reasons, and an utterance-evidence index for six selected Claude stateful policy discussions and their six matched ordinary discussions. Three items are represented. The archive contains 12 discussions, 324 message records including moderator messages, and 60 condition-specific agent records. These are not necessarily distinct source personas. Discussions were purposefully selected to illustrate contrasting final positions within the same policy item. The two contrasting compositions differ; only each ordinary/stateful pair holds composition and initial scores fixed. Exact evidence is indexed by discussion identifier, utterance sequence, speaker and character offsets.

## Source Data — case component

**Title:** Source Data for Supplementary Fig. 1 and Supplementary Tables 3–5.

**Legend:** One extractable CSV per display item. Supplementary Fig. 1 contains 30 stateful agent records. Supplementary Tables 3–5 contain the exact excerpts, source identifiers, offsets and interpretive notes used in each table. This archive is the case component of the eventual combined Source Data package.
''')
print('Prepared case SI component, a-f figure, per-item Source Data and Supplementary Data 1 ZIP; legend words:',len(caption.split()))

# Additional source package is generated independently; keep its legend on regeneration.
with (O/'FileLegends.md').open('a') as f:
 f.write("\n\n## Source Data — outcome comparison\n\n**Title:** Source Data for main Figure 6 and Supplementary Tables 6–8.\n\n**Legend:** Outcome-Source-Data.zip contains 96 plotted discussion records, 180 item-by-model-by-condition summaries, six model-condition summaries, original machine-readable estimates and independent CSV tables for supplementary displays. All-discussion variance uses divisor G−1; agreement uses population SD≤1 within five-agent discussions. Agreement-conditioned endpoints are distinguished from all discussion means. Source paths and hashes are retained separately.\n")
