"""Common descriptive human/AI group-mean comparison; no external calls."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/research/consensus-representation/source-data'
OUT = ROOT / 'docs/research/group-mean-comparison'
OUT.mkdir(exist_ok=True)
SEED, NBOOT = 20261024, 10000
paths = [SOURCE / 'human-native-groups.csv', SOURCE / 'results.json']
old = json.loads(paths[1].read_text())
h = pd.read_csv(paths[0]).rename(columns={'item': 'item_id'})
items = sorted(h.item_id.unique())
indices = np.random.default_rng(SEED).integers(len(items), size=(NBOOT, len(items)))
frames = {'Human': h}
for model in ['claude', 'gemini', 'mistral']:
    path = ROOT / f'docs/research/robustness/source-data/{model}-group-functionals.csv'
    paths.append(path)
    a = pd.read_csv(path)
    for arm in ['A-baseline', 'A-stateful']:
        frames[f'{model}/{arm}'] = a[['item_id', 'block', 'pre', f'mean_{arm}']].rename(
            columns={'block': 'group', 'pre': 'pre_mean', f'mean_{arm}': 'post_mean'})

def record(point, draws):
    return {'estimate': float(point), 'ci': np.quantile(draws, [.025, .975]).tolist()}

rows, results, draws_by, item_rows = [], {}, {}, []
for name, frame in frames.items():
    records = []
    for item in items:
        q = frame[frame.item_id == item]
        x, y = q.pre_mean.to_numpy(), q.post_mean.to_numpy()
        xc, yc = x-x.mean(), y-y.mean()
        records.append(dict(item=item, n=len(q), vx=np.mean(xc**2), cov=np.mean(xc*yc),
            pre_between=np.var(x, ddof=1), post_between=np.var(y, ddof=1),
            signed_shift=np.mean(y-x), absolute_shift=np.mean(np.abs(y-x)),
            pre_mean=x.mean(), post_mean=y.mean()))
    t = pd.DataFrame(records)
    # Independent check: weighted least squares with within-item centering.
    xall, yall, weights = [], [], []
    for _, q in frame.groupby('item_id'):
        xall.extend(q.pre_mean-q.pre_mean.mean())
        yall.extend(q.post_mean-q.post_mean.mean())
        weights.extend([1/len(q)]*len(q))
    xall, yall, weights = map(np.asarray, [xall, yall, weights])
    slope = t['cov'].mean()/t.vx.mean()
    independent = np.linalg.lstsq((xall*np.sqrt(weights))[:, None], yall*np.sqrt(weights), rcond=None)[0][0]
    assert np.isclose(slope, independent, atol=1e-12)
    reference = old['human']['native']['item_bootstrap'] if name == 'Human' else old['models'][name.split('/')[0]]['levels'][name.split('/')[1]]['item_bootstrap']
    assert np.isclose(slope, reference['initial_final_mean_slope']['estimate'], atol=1e-12)
    point = {'slope': slope}
    draws = {'slope': t['cov'].to_numpy()[indices].mean(axis=1)/t.vx.to_numpy()[indices].mean(axis=1)}
    for key in ['pre_between', 'post_between', 'signed_shift', 'absolute_shift', 'pre_mean', 'post_mean']:
        point[key] = t[key].mean()
        draws[key] = t[key].to_numpy()[indices].mean(axis=1)
    point['between_change'] = point['post_between']-point['pre_between']
    draws['between_change'] = draws['post_between']-draws['pre_between']
    results[name] = {k: record(v, draws[k]) for k, v in point.items()}
    draws_by[name] = draws
    rows.append({'sample': name, 'group_item_records': len(frame), **point})
    item_rows.extend(t.assign(sample=name).to_dict('records'))

contrasts = {}
for model in ['claude', 'gemini', 'mistral']:
    b, s = f'{model}/A-baseline', f'{model}/A-stateful'
    for first, second in [(s, b), (b, 'Human'), (s, 'Human')]:
        contrasts[f'{first} minus {second}'] = {k: record(results[first][k]['estimate']-results[second][k]['estimate'], draws_by[first][k]-draws_by[second][k]) for k in ['slope', 'between_change', 'absolute_shift']}

payload = dict(date='2026-10-24', status='Post-hoc descriptive comparison', seed=SEED,
    n_boot=NBOOT, n_items=len(items), method='Equal-policy weights; within-policy centered slope; joint item bootstrap; between-group sample variance with G-1 denominator; common model without default-response adjustment.',
    results=results, contrasts=contrasts,
    human_room_bootstrap_slope=old['human']['native']['actual_room_cluster_bootstrap']['initial_final_mean_slope'],
    human_balanced5_slope=old['human']['balanced5']['item_bootstrap']['initial_final_mean_slope'],
    verification={'matches_prior_slopes': True, 'independent_weighted_least_squares': True},
    inputs={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
(OUT/'results.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
pd.DataFrame(rows).to_csv(OUT/'comparison.csv', index=False)
pd.DataFrame(item_rows).to_csv(OUT/'item-metrics.csv', index=False)

def fmt(r):
    return f"{r['estimate']:.3f} [{r['ci'][0]:.3f}, {r['ci'][1]:.3f}]"

lines = ['# 인간·일반 AI·상태 기반 AI의 집단 평균 태도 비교', '',
'계산일: 2026-10-24. 기존 자료를 다시 계산한 사후 탐색 비교이며 원고 본문은 변경하지 않았다.', '',
'## 1. 원고의 0.237·0.313·0.226점은 무엇인가?', '',
'이 값은 토론 전후 평균 변화량이 아니다. 같은 정책에서 토론 전 집단 평균 태도(pre-deliberation group mean attitude)가 1점 다른 토론들을 비교할 때, 토론 후 집단 평균 태도(post-deliberation group mean attitude)의 차이가 상태 기반 조건에서 일반 토론보다 얼마나 더 큰지를 나타내는 추가 기울기다. 기존 수치는 모델 기본 응답과 반복 인물을 고려했다. 인간 자료에는 이에 대응하는 모델 기본 응답이 없으므로 아래 공통 비교는 모든 대상에서 그 변수를 제외하고 같은 계산식을 사용했다.', '',
'## 2. 토론 전 집단 평균과 토론 후 집단 평균의 연결', '',
'같은 정책에서 토론 전 집단 평균이 1점 높은 토론은 토론 후 평균이 몇 점 높은가를 나타낸다. 정책마다 평균을 빼서 정책 자체의 지지도 차이를 제거하고, 30개 정책에 같은 비중을 주었다. 값이 0이면 초기 평균과 최종 평균의 선형 연결이 없고, 1이면 초기 1점 차이에 최종 1점 차이가 대응한다.', '',
'| 대상 | 인간 | 일반 토론 | 상태 기반 토론 | 상태 기반−일반 |', '|---|---|---|---|---|']
for model in ['claude', 'gemini', 'mistral']:
    lines.append(f"| {model.capitalize()} | {fmt(results['Human']['slope'])} | {fmt(results[model+'/A-baseline']['slope'])} | {fmt(results[model+'/A-stateful']['slope'])} | {fmt(contrasts[f'{model}/A-stateful minus {model}/A-baseline']['slope'])} |")
lines += ['', '인간과 일반 AI 토론 모두에서 초기 집단 평균과 최종 집단 평균은 양의 관계였다. 상태 기반 조건은 세 모델 모두 일반 토론보다 이 연결이 강했다. Claude와 Mistral의 상태 기반 기울기는 인간 실제 방의 점추정과 비슷했고, Gemini는 더 컸다. 이 유사성을 성과의 개선으로 평가하지 않는다.', '',
'## 3. 토론 후 서로 다른 토론의 결론 차이가 커졌는가?', '',
'이 질문은 위의 기울기와 다르다. 같은 정책을 토론한 여러 집단의 평균 점수에 대해 토론 전·후 표본분산을 계산했다. 집단 수 차이를 고려해 분모는 G−1을 썼다. 단위는 점수의 제곱이다.', '',
'| 대상 | 토론 전 집단 평균의 분산 | 토론 후 집단 평균의 분산 | 전후 차이 [95% 구간] |', '|---|---|---|---|']
for name, r in results.items():
    lines.append(f"| {name} | {r['pre_between']['estimate']:.3f} | {r['post_between']['estimate']:.3f} | {fmt(r['between_change'])} |")
lines += ['', '인간에서는 토론 전보다 토론 후에 집단 평균의 분산이 커졌다. 일반 AI 토론에서는 세 모델 모두 작아졌다. 상태 기반 AI에서는 Gemini에서 커졌고, Claude와 Mistral에서는 초기 수준과 뚜렷한 차이가 없었다. 세 모델의 상태 기반 최종 분산은 모두 일반 토론보다 컸다. 따라서 인간과 AI에서 공통으로 확인되는 관계는 초기 집단 평균과 최종 집단 평균의 연결이며, 토론 전보다 집단 간 차이가 커지는 결과까지 모든 AI 조건에서 같았던 것은 아니다.', '',
'## 4. 실제 토론 전후에 집단 평균은 얼마나 움직였는가?', '',
'토론별 최종 평균에서 초기 평균을 뺀 뒤 절댓값을 취해 평균했다. 예를 들어 3→5점과 7→5점은 모두 2점 이동이다. 아래 값은 기울기나 개인별 이동량과 다르다.', '',
'| 대상 | 집단 평균의 전후 이동 크기 [95% 구간], 점 |', '|---|---|']
for name, r in results.items():
    lines.append(f"| {name} | {fmt(r['absolute_shift'])} |")
lines += ['', '평균 이동량의 크기와 초기·최종 평균의 연결은 서로 다른 특성이다. 상태 기반 규칙을 추가한 뒤 Claude의 집단 평균 이동 크기는 거의 같았고, Gemini는 커졌으며 Mistral은 작아졌다. 평균의 연결이 강해졌다고 해서 모든 모델에서 이동량도 커졌다는 뜻은 아니다.', '',
'## 5. 비교 범위와 검증', '',
'- 인간은 실제 40개 토론방의 30개 정책 응답을 사용했다(방×문항 1,200건, 유효 인원 6–16명). AI는 조건마다 Claude·Gemini 416개, Mistral 415개의 다섯 명 토론을 사용했다.',
'- 인간의 사전·사후 응답은 같은 유효 참여자의 응답으로 계산했다. AI 두 조건은 같은 초기 구성으로 짝지었다. 인간 실제 토론방과 AI 토론은 구성과 절차가 다르므로 인간−AI 차이는 기술적 비교다.',
'- 표의 95% 구간은 30개 정책을 함께 10,000회 재표집한 구간이다. 인간 방 또는 반복 AI 인물의 모든 의존성을 해결한 구간은 아니다. 인간 방을 재표집한 기존 민감도 점검의 기울기는 '+fmt(payload['human_room_bootstrap_slope'])+'였다.',
'- 실제 인간 방에서 민주당 2·공화당 2·무당층 1명의 응답을 추출한 기존 다섯 명 패널 기울기는 '+fmt(payload['human_balanced5_slope'])+'였다. 이는 실제 다섯 명 토론이 아니며, 인간 기준의 크기가 구성과 측정 단위에 따라 달라짐을 보여 준다.',
'- 모든 기울기는 기존 문항별 분석 결과와 일치했고, 문항 내 중심화한 가중 최소제곱으로 독립 계산한 기울기와도 일치했다. 최종 분산은 기존 README의 G−1 기준과 일치한다.',
'- 재현: `scripts/analyze_group_mean_comparison.py`. `results.json`에 추정치·구간·대비·입력 해시, `comparison.csv`와 `item-metrics.csv`에 전체 및 문항별 수치를 저장했다.', '']
(OUT/'README.md').write_text('\n'.join(lines))
print(pd.DataFrame(rows).to_string(index=False))
