"""Read-only extraction of selected AI transcripts and matched ordinary discussions."""
from pathlib import Path
import pandas as pd,json,sqlite3,hashlib
R=Path(__file__).resolve().parents[1];A=pd.read_csv(R/'data/study1/results/exploratory/claude/a1r_agents.csv');c=sqlite3.connect('file:'+str(R/'data/study1/claude.db')+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;O=R/'docs/research/deliberation-case-studies/transcripts';selected=['Q2C-g11#r0','Q2C-g08#r0','Q3C-g10#r0','Q3C-g08#r0','Q5F-g07#r0','Q5F-g05#r0']
for block in selected:
 for label in ['A-baseline','A-stateful']:
  a=A[A.block.eq(block)&A.label.eq(label)];did=a.discussion_id.iloc[0];d=c.execute('select topic,description,status from discussions where id=?',(did,)).fetchone();msgs=[dict(r)for r in c.execute('select seq,speaker,speaker_type,action,content from messages where discussion_id=? order by seq',(did,))];survey=[dict(r)for r in c.execute('select participant,score,reason,phase,item_id from survey_responses where discussion_id=? order by phase,participant',(did,))]
  obj={'model':'claude','block':block,'label':label,'discussion_id':did,'status':d['status'],'topic':d['topic'],'description':d['description'],'participants':a[['participant','party','pre','post']].to_dict('records'),'messages':msgs,'survey':survey};stem=block.replace('#r0','')+'-'+label.removeprefix('A-');(O/(stem+'.json')).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n');lines=['# '+stem,'','discussion_id: '+did,'','## 구성원과 점수','','| 이름 | 정당 | 초기 | 최종 |','|---|---|---|---|']+['| '+' | '.join(str(z)for z in r)+' |'for r in a[['participant','party','pre','post']].itertuples(index=False,name=None)]+['','정당: 1 민주당, 2 공화당, 3 무당층. pre는 원래 초기 응답, post는 최종 설문 점수.','']
  for r in msgs:lines+=['## 발언 '+str(r['seq'])+' · '+r['speaker']+' ('+r['speaker_type']+')','',r['content'],'']
  lines+=['## 최종 설문 이유','']
  for r in survey:
   if r['phase']=='post':lines+=['### '+r['participant']+' · '+str(r['score'])+'점','',r['reason']or'','']
  (O/(stem+'.md')).write_text('\n'.join(lines))
inputs=[Path(__file__),R/'data/study1/results/exploratory/claude/a1r_agents.csv'];manifest={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in inputs};manifest['database_access']='sqlite read-only; selected message and survey rows exported in full; no source data overwritten';(O.parent/'extraction-inputs.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Saved 12 full transcripts and surveys: six selected stateful discussions plus matched ordinary discussions.')
