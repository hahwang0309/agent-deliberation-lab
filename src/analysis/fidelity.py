"""
충실도 지표 (분석 계획 4-2절, 2026-10-08 재설계)

- 값: 사후 점수 − 그 문항의 인간 사후 평균 (문항 효과 제거)
- 셀: 정당 × 사전 점수 구간(0~1, 2~3, 4~6, 7~8, 9~10)을 문항에 걸쳐 합침
- 거리 D(표본, 기준): 셀별 1차 Wasserstein 거리의 기준 빈도 가중 평균
- FR = mean D(AI, 인간 반쪽 B) / mean D(유사 AI, 인간 반쪽 B). 유사 AI는 인간 반쪽 A에서 AI와 같은 구조
  (문항 × 정당별 인원)로 비복원 추출. 반분은 소집단 단위로 여러 번
- H5 검정량: ΔD = D(A-상태, 인간 전체) − D(A-기준선, 인간 전체) (분모가 같아 ΔFR과 부호가 같음)

입력 표의 열: AI·인간 모두 item, party, pre, post. AI는 block(복제 단위), 인간은 group(A1R 소집단).
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance

BIN_EDGES = [-0.5, 1.5, 3.5, 6.5, 8.5, 10.5]  # 0~1, 2~3, 4~6, 7~8, 9~10


def _cells(frame: pd.DataFrame, center: Dict[str, float]) -> Dict[tuple, np.ndarray]:
    value = frame["post"].to_numpy(float) - frame["item"].map(center).to_numpy(float)
    bins = pd.cut(frame["pre"], BIN_EDGES, labels=False).to_numpy()
    out: Dict[tuple, list] = {}
    for party, b, v in zip(frame["party"].to_numpy(), bins, value):
        out.setdefault((party, b), []).append(v)
    return {k: np.asarray(v) for k, v in out.items()}


def distance(sample: pd.DataFrame, ref: pd.DataFrame, center: Dict[str, float]) -> float:
    """셀별 Wasserstein 거리의 기준(ref) 빈도 가중 평균 (둘 다 있는 셀만)"""
    s, r = _cells(sample, center), _cells(ref, center)
    num = wsum = 0.0
    for cell, rv in r.items():
        if cell in s:
            num += len(rv) * wasserstein_distance(s[cell], rv)
            wsum += len(rv)
    return num / wsum if wsum else float("nan")


def item_centers(human: pd.DataFrame) -> Dict[str, float]:
    return human.groupby("item")["post"].mean().to_dict()


def pseudo_ai(half: pd.DataFrame, ai: pd.DataFrame, rng: np.random.Generator) -> Optional[pd.DataFrame]:
    """AI와 같은 구조(문항 × 정당별 인원)로 인간 반쪽에서 비복원 추출. 인원이 모자라면 None"""
    need = ai.groupby(["item", "party"]).size()
    pools = {k: g for k, g in half.groupby(["item", "party"])}
    parts = []
    for (item, party), n in need.items():
        pool = pools.get((item, party))
        if pool is None or len(pool) < n:
            return None
        parts.append(pool.iloc[rng.choice(len(pool), n, replace=False)])
    return pd.concat(parts)


def fidelity(ais: Dict[str, pd.DataFrame], human: pd.DataFrame, rng: np.random.Generator,
             nsplit: int = 8) -> Dict[str, Dict[str, float]]:
    """조건별 {D_full, FR}. 같은 반분·유사 AI를 모든 조건에 써서 짝지은 비교가 되게 한다.
    인간 기준은 AI가 있는 문항만 쓴다"""
    items = set.intersection(*[set(a["item"]) for a in ais.values()])
    human = human[human["item"].isin(items)]
    center = item_centers(human)
    out = {k: {"D_full": distance(a, human, center)} for k, a in ais.items()}
    ref_ai = next(iter(ais.values()))  # 구조(문항 × 정당 인원)는 조건마다 같다(같은 집단 복제)
    groups = human["group"].unique()
    nums: Dict[str, List[float]] = {k: [] for k in ais}
    dens: List[float] = []
    for _ in range(nsplit * 3):  # 인원이 모자란 반분은 버리고 다시 뽑는다
        if len(dens) == nsplit:
            break
        side = dict(zip(groups, rng.random(len(groups)) < 0.5))
        mask = human["group"].map(side).to_numpy(bool)
        a_half, b_half = human[mask], human[~mask]
        pseudo = pseudo_ai(a_half, ref_ai, rng)
        if pseudo is None:
            continue
        dens.append(distance(pseudo, b_half, center))
        for k, a in ais.items():
            nums[k].append(distance(a, b_half, center))
    for k in ais:
        out[k]["FR"] = float(np.mean(nums[k]) / np.mean(dens)) if dens else float("nan")
    out["_splits"] = {"used": len(dens)}
    return out


def resample(ais: Dict[str, pd.DataFrame], human: pd.DataFrame, rng: np.random.Generator):
    """2단 군집 부트스트랩 1회: 문항 재표집 → 문항 안에서 AI 블록 재표집(조건 간 같은 블록), 인간 소집단 재표집.
    같은 문항·소집단이 여러 번 뽑히면 서로 다른 단위로 이름을 바꾼다"""
    first = next(iter(ais.values()))
    items = np.array(sorted(set(first["item"])))
    human = human[human["item"].isin(items)]
    drawn = rng.choice(items, len(items), replace=True)
    groups = human["group"].unique()
    g_drawn = rng.choice(groups, len(groups), replace=True)
    h_parts = []
    for gi, g in enumerate(g_drawn):
        h_parts.append(human[human["group"] == g].assign(group=f"{g}#{gi}"))
    h_all = pd.concat(h_parts)
    new_h, new_ai = [], {k: [] for k in ais}
    for ii, item in enumerate(drawn):
        tag = f"{item}#{ii}"
        new_h.append(h_all[h_all["item"] == item].assign(item=tag))
        blocks = ais[next(iter(ais))]
        blocks = blocks[blocks["item"] == item]["block"].unique()
        b_drawn = rng.choice(blocks, len(blocks), replace=True)
        for k, a in ais.items():
            a_item = a[a["item"] == item]
            for bi, b in enumerate(b_drawn):
                new_ai[k].append(a_item[a_item["block"] == b].assign(item=tag, block=f"{b}#{ii}#{bi}"))
    return {k: pd.concat(v) for k, v in new_ai.items()}, pd.concat(new_h)


def bootstrap(ais: Dict[str, pd.DataFrame], human: pd.DataFrame, n_boot: int, seed: int,
              nsplit: int = 4) -> pd.DataFrame:
    """부트스트랩 반복마다 조건별 D_full, FR (열: rep, condition, D_full, FR)"""
    rng = np.random.default_rng(seed)
    rows = []
    for rep in range(n_boot):
        a, h = resample(ais, human, rng)
        res = fidelity(a, h, rng, nsplit)
        for k in ais:
            rows.append({"rep": rep, "condition": k, **res[k]})
    return pd.DataFrame(rows)
