"""Summarise existing coding checks; no new judgments or external calls."""
import hashlib,json
from pathlib import Path
import pandas as pd
R=Path(__file__).resolve().parents[1];B=R/'docs/research';out=B/'submission-preparation';out.mkdir(exist_ok=True)
p=R/'data/study1/results/exploratory/coding/delidata_validate_glm.csv'
t=pd.read_csv(p,keep_default_na=False);valid=t[(t.type!='')&(t.target!='')];rows=[]
for axis in ['type','target']:
 g=valid['gold_'+axis];y=valid[axis];po=float((g==y).mean());pe=sum(float((g==k).mean()*(y==k).mean()) for k in set(g)|set(y))
 for label in sorted(set(g)|set(y)):
  tp=int(((g==label)&(y==label)).sum());ng=int((g==label).sum());npred=int((y==label).sum())
  rows.append(dict(axis=axis,label=label,n_gold=ng,n_pred=npred,n_correct=tp,precision=tp/npred if npred else None,recall=tp/ng if ng else None))
 rows.append(dict(axis=axis,label='ALL',n_gold=len(g),n_pred=len(y),n_correct=int((g==y).sum()),accuracy=po,kappa=(po-pe)/(1-pe)))
pd.DataFrame(rows).to_csv(out/'existing-human-label-validation.csv',index=False)
n=json.loads((R/'data/study1/results/exploratory/claude/n10.json').read_text())
res={'source':str(p.relative_to(R)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'n_attempted':len(t),'n_valid':len(valid),'n_failed':len(t)-len(valid),'metrics':rows,'ai_intercoder_agreement':n['coder_agreement'],'new_human_judgments':False,'new_api_calls':0}
(out/'coding-validation-status.json').write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n')
lines=['# 既存 코딩 검증의 확인 범위'.replace('既存','기존'),'','2026-10-26. 저장된 판정만 재집계했다. 신규 사람 판정과 외부 API 호출은 수행하지 않았다.','','## 인간 원자료의 기존 주석과 비교','',f'보존된 DeliData 검증 표본 {len(t)}건 중 유효 판정 {len(valid)}건을 기존 인간 주석과 비교했다. 이 표본은 라벨별 층화 표본이므로 전체 자연 발언의 오분류율로 일반화하지 않는다. AI 발언에 대한 새 사람 판정을 대신하지도 않는다.','','| 분류 축 | 라벨 | 기존 주석 n | 예측 n | 정밀도 | 재현율 |','|---|---|---:|---:|---:|---:|']
for x in rows:
 if x['label']!='ALL':lines.append(f"| {x['axis']} | {x['label']} | {x['n_gold']} | {x['n_pred']} | {x['precision']:.3f} | {x['recall']:.3f} |" if x['precision'] is not None and x['recall'] is not None else f"| {x['axis']} | {x['label']} | {x['n_gold']} | {x['n_pred']} | 산출 불가 | 산출 불가 |")
lines+=['','정밀도는 해당 라벨로 판정한 발언 중 기존 인간 주석과 같은 비율, 재현율은 기존 인간 주석의 해당 발언을 찾아낸 비율이다. 두 값은 검증용 층화 표본 안의 결과다.','','## AI 발언의 코더 간 비교','',f"두 자동 코더가 모두 유효하게 분류한 AI 발언 {n['coder_agreement']['n']:,}건에서 주 기능(target)의 일치율은 {n['coder_agreement']['target']['exact']:.3f}, κ는 {n['coder_agreement']['target']['kappa']:.3f}였다. 이는 코더 간 일치도이며 사람 기준 정확도가 아니다. 답 제시와 이유 설명의 개별 비율은 사람 검증 확인 표시를 유지한다.",'','## 완료·미완료 구분','','- 완료: 기존 인간 주석 대비 검증 결과 재집계, AI 코더 간 비교, 입장 변화 발언의 GLM 불일치 조정 및 일치 표본 민감도.','- 미완료: AI 발언 유형과 정책 논거 참조에 대한 실제 사람 판정 결과 반영. 로컬 A/B 배포 양식에서 최종 판정 파일은 확인되지 않았다.','- 후속: 진행 중인 판정 결과를 연결하거나, 자동 판정에 의존하는 주장의 범위와 최종 검증 절차를 저자가 확정한다. 기존 460건 전체 또는 반드시 두 사람이 필요하다고 전제하지 않는다.','','[기계 판독 결과](coding-validation-status.json) · [라벨별 CSV](existing-human-label-validation.csv)']
(out/'CodingValidationStatus.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'attempted':len(t),'valid':len(valid),'failed':len(t)-len(valid),'target':next(x for x in rows if x['axis']=='target' and x['label']=='ALL')},ensure_ascii=False))
