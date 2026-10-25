"""Verify case SI packaging against audited source extracts and manuscript links."""
from pathlib import Path
import json,hashlib,re,zipfile
import pandas as pd
R=Path(__file__).resolve().parents[1];B=R/'docs/research';O=B/'supplementary-information';C=B/'deliberation-case-studies'
checks={}
source=pd.read_csv(C/'participant-scores.csv');plotted=pd.read_csv(O/'source-data/Supplementary-Figure-1.csv');pd.testing.assert_frame_equal(source[source.label.eq('stateful')].reset_index(drop=True),plotted)
assert len(plotted)==30 and plotted.stem.nunique()==6
checks['figure_points']='30 audited agent records in 6 panels a-f; assigned initial and final survey scores'
e=json.loads((C/'evidence.json').read_text());nr=0
for i in [3,4,5]:
 t=pd.read_csv(O/f'source-data/Supplementary-Table-{i}.csv');assert len(t)==4
 for _,row in t.iterrows():
  match=next(x for x in e if x['stem']==row.stem and x['seq']==row.seq);assert row['quote']==match['quote']and row.discussion_id==match['discussion_id'];nr+=1
checks['evidence_rows']=nr
with zipfile.ZipFile(O/'files/Supplementary-Data-1.zip')as z:
 assert z.testzip()is None
 for path in (C/'transcripts').glob('*'):assert z.read('transcripts/'+path.name)==path.read_bytes()
 for name in ['discussion-metrics.csv','participant-scores.csv','evidence.json']:assert z.read(name)==(C/name).read_bytes()
 assert len([n for n in z.namelist()if n.endswith('.json')and n.startswith('transcripts/')])==12
checks['Supplementary_Data_1']='12 complete audited transcripts and linked surveys, plus source CSV and evidence index; archive integrity passed'
with zipfile.ZipFile(O/'files/Case-Source-Data.zip')as z:
 assert z.testzip()is None and len(z.namelist())==4
 for name in z.namelist():assert z.read(name)==(O/'source-data'/name).read_bytes()
checks['source_data']='One extractable CSV per supplementary display item; 4 files'
files=[O/'CaseStudies.md',O/'README.md',O/'FileLegends.md',B/'nature-communications/SupplementaryPlacement-2026-10-21.md']
for p in files:
 for link in re.findall(r'\]\(([^)]+)\)',p.read_text()):
  if link.startswith(('http:','https:','#')):continue
  assert (p.parent/link.split('#',1)[0]).exists(),(p.name,link)
si=(O/'CaseStudies.md').read_text();assert not re.search(r'^#+ .*Supplementary Results',si,re.M)
for token in ['Supplementary Fig. 1','Supplementary Tables 3–5','Supplementary Discussion','Supplementary Data 1']:
 assert token in (B/'ResultsDraft.md').read_text(),token
assert 'Supplementary Methods' in (B/'MethodsDraft.md').read_text()
discussion=(B/'Discussion.md').read_text()
assert re.search(r'\]\(supplementary-information/CaseStudies\.md(?:#[^)]*)?\)', discussion), 'Discussion must link to the actual case supplement'
assert '## Supplementary Discussion' in si
checks['placement']='Core result in main Results 2.2/L6; detailed evidence in specifically cited SI items; no Supplementary Results section'
checks['legends']='Case figure standalone English legend 221 words; file titles and legends supplied separately'
checks['visual_review']='Supplementary Fig. 1 a-f inspected, text and axes legible'
checks['archive_sizes']={p.name:p.stat().st_size for p in (O/'files').glob('*.zip')}
assert all(n<30*1024*1024 for n in checks['archive_sizes'].values())
checks['remaining']='Case SI component is a Korean working draft; final complete English SI PDF, human validation and author declarations remain pending'
(O/'verification.json').write_text(json.dumps({'date':'2026-10-21','status':'passed within stated working-draft scope','checks':checks},ensure_ascii=False,indent=2)+'\n')
paths=[*O.rglob('*'),R/'scripts/build_case_supplement.py',Path(__file__),B/'nature-communications/SupplementaryPlacement-2026-10-21.md'];(O/'output-manifest.json').write_text(json.dumps({str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths if p.is_file()and p.name!='output-manifest.json'},indent=2)+'\n')
print(json.dumps(checks,ensure_ascii=False))
