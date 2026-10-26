"""Refit E1--E5 from published numeric rows, without a DB or model API call."""
import argparse,json,sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.analysis import study1

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--source-data',required=True,type=Path)
 p.add_argument('--out',required=True,type=Path)
 p.add_argument('--hypotheses',nargs='+',default=['E1','E2','E3','E4','E5'])
 a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 idx=pd.read_csv(a.source_data/'AI-run-index.csv')
 keep=idx.included_registered_pool.astype(str).str.lower().eq('true')
 surveys=pd.read_csv(a.source_data/'AI-survey-numeric.csv',low_memory=False)
 surveys=surveys[surveys.discussion_id.isin(set(idx.loc[keep,'discussion_id']))]
 reference=json.loads((a.source_data/'registered-estimates.json').read_text())['rows']
 checks=[]
 for model,g in surveys.groupby('model'):
  short='claude' if model.startswith('claude') else 'gemini' if model.startswith('gemini') else 'mistral'
  results={}
  if 'E1' in a.hypotheses:results['E1']=study1.e1(g)
  if set(a.hypotheses)&{'E2','E3'}:results.update(study1.e2_e3(g))
  if set(a.hypotheses)&{'E4','E5'}:results.update(study1.e4_e5(g))
  for h,r in results.items():
   if h not in a.hypotheses:continue
   old=next(x['record'] for x in reference if x['model']==short and x['hypothesis']==h)
   diff=abs(r['estimate']-old['estimate']);ci_diff=float(np.max(np.abs(np.array(r['ci'])-old['ci'])))
   checks.append({'model':short,'hypothesis':h,'estimate':r['estimate'],'reference_estimate':old['estimate'],'absolute_difference':diff,'max_ci_difference':ci_diff,'matches_1e-6':diff<1e-6 and ci_diff<1e-6})
  (a.out/(short+'.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2))
  print(short,{k:v['estimate'] for k,v in results.items()},flush=True)
 report={'api_calls':0,'raw_databases_used':False,'hypotheses':a.hypotheses,'checks':checks,'all_match_1e_6':all(x['matches_1e-6'] for x in checks)}
 (a.out/'verification.json').write_text(json.dumps(report,indent=2))
 assert report['all_match_1e_6'], 'Do not overwrite archived results: inspect discrepancies.'

if __name__=='__main__':main()
