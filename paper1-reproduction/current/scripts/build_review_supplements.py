"""Reproducible review supplements: existing registered fits and a paired label bootstrap."""
from pathlib import Path
import sys,json,hashlib,sqlite3,collections
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis.coding import human_labels,composition
B=ROOT/'docs/research';O=B/'review-revision';S=O/'source-data';S.mkdir(parents=True,exist_ok=True)
def write(name,v): (S/name).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
# Resample all three arms together at the original topic/group level, after combining labels.
ai_path=ROOT/'data/study1/results/exploratory/coding/n10_comparison_glm.csv'
ai=pd.read_csv(ai_path);h=composition(human_labels(str(ROOT/'data/raw/delidata')),'topic_key').set_index('topic_key')
frames={'Human':h}
for arm in ['A-baseline','A-stateful']: frames[arm]=composition(ai[ai.label==arm],'topic_key').set_index('topic_key')
ids=sorted(set.intersection(*(set(t.index) for t in frames.values())))
assert len(ids)==68 and len(ai)==2440
arr=np.column_stack([(t.loc[ids,'solution']+t.loc[ids,'reasoning']).to_numpy() for t in frames.values()])
rng=np.random.default_rng(20261020);idx=rng.integers(0,len(ids),(10000,len(ids)));draw=arr[idx].mean(axis=1)
out={'status':'Post-hoc review supplement; automated AI labels, human validation ongoing','seed':20261020,'n_boot':10000,'unit':'paired original group; equal group weights','n_groups':len(ids),'n_ai_utterances':len(ai),'method':'Combine solution + reasoning within each group before jointly resampling matched Human/baseline/stateful rows. Percentile 95% intervals.','estimates':{}}
for i,k in enumerate(frames):out['estimates'][k]={'estimate':float(arr[:,i].mean()),'ci':np.quantile(draw[:,i],[.025,.975]).tolist(),'n':68,'unit':'group'}
for a,c in [(1,0),(2,0),(2,1)]:
 out['estimates'][list(frames)[a]+' minus '+list(frames)[c]]={'estimate':float((arr[:,a]-arr[:,c]).mean()),'ci':np.quantile(draw[:,a]-draw[:,c],[.025,.975]).tolist(),'n':68,'unit':'paired group'}
write('task-content-bootstrap.json',out)
pd.DataFrame(arr,index=ids,columns=list(frames)).rename_axis('topic_key').to_csv(S/'task-content-groups.csv')
raw=list((ROOT/'data/raw/delidata').glob('*.tsv'))
write('task-content-input-hashes.json',{str(p.relative_to(ROOT)):sha(p) for p in [ai_path,ROOT/'src/analysis/coding.py']+raw})
# Retain registered coefficients, fit status, and original multiplicity corrections without refitting.
files={p.name.removeprefix('results-').removesuffix('.json'):p for p in (ROOT/'data/study1/results').glob('results-*.json')}
models={m:next((mid,p)for mid,p in files.items()if mid.startswith(m))for m in ['claude','gemini','mistral']}
rows=[]
for short,(mid,p) in models.items():
 d=json.loads(p.read_text())
 for name,v in d['hypotheses'].items():
  entries=v.items() if name=='H2c' else [(None,v)]
  for sub,r in entries:
   label=name+(' '+sub if sub else '')
   fam='question1_holm'if name.startswith('E')else 'reference_holm'
   mult=d['families'].get(fam,{}).get(name,{}) if sub!='gamma' else {}
   rows.append({'model':short,'hypothesis':label,'source':str(p.relative_to(ROOT)),'json_path':['hypotheses',name]+([sub]if sub else []),'record':r,'multiplicity':mult,'family':fam if mult else ('H5 separate'if name=='H5'else 'reported coefficient; no family correction')})
write('registered-estimates.json',{'status':'Original registered analysis outputs; no refitting','rows':rows})
def num(x):
 if x is None:return '—'
 if isinstance(x,(list,tuple)):return '['+', '.join(num(z)for z in x)+']'
 if isinstance(x,(dict,str)):return str(x).replace('|','/')
 return f'{x:.5g}'
lines=['# Supplementary Table 2. 등록 가설 전체 결과','','등록 결과 JSON의 추정값을 그대로 옮겼다. 원 결과·모형식·진단 전체는 [기계 판독 원본](source-data/registered-estimates.json)에 있다. 경계 적합과 수렴 실패는 구분한다. H2c γ는 동반 보고 계수이며 별도 Holm 가족 검정이 아니다. H5는 잠금 22문항의 별도 검정이다. 재표집 p=0은 유한 재표집에서 반대 방향 추정이 없었다는 뜻이며 정확히 0인 확률로 해석하지 않는다.','','| 모델 | 가설 | 추정값 [95% 구간] | 원 p | Holm p | n / 집단·문항 | 방법·적합 상태 |','|---|---|---|---|---|---|---|']
for row in rows:
 r=row['record'];p=r.get('p',r.get('p_boot'));pstr=(f"0 (원 저장값; {r.get('n_boot',1000)}회 재표집)" if p==0 and 'p_boot'in r else num(p))
 n='; '.join(f'{k}={num(r[k])}' for k in ['n','groups','n_items','n_ai','n_boot','n_boot_ok']if k in r)
 status=r.get('method','bootstrap'if 'p_boot'in r else '원 모형');status+='; 경계 적합'if r.get('singular') else ''
 messages=r.get('messages',r.get('mixed_model_messages',[]));status+='; '+str(messages).replace('\n',' ').replace('\\n',' ') if messages else ''
 lines.append(f"| {row['model'].title()} | {row['hypothesis']} | {num(r.get('estimate'))} {num(r.get('ci'))} | {pstr} | {('0 (원 저장값; 재표집 해상도 제한)' if row['multiplicity'].get('p_holm')==0 else num(row['multiplicity'].get('p_holm')))} | {n} | {status} |")
lines+=['','단위: E1 정확도 비율 차이; E2 정책 절대 이동량 및 E3 SD 감소량은 0–10점; E4·E5·H3은 0–100점 이동 관련 계수; H1은 등록 조건부 로그오즈 상호작용; H2는 과잉 수렴비 FR (귀무값 1); H2b는 자료만 대비 일반 토론의 조건 계수; H2c는 거리 1점당 이동 계수; H5는 Wasserstein 거리 변화. 각 모형의 정확한 결과변수·대비·무선효과는 [등록 분석 계획](../study1-analysis-plan.md)과 원 JSON의 formula를 따른다. H1의 확률 척도 보조 비교는 [강건성 보고서](../robustness/README.md)에 별도로 제시했다.','','등록 결과를 재표집 보조 결과로 대체하지 않았다. 논거 평가–반응 연결, Fig.2d 합친 라벨, 집단 안·사이 분산과 반복 인물 모형은 별도 사후 분석이다.']
(O/'RegisteredResults.md').write_text('\n'.join(lines)+'\n')
# Publicly relevant timing audit; readonly, only main-study batches.
timing=[]
for short,(mid,p)in models.items():
 con=sqlite3.connect(f'file:{ROOT}/data/study1/{short}.db?mode=ro',uri=True)
 groups=collections.Counter();early=[]
 for did,cfg,stamp in con.execute("select id, config, completed_at from discussions where status='completed' and completed_at < '2026-10-09 13:54:00'"):
  ex=json.loads(cfg).get('experiment',{})
  if not ex.get('batch','').startswith('study1-'):continue
  window='before_minute'if stamp<'2026-10-09 13:53:00' else 'during_minute'
  groups[(ex['batch'],ex['label'],window)]+=1
  early.append({'id':did,'topic_key':ex.get('topic_key'),'label':ex['label'],'batch':ex['batch'],'completed_at_UTC':stamp,'window':window})
 excluded=json.loads(p.read_text())['excluded_blocks']
 for r in early:r['included_in_retained_main_run_pool']=not any(e['topic_key']==r['topic_key']for e in excluded)
 timing.append({'model':short,'counts':[{'batch':b,'label':l,'window':w,'n':n}for (b,l,w),n in sorted(groups.items())],'runs':early})
 con.close()
write('registration-condition-audit.json',{'seconds':'unknown; registration recorded as 2026-10-09 22:53 KST','models':timing})
l=['# 등록 분 경계의 실행 조건과 분석 포함 범위','','DB는 읽기 전용으로 조회했다. 등록 분 시작 전 200회, 분 종료 전 208회이며 정확한 등록 전 완료 수는 200–208회다. 아래 포함 여부는 본 실험의 등록 분석 잔여 실행 풀 기준이고, 각 가설에 모든 실행이 사용된다는 뜻은 아니다.','','| 모델 | 배치 | 조건 | 분 시작 전 | 해당 분 추가 | 잔여 실행 풀 포함 |','|---|---|---|---|---|---|']
for d in timing:
 keys=sorted(set((r['batch'],r['label'])for r in d['counts']))
 for b,a in keys:
  n=lambda w:sum(r['n']for r in d['counts']if r['batch']==b and r['label']==a and r['window']==w)
  l.append(f"| {d['model'].title()} | {b} | {a} | {n('before_minute')} | {n('during_minute')} | 포함 |")
l+=['','식별자·완료 시각·블록 제외 대조: [감사 원본](source-data/registration-condition-audit.json). 결과 열람 여부는 당시 기록과 저자 진술에 의존하며 DB 시각만으로 확인할 수 없다.']
(O/'RegistrationConditions.md').write_text('\n'.join(l)+'\n')
# Model summary with intervals and clearly named outcomes.
l=['# Table 2. 규칙 추가에 대한 모델별 성과','','일반 토론 대비 상태 기반 토론의 효과다. 수렴은 SD 감소량 증가, 인간 거리는 감소할수록 인간 최종 분포에 가까움을 뜻한다. 각 칸은 추정값 [95% 구간]이다. 등록 결과와 사후 관계를 구분한다.','','| 모델 | 논리 정확도 (%포인트; 등록 E1) | 정책 SD 감소량 (점; 등록 E3) | 인간 분포 거리 변화 (등록 H5) | 논거 질 반응의 규칙 효과 (점; 등록 E4) | 집단 내부 / 평균 사이 분산 (사후 문항 평균; 반복 인물 구간 아래) | 초기 평균 연결 증가 (사후) |','|---|---|---|---|---|---|---|']
for short,(mid,p)in models.items():
 d=json.loads(p.read_text())['hypotheses'];rob=json.loads((B/f'robustness/source-data/{short}-persona.json').read_text())
 # variance keys inspected below; raw complete source remains linked.
 def fmt(r,scale=1):return f"{r['estimate']*scale:+.3f} [{r['ci'][0]*scale:.3f}, {r['ci'][1]*scale:.3f}]"
 orig=json.loads((B/'novelty-review/source-data/results.json').read_text())['results'][short]['contrasts']
 assoc=rob['initial_mean_association_delta']['coefficients']['pre_centered']
 l.append(f"| {short.title()} | {fmt(d['E1'],100)} | {fmt(d['E3'])} | {fmt(d['H5'])} | {fmt(d['E4'])} | 문항 평균: {orig['within']['estimate']:+.3f} / {orig['between']['estimate']:+.3f}; 반복 인물 구간은 아래 | {fmt(assoc)} |")
l+=['','집단 평균 사이 분산의 반복 인물 모형 차이: Claude +0.517 [0.218, 0.816], Gemini +1.045 [0.652, 1.439], Mistral +0.616 [0.316, 0.916]. 내부 분산은 Claude −1.788 [−2.224, −1.353], Gemini −4.133 [−4.627, −3.640], Mistral −0.297 [−0.574, −0.020]이나 Mistral의 다른 유효 최적화 구간 [−0.608, 0.018]은 0을 포함했다. 분산 단위는 (0–10점 정책 척도)²다.','','논거 반응 열은 강−약 효과가 규칙 추가로 얼마나 달라졌는지 나타내는 질×조건 상호작용이다. 일반 토론 자체의 질 효과 H3a는 Supplementary Table 2에 제시했다. 별도 평가와 연결한 Claude의 사후 재표집 추정은 일반 토론 −0.31 [−2.36, 1.86], 상태 기반 토론 +0.55 [−0.68, 1.79]이며 ±5점 기준은 이 두 구간에만 적용했다.','','전체 등록 p·Holm 보정·분모·적합 상태: [Supplementary Table 2](review-revision/RegisteredResults.md). 사후 관계의 방법·진단: [강건성 방법](robustness/Methods.md), [추정값](robustness/README.md). 근거 절: Results 2.6–2.8. 수렴의 세 모델 공통 방향과 정확도·인간 재현의 모델 차이를 함께 보여 준다.']
(B/'Table2.md').write_text('\n'.join(l)+'\n')
print(json.dumps({'combined_label_CIs':out['estimates'],'registered_rows':len(rows),'timing':[{r['model']:len(r['runs'])}for r in timing]},ensure_ascii=False))

# Preserve the post-hoc absolute-level table when regenerating the registered summary.
import subprocess,sys
subprocess.run([sys.executable,str(ROOT/"scripts/build_manuscript_revision_additions.py"),"--tables-only"],check=True)
