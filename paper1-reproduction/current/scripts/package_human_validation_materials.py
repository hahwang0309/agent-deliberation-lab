"""Package frozen review data with guides and a blind adjudication interface.

Rendering Guide.html requires the bundled Node `marked` package; supply its path.
Does not change sampled cases or any submitted human responses.
"""
import argparse
import hashlib
import json
import subprocess
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path

from build_human_validation_materials import OUT, PAGE, ROOT


ADJ_SCRIPT = r'''
let submissions={};
$('who').textContent='책임자 · 불일치 조정';
$('split').value='main';$('split').disabled=true;
const tools=document.createElement('div');tools.className='toolbar';tools.innerHTML='<label>A 독립 판정 <input type="file" id="aFile" accept=".json"></label><label>B 독립 판정 <input type="file" id="bFile" accept=".json"></label><button id="draft">두 파일로 조정 초안 만들기</button><label>조정 담당자 <input id="adjudicator" placeholder="식별자"></label>';
document.querySelector('.card').append(tools);
$('adjudicator').value=localStorage.getItem(storeKey+':adjudicator')||'';
$('adjudicator').oninput=()=>{try{localStorage.setItem(storeKey+':adjudicator',$('adjudicator').value)}catch(e){}};
for(let [id,who] of [['aFile','A'],['bFile','B']])$(id).onchange=async e=>{try{let x=JSON.parse(await e.target.files[0].text());if(x.packet_id!==P.packet_id||x.coder_id!==who||x.codebook_version!==P.codebook_version)throw Error('표본·검토자·기준표 버전 불일치');for(let c of P.cases.filter(c=>c.split==='main')){let r=x.records?.[c.case_id];if(!r||r.review_status!=='completed'||!r.rationale?.trim()||Object.entries(P.schema[c.task]).some(([k,v])=>v==='integer_list'?!Array.isArray(r.labels?.[k]):!v.includes(r.labels?.[k])))throw Error('미완료 또는 잘못된 라벨: '+c.case_id)}submissions[who]=x;alert(who+' 파일 불러옴. 두 파일을 준비한 뒤 조정 초안을 만드세요.')}catch(err){alert(err.message)}};
const equal=(a,b)=>JSON.stringify(Array.isArray(a)?[...a].sort((x,y)=>x-y):a)===JSON.stringify(Array.isArray(b)?[...b].sort((x,y)=>x-y):b);
$('draft').onclick=()=>{if(!submissions.A||!submissions.B){alert('A·B 독립 판정을 모두 불러오세요.');return}if(!confirm('현재 조정 입력을 새 초안으로 바꿉니다. 기존 작업을 먼저 내려받았는지 확인하세요.'))return;records={};for(let c of P.cases.filter(c=>c.split==='main')){let a=submissions.A.records[c.case_id],b=submissions.B.records[c.case_id],labels={},disputed=[];for(let k of Object.keys(P.schema[c.task])){if(equal(a.labels[k],b.labels[k]))labels[k]=a.labels[k];else disputed.push(k)}records[c.case_id]={labels,rationale:disputed.length?'':'두 독립 검토자의 라벨 일치. A 이유: '+a.rationale+' / B 이유: '+b.rationale,evidence_quote:'',issue:[a.issue,b.issue].filter(Boolean).join(' / '),review_status:disputed.length?'pending':'completed',updated_at:new Date().toISOString(),reviewer_a:a,reviewer_b:b,disputed_fields:disputed,decision_basis:disputed.length?'':'두 독립 판정 일치'}}persist();show(current.case_id)};
const baseShow=show;
show=function(id){baseShow(id);let r=record(current);if(!r.reviewer_a){let p=document.createElement('p');p.className='warn';p.textContent='A·B 파일로 조정 초안을 먼저 만드세요. 예전 조정 파일을 불러와 이어갈 수도 있습니다.';$('form').prepend(p);return}let box=document.createElement('div');box.className='card';box.innerHTML='<h3>독립 판정 비교</h3><p class="small">불일치: '+esc(r.disputed_fields.map(k=>P.field_labels[k]).join(', ')||'없음')+'</p>';
for(let [title,v]of [['A',r.reviewer_a],['B',r.reviewer_b]]){let h=document.createElement('h3');h.textContent=title;let pre=document.createElement('pre');pre.textContent=Object.entries(v.labels).map(([k,val])=>P.field_labels[k]+': '+(Array.isArray(val)?val.join(', '):(P.value_labels[val]||val))).join('\n')+'\n판정 이유: '+v.rationale+'\n근거: '+v.evidence_quote;box.append(h,pre)}$('form').prepend(box);
let label=document.createElement('label');label.className='field';let span=document.createElement('span');span.textContent='조정 근거 · 불일치 사례 필수';let t=document.createElement('textarea');t.value=r.decision_basis||'';t.oninput=()=>{r.decision_basis=t.value;r.review_status='pending';r.updated_at=new Date().toISOString();persist();edited()};label.append(span,t);$('form').insertBefore(label,$('form').lastChild);
let finish=$('form').lastChild, old=finish.onclick;finish.onclick=()=>{if(r.disputed_fields.length&&!r.decision_basis.trim()){alert('불일치를 어떻게 결정했는지 조정 근거를 적으세요.');return}old()}};
$('save').onclick=()=>{if(!$('adjudicator').value.trim()){alert('조정 담당자 식별자를 입력하세요.');return}let x={packet_id:P.packet_id,codebook_version:P.codebook_version,coder_id:'ADJ',adjudicator_id:$('adjudicator').value.trim(),exported_at:new Date().toISOString(),records};let b=new Blob([JSON.stringify(x,null,2)],{type:'application/json'}),url=URL.createObjectURL(b),a=document.createElement('a');a.href=url;a.download='human-validation-ADJ-'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
'''


def enhance(page):
    page = page.replace('<button id="next">다음</button>', '<button id="next">다음</button><button id="incomplete">다음 미완료 사례</button>')
    page = page.replace("refresh();\n</script>", """
$('incomplete').onclick=()=>{let remaining=P.cases.filter(c=>c.split===$('split').value&&!complete(c));if(!remaining.length){alert('이 단계의 모든 사례가 완료되었습니다.');return}let after=remaining.find(c=>P.cases.indexOf(c)>P.cases.indexOf(current))||remaining[0];$('task').value=after.task;refresh();show(after.case_id);$('case').scrollIntoView()};
refresh();
</script>""")
    page = page.replace('<button id="save" class="primary">', '<button onclick="document.getElementById(\'form\').scrollIntoView()">판정 입력으로 이동</button><button id="save" class="primary">')
    page = page.replace('<div id="form" class="card"></div></main>', '<div id="form" class="card"></div><div class="toolbar card"><button onclick="document.getElementById(\'prev\').click();document.getElementById(\'case\').scrollIntoView()">이전 사례</button><button onclick="document.getElementById(\'next\').click();document.getElementById(\'case\').scrollIntoView()">다음 사례</button><button onclick="window.scrollTo(0,0)">선택 메뉴로</button></div></main>')
    page = page.replace("r.updated_at=new Date().toISOString();persist()", "r.review_status='pending';r.updated_at=new Date().toISOString();persist();edited()")
    # Restore completion handler after general edit-state change above.
    page = page.replace("r.review_status='completed';r.review_status='pending';r.updated_at=new Date().toISOString();persist();edited()", "r.review_status='completed';r.updated_at=new Date().toISOString();persist()")
    # An edit after completion returns the case to pending; the button must say so.
    page = page.replace("function persist(){", "function edited(){let d=$('done');if(d&&d.textContent.startsWith('완료'))d.textContent='이 사례 판정 완료 · 수정되어 다시 눌러야 함'}\nfunction persist(){", 1)
    page = page.replace("b.className='primary';", "b.className='primary';b.id='done';", 1)
    page = page.replace("b.textContent='완료됨 · 수정한 내용도 내려받기에 반영됩니다';", "b.textContent='완료됨 · 수정하면 다시 눌러야 함';", 1)
    # Invalid seq input must not leave the previous valid list stored.
    old_invalid = "input.setCustomValidity('발언 번호를 쉼표로 구분하세요.');input.reportValidity();return}"
    assert old_invalid in page
    page = page.replace(old_invalid, "input.setCustomValidity('발언 번호를 쉼표로 구분하세요.');input.reportValidity();r.labels[k]='';r.review_status='pending';r.updated_at=new Date().toISOString();persist();edited();return}", 1)
    anchor = "if(c.task==='evidence'){let l=r.labels;"
    checks = """if(c.task==='device'&&((!c.instruction)!==(r.labels.instruction_followed==='none'))){alert('별도 지시가 없을 때만 지시 수행 항목을 해당 없음으로 선택하세요.');return}
if(c.task==='evidence'){let l=r.labels;
if(l.references_argument!=='yes'&&(l.argument_source!=='none'||l.argument_seqs.length||['relevant','supports','rebutted'].some(k=>l[k]!=='none')||l.rebuttal_resolved!=='undeterminable')){alert('참조가 없거나 판단 어려움이면 출처·관련성·지지·반박은 해당 없음, 근거 번호는 비움, 반박 답변은 판단 어려움으로 입력하세요.');return}
if(l.references_argument==='yes'&&(l.argument_source==='none'||['relevant','supports','rebutted'].some(k=>l[k]==='none'))){alert('참조가 있으면 출처와 관련성·지지·반박을 해당 없음으로 두지 마세요.');return}
if(l.references_argument==='yes'&&((l.rebutted==='no'&&l.rebuttal_resolved!=='not_rebutted')||(l.rebutted==='yes'&&l.rebuttal_resolved==='not_rebutted')||(l.rebutted==='undeterminable'&&l.rebuttal_resolved!=='undeterminable'))){alert('반박 여부와 반박 답변 항목의 건너뛰기 규칙을 확인하세요.');return}
"""
    assert anchor in page
    return page.replace(anchor, checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', required=True); parser.add_argument('--marked', required=True)
    args = parser.parse_args()
    guide = (OUT / 'Guide.md').read_text()
    js = "const fs=require('fs'); const {marked}=require(process.argv[1]); process.stdout.write(marked.parse(fs.readFileSync(0,'utf8')));"
    def render_guide(markdown):
        rendered = subprocess.run([args.node, '-e', js, args.marked], input=markdown, text=True, capture_output=True, check=True).stdout
        return '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>사람 검증 가이드</title><style>body{font:17px/1.75 system-ui;max-width:1100px;padding:25px;margin:auto;color:#173043}table{border-collapse:collapse;width:100%;font-size:15px}td,th{border:1px solid #b7c9d4;padding:10px;text-align:left}th{background:#eaf3f6}pre{white-space:pre-wrap;background:#eff3f5;padding:15px}h2{margin-top:45px}a{color:#076c86}</style>'+rendered+'</html>'
    guide_html = render_guide(guide)
    # Independent coders must not see existing label prevalence or anticipated findings.
    definitions = guide[guide.index('## 3. 공통 판정 원칙'):guide.index('## 7. 불일치 조정')]
    definitions = '\n'.join(line for line in definitions.splitlines() if not line.startswith('**원고의 주요 비교는'))
    reviewer_guide = '''# 검토자용 안내·판정 기준표

기준표 버전: 2026-10-20. 본 검증 460건(U 발언 유형 200, D 토론 행동 200, E 근거–결론 연결 60), 연습 24건(U 10, D 10, E 4).

## 시작하고 제출하는 방법

1. 압축을 풀고 index.html을 브라우저에서 연다. 파일 전체를 같은 폴더에 둔다. 인터넷·로그인 없이 사용할 수 있다.
2. 먼저 ‘연습’의 세 대상을 모두 판정하고 책임자와 기준을 맞춘다. 책임자가 기준을 확정한 뒤 본 검증을 시작한다.
3. 본 검증은 각자 독립적으로 한다. 다른 검토자·자동 판정을 보거나 답을 상의하지 않는다. 영어 원문을 읽고 아래 정의에 따라 판단한다.
4. 각 항목과 판정 이유를 입력하고 완료 버튼을 누른다. 긴 대화를 읽은 뒤 화면 아래 버튼으로 다음 사례로 이동할 수 있다. ‘다음 미완료 사례’는 아직 끝내지 않은 사례를 찾는다.
5. 작업이 끝날 때마다 ‘판정 파일 내려받기’를 누른다. 임시 저장만 믿지 않는다. 다음 작업에서는 자신의 이전 판정 파일을 불러와 이어간다. 불러오기는 현재 입력을 대체하므로 먼저 백업한다.
6. 본 검증 완료 후 내려받은 판정 파일과 ReviewerRecord.md를 책임자에게 제출한다. 미완료·자료 문제는 사례 ID와 함께 알린다.

예시는 정의를 설명하기 위한 가상 문장이다. 실제 사례의 정답은 제공하지 않는다. 원문은 번역하지 않고 유지했다. 번역 보조를 쓴다면 원문을 확인하고 도구·범위를 작업 기록에 남긴다. 다른 언어모델에 사람 판정을 대신 맡기지 않는다.

'''+definitions+'\n\n## 제출 확인\n\n- [ ] 본 검증 U 200 / D 200 / E 60 완료\n- [ ] 판정 이유와 E 근거 번호 입력\n- [ ] 판정 파일을 내려받아 책임자에게 제출\n- [ ] ReviewerRecord.md 작성·제출\n- [ ] 자료 문제·미완료 사례를 별도로 알림\n'
    (OUT / 'ReviewerGuide.md').write_text(reviewer_guide)
    reviewer_html = render_guide(reviewer_guide)
    for coder in ['A', 'B']:
        dest = OUT / f'reviewer-{coder}'
        (dest / 'index.html').write_text(enhance(PAGE.replace('__CODER__', coder)))
        (dest / 'Guide.html').write_text(reviewer_html)
        (dest / 'Guide.md').write_text(reviewer_guide)
        (dest / 'ReviewerRecord.md').write_text((OUT / 'templates/ReviewerRecord.md').read_text())
        with zipfile.ZipFile(OUT / f'reviewer-{coder}.zip', 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(dest.iterdir()):
                z.write(p, arcname=unicodedata.normalize('NFC', f'reviewer-{coder}/{p.name}'))
    dest = OUT / 'coordinator'
    template_path = dest / 'adjudication-template.json'
    template = json.loads(template_path.read_text())
    template['coder_id'] = 'ADJ'
    template_path.write_text(json.dumps(template, ensure_ascii=False, indent=2))
    packet = json.loads((dest / 'packet.json').read_text())
    (dest / 'packet.js').write_text('window.PACKET = '+json.dumps(packet, ensure_ascii=False).replace('</', '<\\/')+';')
    adj = enhance(PAGE.replace('__CODER__', 'ADJ'))
    adj = adj.replace("refresh();\n</script>", ADJ_SCRIPT+"\nrefresh();\n</script>")
    assert '두 파일로 조정 초안 만들기' in adj
    adj = adj.replace('다른 검토자의 파일을 불러오지 마세요.', '독립 판정 파일은 아래 A·B 선택란에 넣으세요. 이전 조정 파일은 이전 판정 불러오기를 사용하세요.')
    (dest / 'adjudication.html').write_text(adj)
    (dest / 'Guide.html').write_text(guide_html.replace('href="ReviewerGuide.md"', 'href="../ReviewerGuide.md"'))
    mapping = json.loads((dest / 'case-map-and-machine-labels.json').read_text())
    counts = Counter((m['task'], m['source'].get('label'), m['source'].get('device',''), m['source'].get('study','')) for m in mapping if m['split']=='main')
    strata = Counter((m['source']['label'], m['source']['stratum']) for m in mapping if m['split']=='main' and m['task']=='utterance')
    text = '''# 고정 표본 추출 기록

작성일: 2026-10-20. 추출 시드 20261020. 응답·분류 결과를 기준으로 표본을 고르지 않았다. 사람 검증은 아직 미실시다.

## 표집틀과 추출

- U: 기존 N10 비교용 2,440발언에서 조건 × 초기 정답자 수(k=0/1/2+) × 집단 크기(2–3/4–6)의 12개 층으로 200건 비례 추출. 각 층 최소 1건. 일반 토론 100, 규칙 토론 100. 원래 N10 비교용 집단의 표집틀에 한정하며 전체 실험 발언으로 일반화하지 않는다.
- D: 기존 1,500개의 ‘장치 종류 × 발언’에서 네 종류 및 지시 없는 대조 각 40건, 총 200건. 종류 안에서는 논리/정책 과제 비율에 따라 추출. 원래 종류별 300건에 대한 검증이다. 같은 발언이 여러 종류에 속할 수 있으며 해당 표집 단위를 보존했다.
- E: 기존 600명의 ‘참여자 × 토론’ 표집틀에서 30문항 × 두 토론 조건별로 한 명씩 무작위 추출, 총 60건. 기존에 문항별 두 블록·각 다섯 참여자를 추출한 범위에 한정한다.
- 연습: U 10, D 10(종류별 2), E 4. 본 검증에 등장한 토론 ID를 모두 제외한 뒤 추출해 대화 노출이 겹치지 않는다. 서로 다른 검증 묶음의 본 표본 사이에는 대화가 겹칠 수 있다.
- 가중치: 각 본 검증 층의 원 표집틀 건수 / 추출 건수. source_pool_weighted는 해당 원 표집틀에 대한 재가중이며, 전체 AI 대화의 모집단 가중치가 아니다.
- 모든 사례는 Claude 시뮬레이션이다. 자동 분류 모델의 계열과 시뮬레이션 모델의 계열은 별개다.

## 본 검증의 실제 배분

| 묶음 | 토론 조건 | 장치 종류 | 과제 | 건수 |
|---|---|---|---|---:|
'''
    text += '\n'.join('| '+' | '.join(str(x) if x else '—' for x in k)+f' | {n} |' for k,n in sorted(counts.items()))
    text += '\n\n### U 세부 층\n\n| 조건 | k·집단 크기 | 건수 |\n|---|---|---:|\n'
    text += '\n'.join(f'| {k[0]} | {k[1]} | {n} |' for k,n in sorted(strata.items()))
    ds=[m for m in mapping if m['split']=='main' and m['task']=='device']
    duplicate_count=len(ds)-len({(m['source']['discussion_id'],m['source']['seq']) for m in ds})
    text += f'\n\nD 본 검증의 물리적으로 같은 발언 중복: {duplicate_count}건(다른 장치 범주). 의존성을 고려할 때 토론 단위와 중복을 반영한다. 독립 발언 200개라고 보고하지 않는다.\n'
    text += '\n## 출처·눈가림·재현\n\nmanifest.json에 고정 패킷 ID, 시드, 입력 파일 해시를 기록했다. packet.json은 검토자에게 보여 준 원문, case-map-and-machine-labels.json은 사례 ID와 원자료·자동 판정 연결이다. 자동 코딩의 결측은 null로 유지한다. 검토자 배포 묶음에는 조건·장치 종류·초기 정답자 수·원자료 ID·자동 라벨을 넣지 않았다. 단, 지시 수행을 판단하기 위한 지시문과 원문 내용으로 조건을 짐작할 수 있어 완전 눈가림은 아니다.\n\n검토자용 판정 예시의 정답을 모델이 만들어 채우지 않았다. 모든 판정은 빈 상태다. build_human_validation_materials.py가 고정 표본·원문을 생성하고 package_human_validation_materials.py가 입력 화면·가이드·배포 압축을 구성한다. 배포 후 동일 경로를 다시 추출해 덮어쓰지 않는다.\n'
    (dest / 'Sampling.md').write_text(text)
    manifest = json.loads((dest / 'manifest.json').read_text())
    manifest['materials_sha256'] = {str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'manifest.json' and 'completed-results' not in p.parts}
    manifest['tool_sources'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__), ROOT/'scripts/summarize_human_validation.py']}
    (dest / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print('Packaged A/B packets, adjudication interface, guide, and frozen manifest.')


if __name__ == '__main__':
    main()
