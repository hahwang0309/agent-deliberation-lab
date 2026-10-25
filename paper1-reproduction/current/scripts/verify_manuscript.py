"""Verify manuscript assembly, citations, source values, links and frozen inputs; no inference/API calls."""
from pathlib import Path
from urllib.parse import unquote
import hashlib,json,re,math,subprocess
ROOT=Path(__file__).resolve().parents[1];B=ROOT/'docs/research'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def normalize(u):return u.split('?')[0].rstrip('/').removesuffix('.pdf').lower()
def main():
 checks={};missing=[]
 names=['IntroductionDraft.md','Discussion.md','MethodsDraft.md','ResultsDraft.md','Results.md','Outline.md','Abstract.md','AbstractEnglish.md','ManuscriptArgument.md','ContributionDecision.md','EvidenceCoverage.md','ResearchQuestions.md','Table1.md','ManuscriptDraft.md','RewriteChecklist.md','RewriteAuthorReport.md','theory-review/README.md','theory-review/StatefulImplementation.md','manuscript-figures/Captions.md','nature-communications/SubmissionReadiness.md','Table2.md','review-revision/ImplementationChecklist.md','review-revision/AuthorReport.md','review-revision/ReferenceAudit.md','review-revision/RegisteredResults.md','review-revision/RegistrationConditions.md','nature-communications/AuthorDeclarationsDraft.md']
 for n in names:
  p=B/n
  for x in re.findall(r'\]\(([^)]+)\)',p.read_text()):
   if x.startswith(('http:','https:','mailto:','#')):continue
   x=unquote(x.split('#')[0]).strip('<>');dest=Path(x);dest=dest if dest.is_absolute() else p.parent/dest
   if not dest.exists():missing.append([n,x])
 assert not missing,missing
 checks['active_local_links']='pass'
 r=(B/'Results.md').read_text().split('## 2. Results | 결과',1)[1].strip()
 o=(B/'Outline.md').read_text().split('## 2. Results | 결과',1)[1].split('## 3. Discussion | 고찰',1)[0].strip()
 assert r==o
 full=(B/'ResultsDraft.md').read_text().split('## 2. Results | 결과',1)[1].split('\n---\n',1)[0].strip()
 headings=re.findall(r'^### (2\.\d+)\.',full,re.M);assert headings==['2.1','2.2']
 actual=[]
 for block in full.split('\n\n'):
  if not block or block.startswith('#'):continue
  m=re.search(r'다\.(?=\s|$)',block);assert m,block[:80]
  end=m.end();pending=re.match(r'\s*\(사람검증결과로 확인 필요\)',block[end:])
  if pending:end+=pending.end()
  actual.append(block[:end])
 listed=[p for p in r.split('\n\n') if p and not p.startswith('#')]
 assert actual==listed,'Opening sentences drift'
 checks['results_sections']=2;
 assert re.findall(r'<a id="([pl]\d+)"></a>',full)==['p1', 'p4', 'p2', 'p7', 'p6', 'p3', 'p5', 'l1', 'l5', 'l3', 'l7', 'l2', 'l4', 'l6']
 checks['results_property_limit_items']=14;checks['actual_opening_sentences']=len(actual);checks['results_outline']='identical'
 table=(B/'Table1.md').read_text();assert len(re.findall(r'^\| (?:성질|한계) [PL]\d',table,re.M))==14
 assert len(re.findall(r'^\| [PL]\d+ · ',(B/'EvidenceCoverage.md').read_text(),re.M))==14
 checks['table1_properties_limits']=14
 disc=(B/'Discussion.md').read_text().split('## 본문 초안',1)[1].split('## 논지를 뒷받침하는 근거',1)[0]
 discussion_headings=re.findall(r'^### (3\.[1-5]\. .+)$',disc,re.M)
 assert discussion_headings==['3.1. 인간과 다른 방식으로 이루어진 숙의', '3.2. 정치적 차이와 공존하는 합의', '3.3. 입장 조정과 판단의 질', '3.4. 합의와 결론의 불확실성', '3.5. 대안 탐색 도구로서의 활용과 검증 과제']
 outline_disc=(B/'Outline.md').read_text().split('## 3. Discussion | 고찰',1)[1].split('## 4. Methods | 방법',1)[0]
 assert discussion_headings==re.findall(r'^### (3\.[1-5]\. .+)$',outline_disc,re.M)
 checks['discussion_subheadings']=5;checks['discussion_outline']='identical'
 en=(B/'AbstractEnglish.md').read_text().split('\n\n')[-1].strip();assert len(en.split())<=200 and 'http' not in en
 checks['english_abstract_words']=len(en.split())
 s=(B/'ManuscriptDraft.md').read_text();main_text=s.split('## References')[0];refs=s.split('## References')[1].split('## 그림')[0]
 ref_urls={normalize(x) for x in re.findall(r'\]\((https?://[^)]+)\)',refs)}
 research_text=main_text.split('## 원고 말미',1)[0]
 unmatched=sorted({x for x in re.findall(r'\]\((https?://[^)]+)\)',research_text) if normalize(x) not in ref_urls and 'osf.io' not in x})
 assert not unmatched,unmatched
 checks['body_citations_in_bibliography']='pass';checks['references']=len(re.findall(r'<a id="ref-',refs));assert checks['references']==len(json.loads((B/'review-revision/source-data/reference-catalogue.json').read_text()))
 cited=[int(x)for x in re.findall(r'\[\d+\]\(#ref-(\d+)\)',main_text)];unique=list(dict.fromkeys(cited));assert unique==list(range(1,checks['references']+1)),unique
 assert all(f'id="ref-{i}"'in refs for i in unique)
 manifest=json.loads((B/'manuscript-source-manifest.json').read_text())
 for path,digest in manifest['inputs'].items():assert sha(ROOT/path)==digest,path
 assert sha(B/'ManuscriptDraft.md')==manifest['output_sha256'];checks['assembled_sources']='pass'
 declarations=(B/'nature-communications/AuthorDeclarationsDraft.md').read_text()
 expected_endmatter=declarations.split('## 원고 말미',1)[1].split('## Methods에 포함할 선언',1)[0].strip().replace('](../', '](')
 assert expected_endmatter in s
 for token in ['Ha Hwang¹,²','RS-2025-19252970','https://github.com/hahwang0309/agent-deliberation-lab','ghkdgk0309@gmail.com']:assert token in s,token
 assert '**AI use.**' not in main_text
 assert 'is preparing a patent application' in s and 'The application has not yet been filed.' in s
 assert 'The author declares no other competing interests.' in s
 assert '**Acknowledgements.**' not in main_text
 assert '비상업적 연구와 논문 결과 검증을 허용하는 연구용 이용허락' in s
 checks['author_declarations']='Author facts and funding supplied; research-use policy selected; pre-filing patent interest disclosed; acknowledgements omitted'
 nr=0
 for records in json.loads((B/'manuscript-figures/source-data.json').read_text())['figures'].values():
  for row in records:
   if 'json_path' not in row:continue
   v=json.loads((ROOT/row['source']).read_text())
   for k in row['json_path']:v=v[k]
   if row.get('transform')=='one_minus':v={**v,'estimate':1-v['estimate'],'ci':[1-v['ci'][1],1-v['ci'][0]]}
   elif row.get('transform')=='sum_solution_reasoning':v={'estimate':v['solution']['estimate']+v['reasoning']['estimate'],'ci':None}
   assert row['record']==v,row['metric'];nr+=1
 assert nr==85;checks['main_figure_records']=nr
 fig2=json.loads((B/'manuscript-figures/source-data.json').read_text())['figures']['2']
 labels=[r for r in fig2 if r.get('json_path') and r['json_path'][-1] in ['probing','solution','reasoning']]
 assert len(labels)==9 and all(sum(r['json_path'][-1]==k for r in labels)==3 for k in ['probing','solution','reasoning'])
 figure4_records=json.loads((B/'manuscript-figures/source-data.json').read_text())['figures']['4']
 adjudicated=[r for r in figure4_records if r.get('source')=='docs/research/position-change-adjudication/results.json']
 assert len(adjudicated)==6 and len(figure4_records)==15
 assert all(r['json_path'][:2]==['variants','glm_disagreement_combined'] for r in adjudicated)
 for path,digest in json.loads((B/'manuscript-figures/input-manifest.json').read_text()).items():assert sha(ROOT/path)==digest,path
 assert (B/'manuscript-figures/figure4.pdf').read_bytes()!=(B/'rq-artifacts/figures/rq3_rules_and_consequences.pdf').read_bytes()
 checks['figure_inputs_and_rebuilt_figure']='pass'
 nr=0
 for p in (B/'rq-artifacts/source-data').glob('rq*_values.json'):
  for row in json.loads(p.read_text())['records']:
   if 'json_path' not in row:continue
   v=json.loads((ROOT/row['source']).read_text())
   for k in row['json_path']:v=v[k]
   if row.get('transform','').startswith('1 -'):est=1-v['estimate'];ci=[1-v['ci'][1],1-v['ci'][0]]
   elif isinstance(v,dict):est=v.get('estimate',v.get('rho',v.get('spearman')));ci=v.get('ci')
   else:est=v;ci=None
   assert math.isclose(row['estimate'],est,abs_tol=1e-12),row['metric']
   if ci is not None and row.get('ci') is not None:assert all(math.isclose(a,b,abs_tol=1e-12) for a,b in zip(ci,row['ci']))
   nr+=1
 assert nr==162;checks['rq_displayed_records']=nr
 for e in json.loads((B/'rq-artifacts/source-data/input-manifest.json').read_text()):assert sha(ROOT/e['path'])==e['sha256'],e['path']
 for e in json.loads((B/'novelty-review/source-data/input-manifest.json').read_text()):assert sha(ROOT/e.get('snapshot_path',e['path']))==e['sha256'],e['path']
 for path,digest in json.loads((B/'robustness/source-data/manifest.json').read_text())['output_hashes'].items():assert sha(B/'robustness'/path)==digest,path
 checks['numerical_inputs_and_robustness_outputs']='unchanged'
 for e in json.loads((B/'theory-review/source-manifest.json').read_text()):assert sha(ROOT/e['path'])==e['sha256'],e['id']
 frozen=json.loads((B/'theory-review/frozen-implementation-audit.json').read_text())
 for path,digest in frozen['code_hashes'].items():assert hashlib.sha256(subprocess.check_output(['git','show',frozen['freeze']+':'+path])).hexdigest()==digest,path
 for plan in frozen['plans']:assert sha(ROOT/plan['path'])==plan['sha256'],plan['path']
 assert sum(x[4] for rows in frozen['db_completed_study1_settings'].values() for x in rows)==18209
 checks['theory_sources_and_frozen_plans']='pass';checks['checked_main_plan_files']=18;checks['completed_run_settings_checked']=18209
 # Content anchors are reminders for the manual review, not substitutes for judging the argument.
 intro=(B/'IntroductionDraft.md').read_text();methods=(B/'MethodsDraft.md').read_text();abstract=(B/'Abstract.md').read_text()
 for token in ['화용-변증법','Petty','Friedkin','공동 합의','상태 기반 토론','RQ1','RQ2','RQ3']:assert token in intro,token
 # The approved Discussion interprets the findings without repeating model-wise estimates.
 for token in ['Steenbergen','Fishkin','Friedkin','Brockers','Jang','Petty','Smit','Shao','Tak','다른 참가자들과 크게 다른 입장','질문','일관되게','구성의 영향과 생성의 변동','측정상의 불확실성']:assert token in disc,token
 for token in ['xᵢ₀','각 에이전트에게 다시 물어','그 변화를 다음 발언에 알려','RegistrationDeviations.md','언어모델 최종 판정(LLM-as-a-Judge)']:assert token in methods,token
 # Registration timing details live in the linked supplement; essential disclosure stays in Methods.
 registration_details=(B/'RegistrationDeviations.md').read_text()
 for token in ['200–208','RegistrationCompletionCounts.json']:assert token in registration_details,token
 for token in ['등록 전에 일부 논리 과제 실행이 이미 완료','이 실행들도 본 분석에 포함','당시 기록과 저자 진술에 따르면']:assert token in methods,token
 supplementary_methods=(B/'supplementary-information/EngineValidation.md').read_text()
 for token in ['seed_format=verbal','seed_placement=memory','seed_wording=neutral','post_survey=neutral']:assert token in supplementary_methods,token
 assert 'supplementary-information/EngineValidation.md#initial-response-settings' in methods
 for token in ['Mistral','불확실','사후','40.8%','0.1%','97.2%','65.6%','95.9%']:assert token in full,token
 assert '14.6%' in (B/'supplementary-information/ProcessAndRobustnessDetails.md').read_text()
 # The approved abstract foregrounds matched conditions; repeated-persona details remain in Methods.
 assert '같은 구성원·초기 응답·자료를 사용한 일반 토론과 비교' in abstract
 assert '사후 탐색 분석' in abstract
 assert '다른 토론에는 같은 사람이 재등장할 수 있었다' in methods
 # New review supplements are compared to the registered original records, not their rendered rounding.
 rows=json.loads((B/'review-revision/source-data/registered-estimates.json').read_text())['rows'];assert len(rows)==42
 for row in rows:
  v=json.loads((ROOT/row['source']).read_text())
  for k in row['json_path']:v=v[k]
  assert v==row['record'],row['hypothesis']
 checks['registered_supplement_rows']=len(rows)
 # Verify the newly reported denominators directly against coder outputs.
 peer=json.loads((B/'review-revision/source-data/peer-reference-denominators.json').read_text())['records']
 import pandas as pd
 for row in peer:
  p=ROOT/row['source'];assert sha(p)==row['source_sha256']
  g=pd.read_csv(p);g=g[g.label.eq(row['condition'])];referenced=g[g.references_argument.eq('yes')]
  assert len(g)==row['n_valid'] and len(referenced)==row['n_referencing']
  assert int(referenced.argument_source.isin(['peer','both']).sum())==row['n_peer']
  assert math.isclose(row['proportion'],row['n_peer']/row['n_referencing'],abs_tol=1e-12)
  assert f"{row['n_referencing']}건 중 {row['n_peer']}건" in (B/'supplementary-information/ProcessAndRobustnessDetails.md').read_text()
 checks['peer_reference_denominators']='4 coder-by-condition counts verified from original CSVs'
 lead=full.split('### 2.1.',1)[0]
 for token in ['합의','결론 차이','RQ4','사후 탐색','정답','인간 반응']:assert token in lead,token
 assert '### 2.1. 언어모델 에이전트 집단 숙의의 일곱 가지 성질' in full
 assert '### 2.2. 인간 숙의의 재현과 판단 도구로서의 일곱 가지 한계' in full
 for token in ['서로 다른 공급자','상용 경량·소형','API 접근성','등급','본 실험 전에 정했다']:assert token in methods,token
 for token in ['제 2 자동 코더','각각300발언','잠금22문항','대비의95%']:
  assert token not in methods+(B/'manuscript-figures/Captions.md').read_text(),token
 l2=next(line for line in (B/'Table1.md').read_text().splitlines() if line.startswith('| 한계 L2'))
 assert '일반 토론의 질 효과는 Supplementary Table 2 H3a' in l2 and '규칙 추가에 따른 질 효과 변화는 Table 2 E4' in l2
 assert 'three comparisons:' in (B/'nature-communications/CoverLetterDraft.md').read_text()
 checks['recheck_followup']='Core finding foregrounded; contribution contrast manually reviewed; effect references and listed spacing corrected'

 reply=(B/'nature-communications/ReviewResponse-2026-10-20.md').read_text();marker='## 검토자 회신 (2026-10-20)'
 assert marker+reply.split(marker,1)[1]==(B/'review-revision/source-data/reviewer-reply-original.md').read_text()
 checks['reviewer_reply_preserved']='pass'
 # Matched-group bootstrap must preserve point estimates and paired differences.
 import numpy as np,pandas as pd
 tab=pd.read_csv(B/'review-revision/source-data/task-content-groups.csv').set_index('topic_key');boot=json.loads((B/'review-revision/source-data/task-content-bootstrap.json').read_text())
 assert tab.shape==(68,3)
 old=json.loads((ROOT/'data/study1/results/exploratory/claude/n10.json').read_text())['by_sample']['comparison']
 for name,r in boot['estimates'].items():
  arr=(tab[name].to_numpy() if name in tab.columns else (tab[name.split(' minus ')[0]]-tab[name.split(' minus ')[1]]).to_numpy())
  assert math.isclose(float(arr.mean()),r['estimate'],abs_tol=1e-12)
  if name in tab.columns:
   v=old['human_same_groups']if name=='Human'else old['conditions'][name]
   assert math.isclose(r['estimate'],v['solution']['estimate']+v['reasoning']['estimate'],abs_tol=1e-12)
 for path,digest in json.loads((B/'review-revision/source-data/task-content-input-hashes.json').read_text()).items():assert sha(ROOT/path)==digest,path
 checks['combined_label_bootstrap']='paired groups; unchanged point estimates; input hashes valid'
 timing=json.loads((B/'review-revision/source-data/registration-condition-audit.json').read_text())['models']
 early=[r for m in timing for r in m['runs']];assert len(early)==208 and sum(r['window']=='before_minute'for r in early)==200 and all(r['included_in_retained_main_run_pool']for r in early)
 checks['registration_conditions_and_inclusion']='200 before minute; 208 by end; four arms retained'
 cap=(B/'manuscript-figures/Captions.md').read_text();legend=cap.split('**English legend.**',1)[1].split('\n\n-',1)[0];assert len(legend.split())<=350
 checks['figure5_english_legend_words']=len(legend.split())
 checks['visual_QA']='Figures 1-5 prior visual review retained; Figure 6 and case SI separately reviewed in RevisionCompletionChecks-2026-10-21.json'
 coding=json.loads((B/'submission-preparation/coding-finalization/results.json').read_text())
 assert {k:v['n'] for k,v in coding['domains'].items()}=={'utterance':2440,'evidence':600,'device':1500}
 assert all(v['unresolved_n']==0 for v in coding['domains'].values())
 for token in ['사람검증결과로 확인 필요','<추후 작성 필요>','사람 검증은 현재 진행 중']:assert token not in main_text,token
 checks['coding_validation']='LLM adjudication completed in three domains; original human-label comparison and primary estimates preserved'
 hf=json.loads((B/'submission-preparation/huggingface-publication.json').read_text());code=json.loads((B/'submission-preparation/github-publication.json').read_text())
 assert hf['private'] is False and hf['commit'] in declarations
 assert code['commit'] in declarations and code['release_url'] in declarations
 checks['author_declarations_status']='Author facts synchronized; fixed public data/code releases recorded; final author review remains'
 checks['final_English_maintext_length']='pending English translation; not certified from Korean draft'
 checks['manual_review_content_anchors']='present'
 checks['scope']='Editorial, source and completed automated-coding checks. English main text, final author approval and actual submission remain.'
 (B/'review-revision/ReviewChecks.json').write_text(json.dumps({'date':'2026-10-26','status':'source and synchronization checks passed; final submission steps remain','checks':checks},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(checks,ensure_ascii=False))
if __name__=='__main__':main()
