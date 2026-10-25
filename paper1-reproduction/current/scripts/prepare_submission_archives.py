"""Prepare local data/code archives. No upload, API calls, git commit or push."""
from pathlib import Path
import csv,hashlib,json,shutil,sqlite3,subprocess,sys,zipfile
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R));B=R/'docs/research';O=B/'submission-preparation';D=O/'source-data';C=O/'code-release';D.mkdir(exist_ok=True);C.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def copy(src,dst):dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
def zip_tree(root,out):
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for p in sorted(root.rglob('*')):
   if p.is_file():z.write(p,p.relative_to(root))
 with zipfile.ZipFile(out) as z:assert z.testzip() is None
# Read the frozen 18 plan paths, excluding pilots and later runs.
from src.analysis import data as adata
freeze=json.loads((B/'theory-review/frozen-implementation-audit.json').read_text())
plans=adata.load_plans([str(R/p['path']) for p in freeze['plans']])
runs,surveys=adata.load_runs([str(R/f'data/study1/{m}.db') for m in ['claude','gemini','mistral']],plans,{'anthropic':'claude-haiku-4-5-20251001','google':'gemini-3.5-flash-lite','mistral':'mistral-small-2603'})
assert int((runs.status=='completed').sum())==18209
required={'wason':['A-baseline','A-stateful','B-resolve','C-unseeded'],'a1r':['A-baseline','A-stateful','B-materials','C-reanswer','D-prior'],'argq':[f'{q}-{s}-{e}' for q in ['strong','weak'] for s in ['minority','majority'] for e in ['baseline','stateful']]+['C-reanswer']}
kept,excluded=adata.exclusions(runs,required);assert len(kept)==18205
runs['included_registered_pool']=runs.discussion_id.isin(set(kept.discussion_id))
runs.to_csv(D/'AI-run-index.csv',index=False);surveys.to_csv(D/'AI-survey-numeric.csv',index=False)
(D/'excluded-blocks.json').write_text(json.dumps(excluded,ensure_ascii=False,indent=2)+'\n')
# Numeric structured study inputs already used by exploratory analyses.
inputfiles=[]
for m in ['claude','gemini','mistral']:
 for name in ['a1r_agents.csv','a1r_blocks.csv','wason_runs.csv','s1_items.csv','n7_participants.csv','n9_ai_events.csv','n9_ai_participants.csv']:
  p=R/f'data/study1/results/exploratory/{m}/{name}'
  if p.exists():inputfiles.append(p)
for folder in ['data/study1/results/exploratory/human','docs/research/robustness/source-data','docs/research/group-mean-comparison','docs/research/consensus-representation/ordinary-stateful-check','docs/research/consensus-representation/outcome-variability','docs/research/supplementary-information/source-data']:
 inputfiles.extend((R/folder).glob('*.csv'))
for p in inputfiles:
 # This local review archive may retain source-row identifiers. Public release needs author/rights review.
 copy(p,D/'analysis-inputs'/p.relative_to(R))
# One file per main display with panel-level provenance; preserve original records separately.
s=json.loads((B/'manuscript-figures/source-data.json').read_text());displaymap=[]
for n,records in s['figures'].items():
 flat=[]
 for r in records:
  v=r.get('record',{});ci=v.get('ci') or [None,None]
  flat.append({'metric':r.get('metric',r.get('type')),'estimate':v.get('estimate'),'ci_low':ci[0],'ci_high':ci[1],'source':r.get('source'),'json_path':json.dumps(r.get('json_path')),'transform':r.get('transform'),'full_record':json.dumps(v,ensure_ascii=False)})
 p=D/f'Figure-{n}.csv';pd.DataFrame(flat).to_csv(p,index=False);displaymap.append({'display':f'Figure {n}','data':p.name,'scope':'plotted estimates and original source paths; Figure 1 is schematic'})
for n in [6]:copy(B/f'manuscript-figures/figure{n}-source-data.csv',D/f'Figure-{n}.csv');displaymap.append({'display':'Figure 6','data':'Figure-6.csv','scope':'96 discussion-level plotted records'})
for name in ['Table1.md','Table2.md']:copy(B/name,D/name);displaymap.append({'display':name[:-3],'data':name,'scope':'table text; model estimates in registered-estimates.json and analysis inputs'})
copy(B/'review-revision/source-data/registered-estimates.json',D/'registered-estimates.json')
variants=json.loads((B/'rq-artifacts/source-data/task-variants-values.json').read_text())
pd.json_normalize(variants['records']).to_csv(D/'Supplementary-Table-1.csv',index=False)
reg=json.loads((B/'review-revision/source-data/registered-estimates.json').read_text())
pd.json_normalize(reg['rows']).to_csv(D/'Supplementary-Table-2.csv',index=False)
peer=json.loads((B/'review-revision/source-data/peer-reference-denominators.json').read_text())
pd.json_normalize(peer['records']).to_csv(D/'Supplementary-Table-11.csv',index=False)
with zipfile.ZipFile(B/'supplementary-information/files/Engine-Check-Source-Data.zip') as z:
 for name in ['Supplementary-Table-9.csv','Supplementary-Table-10.csv']:(D/name).write_bytes(z.read(name))
for p in (B/'position-change-mentions').glob('*.csv'):
 if not p.name.startswith(('classified-','maintenance-')):copy(p,D/'position-change-original'/p.name)
for name in ['estimates.csv','combined-labels.csv','selection.csv']:
 copy(B/'position-change-adjudication'/name,D/'position-change-adjusted'/name)
for n in [1,2,9,10,11]:displaymap.append({'display':f'Supplementary Table {n}','data':f'Supplementary-Table-{n}.csv','scope':'original descriptive rows or original saved estimates; not new classification'})
displaymap.append({'display':'Supplementary Table 13 and Supplementary Figure 2','data':'position-change-adjusted/estimates.csv','additional_inputs':'position-change-original/ and combined-labels.csv','scope':'adjusted and original coding estimates separated'})

for p in (B/'supplementary-information/source-data').glob('*.csv'):
 copy(p,D/p.name);displaymap.append({'display':p.stem,'data':p.name,'scope':'display-specific source records'})
# Classification labels can be recalculated without including full utterance text.
for name in ['n10_comparison_glm.csv','n10_comparison_large.csv','evidence_glm.csv','evidence_sonnet.csv','delidata_validate_glm.csv']:
 copy(R/'data/study1/results/exploratory/coding'/name,D/'coding-labels'/name)
# Preserve exact plot inputs with directory structure for offline regeneration.
required_plot_files=set()
for manifest in ['manuscript-figures/input-manifest.json','manuscript-figures/figure6-manifest.json']:
 d=json.loads((B/manifest).read_text());entries=d.get('inputs',d)
 required_plot_files.update(p for p in entries if p.startswith(('docs/','data/','scripts/')))
required_plot_files.update(['docs/research/consensus-representation/ordinary-stateful-check/model-summary.csv','docs/research/consensus-representation/ordinary-stateful-check/item-outcomes.csv','docs/research/consensus-representation/outcome-variability/discussion-outcomes.csv','docs/research/consensus-representation/source-data/results.json'])
for rel in sorted(required_plot_files):
 p=R/rel
 if p.is_file() and p.suffix.lower() not in ['.db','.sqlite']:copy(p,D/'plot-inputs'/rel)
copy(B/'manuscript-figures/source-data.json',D/'main-figure-records.json')
(D/'display-map.json').write_text(json.dumps(displaymap,ensure_ascii=False,indent=2)+'\n')
(D/'README.md').write_text('''# Prepared Source Data\n\nLocal preparation archive, not a public deposit. Copyright, ethics and access scope require final author confirmation.\n\nAI-run-index.csv lists all frozen-plan runs and the registered-pool inclusion flag. AI-survey-numeric.csv contains preserved numerical pre/post records, including missing values, choices and identifiers; it contains no discussion transcripts. The 18,209 completed and 18,205 retained run totals are not independent sample sizes for every hypothesis. analysis-inputs contains study-specific derived numeric rows; identifiers may link to source-human rows and require disclosure review before public release.\n\nFigure files contain plotted estimates or, for Figure 6, all 96 points. display-map.json indexes the source components. Source paths and hashes are retained. plot-inputs preserves the inputs needed to regenerate the six main figures offline; this is not a new fit of all registered mixed models. Full-model reanalysis also requires original licensed human data, frozen plans, study-specific coding inputs and the R environment described in the code documentation.\n\nFull transcripts of 12 illustrative discussions are supplied separately in Supplementary Data 1. They are not the complete experimental corpus. No fixed percentage of the full corpus is claimed sufficient for verification.\n''')
# Current implementation snapshot: source/config only, no credentials or raw datasets.
codefiles=set()
for folder in ['src','config']:
 for p in (R/folder).rglob('*'):
  if p.is_file() and '__pycache__' not in p.parts and p.suffix.lower() in ['.py','.yaml','.r']:codefiles.add(p)
for p in (R/'scripts').glob('*'):
 if p.is_file() and p.suffix.lower() in ['.py','.R']:codefiles.add(p)
for name in ['requirements.txt','requirements-dev.txt']:
 if (R/name).is_file():codefiles.add(R/name)
for p in codefiles:copy(p,C/'current'/p.relative_to(R))
copy(R/'LICENSE',C/'LICENSE')
copy(R/'REPRODUCIBILITY.md',C/'REPRODUCIBILITY.md')
copy(R/'LICENSE',C/'current/LICENSE')
# Freeze snapshot is the actual committed experimental code, not the current analysis tree.
rev=freeze['freeze'];tree=subprocess.check_output(['git','ls-tree','-r','--name-only',rev],cwd=R,text=True).splitlines()
paths=[p for p in tree if p.startswith(('src/','config/','scripts/')) or p in ['requirements.txt','requirements-dev.txt']]
with (C/'frozen-experiment.tar').open('wb') as f:subprocess.run(['git','archive',rev,*paths],cwd=R,stdout=f,check=True)
(C/'README.md').write_text('''# Code prepared for review\n\nThis is the local reproduction release snapshot. The author-confirmed research-use license is in LICENSE. Public release metadata are recorded separately; no release DOI is invented.\n\ncurrent contains the current engine and analysis source; frozen-experiment.tar contains the committed experimental version. Frozen SHA: '''+rev+'''. Current uncommitted analysis files are separately hashed in manifest.json, rather than misidentified as the frozen commit.\n\nOffline figure regeneration: extract Source-Data-Prepared.zip beside current, copy plot-inputs into current preserving paths, create a Python environment and install the analysis dependencies, then run python scripts/build_manuscript_figures.py. No API credentials or paid calls are required. Source-data record equality is the reproducibility target; PDF byte equality is not required because rendering metadata can differ.\n\nFull statistical reanalysis: use scripts/analyze_study1.py with the three original experiment DBs, the 18 frozen plan files and the source human datasets; this path is not claimed complete in the public preparation archive. R packages lme4 and lmerTest are additionally required. See src/analysis/mixed.py for the bridge. Study-specific exploratory scripts and their command-line help specify the further inputs. Archived model outputs support auditing without making new API calls.\n\nHa Hwang confirmed personal ownership, research-use licensing and publication before submission. The operative license applies to covered original code; patent rights are not granted. See REPRODUCIBILITY.md for CSV-only E1--E5 refitting and verified scope. Third-party data and dependency licenses remain separate. No .env, API credentials, logs, database backups or raw discussion databases are included.\n''')
# Record the tested Python installation separately from the reused R environment.
old_draft=C/'LICENSE-RESEARCH-USE.draft.md'
if old_draft.exists():old_draft.unlink()
fresh_check=O/'clean-reproduction-check.json'
fresh=json.loads(fresh_check.read_text()) if fresh_check.exists() else {}
import importlib.metadata,platform
versions={p:importlib.metadata.version(p) for p in ['numpy','pandas','scipy','statsmodels','matplotlib','PyYAML']}
(C/'requirements-analysis.lock.txt').write_text('\n'.join(f'{p}=={v}' for p,v in versions.items())+'\n')
(C/'environment.json').write_text(json.dumps({'python':sys.version,'platform':platform.platform(),'packages':versions,'fresh_install_tested':bool(fresh.get('fresh_python_environment_installed')),'api_calls':0,'R':'4.6.1','lme4':'2.0.6','lmerTest':'3.2.1','R_versions_verified_locally':True,'fresh_R_install_tested':False,'verified_scope':fresh},indent=2)+'\n')
for root in [D,C]:
 files={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and p.name!='manifest.json'}
 (root/'manifest.json').write_text(json.dumps({'status':'local preparation; research-use code license applied; dataset and release access recorded separately','files':files},ensure_ascii=False,indent=2)+'\n')
zip_tree(D,O/'Source-Data-Prepared.zip');zip_tree(C,O/'Code-Prepared.zip')
summary={'runs':len(runs),'completed_runs':int((runs.status=='completed').sum()),'registered_pool_runs':len(kept),'survey_rows':len(surveys),'code_files':len(codefiles),'numerical_input_files':len(inputfiles),'archives':{n:(O/n).stat().st_size for n in ['Source-Data-Prepared.zip','Code-Prepared.zip']},'uploads':0,'commits':0,'pushes':0}
(O/'archive-preparation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False))
