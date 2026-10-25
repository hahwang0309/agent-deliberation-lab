"""Assemble current chapter drafts into one reviewable manuscript; no inference or API calls."""
from pathlib import Path
import re,json
ROOT=Path(__file__).resolve().parents[1]
b=ROOT/'docs/research'
# Preserve direct edits in the combined manuscript. Import them into chapter sources before regeneration.
import hashlib
_current_path = b/'ManuscriptDraft.md'
_manifest_path = b/'manuscript-source-manifest.json'
if _current_path.exists() and _manifest_path.exists():
    _last_manifest = json.loads(_manifest_path.read_text())
    _saved_digest = _last_manifest.get('output_sha256')
    if not _saved_digest or hashlib.sha256(_current_path.read_bytes()).hexdigest() != _saved_digest:
        raise SystemExit('통합 원고에 직접 수정된 내용이 있습니다. 현재 버전을 백업하고 장별 초안에 먼저 반영해야 합니다. 덮어쓰기를 중단했습니다.')
intro=(b/'IntroductionDraft.md').read_text().split('## 1. Introduction | 서론',1)[1].strip()
results=(b/'ResultsDraft.md').read_text().split('## 2. Results | 결과',1)[1].split('\n---\n',1)[0].strip()
disc=(b/'Discussion.md').read_text().split('## 본문 초안',1)[1].split('## 논지를 뒷받침하는 근거',1)[0].strip()
methods=(b/'MethodsDraft.md').read_text().split('## 4. Methods | 방법',1)[1].split('\n---\n',1)[0].strip()
abstract=(b/'Abstract.md').read_text().split('# 초록',1)[1].strip();en=(b/'AbstractEnglish.md').read_text().split('\n\n')[-1].strip()
declarations=(b/'nature-communications/AuthorDeclarationsDraft.md').read_text()
author_info=declarations.split('## 저자 정보',1)[1].split('저자가 밝힌 직위',1)[0].strip()
endmatter=declarations.split('## 원고 말미',1)[1].split('## Methods에 포함할 선언',1)[0].strip()
# Declaration source lives one directory below the assembled manuscript.
endmatter=endmatter.replace('](../', '](')
catalogue=json.loads((b/'review-revision/source-data/reference-catalogue.json').read_text())
def norm(url):
    url=url.split('?')[0].rstrip('/').removesuffix('.pdf')
    url=re.sub(r'arxiv.org/(?:pdf|html|abs)/','arxiv.org/',url)
    return re.sub(r'(arxiv.org/\d{4}\.\d+)v\d+',r'\1',url).lower()
lookup={}
for id,r in catalogue.items():
    for url in [r['url'],r.get('manuscript_alias')]+[v['url']for v in r['access_links']]:
        if url:lookup[norm(url)]=id
order=[]
def number_citations(text):
    def repl(match):
        label,url=match.groups();id=lookup.get(norm(url))
        if not id:return match[0]
        if id not in order:order.append(id)
        n=order.index(id)+1
        return label+f' [{n}](#ref-{n})'
    return re.sub(r'\[([^\]]+)\]\((https?://[^\s]+?)\)(?=[).,;·\s가-힣])',repl,text)
# Markdown DOI paths may contain parentheses. The URL regexp includes these until the closing link delimiter.
intro,results,disc,methods=[number_citations(t)for t in [intro,results,disc,methods]]
refs='\n\n'.join(f'<a id="ref-{i}"></a>{i}. {catalogue[id]["citation"]} [원문]({catalogue[id]["url"]}).'for i,id in enumerate(order,1))
text='''# Human-inspired rules reshape deliberation and collective judgment in language model groups

'''+author_info+'''

**국문 통합 작업 원고 · 2026-10-26.** 등록·탐색·강건성 결과와 입장 변화 언급의 GLM 조정 결과를 반영한 검토용 초안이다. 발언 유형·논거 참조·규칙 수행의 추가 LLM 판정 조정을 완료했으며 원 주 분석과 조정 민감도를 구분했다. 확정 저자 정보와 자료·코드 제공 범위를 반영했으며, 본문 영문화·최종 저자 승인과 투고 편집은 남아 있다.

[그림 여섯 개·범례](manuscript-figures/Captions.md) · [Table 1](Table1.md) · [Table 2](Table2.md) · [강건성 보고서](robustness/README.md) · [투고 준비 상태](nature-communications/SubmissionReadiness.md)

## 국문 초록

'''+abstract+'\n\n## English abstract\n\n'+en+'\n\n## 1. Introduction | 서론\n\n'+intro+'\n\n## 2. Results | 결과\n\n'+results+'\n\n## 3. Discussion | 고찰\n\n'+disc+'\n\n## 4. Methods | 방법\n\n'+methods+'''

## 원고 말미

'''+endmatter+'''

[저자 작성 항목과 작성 안내](nature-communications/AuthorDeclarationsDraft.md)에 미확정 정보와 후속 작업을 정리했다. 윤리·AI 사용은 Methods 4.10에 통합했다.

## References

'''+refs+'''

번호는 본문 첫 인용 순서다. 정식 서지·버전·게재 상태와 원문 접근 링크는 [서지 대조 기록](review-revision/ReferenceAudit.md)에 보존했다. 원전의 확인 범위와 설계 계보는 [이론 검토](theory-review/README.md), 수치 규칙과 측정은 [보충 구현 설명](theory-review/StatefulImplementation.md), 추가 통계 방법은 [강건성 방법 기록](robustness/Methods.md)에 있다.

## 그림·표와 보충자료 연결

- [Figure 1: 공통 비교 설계](manuscript-figures/figure1.pdf)
- [Figure 2: 초기 답·변경·소수 입장·발언 구성](manuscript-figures/figure2.pdf)
- [Figure 3: 추가 합의·기준점·논거 평가와 반응](manuscript-figures/figure3.pdf)
- [Figure 4: 규칙 수행·정확도·수렴·인간 거리](manuscript-figures/figure4.pdf)
- [Figure 5: 정당과 토론 집단의 여러 분포 수준](manuscript-figures/figure5.pdf)
- [Figure 6: 두 조건 모두의 결론 분포와 합의점](manuscript-figures/figure6.pdf)
- [Table 1: 일곱 성질·일곱 한계와 평가 항목](Table1.md)
- [Table 2: 모델별 성과와 구간](Table2.md)
- [Supplementary Table 2: 등록 가설 전체 결과](review-revision/RegisteredResults.md)
- [Supplementary Table 1: 원 과제와 변형 과제](rq-artifacts/tables/task-variants.md)
- [이론–구현–측정 대응표](theory-review/README.md)
- [상태 갱신·피드백·사후 측정의 보충 방법](theory-review/StatefulImplementation.md)
- [리뷰 수정 검증표](review-revision/ImplementationChecklist.md)
- [강건성 방법·진단·추정값·원자료 연결](robustness/README.md)
- [논거 평가–반응 연결](argument-quality-response/README.md)
- [정당 분포 분석](party-dispersion/README.md)
- [집단 안·사이 분산 분석](novelty-review/CentralFindingProposal.md)
- [Supplementary Fig. 1·Tables 3–5·Methods·Discussion: 대조 토론의 상세 근거](supplementary-information/CaseStudies.md)
- [Supplementary Tables 6–8: 분포·정당 관점·인간 주제 비교](supplementary-information/AnalysisDetails.md)
- [Supplementary Table 14: 인간·일반·상태 기반의 초기–최종 평균 관계와 전후 분산](supplementary-information/GroupMeanComparison.md#supplementary-table-14)
- [Supplementary Table 15: 모델 간 정책 선호 상관](supplementary-information/CrossModelPolicyPreferences.md#supplementary-table-15)
- [Supplementary Methods: 동일 기준 발언 표집·코딩의 상세 절차](supplementary-information/CodingProcedures.md)
- [Source Data: Fig.6 및 추가 보충 표](supplementary-information/files/Outcome-Source-Data.zip)
- [Supplementary Data 1: 전체 전사와 설문](supplementary-information/files/Supplementary-Data-1.zip)

이 통합본은 분리된 장별 초안을 묶은 작업 스냅샷이다. 장별 파일을 수정하면 다시 조합하고 정합성을 확인한다.
'''
(b/'ManuscriptDraft.md').write_text(text)

import hashlib
inputs=[b/name for name in ["Abstract.md","AbstractEnglish.md","IntroductionDraft.md","ResultsDraft.md","Discussion.md","MethodsDraft.md","nature-communications/AuthorDeclarationsDraft.md","literature-review/sources.json","review-revision/source-data/reference-catalogue.json"]]
(b/"manuscript-source-manifest.json").write_text(json.dumps({"date":"2026-10-26","status":"Working manuscript; author facts and automated coding finalized; fixed public data/code versions documented; English editing and final approval remain","inputs":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in inputs},"output_sha256":hashlib.sha256((b/"ManuscriptDraft.md").read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+"\n")
print("Assembled ManuscriptDraft.md and source hashes.")
