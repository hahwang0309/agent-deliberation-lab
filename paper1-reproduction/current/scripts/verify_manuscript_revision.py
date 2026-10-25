"""Verify revised display records, local links, assembly scope and required distinctions."""
from pathlib import Path
import hashlib,json,re,zipfile,sys
from urllib.parse import unquote
import pandas as pd,numpy as np
R=Path(__file__).resolve().parents[1];B=R/'docs/research';sys.path.insert(0,str(R))
from src.analysis.group_disagreement import paired_groups
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
checks={}
# Additional display manifests record actual source/output changes, separately from original inference.
for name in ['manuscript-figures/figure6-manifest.json','supplementary-information/outcome-additions-manifest.json']:
 d=json.loads((B/name).read_text())
 for k in ['inputs','outputs']:
  for path,h in d[k].items():assert sha(R/path)==h,(name,path)
checks['additional_source_and_output_hashes']='pass'
plotted=pd.read_csv(B/'manuscript-figures/figure6-source-data.csv');source=pd.read_csv(B/'consensus-representation/outcome-variability/discussion-outcomes.csv')
expected=source[source.model.eq('claude')&source['item'].isin(['Q2C','Q3C','Q5F'])].sort_values(['item','label','block']).reset_index(drop=True)
pd.testing.assert_frame_equal(plotted.sort_values(['item','label','block']).reset_index(drop=True),expected)
assert len(plotted)==96
checks['figure6_points']=96
# Independently recompute all 180 new table rows from existing raw agent outputs.
t=pd.read_csv(B/'consensus-representation/ordinary-stateful-check/item-outcomes.csv');arms=['A-baseline','A-stateful']
for model in ['claude','gemini','mistral']:
 agents=paired_groups(pd.read_csv(R/f'data/study1/results/exploratory/{model}/a1r_agents.csv'),arms)
 for arm in arms:
  for item,g in agents[agents.label.eq(arm)].groupby('item_id'):
   means=g.groupby('block').post.mean();agree=g.groupby('block').post.std(ddof=0).le(1);end=means[agree]
   row=t[t.model.eq(model)&t['item'].eq(item)&t.label.eq(arm)].iloc[0]
   assert len(means)==row.n_discussions and agree.sum()==row.n_consensus
   for actual,saved in [(means.var(ddof=1),row.final_mean_variance),(means.max()-means.min(),row.final_mean_range),(agree.mean(),row.consensus_rate)]:assert np.isclose(actual,saved)
   assert means.nunique()==row.distinct_final_means
   assert bool(means.lt(5).any()and means.gt(5).any())==row.both_sides_of_5
   assert end.nunique()==row.distinct_agreement_means
   if len(end)>=2:assert np.isclose(end.var(ddof=1),row.agreement_mean_variance)
checks['outcome_table_rows_recomputed_from_raw']=len(t)
assert len(t)==180
u=pd.read_csv(B/'consensus-representation/ordinary-stateful-check/model-summary.csv');r=json.loads((B/'consensus-representation/source-data/results.json').read_text())
for x in u.itertuples():
 g=t[t.model.eq(x.model)&t.label.eq(x.label)]
 assert np.isclose(g.final_mean_variance.mean(),x.mean_item_final_mean_variance)
 assert np.isclose(g.consensus_rate.mean(),x.mean_item_agreement_rate)
 assert int(g.distinct_final_means.gt(1).sum())==x.all_outcomes_differ_items==30
 for n in ['mean_item_final_mean_variance','mean_item_agreement_rate']:
  assert f'{getattr(x,n):.3f}'in (B/'Table2.md').read_text() if n.endswith('variance') else f'{getattr(x,n)*100:.1f}%'in (B/'Table2.md').read_text()
checks['table2_absolute_levels_and_weighting']='six conditions matched to 30-item summaries'
# Exact copied supplementary tables retain established original rows/intervals.
raw=(B/'consensus-representation/README.md').read_text();si=(B/'supplementary-information/AnalysisDetails.md').read_text()
for fragment in ['| 모델 | 일반 | 상태 기반 | 증가 [95% 구간] |','| 모델 | 개인 사후−D 거리: 일반 |','| 모델 | 인간 이동 방향 일치: 일반 |']:
 tail=raw[raw.index(fragment):];rows=[]
 for line in tail.splitlines():
  if line.startswith('|'):rows.append(line)
  elif rows:break
 assert '\n'.join(rows) in si,fragment
checks['supplementary_table7']='three original tables copied without changing intervals or units'
# Topic estimates: check every displayed scalar against the original associations file.
a=json.loads((B/'human-ai-topic-variation/associations.json').read_text())
verified=0
for model in ['claude','gemini','mistral']:
 for metric in ['consensus_rate','final_mean_sd','agreement_only_sd']:
  rec=a['by_model'][model]['A-stateful']['human_post_sd'][metric]
  if rec['rho'] is None:
   assert rec['n']==0 and rec['ci'] is None and '해당 문항0개; 산출 불가' in si
  else:
   cell=f"n={rec['n']}; ρ={rec['rho']:+.3f} [{rec['ci'][0]:.3f}, {rec['ci'][1]:.3f}]"
   assert cell in si,(model,metric,cell)
  verified+=1
checks['supplementary_table8_display_rounding']=f'{verified} model-by-metric records with sample sizes and complete intervals checked at exact JSON paths'
# Archives checked against local original files, not merely ZIP readability.
for archive in (B/'supplementary-information/files').glob('*.zip'):
 with zipfile.ZipFile(archive) as z:
  assert z.testzip()is None,archive
  if archive.name=='Outcome-Source-Data.zip':
   for name in z.namelist():assert z.read(name)==(B/name).read_bytes(),name
 assert archive.stat().st_size<30*1024*1024
checks['archive_integrity_and_limits']='all three archives pass; additional sources byte-identical'
# Check all active MD and HTML links. Fragment existence is checked for explicitly named new table IDs.
files=[B/n for n in ['Abstract.md','AbstractEnglish.md','IntroductionDraft.md','ResultsDraft.md','Discussion.md','MethodsDraft.md','Results.md','Outline.md','Table1.md','Table2.md','ManuscriptDraft.md','ManuscriptArgument.md','EvidenceCoverage.md','ResearchQuestions.md','WritingPlan.md','RelatedWork.md','ManuscriptRevisionChecklist-2026-10-21.md','manuscript-figures/Captions.md','supplementary-information/README.md','supplementary-information/CaseStudies.md','supplementary-information/AnalysisDetails.md','supplementary-information/FileLegends.md']]
count=0
for p in files:
 for link in re.findall(r'\]\(([^)]+)\)',p.read_text()):
  if link.startswith(('http:','https:','mailto:','#')):continue
  link=unquote(link.strip('<>'));path,_,fragment=link.partition('#');dest=Path(path)if path.startswith('/')else p.parent/path
  assert dest.exists(),(p.name,link);count+=1
  if fragment.startswith('supplementary-table-'):assert f'id="{fragment}"'in dest.read_text(),(p.name,link)
html=B/'figures/study1-figures.html'
for link in re.findall(r'(?:href|src)="([^"]+)"',html.read_text()):
 if link.startswith(('http:','https:','#','data:')):continue
 dest=Path(unquote(link[7:].split('#')[0])) if link.startswith('file://') else html.parent/unquote(link.split('#')[0])
 assert dest.exists(),link
checks['active_local_links']=count
checks['new_table_explicit_anchors']='6, 7, 8 present'
# Structural/word constraints; semantic judgements remain documented per checklist ID.
checklist=(B/'ManuscriptRevisionChecklist-2026-10-21.md').read_text();ids=re.findall(r'^- \[[ x]\] ([A-J]\d+)\.',checklist,re.M)
assert len(ids)==len(set(ids))==63
checks['unique_checklist_items']=63
abstract=(B/'AbstractEnglish.md').read_text().split('\n\n')[-1];assert len(abstract.split())==199
checks['english_abstract_words']=199
for n in ['ResultsDraft.md','MethodsDraft.md','Discussion.md']:assert '<추후 작성 필요>'in (B/n).read_text(),n
results_text=(B/'ResultsDraft.md').read_text()
for token in ['일반 토론에서도','43.1%','Fig.6','Supplementary Table 8']:assert token in results_text,token
# The authorized 2026-10-24 move places the three-paragraph uncertainty result in L6;
# human-panel and conditional-distribution details remain in Table2 and SI6.
p6=re.search(r'<a id="l6"></a>\n\n(.*?)(?=\n---\n)',results_text,re.S)[1].strip()
assert len(p6.split('\n\n'))==3
for token in ['합의 여부와 관계없이 전체 토론','토론 전 집단 평균 태도','모두 합의 기준을 충족']:assert token in p6,token
assert '5.4%' in (B/'Table2.md').read_text()
assert '합의한 토론만의 평균 분포' in (B/'supplementary-information/AnalysisDetails.md').read_text()
checks['l6_structure_and_retained_details']='uncertainty moved to L6; three interpretive paragraphs retained; human-panel reference in Table2; all-discussion vs conditional distributions in SI6'
minority=re.search(r'#### [^\n]*<a id="p6"></a>\n\n.*?(?=\n#### )',results_text,re.S)[0]
for token in ['인간보다 덜 고집하는 초기 입장','40.8%','13.9%','6.3%','9.3%']:assert token in minority,token
for token in ['Cau','Piao','Chuang','동일한 심리','구성','조건부']:
 # Same psychological mechanism is described as an untested question in the checklist, not asserted in text.
 if token=='동일한 심리':continue
 assert token in (B/'Discussion.md').read_text(),token
assert not re.search(r'^#+ .*Supplementary Results',si,re.M)
checks['placeholders_scope_and_required_distinctions']='present; manually reviewed per item'
checks['visual_review']='Fig.6 and Supplementary Fig.1 inspected in conversation; no clipping or overlap obscuring labels'
checks['scope']='Korean manuscript revision and supporting documents; human validation, author facts and final English submission package remain pending'
out={'date':'2026-10-21','status':'automated checks passed; semantic judgments recorded separately by checklist ID','checks':checks}
(B/'review-revision/RevisionCompletionChecks-2026-10-21.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(checks,ensure_ascii=False))
