"""Build a minimal HF candidate from preserved numeric inputs and analyzed texts.

No upload, credentials, raw DB, full briefing PDF or complete experiment corpus.
"""
import csv, hashlib, hmac, json, os, shutil, sqlite3, zipfile
import yaml
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PREP=ROOT/'docs/research/submission-preparation'
OUT=PREP/'huggingface-release'
SOURCE=PREP/'source-data'
PRIVATE=PREP/'private-release-records'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write_jsonl(p,rows):
 p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
def main():
 if OUT.exists():
  # Rebuild only this explicitly generated candidate; private salt is elsewhere.
  shutil.rmtree(OUT)
 OUT.mkdir(parents=True,exist_ok=True);PRIVATE.mkdir(exist_ok=True)
 salt_path=PRIVATE/'pseudonymization-salt'
 if not salt_path.exists():salt_path.write_bytes(os.urandom(32))
 salt=salt_path.read_bytes()
 def pseudonym(x):return 'person-'+hmac.new(salt,str(x).encode(),hashlib.sha256).hexdigest()[:16]
 dictionary=[];private_cols={'original_quote','raw_response_line','quote'}
 # All archived numerical input rows; remove free-text quote duplicates and
 # pseudonymize source-person keys consistently without publishing the map.
 for src in SOURCE.rglob('*'):
  if not src.is_file() or src.name in ['manifest.json','README.md']:continue
  rel=src.relative_to(SOURCE)
  if src.suffix not in ['.csv','.json','.py']:continue
  dest=OUT/'numeric'/rel;dest.parent.mkdir(parents=True,exist_ok=True)
  if src.suffix=='.csv':
   with src.open() as f:
    reader=csv.DictReader(f);fields=[x for x in (reader.fieldnames or []) if x not in private_cols];rows=[]
    for r in reader:
     row={k:r[k] for k in fields}
     for k in ['persona','source_person_id','respondent_id']:
      if k in row and row[k]:row[k]=pseudonym(row[k])
     if 'db' in row:row['db']=Path(row['db']).name
     rows.append(row)
   with dest.open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
   dictionary.extend({'file':str(dest.relative_to(OUT)),'column':col,'meaning':meaning(col),'rows':len(rows)} for col in fields)
  else:shutil.copy2(src,dest)
 # Exact target+context inputs used for utterance labels; IDs map to label rows.
 c=PREP/'coding-finalization'
 for kind in ['utterance','evidence','device']:
  src=c/(kind+'-inputs.jsonl')
  if src.exists() and kind!='evidence':shutil.copy2(src,OUT/(kind+'-inputs.jsonl'))
  if src.exists() and kind=='evidence':
   unique={};reasons=[];frame={r['id']:r for r in csv.DictReader((c/'evidence-frame.csv').open())}
   for line in src.read_text().splitlines():
    row=json.loads(line);r=row['input'];did=frame[row['id']]['discussion_id']
    unique[did]={'discussion_id':did,'proposal':r['proposal'],'transcript':r['transcript']}
    reasons.append({'id':row['id'],'discussion_id':did,**{k:v for k,v in r.items() if k not in ['proposal','transcript']}})
   write_jsonl(OUT/'evidence-discussions.jsonl',unique.values())
   write_jsonl(OUT/'evidence-reasons.jsonl',reasons)
  for tail in ['frame.csv','combined.csv','summary.json','selection.csv','initial-pairs.json','initial.jsonl','judge.jsonl','rubric.txt','selection-freeze.json']:
   src=c/(kind+'-'+tail)
   if src.exists():shutil.copy2(src,OUT/(kind+'-'+tail))
 for name in ['results.json','robustness-estimates.csv','utterance-composition.json','supported-high-retry.json','format-amendment.json','throughput-amendment.json','batch-amendment.json','evidence-format-amendment.json']:
  src=c/name
  if src.exists():shutil.copy2(src,OUT/('coding-'+name))
 # The position-change labels were target-only; do not pretend context was used.
 p7=ROOT/'docs/research/position-change-mentions'
 shutil.copy2(p7/'blind-inputs.jsonl',OUT/'position-change-target-inputs.jsonl')
 for source,name in [(ROOT/'docs/research/position-change-adjudication/protocol.json','position-change-protocol.json'),(c/'protocol.json','supplemental-coding-protocol.json')]:
  if source.exists():shutil.copy2(source,OUT/name)
 # Whole evidence transcripts and post reasons are already in evidence-inputs.
 # Include the separate 12 purpose-selected case transcripts, with actual DB
 # pre/post rows but without internal prompt/config dumps.
 cases=[]
 con=sqlite3.connect(f'file:{ROOT}/data/study1/claude.db?mode=ro',uri=True)
 for src in (ROOT/'docs/research/deliberation-case-studies/transcripts').glob('*.json'):
  obj=json.loads(src.read_text());cases.append({'file':src.name,'content':obj})
 write_jsonl(OUT/'case-studies.jsonl',cases)
 # Publish the original classification labels, including failures, for transparency.
 code=ROOT/'data/study1/results/exploratory/coding'
 for name in ['devices_large.csv','devices_small.csv','devices_sample.csv']:
  shutil.copy2(code/name,OUT/name)
 for model in ['claude','gemini','mistral']:
  folder=ROOT/f'data/study1/results/exploratory/{model}'
  for src in folder.glob('n9_llm_choices*.csv'):
   dest=OUT/'numeric/card-extraction'/model/src.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
 for src in (ROOT/'docs/research/argument-quality-response/source-data').glob('*.csv'):
  dest=OUT/'numeric/argument-quality'/src.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
 # Publish IBM selection identifiers and hashes, not the original argument corpus.
 source_arguments={}
 for split in ['train','dev','test']:
  with (ROOT/f'data/raw/argq/{split}.csv').open() as f:
   for i,row in enumerate(csv.DictReader(f)):
    source_arguments.setdefault(row['argument'],[]).append({'split':split,'zero_based_row':i,'WA':row['WA']})
 plan=yaml.safe_load((ROOT/'data/study1/plans/argq-claude.yaml').read_text());selected=[]
 for topic in plan['topics']:
  for quality,args in topic['meta']['arguments'].items():
   for position,a in enumerate(args):
    matches=source_arguments.get(a['argument'],[])
    assert matches,'Selected argument absent from the preserved IBM CSVs'
    selected.append({'topic_key':topic['key'],'quality':quality,'argument_position':position,'argument_sha256':hashlib.sha256(a['argument'].encode()).hexdigest(),'quality_score':a['wa'],'tokens':a['tokens'],'upstream_rows':matches})
 write_jsonl(OUT/'ibm-selected-argument-index.jsonl',selected)
 # Card extraction audit: record sample selected before reading extracted choices.
 # The full event/participant numeric series are in numeric/analysis-inputs.
 choices=ROOT/'data/study1/results/exploratory/claude/n9_llm_choices.csv'
 if not choices.exists():choices=ROOT/'data/study1/results/exploratory/coding/n9_llm_choices.csv'
 candidate=[]
 for key in ['claude','gemini','mistral']:
  utt=ROOT/f'data/study1/results/exploratory/{key}/utterances.csv'
  if not utt.exists():continue
  with utt.open() as f:
   for r in csv.DictReader(f):
    if r.get('study')=='wason' and r.get('speaker_type')!='moderator' and r.get('topic_key','').startswith('deli-') and r.get('label') in ['A-baseline','A-stateful']:
     r['participant_model']=key;candidate.append(r)
 import random
 rng=random.Random(20261026);by={}
 for r in candidate:by.setdefault((r['participant_model'],r['label']),[]).append(r)
 audit=[]
 for (key,label),pool in sorted(by.items()):
  db=sqlite3.connect(f'file:{ROOT}/data/study1/{key}.db?mode=ro',uri=True)
  for r in rng.sample(pool,min(30,len(pool))):
   text=db.execute('SELECT content FROM messages WHERE discussion_id=? AND seq=?',(r['discussion_id'],int(r['seq']))).fetchone()
   audit.append({'participant_model':key,'condition':label,'discussion_id':r['discussion_id'],'seq':r['seq'],'speaker':r['speaker'],'text':text[0] if text else None,'frame_n':len(pool),'sample_n':min(30,len(pool))})
  db.close()
 write_jsonl(OUT/'card-extraction-audit-texts.jsonl',audit);con.close()
 with (OUT/'columns.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['file','column','meaning','rows']);w.writeheader();w.writerows(dictionary)
 shutil.copy2(ROOT/'config/coding_prompts.yaml',OUT/'coding-prompts.yaml')
 shutil.copy2(ROOT/'config/config.yaml',OUT/'experiment-settings.yaml')
 shutil.copy2(ROOT/'config/prompts.yaml',OUT/'experiment-prompt-templates.yaml')
 # Plot metadata needs a design source path, not the private manuscript text.
 design=OUT/'numeric/plot-inputs/docs/research/MethodsDraft.md';design.parent.mkdir(parents=True,exist_ok=True)
 design.write_text('# Public design record\n\n471 source logic groups; 30 policy items; 32 argument-quality target-side sets; 18,209 completed runs. This is a public design placeholder for figure provenance, not the manuscript Methods text. Numeric figure inputs are preserved separately.\n')
 # References and original dataset pointers, never entire upstream corpora.
 (OUT/'THIRD_PARTY.md').write_text('''# Third-party sources\n\nDeliData: https://huggingface.co/datasets/gkaradzhov/DeliData (CC BY 4.0).\nAmerica in One Room: https://doi.org/10.7910/DVN/KJ8IH2 (Harvard Dataverse V1, CC0 1.0).\nIBM Argument Quality Ranking 30k: https://huggingface.co/datasets/ibm-research/argument_quality_ranking_30k. Its card header says CC BY 3.0, while the licensing section says CC BY-SA 3.0. We do not redistribute the full IBM dataset or claim ownership of original arguments. Original text retains upstream attribution and terms; generated discussion/annotations do not remove them. The full A1R briefing document is not redistributed here.\n\nHuman source-person keys in numeric derived rows are pseudonyms. Synthetic speaker names are not recruited human participants. Source-person linkage is not a promise of irreversible anonymization.\n''')
 (OUT/'README.md').write_text('''---\nlanguage:\n- en\n- ko\nlicense: other\nlicense_name: research-use-terms-to-be-finalized\npretty_name: Agent deliberation Study 1 reproduction data\n---\n\n# Agent deliberation Study 1\n\nReproduction data release, 2026-10-26. Repository: haha0309/agent-deliberation-study1. Cite a fixed repository revision when using these data.\n\nThis repository contains analysis-level numerical inputs for 18,209 completed runs (including specified exclusions), exact analyzed coding targets and context, paired position-change targets, and purpose-selected case records. It is not the complete raw discussion corpus.\n\n`numeric/AI-run-index.csv` separates failed/retried records from the analysis inclusion flag. `numeric/AI-survey-numeric.csv` contains pre/post numerical responses. Numerical input and display mappings are under `numeric/analysis-inputs` and `numeric/display-map.json`. `columns.csv` describes fields.\n\nUtterance/evidence/device inputs use opaque ids joined to the respective frame and label files. Evidence coding includes the full original 120 discussion inputs and 600 final explanations. Position-change coding used target-only inputs, not preceding context. New coding is a post-hoc robustness analysis, not human accuracy validation. Original labels and primary estimates are preserved separately.\n\nThe 12 case discussions were purpose-selected, not a representative random sample. Card-extraction audit texts are stratified by model and condition with seed 20261026, 30 per cell; this is an audit input set, not completed independent validation. Numerical event series permit recalculation of process outcomes; rerunning extraction on every utterance would require additional raw transcripts.\n\n## Reproduction\n\nCode is released separately at https://github.com/hahwang0309/agent-deliberation-lab. From the reproduction code root run `python scripts/reanalyze_public_numeric.py --source-data PATH/numeric --out OUTPUT`. Python dependencies and R/lme4/lmerTest are required. The original local check refit 15 E1--E5 model contrasts from numeric CSVs, without raw DBs or model APIs, reproducing estimates and confidence limits within 1e-6. This does not assert all registered and exploratory models have been refit.\n\nFor six-figure regeneration, copy `numeric/plot-inputs/` into the reproduction code root preserving paths and run `python scripts/build_manuscript_figures.py`. Archived estimates reproduce displays, not statistical fitting. The experimental frozen version is 7a244351f3374b3e1ac4b02bf55a4f41ff9ca91c.\n\n## Access and terms\n\nNo arbitrary percentage of the full corpus defines sufficiency. This release separates numerical reanalysis, text-coding audit, and complete original extraction. The full raw discussion databases are not included. Requests for additional records needed to assess the paper may be addressed to the corresponding author; any applicable third-party restrictions and access arrangements will be disclosed to the journal. No unavailable file is represented as public.\n\nData reuse terms must be finalized before publishing; the research-use code license does not automatically license this dataset. Third-party sources retain their own terms; see THIRD_PARTY.md. Contact: Ha Hwang, ghkdgk0309@gmail.com.\n''')
 readme=(OUT/'README.md').read_text().replace('license_name: research-use-terms-to-be-finalized','license_name: ha-hwang-research-data-use-1.0\nlicense_link: LICENSE').replace('Evidence coding includes the full original 120 discussion inputs and 600 final explanations.','Evidence coding includes the full original 120 discussion inputs in `evidence-discussions.jsonl` and 600 final explanations in `evidence-reasons.jsonl`; join on discussion_id to reconstruct the exact original input.').replace('Data reuse terms must be finalized before publishing; the research-use code license does not automatically license this dataset.','Original research dataset material is supplied under the accompanying research-data-use terms. The separately published software license does not automatically license third-party datasets.')
 (OUT/'README.md').write_text(readme)
 (OUT/'LICENSE').write_text('''Ha Hwang Research Data Use Terms 1.0\nCopyright (c) 2026 Ha Hwang, to the extent applicable rights exist.\n\nOriginal generated research records and annotations may be used, copied, analysed and redistributed for non-commercial scientific research, education and verification of the associated paper. Retain attribution, identify modifications, cite the paper and fixed dataset version, and retain these same terms on redistributed covered material. Commercial exploitation requires separate permission: ghkdgk0309@gmail.com. No restriction here creates ownership over independently available facts or overrides statutory rights.\n\nThird-party materials are excluded from this grant and retain their own terms, including upstream CC BY 4.0, CC0, or the IBM card's stated CC BY/CC BY-SA conditions as applicable; see THIRD_PARTY.md. No patent license or warranty is granted. This is not a blanket license for the complete experimental corpus.\n''')
 manifest={str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='manifest.json'}
 (OUT/'manifest.json').write_text(json.dumps({'status':'prepared release; public access verified separately in publication record','target_repository':'haha0309/agent-deliberation-study1','files':manifest},indent=2)+'\n')
 with zipfile.ZipFile(PREP/'HuggingFace-Release-Candidate.zip','w',zipfile.ZIP_DEFLATED) as z:
  for p in OUT.rglob('*'):
   if p.is_file():z.write(p,p.relative_to(OUT))
 report={'files':len(manifest),'bytes':sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()),'numeric_csv_columns':len(dictionary),'case_discussions':len(cases),'card_audit_texts':len(audit),'raw_db_files':0,'uploads':0}
 (PREP/'public-data-build.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

def meaning(k):
 return {'discussion_id':'Stable synthetic run identifier; joins numerical responses and coded texts.','participant':'Synthetic participant name within a run.','persona':'Pseudonym for a reused source-person setting; preserves cross-run dependency.','pre':'Initial attitude/answer before discussion; scale supplied by study.','post':'Final attitude/answer after discussion.','score':'Observed numeric survey answer; use scale and study.','label':'Original experimental condition label; see condition dictionary.','phase':'pre or post measurement.','block':'Matched experimental unit; preserve in resampling.','seq':'Utterance sequence index within discussion.','weight':'Inverse-probability sampling weight.','included_registered_pool':'True if retained in the registered analysis pool.','correct':'Whether the selected logic-task answer is correct.','D':'Unseeded model response used as the default-attitude reference.','party':'Assigned/source political-party category, not a claim about real agent identity.'}.get(k,'Study-specific field; definition follows analysis script and source file named in this row.')

if __name__=='__main__':main()
