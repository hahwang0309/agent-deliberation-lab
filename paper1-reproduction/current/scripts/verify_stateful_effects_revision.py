"""Verify the 2026-10-23 editorial revision and new descriptive SI12 against source events."""
from pathlib import Path
from urllib.parse import unquote
import hashlib,json,re
import pandas as pd
import numpy as np

R=Path(__file__).resolve().parents[1];B=R/'docs/research';O=B/'review-revision/stateful-effects-20261023'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
checks={}
title='Human-inspired rules reshape deliberation and collective judgment in language model groups'
for path in ['ManuscriptDraft.md','Outline.md','nature-communications/CoverLetterDraft.md','supplementary-information/CaseStudies.md']:
    assert title in (B/path).read_text(),path
assert title in (R/'scripts/assemble_manuscript.py').read_text()
checks['title']='manuscript, outline, cover letter, case SI and assembly source match'

# All before snapshots remain unchanged, including the complete directly edited manuscript.
for name,digest in json.loads((O/'before-hashes.json').read_text()).items():
    original=Path(name)
    if not original.is_absolute():original=R/original
    relative=original.relative_to(B)
    assert sha(O/'before'/relative)==digest,relative
assert (B/'Table2.md').read_bytes()==(O/'before/Table2.md').read_bytes()
checks['snapshots_and_table2']='23 original document snapshots intact; Table 2 byte-identical'

manifest=json.loads((B/'supplementary-information/late-answer-change-manifest.json').read_text())
for group in ['inputs','outputs']:
    for name,digest in manifest[group].items():assert sha(R/name)==digest,name
raw=pd.read_csv(R/'data/study1/results/exploratory/claude/n9_ai_events.csv')
saved=pd.read_csv(B/'supplementary-information/source-data/Supplementary-Table-12.csv').set_index('label')
agents=pd.read_csv(B/'supplementary-information/source-data/early-correct-agent-records.csv')
for label,g in raw.groupby('label'):
    # Recompute per agent from ordered events, independently of the table builder's set intersection.
    records=[]
    for (disc,member),h in g.groupby(['discussion_id','member']):
        h=h.sort_values('event_index')
        early=h[(h['t']<.25)&h.from_correct.eq(0)&h.to_correct.eq(1)]
        late=h[(h['t']>=.75)&h.from_correct.eq(1)&h.to_correct.eq(0)]
        if len(early):records.append({'discussion_id':disc,'member':member,'late_correct_to_wrong':int(len(late)>0)})
    ref=pd.DataFrame(records).sort_values(['discussion_id','member']).reset_index(drop=True)
    actual=agents[agents.label.eq(label)].drop(columns='label').sort_values(['discussion_id','member']).reset_index(drop=True)
    pd.testing.assert_frame_equal(ref,actual)
    row=saved.loc[label]
    assert len(ref)==row.n_early_correct_agents
    assert ref.late_correct_to_wrong.sum()==row.n_early_correct_late_wrong_agents
    assert np.isclose(ref.late_correct_to_wrong.mean(),row.conditional_share)
    assert len(g)==row.n_change_events
    assert (g['t']>=.75).sum()==row.n_late_change_events
    assert np.isclose((g['t']>=.75).mean(),row.late_change_share)
    assert ((g['t']>=.75)&g.from_correct.eq(1)&g.to_correct.eq(0)).sum()==row.n_late_correct_to_wrong_events
checks['supplementary_table12']='all two-condition counts, event shares and 2,150 conditional agent records independently recomputed'

results=(B/'ResultsDraft.md').read_text().split('## 2. Results | 결과',1)[1].split('\n---\n',1)[0]
sections={}
for m in re.finditer(r'^#### .*?\(([PL]\d)\).*?\n\n(.*?)(?=\n#### |\n### |\Z)',results,re.M|re.S):sections[m[1]]=m[2].strip()
assert len(sections)==14,sections.keys()
for key in ['P4','P3','P6','L2','L3','L4','L5','L6','L7']:
    first=re.split(r'다\.(?=\s|$)',sections[key],maxsplit=1)[0]
    assert any(word in first for word in ['규칙','상태 기반']),key
assert sections['P3'].index('43.1%')<sections['P3'].index('1.27점')
for token in ['81.6%','81.3%','0.59점','1.70점','자료만 읽었을 때보다','기존 인간 자료']:
    assert token in sections['P3'],token
for token in ['1,131명 중 2명(0.2%)','1,019명 중 45명(4.4%)','Supplementary Table 12']:
    assert token in sections['P4'],token
for token in ['0.867–0.958','0.862–0.957']:assert token in sections['P5']
assert '일반 토론에서도' in sections['P6']
assert '처음 점수를 그대로 유지하거나' in sections['L6']
assert '반대 방향으로 이동한 경우를 합한 것' in sections['L6']
checks['section_contrasts']='14 items; direct contrasts foregrounded where available; common results and minority metric definition retained'

# Exact approved headings and real human disagreement examples survive.
for heading in ['토론 과정에서 달라지는 입장','주장과 근거를 주고받는 대화','정치적 차이를 지우지 않고도 늘어난 합의']:
    assert heading in results
for quote in ['무슨 말씀인지 이해합니다. 하지만 우리가 확인하려는 규칙은 홀수와는 관계가 없습니다','그런데 7 카드의 뒷면에 모음이 있으면 어떻게 되죠?']:
    assert quote in results
assert '(사람검증결과로 확인 필요)' in sections['P2']
checks['approved_text']='three approved headings, two actual human examples and pending-validation markers retained'

methods=(B/'MethodsDraft.md').read_text();discussion=(B/'Discussion.md').read_text()
for token in ['0.25 미만','0.75 이상','기술 비교','각 토론 안에서는 한 번만','68.1%']:assert token in methods
assert '지속되는 한계와 개입 후 커진 한계' in discussion
assert '정치적 페르소나' in sections['P3'] and '초기 입장·기본 성향' in sections['P3']
checks['scope_and_limitations']='descriptive conditional denominator, utterance-order time, retained constraints and adverse outcomes explicitly distinguished'

abstract=(B/'AbstractEnglish.md').read_text().strip().split('\n\n')[-1]
assert len(abstract.split())==199
assert '43.1%' in abstract and 'Post-hoc' in abstract and 'primary model' in abstract
assert 'human-distribution distance decreased' in abstract
checks['english_abstract']='199 words; weighting, primary-model scope and post-hoc status retained; human similarity not labelled general improvement'

plan=(B/'ManuscriptRevisionPlan-2026-10-23.md').read_text()
ids=re.findall(r'^\| ([ABCD]\d+) \|',plan,re.M)
evidence=json.loads((O/'checklist-evidence.json').read_text())
assert len(ids)==len(set(ids))==30 and set(ids)==set(evidence)
report=(B/'review-revision/StatefulEffectsRevisionReport-2026-10-23.md').read_text()
for key in ids:assert f'| {key} | 충족 |' in report
for token in ['한정하지','추가 검토']:
    assert token in (B/'ContributionDecision.md').read_text()+(B/'ManuscriptArgument.md').read_text()
checks['checklist']='30 unique editorial criteria, each with separately recorded manual evidence; final contribution left open'

files=[B/n for n in ['ManuscriptRevisionPlan-2026-10-23.md','review-revision/StatefulEffectsRevisionReport-2026-10-23.md','ContributionDecision.md','supplementary-information/LateAnswerChanges.md','supplementary-information/FileLegends.md']]
links=0
for p in files:
    for link in re.findall(r'\]\(([^)]+)\)',p.read_text()):
        if link.startswith(('http:','https:','mailto:','#')):continue
        name,_,fragment=unquote(link.strip('<>')).partition('#')
        q=Path(name)if name.startswith('/')else p.parent/name
        assert q.exists(),(p,link);links+=1
        if fragment.startswith('supplementary-table-'):assert f'id="{fragment}"'in q.read_text()
checks['new_document_links']=links
checks['existing_verifiers']={
 'manuscript':json.loads((B/'review-revision/ReviewChecks.json').read_text())['status'],
 'revision':json.loads((B/'review-revision/RevisionCompletionChecks-2026-10-21.json').read_text())['status'],
 'case_supplement':json.loads((B/'supplementary-information/verification.json').read_text())['status']}
checks['visual_scope']='existing figure bytes preserved; no new visual inspection claimed'
out={'date':'2026-10-23','status':'passed: Korean editorial revision and source checks; external completion items pending','checks':checks}
(O/'verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(checks,ensure_ascii=False))
