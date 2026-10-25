"""Synchronize actual Results openings and the current editorial guide in the figure index."""
from pathlib import Path
import re
R=Path(__file__).resolve().parents[1];B=R/'docs/research'
full=(B/'ResultsDraft.md').read_text().split('## 2. Results | 결과',1)[1].split('\n---\n',1)[0].strip();blocks=[]
for para in full.split('\n\n'):
 if para.startswith('#'):blocks.append(para)
 elif para:
  m=re.search(r'다\.(?=\s|$)',para);assert m,para[:100]
  end=m.end();pending=re.match(r'\s*\(사람검증결과로 확인 필요\)',para[end:])
  if pending:end+=pending.end()
  blocks.append(para[:end])
r='\n\n'.join(blocks)
(B/'Results.md').write_text('# 결과 절 문단 첫 문장\n\n개정: 2026-10-21. 현행 Results 본문의 실제 첫 문장을 추출했다.\n\n## 2. Results | 결과\n\n'+r+'\n')
p=B/'Outline.md';s=p.read_text();s=s.split('## 2. Results | 결과',1)[0]+'## 2. Results | 결과\n\n'+r+'\n\n## 3. Discussion | 고찰'+s.split('## 3. Discussion | 고찰',1)[1];p.write_text(s)
# The old exploratory figures remain identifiable by original analysis IDs.
box='''<!-- BEGIN CURRENT MANUSCRIPT REVISION -->
<section id="current-manuscript-revision">
<h2>현행 원고 해석 · 2026-10-21</h2>
<p><b>일반 토론과 상태 기반 모두 같은 정책에서 서로 다른 결론을 냅니다.</b> 규칙을 추가하면 내부 합의율은 높아지면서 모든 토론 최종 평균의 분산도 평균적으로 커집니다. 합의한 토론만의 끝점 분산 효과와는 구별합니다. 아래 탐색 그림의 원래 분석 번호·수치는 보존했습니다.</p>
<p>Fig.5의 G분모 분산 분해와 Table2 추가 비교의 G−1분모를 구별합니다. 합의율43.5%는 기존 토론 동일 가중치,43.1%는 새30문항 동일 가중치입니다. 인간의5명 패널은 큰 방에서 숙의한 응답의 추출이며 실제5명 처치가 아닙니다.</p>
<p>구성·초기 입장에 따른 결론, 남아 있는 정당 차이, 시행 조건에 따른 타협은 인간과 닮은 측면입니다. 강한 수렴·소수 유지·질문 탐색의 차이도 함께 평가합니다. 논리 과제는 정답 도달·보존으로, 정책 과제는 합의·결론 분포·관점과 논거의 지속으로 나누어 읽습니다.</p>
<p><a href="../ManuscriptDraft.md">현행 통합 원고</a> · <a href="../manuscript-figures/Captions.md">본문 그림1–6·범례</a> · <a href="../Table2.md">모델별 성과·두 조건 비교</a> · <a href="../supplementary-information/AnalysisDetails.md">Supplementary Tables6–8</a> · <a href="../ai-beliefs-and-deliberation/README.md">원문 문헌 비교</a></p>
<img src="../manuscript-figures/figure6.png" alt="세 정책의 일반·상태 기반 토론별 최종 평균과 합의점" style="max-width:100%;height:auto">
<p>가로축: 토론별 최종 평균0반대–10찬성. 위/아래: 일반/상태 기반. 파랑/주황: 두 조건. 채운 점: 다섯 최종 응답의 모집단SD≤1. 빈 점: 미충족. 한 점은 한 토론이며 각 정책·조건16토론입니다. 세로 간격은 겹침 방지용입니다. 두 조건의 구성은 대응되지만 서로 다른 점의 초기 구성은 다릅니다. 원조·보험은 일반 조건에도 서로 다른 합의점이 있습니다. 탄소세 일반 조건 합의는1개여서 합의점 변동을 평가하지 않습니다.</p>
</section>
<!-- END CURRENT MANUSCRIPT REVISION -->'''
p=B/'figures/study1-figures.html';s=p.read_text();pattern=r'<!-- BEGIN CURRENT MANUSCRIPT REVISION -->.*?<!-- END CURRENT MANUSCRIPT REVISION -->'
if re.search(pattern,s,re.S):s=re.sub(pattern,box,s,flags=re.S)
else:s=s.replace('<section id="synthesis">',box+'\n\n<section id="synthesis">',1)
p.write_text(s)
print('Synchronized Results openings, Outline and current figure-index guide.')
