"""Recover unchanged parsed labels when only quote-edge formatting failed, without API calls."""
from pathlib import Path
from difflib import SequenceMatcher
import json,re

R=Path(__file__).resolve().parents[1];O=R/'docs/research/position-change-mentions'
normalize=lambda x:re.sub(r'\s+',' ',x).strip()
targets={x['id']:x['text']for x in map(json.loads,(O/'blind-inputs.jsonl').read_text().splitlines())}
changes=[]
for model in ['mistral-large-2512','mistral-small-2603']:
    path=O/f'coded-{model}.jsonl';done={x['id']for x in map(json.loads,path.read_text().splitlines())}
    raws=[json.loads(x)for x in (O/f'raw-batches-{model}.jsonl').read_text().splitlines()]
    candidates={}
    for index,raw in enumerate(raws):
        for row in raw['response']['items']:
            id=row['id']
            if id in done or id not in raw['requested_ids']or id not in targets:continue
            q=normalize(row['quote']);text=normalize(targets[id])
            if row['label']=='no':continue
            match=SequenceMatcher(None,q,text,autojunk=False).find_longest_match()
            span=text[match.b:match.b+match.size]
            # Mostly-identical contiguous source text only; never paraphrase or alter class labels.
            if (match.size>=max(35,.75*len(q))and len(span.split())>=6)or(match.size>=max(18,.9*len(q))and len(span.split())>=4):
                candidates[id]=(row,span,index,raw['attempt'])
    with path.open('a')as fh:
        for id,(row,span,index,attempt)in candidates.items():
            record=row|{'quote':span,'original_quote':row['quote'],'quote_edge_repair':True,'model':model,'attempts':attempt,'raw_response_line':index+1}
            assert normalize(record['quote'])in normalize(targets[id])
            fh.write(json.dumps(record,ensure_ascii=False)+'\n');done.add(id)
            changes.append({'id':id,'model':model,'label_unchanged':row['label'],'original_quote':row['quote'],'verified_source_span':span,'raw_response_line':index+1})
    print(model,'complete',len(done),'missing',len(set(targets)-done))
with (O/'quote-edge-repairs.jsonl').open('a')as fh:
    for row in changes:fh.write(json.dumps(row,ensure_ascii=False)+'\n')
