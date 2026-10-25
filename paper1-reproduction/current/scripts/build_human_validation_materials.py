"""Create frozen, offline human-review packets from existing study-1 data; no LLM calls.

Run once before distribution. Refuses to overwrite an existing packet.
"""
import csv
import hashlib
import html
import json
import random
import sqlite3
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/research/human-validation'
SOURCE = ROOT / 'data/study1/results/exploratory/coding'
SEED = 20261020

SCHEMA = {
    'utterance': {
        'type': ['probing', 'non_probing', 'none'],
        'target': ['solution', 'reasoning', 'agree', 'disagree', 'moderation', 'none'],
    },
    'device': {**{k: ['yes', 'partial', 'no'] for k in [
        'addresses_specific_claim', 'concedes_part', 'names_disagreement_between_others',
        'proposes_third_option', 'objects_to_shared_view', 'states_position_change']},
        'instruction_followed': ['yes', 'partial', 'no', 'none']},
    'evidence': {
        'references_argument': ['yes', 'no', 'undeterminable'],
        'argument_source': ['own', 'peer', 'both', 'none'],
        'argument_seqs': 'integer_list',
        'relevant': ['yes', 'no', 'undeterminable', 'none'],
        'supports': ['yes', 'no', 'undeterminable', 'none'],
        'rebutted': ['yes', 'no', 'undeterminable', 'none'],
        'rebuttal_resolved': ['yes', 'no', 'not_rebutted', 'undeterminable'],
    },
}
FIELD_LABELS = {
    'type': '발언 방식', 'target': '주된 기능',
    'addresses_specific_claim': '특정 동료의 구체적 주장에 응답함',
    'concedes_part': '동료 주장의 일부를 인정함',
    'names_disagreement_between_others': '다른 두 사람의 의견 차이를 짚음',
    'proposes_third_option': '절충안·제3의 대안·새로운 틀을 제안함',
    'objects_to_shared_view': '집단이 모이는 의견에 반론함',
    'states_position_change': '자신의 입장이 바뀌었다고 명시함',
    'instruction_followed': '제시된 지시를 수행함',
    'references_argument': '사후 이유가 대화의 구체적 논거를 참조함',
    'argument_source': '참조 논거를 처음 제시한 사람',
    'argument_seqs': '참조 논거가 등장한 발언 번호(쉼표로 구분)',
    'relevant': '논거가 최종 입장과 관련됨', 'supports': '논거가 최종 입장을 뒷받침함',
    'rebutted': '참조 논거에 반박이 제기됨', 'rebuttal_resolved': '반박에 답변·수용·해명이 있었음',
}
VALUE_LABELS = {
    'yes': '예', 'partial': '일부 해당', 'no': '아니오', 'none': '해당 없음',
    'undeterminable': '자료만으로 판단 어려움', 'not_rebutted': '반박 없음',
    'own': '본인', 'peer': '동료', 'both': '본인과 동료 모두',
    'probing': '질문·입력 요청', 'non_probing': '진술',
    'solution': '답 제시', 'reasoning': '이유 설명', 'agree': '동의',
    'disagree': '반대', 'moderation': '진행·의견 요청',
}


def read(name):
    with (SOURCE / f'{name}.csv').open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def stratified(rows, n, keys, rng):
    """Proportional allocation, at least one per nonempty stratum; fixed population."""
    pools = defaultdict(list)
    for r in rows:
        pools[tuple(r[k] for k in keys)].append(r)
    assert len(pools) <= n <= len(rows)
    allocation = {k: 1 for k in pools}
    while sum(allocation.values()) < n:
        eligible = [k for k in pools if allocation[k] < len(pools[k])]
        k = max(sorted(eligible), key=lambda k: n * len(pools[k]) / len(rows) - allocation[k])
        allocation[k] += 1
    selected = []
    for k in sorted(pools):
        pool = sorted(pools[k], key=lambda x: json.dumps(x, sort_keys=True))
        for r in rng.sample(pool, allocation[k]):
            selected.append((r, {'stratum': list(k), 'population_n': len(pool),
                                 'sample_n': allocation[k], 'weight': len(pool) / allocation[k]}))
    return selected


def key(task, row):
    return (row['discussion_id'], row['participant'] if task == 'evidence' else row['seq'],
            row.get('device', '') if task == 'device' else '')


PAGE = r'''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>숙의 연구 사람 검증</title>
<style>
*{box-sizing:border-box}body{font:17px/1.65 system-ui,sans-serif;color:#172c3b;background:#f2f5f7;margin:0}
header{background:#142f42;color:white;padding:22px max(24px,calc((100vw - 1200px)/2))}h1{font-size:25px;margin:0}
main{max-width:1200px;margin:24px auto;padding:0 20px}.toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:12px}
button,select,input{font:inherit;padding:8px;border:1px solid #a8b8c2;border-radius:6px}button{cursor:pointer;background:white}
button.primary{background:#136c85;color:white}button:disabled{opacity:.5}a{color:#08748e}
.card{padding:24px;background:white;border-radius:12px;margin:18px 0;border:1px solid #d9e2e7}
.tag{background:#e5f1f4;padding:4px 10px;border-radius:6px;font-size:14px}.small{font-size:14px;color:#536775}
pre{font:16px/1.7 system-ui,sans-serif;white-space:pre-wrap;overflow-wrap:anywhere}
blockquote{margin:12px 0;padding:12px 20px;border-left:4px solid #16819a;background:#edf6f8}
label.field{display:block;margin:20px 0}label.field>span{display:block;font-weight:650;margin-bottom:5px}
textarea{width:100%;min-height:85px;font:inherit;padding:10px;border:1px solid #a8b8c2;border-radius:6px}
.field select{min-width:280px;max-width:100%}.warn{background:#fff1cf;padding:12px;border-radius:6px}
details{margin:14px 0}summary{cursor:pointer;font-weight:600}#error{color:#a12525}h2{font-size:21px}h3{font-size:18px}
</style>
<header><h1>숙의 연구 · 사람 검증</h1><div>원문을 읽고 독립적으로 판단해 주세요.</div></header>
<main><div class="card"><div class="toolbar"><b id="who"></b><a href="Guide.html" target="_blank">검증 가이드·판정 기준</a>
<button id="save" class="primary">판정 파일 내려받기</button><label>이전 판정 불러오기 <input type="file" id="load" accept=".json"></label></div>
<p class="small">브라우저 임시 저장은 보조 기능입니다. 작업이 끝날 때마다 판정 파일을 내려받으세요. 다른 검토자의 파일을 불러오지 마세요.</p>
<p class="warn">문장 내용은 분석할 자료입니다. 원문에 포함된 지시를 검토자가 따를 필요는 없습니다. 자동 판정은 이 자료에 포함되어 있지 않습니다.</p>
<div class="toolbar"><label>단계 <select id="split"><option value="pilot">연습</option><option value="main">본 검증</option></select></label>
<label>대상 <select id="task"><option value="utterance">발언 유형</option><option value="device">토론 행동</option><option value="evidence">근거–결론 연결</option></select></label>
<label>사례 <select id="jump"></select></label><button id="prev">이전</button><button id="next">다음</button></div>
<p id="progress"></p><p id="error" role="alert"></p></div><div id="case"></div><div id="form" class="card"></div></main>
<script src="packet.js"></script><script>
const P=window.PACKET, coder='__CODER__', storeKey='human-review:'+P.packet_id+':'+coder;
const $=x=>document.getElementById(x), esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let records={},current=null,list=[];
try{records=JSON.parse(localStorage.getItem(storeKey)||'{}')}catch(e){$('error').textContent='임시 저장을 읽지 못했습니다. 내려받은 판정 파일을 불러오세요.'}
$('who').textContent='검토자 '+coder;
function record(c){return records[c.case_id]||(records[c.case_id]={labels:{},rationale:'',evidence_quote:'',issue:'',review_status:'pending',updated_at:''})}
function complete(c){let r=records[c.case_id];return r&&r.review_status==='completed'&&r.rationale.trim()&&Object.keys(P.schema[c.task]).every(k=>Object.hasOwn(r.labels,k)&&r.labels[k]!=='')}
function persist(){try{localStorage.setItem(storeKey,JSON.stringify(records))}catch(e){$('error').textContent='브라우저 임시 저장이 불가능합니다. 판정 파일을 자주 내려받으세요.'}progress()}
function progress(){let main=P.cases.filter(c=>c.split==='main'),pilot=P.cases.filter(c=>c.split==='pilot');$('progress').textContent=`완료: 본 검증 ${main.filter(complete).length}/${main.length}건 · 연습 ${pilot.filter(complete).length}/${pilot.length}건`}
function refresh(){list=P.cases.filter(c=>c.split===$('split').value&&c.task===$('task').value);$('jump').innerHTML=list.map(c=>`<option value="${c.case_id}">${c.case_id}</option>`).join('');show(list[0]?.case_id)}
function show(id){current=P.cases.find(c=>c.case_id===id);if(!current)return;$('jump').value=id;let c=current,r=record(c),i=list.indexOf(c);$('prev').disabled=i===0;$('next').disabled=i===list.length-1;
let txt=`<div class="card"><span class="tag">${esc(c.case_id)} · ${c.split==='pilot'?'연습':'본 검증'}</span><h2>${esc(c.proposal)}</h2>`;
if(c.description)txt+=`<pre>${esc(c.description)}</pre>`;
if(c.task==='evidence')txt+=`<p><b>검토 대상: ${esc(c.speaker)}</b> · 사전 점수 ${c.pre} → 사후 점수 ${c.post}<br>0=매우 반대, 10=매우 찬성</p><h3>토론 후 이유</h3><blockquote><pre>${esc(c.reason)}</pre></blockquote><h3>전체 대화</h3><pre>${esc(c.transcript)}</pre>`;
else{txt+=`<h3>바로 앞 대화</h3><pre>${esc(c.context)||'(앞선 발언 없음)'}</pre>`;
if(c.task==='device')txt+=`<h3>해당 차례에 제공된 지시</h3><pre>${esc(c.instruction)||'(별도 지시 없음)'}</pre>`;
txt+=`<h3>판정할 발언 · #${c.seq} ${esc(c.speaker)}</h3><blockquote><pre>${esc(c.text)}</pre></blockquote><details><summary>더 앞선 대화 전체 보기</summary><pre>${esc(c.prior_transcript)||'(앞선 발언 없음)'}</pre></details>`}txt+='</div>';$('case').innerHTML=txt;
$('form').innerHTML=`<h2>판정 입력</h2><p class="small">빈칸=미입력, none=해당 없음입니다. 다릅니다. 판단이 어려우면 사유를 기록하세요.</p>`;
for(let [k,opts]of Object.entries(P.schema[c.task])){let label=document.createElement('label');label.className='field';let name=document.createElement('span');name.textContent=P.field_labels[k];label.append(name);let input=document.createElement(opts==='integer_list'?'input':'select');
if(opts==='integer_list'){input.placeholder='예: 3, 7, 12 / 참조 없음은 빈칸';input.value=(r.labels[k]||[]).join(', ');input.onchange=()=>{let s=input.value.trim();if(s&&!/^\d+(\s*,\s*\d+)*$/.test(s)){input.setCustomValidity('발언 번호를 쉼표로 구분하세요.');input.reportValidity();return}input.setCustomValidity('');r.labels[k]=s?[...new Set(s.split(',').map(Number))]:[];r.updated_at=new Date().toISOString();persist()}}
else{input.innerHTML='<option value="">선택하세요</option>'+opts.map(v=>`<option value="${v}">${esc(P.value_labels[v]||v)} (${v})</option>`).join('');input.value=r.labels[k]||'';input.onchange=()=>{r.labels[k]=input.value;r.updated_at=new Date().toISOString();persist()}}label.append(input);$('form').append(label)}
for(let [k,title]of [['rationale','판정 이유 · 필수'],['evidence_quote','근거 문장·발언 번호 · 가능한 경우 기록'],['issue','애매한 점·자료 문제 · 있을 때 기록']]){let label=document.createElement('label');label.className='field';let span=document.createElement('span');span.textContent=title;let t=document.createElement('textarea');t.value=r[k]||'';t.oninput=()=>{r[k]=t.value;r.updated_at=new Date().toISOString();persist()};label.append(span,t);$('form').append(label)}
let b=document.createElement('button');b.className='primary';b.textContent=r.review_status==='completed'?'완료 표시 다시 확인':'이 사례 판정 완료';b.onclick=()=>{if(c.task==='evidence'&&!Object.hasOwn(r.labels,'argument_seqs'))r.labels.argument_seqs=[];let missing=Object.keys(P.schema[c.task]).filter(k=>!Object.hasOwn(r.labels,k)||r.labels[k]==='');if(missing.length||!r.rationale.trim()){alert('모든 항목과 판정 이유를 입력하세요.');return}
if(c.task==='evidence'){let l=r.labels;if(l.references_argument==='yes'&&!l.argument_seqs.length){alert('참조 논거가 등장한 발언 번호를 입력하세요.');return}if(l.argument_seqs.some(s=>!c.available_seqs.includes(s))){alert('대화에 없는 발언 번호가 있습니다.');return}}
r.review_status='completed';r.updated_at=new Date().toISOString();persist();b.textContent='완료됨 · 수정한 내용도 내려받기에 반영됩니다';};$('form').append(b);progress()}
$('split').onchange=refresh;$('task').onchange=refresh;$('jump').onchange=e=>show(e.target.value);$('prev').onclick=()=>show(list[list.indexOf(current)-1].case_id);$('next').onclick=()=>show(list[list.indexOf(current)+1].case_id);
$('save').onclick=()=>{let result={packet_id:P.packet_id,coder_id:coder,codebook_version:P.codebook_version,exported_at:new Date().toISOString(),records};let blob=new Blob([JSON.stringify(result,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='human-validation-'+coder+'-'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
$('load').onchange=async e=>{try{let p=JSON.parse(await e.target.files[0].text());if(p.packet_id!==P.packet_id||p.coder_id!==coder||p.codebook_version!==P.codebook_version)throw Error('다른 표본·검토자·기준표 버전의 파일입니다.');if(!p.records||typeof p.records!=='object'||Array.isArray(p.records))throw Error('판정 파일 형식이 올바르지 않습니다.');for(let id of Object.keys(p.records))if(!P.cases.some(c=>c.case_id===id))throw Error('알 수 없는 사례가 포함되어 있습니다.');if(!confirm('현재 입력을 불러온 파일 내용으로 바꿉니다. 현재 입력을 먼저 내려받았는지 확인하세요.'))return;records=p.records;persist();show(current.case_id)}catch(err){alert('불러오기 실패: '+err.message)}};
refresh();
</script></html>'''


def build():
    if (OUT / 'coordinator/manifest.json').exists():
        raise SystemExit('Frozen packet already exists; do not overwrite distributed material.')
    rng = random.Random(SEED)
    u = read('n10_comparison_glm')
    d = read('devices_sample')
    e = read('evidence_sample')
    assert len({key('utterance', r) for r in u}) == len(u)
    assert len({key('device', r) for r in d}) == len(d)
    assert len({key('evidence', r) for r in e}) == len(e)
    selected = []
    for task, rows, n, fields in [('utterance', u, 200, ['label', 'stratum']),
                                   ('evidence', e, 60, ['item_id', 'label'])]:
        selected.extend((task, 'main', r, m) for r, m in stratified(rows, n, fields, rng))
    for dev in sorted({r['device'] for r in d}):
        pool = [r for r in d if r['device'] == dev]
        selected.extend(('device', 'main', r, m) for r, m in stratified(pool, 40, ['device', 'study'], rng))
    # Hold out entire conversations for calibration: no main transcript is reused in pilot.
    used_discussions = {r['discussion_id'] for _, _, r, _ in selected}
    for task, rows, n in [('utterance', u, 10), ('device', d, 10), ('evidence', e, 4)]:
        pool = [r for r in rows if r['discussion_id'] not in used_discussions]
        if task == 'device':
            pilot = []
            for dev in sorted({r['device'] for r in pool}):
                pilot.extend(rng.sample([r for r in pool if r['device'] == dev], 2))
        else:
            pilot = rng.sample(pool, n)
        selected.extend((task, 'pilot', r, {}) for r in pilot)
    rng.shuffle(selected)
    con = sqlite3.connect(f'file:{ROOT / "data/study1/claude.db"}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    cache = {}
    def discussion(did):
        if did not in cache:
            meta = dict(con.execute('select topic,description from discussions where id=?', (did,)).fetchone())
            msgs = [dict(x) for x in con.execute('select seq,speaker,speaker_type,content from messages where discussion_id=? order by seq', (did,))]
            cache[did] = meta, msgs
        return cache[did]
    def transcript(msgs):
        return '\n\n'.join(f"#{m['seq']} {m['speaker']}{' (moderator)' if m['speaker_type']=='moderator' else ''}: {m['content']}" for m in msgs)
    primary = {'utterance': read('n10_comparison_glm'), 'device': read('devices_large'), 'evidence': read('evidence_glm')}
    secondary = {'utterance': read('n10_comparison_large'), 'device': read('devices_small'), 'evidence': read('evidence_sonnet')}
    lookup = [{t: {key(t, r): r for r in rows} for t, rows in x.items()} for x in [primary, secondary]]
    cases, private = [], []
    counters = defaultdict(int)
    for task, split, row, sampling in selected:
        counters[(task, split)] += 1
        code = {'utterance': 'U', 'device': 'D', 'evidence': 'E'}[task]
        cid = f'{code}-{("P" if split == "pilot" else "M")}{counters[(task, split)]:03d}'
        meta, msgs = discussion(row['discussion_id'])
        c = {'case_id': cid, 'task': task, 'split': split, 'proposal': meta['topic'], 'description': meta['description'] or ''}
        if task == 'evidence':
            reason = con.execute("select reason from survey_responses where discussion_id=? and participant=? and phase='post' and participant_type='ai'", (row['discussion_id'], row['participant'])).fetchall()
            assert len(reason) == 1 and reason[0][0]
            c.update(speaker=row['participant'], pre=float(row['pre']), post=float(row['post']), reason=reason[0][0], transcript=transcript(msgs), available_seqs=[m['seq'] for m in msgs])
        else:
            seq = int(row['seq'])
            target = [m for m in msgs if m['seq'] == seq]
            assert len(target) == 1 and target[0]['speaker'] == row['speaker']
            before = [m for m in msgs if m['seq'] < seq]
            c.update(seq=seq, speaker=row['speaker'], text=target[0]['content'],
                     context=transcript([m for m in before if m['speaker_type'] != 'moderator'][-3:]), prior_transcript=transcript(before))
            if task == 'device':
                assert c['text'] == row['text']
                c['instruction'] = row['instruction']
        cases.append(c)
        private.append({'case_id': cid, 'task': task, 'split': split,
                        'source': {k: v for k, v in row.items() if k not in ['text', 'context', 'instruction']},
                        'sampling': sampling,
                        'cluster': row.get('topic_key') if task == 'utterance' else row['discussion_id'] if task == 'device' else row['item_id'],
                        'primary': lookup[0][task].get(key(task, row)), 'secondary': lookup[1][task].get(key(task, row))})
    con.close()
    cases.sort(key=lambda c: (c['split'] != 'pilot', c['task'], c['case_id']))
    body = {'schema': SCHEMA, 'field_labels': FIELD_LABELS, 'value_labels': VALUE_LABELS,
            'codebook_version': '2026-10-20', 'cases': cases}
    packet_id = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    body['packet_id'] = packet_id
    for coder in ['A', 'B']:
        dest = OUT / f'reviewer-{coder}'
        dest.mkdir(parents=True, exist_ok=True)
        (dest / 'index.html').write_text(PAGE.replace('__CODER__', coder), encoding='utf-8')
        # Escape script terminators even though this is a separate JS file.
        (dest / 'packet.js').write_text('window.PACKET = '+json.dumps(body, ensure_ascii=False).replace('</', '<\\/')+';', encoding='utf-8')
        blank = {c['case_id']: {'labels': {}, 'rationale': '', 'evidence_quote': '', 'issue': '', 'review_status': 'pending', 'updated_at': ''} for c in cases}
        write_json(dest / '판정양식.json', {'packet_id': packet_id, 'codebook_version': body['codebook_version'], 'coder_id': coder, 'records': blank})
    write_json(OUT / 'coordinator/case-map-and-machine-labels.json', private)
    write_json(OUT / 'coordinator/packet.json', body)
    write_json(OUT / 'coordinator/adjudication-template.json', {
        'packet_id': packet_id, 'codebook_version': body['codebook_version'], 'adjudicator_id': '',
        'records': {c['case_id']: {'labels': {}, 'rationale': '', 'evidence_quote': '', 'issue': '', 'review_status': 'pending', 'updated_at': '', 'disputed_fields': [], 'decision_basis': ''} for c in cases if c['split']=='main'}})
    sources = [SOURCE / f'{n}.csv' for n in ['n10_comparison_glm', 'n10_comparison_large', 'devices_sample', 'devices_large', 'devices_small', 'evidence_sample', 'evidence_glm', 'evidence_sonnet']]
    sources += [ROOT / 'data/study1/claude.db', ROOT / 'config/coding_prompts.yaml', Path(__file__)]
    manifest = {'packet_id': packet_id, 'created_date': '2026-10-20', 'seed': SEED,
                'main_n': 460, 'pilot_n': 24, 'population_n': {'utterance': len(u), 'device': len(d), 'evidence': len(e)},
                'sampling': 'N10 condition × k/size proportional (min 1); N6 40 per device, proportional by study; layer3 one per item × condition. Pilot excludes all main discussion IDs. Device unit is category × utterance; category overlaps retained.',
                'scope': 'Claude simulation; N10 already selected comparison-group utterances, N6 already selected category samples, layer3 previously selected 600 agent cases. No inference to all utterances or other model families.',
                'sources': [{'path': str(p.relative_to(ROOT)), 'sha256': digest(p)} for p in sources]}
    write_json(OUT / 'coordinator/manifest.json', manifest)
    print(json.dumps({'output': str(OUT), 'main': 460, 'pilot': 24, 'packet_id': packet_id}, indent=2))


if __name__ == '__main__':
    build()
