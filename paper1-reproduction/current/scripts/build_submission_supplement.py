"""Assemble a Korean SI review document and local attachments; never uploads."""
from pathlib import Path
import hashlib,json,re,shutil,subprocess,zipfile
R=Path(__file__).resolve().parents[1];B=R/'docs/research';O=B/'submission-preparation/supplement';O.mkdir(parents=True,exist_ok=True);A=O/'assets';A.mkdir(exist_ok=True)
files=[
('Supplementary Table 1 원 과제와 변형 과제','rq-artifacts/tables/task-variants.md'),
('Supplementary Table 2 등록 가설 전체 결과','review-revision/RegisteredResults.md'),
('대조 토론 사례','supplementary-information/CaseStudies.md'),
('합의와 정당 분포의 상세 비교','supplementary-information/AnalysisDetails.md'),
('설정과 본 실험 전 작동 점검','supplementary-information/EngineValidation.md'),
('대화 과정과 강건성 해설','supplementary-information/ProcessAndRobustnessDetails.md'),
('후반 답 변경','supplementary-information/LateAnswerChanges.md'),
('입장 변화 언급의 재분류','supplementary-information/PositionChangeMentions.md'),
('인간과 AI의 집단 평균 비교','supplementary-information/GroupMeanComparison.md'),
('모델 간 정책 선호 상관','supplementary-information/CrossModelPolicyPreferences.md'),
('코딩 상세 절차','supplementary-information/CodingProcedures.md'),
('기존 코딩 검증과 확인 범위','supplementary-information/CodingValidation.md'),
('상태 기반 규칙의 동결 구현','theory-review/StatefulImplementation.md'),
('강건성 분석 방법','robustness/Methods.md'),
('등록과 실제 보고의 대조','supplementary-information/RegistrationAndReporting.md'),
('별도 파일의 제목과 범례','supplementary-information/FileLegends.md')]
sections={(B/f).resolve():f'section-{i}' for i,(_,f) in enumerate(files,1)};assetmap={};unbundled=[]
def replace_link(match,p):
 label,url=match.groups()
 if url.startswith(('http:','https:','mailto:','#')):return match.group(0)
 raw,sep,frag=url.partition('#');dest=(p.parent/raw).resolve()
 if dest in sections:return f'[{label}](#{frag if frag else sections[dest]})'
 if dest.is_file() and dest.suffix.lower() not in ['.md','.db','.sqlite','.py','.r'] and dest.stat().st_size<15*1024*1024:
  key=dest
  if key not in assetmap:
   name=hashlib.sha256(str(dest.relative_to(R)).encode()).hexdigest()[:8]+'-'+dest.name
   shutil.copy2(dest,A/name);assetmap[key]=name
  return f'[{label}](assets/{assetmap[key]})'
 if dest.is_file() and dest.suffix.lower() in ['.md','.py','.r'] and dest.stat().st_size<2*1024*1024:
  name=hashlib.sha256(str(dest.relative_to(R)).encode()).hexdigest()[:8]+'-'+dest.name
  shutil.copy2(dest,A/name);assetmap[dest]=name
  unbundled.append({'from':str(p.relative_to(R)),'target':url,'packaged_record':'assets/'+name,'role':'additional provenance; core methods are in the combined SI'})
  return f'[{label}](assets/{name})'
 unbundled.append({'from':str(p.relative_to(R)),'target':url,'missing':True})
 return label+'（별도 접근 확인 필요: '+dest.name+'）'
parts=['# Supplementary Information\n\nHuman-inspired rules reshape deliberation and collective judgment in language model groups\n\nHa Hwang\n\n2026-10-26 국문 검토용 합본. 보존된 결과와 상세 방법을 묶었다. 추가 LLM 판정 조정과 확정 저자 정보를 반영했다. 원 분석값과 조정 민감도는 구분했다. 영문 번역과 최종 투고 승인은 포함하지 않는다.\n\n## 내용 안내\n\n보충 표 1–15, 보충 그림 1–2, 상세 방법·해석, 등록·실제 수행 대조를 포함한다. 수치 원자료와 전체 예시 토론은 함께 준비한 별도 파일에서 제공한다.\n']
for i,(title,f) in enumerate(files,1):
 p=B/f;t=p.read_text();aliases=re.findall(r'<a id="([^"]+)"></a>',t.splitlines()[0])
 t=re.sub(r'^# .+\n','',t,count=1)
 t=''.join('<a id="'+v+'"></a>\n\n' for v in aliases)+t
 t=t.replace('Human-inspired rules reshape deliberation and collective judgment in language model groups\n','')
 # Remove only dated component-production notes; preserve scientific qualifications and pending markers.
 paras=t.strip().split('\n\n');paras=[x for x in paras if not (x.startswith(('작성:', '작성일:', '계산일:', '2026-10-21.', '국문 작업 원고,')))]
 t='\n\n'.join(paras)
 t=re.sub(r'<a id="([^"]+)"></a>', r'\n\n[]{#\1}\n\n', t)
 t=re.sub(r'^(#{2,5}) ', lambda m: '#'+m.group(1)+' ', t, flags=re.M)
 t=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',lambda m:replace_link(m,p),t)
 # Each component begins on a new page in Word; keep unique anchors in Markdown.
 parts.append(f'\n\n## {title} {{#{sections[p.resolve()]}}}\n\n'+t)
text='\n'.join(parts)+'\n';md=O/'SupplementaryInformation.ko.md';md.write_text(text)
manifest={'status':'Korean review compilation; human validation and author facts pending','components':{f:hashlib.sha256((B/f).read_bytes()).hexdigest() for _,f in files},'assets':{str(p.relative_to(R)):name for p,name in assetmap.items()},'nonembedded_trace_records':unbundled}
(O/'compilation-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
subprocess.run(['pandoc',str(md),'-f','markdown+raw_html','-t','html5','--standalone','--resource-path',str(O),'--metadata','title=Supplementary Information','-o',str(O/'SupplementaryInformation.ko.html')],check=True)
if '--docx' in __import__('sys').argv:
 subprocess.run(['pandoc',str(md),'--resource-path',str(O),'-o',str(O/'SupplementaryInformation.ko.docx')],check=True)
 from docx import Document
 from docx.shared import Inches,Pt
 from docx.oxml import OxmlElement
 from docx.oxml.ns import qn
 from docx.enum.section import WD_ORIENT
 doc=Document(O/'SupplementaryInformation.ko.docx')
 for sec in doc.sections:
  sec.orientation=WD_ORIENT.LANDSCAPE;sec.page_width=Inches(11.69);sec.page_height=Inches(8.27)
  sec.top_margin=sec.bottom_margin=Inches(.65);sec.left_margin=sec.right_margin=Inches(.65)
  footer=sec.footer.paragraphs[0];footer.alignment=2;run=footer.add_run();fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');run._r.addnext(fld)
 for name in ['Normal','Body Text','Caption','Table']:
  if name in doc.styles:
   st=doc.styles[name];st.font.name='Arial Unicode MS';st.font.size=Pt(10)
   st.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'Arial Unicode MS')
   if hasattr(st,'paragraph_format'):st.paragraph_format.space_after=Pt(5)
 for name in ['Title','Heading 1','Heading 2','Heading 3','Heading 4']:
  st=doc.styles[name];st.font.color.rgb=__import__('docx').shared.RGBColor(0,0,0);st.font.name='Arial Unicode MS'
  st.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'Arial Unicode MS')
 for p in doc.paragraphs:
  if p.style.name=='Heading 2':p.paragraph_format.page_break_before=False
  if p.style.name.startswith('Heading') or p.text.startswith('Title:'):p.paragraph_format.keep_with_next=True
 for table in doc.tables:
  table.autofit=False;n=len(table.columns);width=10.39/n
  for col in table.columns:col.width=Inches(width)
  for ri,row in enumerate(table.rows):
   nosplit=OxmlElement('w:cantSplit');row._tr.get_or_add_trPr().append(nosplit)
   if ri==0:
    hdr=OxmlElement('w:tblHeader');row._tr.get_or_add_trPr().append(hdr)
   for cell in row.cells:
    cell.width=Inches(width)
    for p in cell.paragraphs:
     p.paragraph_format.space_after=Pt(2);p.paragraph_format.keep_with_next=False
     for run in p.runs:run.font.size=Pt(8.5 if n>=7 else 9.5)
 # Cap all inline charts to landscape content width.
 for shape in doc.inline_shapes:
  ratio=min(1, Inches(10.2)/shape.width, Inches(5.3)/shape.height)
  if ratio<1:shape.height=int(shape.height*ratio);shape.width=int(shape.width*ratio)
 for runprops in doc.element.xpath('.//w:rPr'):
  rf=runprops.find(qn('w:rFonts'))
  if rf is None:rf=OxmlElement('w:rFonts');runprops.insert(0,rf)
  for key in ['ascii','hAnsi','eastAsia','cs']:rf.set(qn('w:'+key),'Arial Unicode MS')
  for key in ['asciiTheme','hAnsiTheme','eastAsiaTheme','cstheme']:
   if qn('w:'+key) in rf.attrib:del rf.attrib[qn('w:'+key)]
 doc.save(O/'SupplementaryInformation.ko.docx')
print(json.dumps({'components':len(files),'assets':len(assetmap),'trace_records_not_embedded':len(unbundled),'output':str(O.relative_to(R))}))
