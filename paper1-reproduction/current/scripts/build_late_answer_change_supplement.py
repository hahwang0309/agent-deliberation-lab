"""Describe early-correct/late-wrong changes from preserved N9 records; no model calls."""
from pathlib import Path
import hashlib,json
import pandas as pd

R=Path(__file__).resolve().parents[1];B=R/'docs/research';S=B/'supplementary-information'
source=R/'data/study1/results/exploratory/claude/n9_ai_events.csv'
e=pd.read_csv(source);rows=[];agents=[]
for label,g in e.groupby('label'):
    early=set(map(tuple,g[(g.t<.25)&g.from_correct.eq(0)&g.to_correct.eq(1)][['discussion_id','member']].values))
    late=g[g.t.ge(.75)];wrong=late[late.from_correct.eq(1)&late.to_correct.eq(0)]
    late_keys=set(map(tuple,wrong[['discussion_id','member']].values))
    both=early&late_keys
    rows.append(dict(label=label,n_change_events=len(g),n_late_change_events=len(late),late_change_share=len(late)/len(g),n_early_correct_agents=len(early),n_early_correct_late_wrong_agents=len(both),conditional_share=len(both)/len(early),n_late_correct_to_wrong_events=len(wrong)))
    for disc,member in sorted(early):agents.append(dict(label=label,discussion_id=disc,member=member,late_correct_to_wrong=int((disc,member)in late_keys)))
table=pd.DataFrame(rows);out=S/'source-data';out.mkdir(exist_ok=True)
table.to_csv(out/'Supplementary-Table-12.csv',index=False)
pd.DataFrame(agents).to_csv(out/'early-correct-agent-records.csv',index=False)
a,b=rows
assert (a['n_early_correct_agents'],a['n_early_correct_late_wrong_agents'])==(1131,2)
assert (b['n_early_correct_agents'],b['n_early_correct_late_wrong_agents'])==(1019,45)
text='# 논리 과제의 후반 답 변경 — 보충 표와 집계 방법\n'
text+='''
작성: 2026-10-23. 기존 주모델 N9 사건 자료에서 수행한 **사후 탐색 기술 집계**다. 새 시뮬레이션·코딩을 실행하지 않았으며 등록 가설 결과와 구분한다. 일반 토론은 첫 반복, 상태 기반 토론은 해당 실행을 사용한다.

## Supplementary Table 12. 토론 후반의 답 변경과 초반 정답 이후의 오답 전환 <a id="supplementary-table-12"></a>

| 지표 | 일반 토론 | 상태 기반 토론 | 집계 단위·분모 |
|---|---:|---:|---|
'''
text+=f"| 전체 답 변경 중 후반 변경 | {a['n_late_change_events']}/{a['n_change_events']} ({a['late_change_share']*100:.1f}%) | {b['n_late_change_events']}/{b['n_change_events']} ({b['late_change_share']*100:.1f}%) | 답 변경 사건 수; 같은 에이전트의 반복 변경 포함 |\n"
text+=f"| 초반에 정답으로 바꾼 뒤 후반에 오답으로 바꾼 에이전트 | {a['n_early_correct_late_wrong_agents']}/{a['n_early_correct_agents']} ({a['conditional_share']*100:.1f}%) | {b['n_early_correct_late_wrong_agents']}/{b['n_early_correct_agents']} ({b['conditional_share']*100:.1f}%) | 각 토론의 에이전트; 초반 오답→정답 전환자가 분모 |\n"
text+=f"| 후반 정답→오답 변경 사건 | {a['n_late_correct_to_wrong_events']} | {b['n_late_correct_to_wrong_events']} | 사건 수; 앞 행의 조건부 에이전트 수와 구별 |\n"
text+='''
- **시간의 뜻:** 실제 경과 시간이 아닌 발언 순서다. 참가자 발언 수를 N, 0부터 센 순서를 i라 하면 t=i/max(N−1,1)로 환산했다. 초반은 t<0.25, 후반은 t≥0.75다.
- **초반 정답 전환:** 자신의 직전 선택이 오답이고 초반 발언에서 현재 선택이 정답으로 바뀐 경우다. 인간에게서 부여받은 초기 정답을 그대로 유지한 경우는 이 조건부 분모에 들어가지 않는다.
- **후반 오답 전환:** 직전까지 추출된 자신의 답이 정답이었고 후반 발언에서 오답으로 바뀐 경우다. 중간에 다른 변경이 있었을 수 있으므로 초반부터 후반까지 정답을 계속 유지했다는 뜻은 아니다. 후반에 다시 정답을 회복했는지와 최종 설문이 오답인지도 이 지표만으로 정해지지 않는다.
- **에이전트 수:** discussion_id×member별로 한 번만 센다. 여러 번의 사건과 서로 다른 사람 수를 구별한다. 같은 초기 조건으로 두 토론을 구성했어도 초반에 정답으로 바꾼 사람의 집합은 달라질 수 있다. 따라서 두 조건의 조건부 비율은 동일한 사람들만의 짝 비교가 아니다.
- **측정 범위:** N9는 발언자 자신의 현재 카드 선택을 별도 추출한 자료다. 주모델 발언의 선택 추출률은 68.1%였다. 선택이 추출되지 않은 발언 사이의 모든 변경을 관찰한 것은 아니다. 마지막 추출과 최종 설문 답의 일치율은 일반 99.3%(n=1,520), 상태 기반 95.3%(n=1,499)였다. 추출률과 최종 설문 일치율은 서로 다른 지표다.
- **해석:** 이미 정답을 제시한 에이전트도 후반에 답을 바꾼 사례가 상태 기반 조건에서 더 많았다는 기술 결과다. 모델 내부 지식의 억제를 측정한 결과나 특정 동료 논거의 인과효과로 표현하지 않는다. 이 표에는 유의성 검정·신뢰구간을 새로 추가하지 않았다.

## 자료와 재현

- [표 수치 CSV](source-data/Supplementary-Table-12.csv)
- [초반 정답 전환 에이전트별 기록](source-data/early-correct-agent-records.csv)
- [입력·출력 해시와 집계 정보](late-answer-change-manifest.json)
- 원 사건 자료: `data/study1/results/exploratory/claude/n9_ai_events.csv`.
- 생성 프로그램: `scripts/build_late_answer_change_supplement.py`. 표의 각 조건부 에이전트를 원 사건의 discussion_id·member와 연결할 수 있다.

영문 제목: **Late answer changes and transitions away from an early correct answer.**

영문 범례: Descriptive post-hoc counts from the primary model's preserved N9 records. Discussion progress is normalized utterance order, not elapsed time. Early means t<0.25 and late means t≥0.75. The conditional agent denominator includes agents who changed from an incorrect to a correct choice early; the numerator includes those who subsequently changed from a correct to an incorrect choice late. Each agent is counted once per discussion. Denominator membership may differ by condition. These changes need not be consecutive, and a late incorrect transition need not remain incorrect at the final survey. No new inferential test is reported. Source Data retain condition, discussion and member identifiers.
'''
(S/'LateAnswerChanges.md').write_text(text)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
outputs=[S/'LateAnswerChanges.md',out/'Supplementary-Table-12.csv',out/'early-correct-agent-records.csv']
manifest={'date':'2026-10-23','status':'post-hoc descriptive counts; no new inference','inputs':{str(source.relative_to(R)):sha(source),str(Path(__file__).relative_to(R)):sha(Path(__file__))},'outputs':{str(p.relative_to(R)):sha(p)for p in outputs},'records':rows}
(S/'late-answer-change-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(rows,ensure_ascii=False))
