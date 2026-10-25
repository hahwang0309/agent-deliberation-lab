"""
연구 1 탐색 분석 (docs/research/study1-exploratory-plan.md 2절). 모든 결과는 [탐색]이며 등록 결과를 대체하지 않는다.

- N0  H1 보완: 초기 정답자 수 k별 정답 비율, 인간·AI 대비 (집단 부트스트랩)
- N2a 1-A 만장일치율, N2b 1-B 합의율·수렴 (조건 차이는 블록 안 짝 차이)
- N3  A1R 숙의군−통제군 문항별 지표 (분산 변화·정당 격차·이동자) + AI 블록 지표, 재표집 복제 저장
- N5  1-A 집단별 대응 (인간 과반 정답 × AI 과반 정답)
- N12 심은 입장의 유지 (1-B C 재응답, 1-A B 재풀이, 1-C C)
모든 함수는 한 모델의 설문 표를 받는다. 재표집 단위는 계획 문서 2-2 표를 따른다.
"""
import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.analysis.data import a1r_set
from src.analysis.humans import initial_correct_bin
from src.analysis.study1 import _post_pre

CONSENSUS_SD = 1.0      # 1-B 합의: 사후 모집단 SD ≤ 1.0 (주)
CONSENSUS_RANGE = 2     # 1-B 합의: 사후 범위 ≤ 2 (민감도)
MOVER = 2               # 이동자: |post − pre| ≥ 2 (0~10)
RETENTION_GAP = 3       # 등록 5-3: C에서 심은 점수와 3점 이상 차이
HUMAN_DRAWS = 200       # 인간 소집단 안 5명 추출 반복 (집단 크기 표준화)
A1R_MIX = {"1": 2, "2": 2, "3": 1}  # 민주 2 · 공화 2 · 무당층 1


def _ci(v: Iterable[float]) -> List[float]:
    a = np.asarray(list(v), dtype=float)
    a = a[~np.isnan(a)]
    if len(a) == 0:
        return [float("nan"), float("nan")]
    return [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]


def _resample(ids: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    return rng.choice(ids, len(ids), replace=True)


def _summ(point: float, draws: Iterable[float], n: Optional[int] = None, unit: str = "") -> Dict[str, Any]:
    out = {"estimate": float(point), "ci": _ci(draws)}
    if n is not None:
        out["n"] = int(n)
    if unit:
        out["resample"] = unit
    return out


# ---------------- 1-A: 실행·집단 표 ----------------

def _choice_set(x) -> Optional[tuple]:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    vals = json.loads(x) if isinstance(x, str) else x
    if vals is None:  # 설문 실패(무응답)는 JSON null로 저장됨
        return None
    return tuple(sorted(str(v).strip().upper() for v in vals))


def wason_runs(surveys: pd.DataFrame, plans: Dict[str, Dict[str, dict]]) -> pd.DataFrame:
    """1-A 원 과제 실행 1행: block, label, replicate, k, size, card_set, acc, unanimous, unanimous_correct, majority_correct.
    만장일치 = 답이 있는 참가자 2명 이상의 최종 카드 집합이 모두 같음. 과반 정답 = 정답자 > 참가자/2 (동률은 아님)"""
    s = surveys[(surveys["study"] == "wason") & surveys["topic_key"].str.startswith("deli-") & (surveys["phase"] == "post")]
    rows = []
    for (d, key, batch, label, rep), g in s.groupby(["discussion_id", "topic_key", "batch", "label", "replicate"]):
        topic = plans[batch][key]
        item = topic["survey"]["items"][0]
        corr = tuple(sorted(c.upper() for c in item["correct"]))
        k = sum(set(v["cards"]) == set(item["correct"]) for v in topic["seeds"].values())
        size = len(topic["personas"])
        sets = [cs for cs in (_choice_set(c) for c in g["choices"]) if cs is not None]
        correct = g["correct"].dropna().astype(float)
        rows.append({"discussion_id": d, "block": key, "label": label, "replicate": rep, "k": initial_correct_bin(k),
                     "k_raw": k, "size": size, "card_set": ",".join(sorted(item["options"])),
                     "n_answered": len(correct), "acc": float(correct.mean()) if len(correct) else np.nan,
                     "unanimous": float(len(sets) >= 2 and len(set(sets)) == 1) if len(sets) >= 2 else np.nan,
                     "unanimous_correct": float(len(sets) >= 2 and len(set(sets)) == 1 and sets[0] == corr)
                     if len(sets) >= 2 else np.nan,
                     "majority_correct": float(correct.sum() > len(correct) / 2) if len(correct) else np.nan})
    return pd.DataFrame(rows)


def human_groups(individuals: pd.DataFrame) -> pd.DataFrame:
    """DeliData 집단 1행 (humans.delidata_groups 출력에서): size, k, acc, unanimous, unanimous_correct, majority_correct"""
    rows = []
    for block, g in individuals.groupby("block"):
        finals = list(g["final"])
        uni = len(set(finals)) == 1
        rows.append({"block": block, "size": int(g["group_size"].iloc[0]), "k": g["k"].iloc[0],
                     "k_raw": int(g["k_raw"].iloc[0]), "card_set": g["card_set"].iloc[0], "n_answered": len(g),
                     "acc": float(g["correct"].mean()), "unanimous": float(uni),
                     "unanimous_correct": float(uni and bool(g["correct"].iloc[0])),
                     "majority_correct": float(g["correct"].sum() > len(g) / 2)})
    return pd.DataFrame(rows)


def _block_arms(runs: pd.DataFrame, human: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """블록 1행: 인간 값, AI 기준선(반복 평균), AI 상태 기반 값. 세 팔이 모두 있는 블록만"""
    base = runs[runs["label"] == "A-baseline"].groupby("block")[cols + ["n_answered"]].mean().add_prefix("base_")
    state = runs[runs["label"] == "A-stateful"].groupby("block")[cols + ["n_answered"]].mean().add_prefix("state_")
    hum = human.set_index("block")[cols + ["n_answered", "k", "size", "card_set"]].rename(
        columns={c: f"human_{c}" for c in cols + ["n_answered"]})
    return hum.join(base, how="inner").join(state, how="inner").reset_index()


def _rate_by_k(frame: pd.DataFrame, col: str, weight: Optional[str], idx: np.ndarray) -> Dict[str, float]:
    """idx로 고른 블록(복원 추출)에서 전체·k별 비율. weight가 있으면 참가자 수 가중(개인 합산), 없으면 블록 평균"""
    f = frame.iloc[idx]
    out = {}
    for name, sub in (("all", f), ("0", f[f["k"] == "0"]), ("1", f[f["k"] == "1"]), ("2+", f[f["k"] == "2+"])):
        v = sub[col].to_numpy(dtype=float)
        ok = ~np.isnan(v)
        if ok.sum() == 0:
            out[name] = np.nan
        elif weight:
            w = sub[weight].to_numpy(dtype=float)[ok]
            out[name] = float(np.sum(v[ok] * w) / np.sum(w))
        else:
            out[name] = float(np.mean(v[ok]))
    return out


def n0_truth_wins(runs: pd.DataFrame, human: pd.DataFrame, n_boot: int, seed: int) -> Dict[str, Any]:
    """N0: k별 개인 정답 비율(참가자 수 가중), 팔 = 인간 / AI 기준선(3회 평균) / AI 상태 기반.
    대비: (k1 − k0), 팔 간 차이. 재표집: 집단(인간·AI 자료가 함께 이동)"""
    fr = _block_arms(runs, human, ["acc"])
    arms = {"human": ("human_acc", "human_n_answered"), "ai_baseline": ("base_acc", "base_n_answered"),
            "ai_stateful": ("state_acc", "state_n_answered")}
    rng = np.random.default_rng(seed)
    ids = np.arange(len(fr))
    draws = {a: [] for a in arms}
    for _ in range(n_boot):
        idx = _resample(ids, rng)
        for a, (c, w) in arms.items():
            draws[a].append(_rate_by_k(fr, c, w, idx))
    point = {a: _rate_by_k(fr, c, w, ids) for a, (c, w) in arms.items()}
    out = {"n_blocks": int(len(fr)), "resample": "block (DeliData group) ×%d" % n_boot,
           "blocks_by_k": fr["k"].value_counts().to_dict(), "rates": {}, "contrasts": {}}
    for a in arms:
        out["rates"][a] = {k: _summ(point[a][k], [d[k] for d in draws[a]]) for k in ("all", "0", "1", "2+")}
        out["contrasts"][f"{a}: k1 - k0"] = _summ(point[a]["1"] - point[a]["0"],
                                                  [d["1"] - d["0"] for d in draws[a]])
    for a in ("ai_baseline", "ai_stateful"):
        out["contrasts"][f"({a} k1-k0) - (human k1-k0)"] = _summ(
            (point[a]["1"] - point[a]["0"]) - (point["human"]["1"] - point["human"]["0"]),
            [(x["1"] - x["0"]) - (h["1"] - h["0"]) for x, h in zip(draws[a], draws["human"])])
    return out


def n2a_unanimity(runs: pd.DataFrame, human: pd.DataFrame, n_boot: int, seed: int) -> Dict[str, Any]:
    """N2a: 1-A 만장일치율(정답·오답 분리), 팔별·k별, 팔 간 차이. 재표집: 집단"""
    cols = ["unanimous", "unanimous_correct", "majority_correct"]
    fr = _block_arms(runs, human, cols)
    fr["human_unanimous_wrong"] = fr["human_unanimous"] - fr["human_unanimous_correct"]
    fr["base_unanimous_wrong"] = fr["base_unanimous"] - fr["base_unanimous_correct"]
    fr["state_unanimous_wrong"] = fr["state_unanimous"] - fr["state_unanimous_correct"]
    metrics = ["unanimous", "unanimous_correct", "unanimous_wrong", "majority_correct"]
    arms = ["human", "base", "state"]
    rng = np.random.default_rng(seed)
    ids = np.arange(len(fr))
    draws = []
    for _ in range(n_boot):
        idx = _resample(ids, rng)
        draws.append({(a, m): _rate_by_k(fr, f"{a}_{m}", None, idx) for a in arms for m in metrics})
    point = {(a, m): _rate_by_k(fr, f"{a}_{m}", None, ids) for a in arms for m in metrics}
    out = {"n_blocks": int(len(fr)), "resample": "block (DeliData group) ×%d" % n_boot, "rates": {}, "differences": {}}
    for a in arms:
        out["rates"][a] = {m: {k: _summ(point[(a, m)][k], [d[(a, m)][k] for d in draws]) for k in ("all", "0", "1", "2+")}
                           for m in metrics}
    for m in metrics:
        for x, y in (("base", "human"), ("state", "human"), ("state", "base")):
            out["differences"][f"{m}: {x} - {y}"] = _summ(point[(x, m)]["all"] - point[(y, m)]["all"],
                                                        [d[(x, m)]["all"] - d[(y, m)]["all"] for d in draws])
    return out


def n5_group_correspondence(runs: pd.DataFrame, human: pd.DataFrame) -> Dict[str, Any]:
    """N5: 집단별 대응. 인간 과반 정답 × AI 과반 정답(기준선: 3회 중 과반 정답 횟수, 상태 기반: 1회) 교차표(k별),
    카드 세트·집단 수준 정답률 상관, 상태 기반에서만 실패한 집단의 특성. 기술 통계"""
    fr = _block_arms(runs, human, ["acc", "majority_correct"])
    base_reps = runs[runs["label"] == "A-baseline"].groupby("block")["majority_correct"].agg(["sum", "count"])
    fr = fr.join(base_reps.rename(columns={"sum": "base_maj_reps", "count": "base_reps"}), on="block")
    fr["base_class"] = np.select([fr["base_maj_reps"] == fr["base_reps"], fr["base_maj_reps"] == 0],
                                 ["all_reps", "none"], "some")
    out = {"n_blocks": int(len(fr)), "crosstab": {}, "stateful_only_failures": {}, "correlations": {}}
    for k, sub in [("all", fr)] + [(k, fr[fr["k"] == k]) for k in ("0", "1", "2+")]:
        ct = pd.crosstab(sub["human_majority_correct"].map({1.0: "human_maj_correct", 0.0: "human_maj_wrong"}),
                         sub["base_class"].map({"all_reps": "ai_base_all_reps", "some": "ai_base_some", "none": "ai_base_none"}))
        ct2 = pd.crosstab(sub["human_majority_correct"].map({1.0: "human_maj_correct", 0.0: "human_maj_wrong"}),
                          sub["state_majority_correct"].map({1.0: "ai_state_correct", 0.0: "ai_state_wrong"}))
        out["crosstab"][k] = {"baseline": ct.to_dict(), "stateful": ct2.to_dict(), "n": int(len(sub))}
    fail = fr[(fr["base_class"] == "all_reps") & (fr["state_majority_correct"] == 0)]
    rest = fr[~((fr["base_class"] == "all_reps") & (fr["state_majority_correct"] == 0))]
    out["stateful_only_failures"] = {
        "n": int(len(fail)), "by_k": fail["k"].value_counts().to_dict(), "by_size": fail["size"].value_counts().to_dict(),
        "mean_k_raw": float(human.set_index("block").loc[fail["block"], "k_raw"].mean()) if len(fail) else None,
        "mean_k_raw_others": float(human.set_index("block").loc[rest["block"], "k_raw"].mean()),
        "human_acc_in_these": float(fail["human_acc"].mean()) if len(fail) else None,
        "human_acc_others": float(rest["human_acc"].mean())}
    cs = fr.groupby("card_set")[["human_acc", "base_acc", "state_acc"]].mean()
    cs_n = fr.groupby("card_set").size()
    out["correlations"] = {
        "group_level_spearman": {"human_vs_base": float(fr["human_acc"].corr(fr["base_acc"], method="spearman")),
                                 "human_vs_state": float(fr["human_acc"].corr(fr["state_acc"], method="spearman")),
                                 "base_vs_state": float(fr["base_acc"].corr(fr["state_acc"], method="spearman")), "n": int(len(fr))},
        "card_set_level_spearman": {"human_vs_base": float(cs["human_acc"].corr(cs["base_acc"], method="spearman")),
                                    "human_vs_state": float(cs["human_acc"].corr(cs["state_acc"], method="spearman")),
                                    "n_card_sets": int(len(cs)), "card_sets_with_1_group": int((cs_n == 1).sum())}}
    return out


# ---------------- 1-B: 블록 지표 ----------------

def _party_map(surveys: pd.DataFrame, plans: Dict[str, Dict[str, dict]], parties: Dict[int, str]) -> pd.DataFrame:
    s = surveys[(surveys["study"] == "a1r")].drop_duplicates(["discussion_id", "participant"])
    out = {}
    for d, k, b, p in zip(s["discussion_id"], s["topic_key"], s["batch"], s["participant"]):
        row = plans[b][k]["meta"]["respondent_rows"].get(p)
        out[(d, p)] = (parties.get(row), row)
    return out


def _metrics(pre: np.ndarray, post: np.ndarray, party: Optional[np.ndarray] = None) -> Dict[str, float]:
    """한 집단(또는 팔) × 문항의 지표. SD는 모집단 SD(E3과 같음)"""
    d = post - pre
    m = {"n": len(pre), "sd_pre": float(np.std(pre)), "sd_post": float(np.std(post)),
         "sd_drop": float(np.std(pre) - np.std(post)), "range_post": float(np.ptp(post)),
         "mean_shift": float(np.mean(d)), "mean_abs_move": float(np.mean(np.abs(d))),
         "movers": float(np.mean(np.abs(d) >= MOVER))}
    m["consensus_sd"] = float(m["sd_post"] <= CONSENSUS_SD)
    m["consensus_range"] = float(m["range_post"] <= CONSENSUS_RANGE)
    mv = d[np.abs(d) >= MOVER]
    m["direction_agree"] = float(max(np.mean(mv > 0), np.mean(mv < 0))) if len(mv) else np.nan
    if party is not None:
        dem, rep = pre[party == "1"], pre[party == "2"]
        dem2, rep2 = post[party == "1"], post[party == "2"]
        if len(dem) and len(rep):
            m["gap_pre"] = float(abs(dem.mean() - rep.mean()))
            m["gap_post"] = float(abs(dem2.mean() - rep2.mean()))
            m["gap_change"] = m["gap_pre"] - m["gap_post"]
    return m


A1R_LABELS = ["A-baseline", "A-stateful", "B-materials", "C-reanswer"]


def a1r_block_metrics(surveys: pd.DataFrame, plans: Dict[str, Dict[str, dict]], parties: Dict[int, str]) -> pd.DataFrame:
    """1-B 반복 집단(groups 세트) 블록 × 조건 1행: 2-3절 지표 + D 조건 평균(모델 기본 입장)"""
    s = surveys[(surveys["study"] == "a1r") & surveys["topic_key"].map(a1r_set).eq("groups")
                & surveys["label"].isin(A1R_LABELS + ["D-prior"])]
    pp = _post_pre(s)
    pm = _party_map(s, plans, parties)
    pp["party"] = [pm[(d, p)][0] for d, p in zip(pp["discussion_id"], pp["participant"])]
    pp["persona"] = [pm[(d, p)][1] for d, p in zip(pp["discussion_id"], pp["participant"])]
    d_mean = pp[pp["label"] == "D-prior"].dropna(subset=["post"]).groupby("topic_key")["post"].mean().rename("D_mean")
    rows = []
    for (topic, label), g in pp[pp["label"].isin(A1R_LABELS)].dropna(subset=["pre", "post"]).groupby(["topic_key", "label"]):
        if len(g) < 3:
            continue
        m = _metrics(g["pre"].to_numpy(float), g["post"].to_numpy(float), g["party"].to_numpy())
        m.update(block=topic, item=g["item_id"].iloc[0], label=label, mean_pre=float(g["pre"].mean()),
                 mean_post=float(g["post"].mean()))
        rows.append(m)
    out = pd.DataFrame(rows).join(d_mean, on="block")
    return out


def a1r_agent_rows(surveys: pd.DataFrame, plans: Dict[str, Dict[str, dict]], parties: Dict[int, str]) -> pd.DataFrame:
    """1-B 에이전트 × 조건 1행 (pre, post, party, persona, D = 같은 페르소나의 D 조건 사후)"""
    s = surveys[(surveys["study"] == "a1r") & surveys["topic_key"].map(a1r_set).eq("groups")]
    pp = _post_pre(s)
    pm = _party_map(s, plans, parties)
    pp["party"] = [pm[(d, p)][0] for d, p in zip(pp["discussion_id"], pp["participant"])]
    pp["persona"] = [pm[(d, p)][1] for d, p in zip(pp["discussion_id"], pp["participant"])]
    d = pp[pp["label"] == "D-prior"].dropna(subset=["post"]).groupby(["topic_key", "participant"])["post"].mean().rename("D")
    return pp.join(d, on=["topic_key", "participant"])


def human_a1r_units(delib: pd.DataFrame, n_draw: int = HUMAN_DRAWS, seed: int = 0) -> pd.DataFrame:
    """인간 숙의군 소집단 × 문항 1행: 전원 지표(full_*)와 5명 층화 추출(민주 2·공화 2·무당층 1, 부족하면 무작위 5) n_draw회 평균(draw_*).
    추출 반복은 집단 크기 표준화이지 표본 증가가 아니다"""
    rng = np.random.default_rng(seed)
    rows = []
    for (grp, item), g in delib.groupby(["group", "item"]):
        pre, post, party = g["pre"].to_numpy(float), g["post"].to_numpy(float), g["party"].astype(str).to_numpy()
        if len(g) < 5:
            continue
        row = {"group": grp, "item": item, "n_members": len(g)}
        row.update({f"full_{k}": v for k, v in _metrics(pre, post, party).items()})
        acc = []
        stratified = all((party == p).sum() >= n for p, n in A1R_MIX.items())
        for _ in range(n_draw):
            if stratified:
                idx = np.concatenate([rng.choice(np.flatnonzero(party == p), n, replace=False) for p, n in A1R_MIX.items()])
            else:
                idx = rng.choice(len(g), 5, replace=False)
            acc.append(_metrics(pre[idx], post[idx], party[idx]))
        for k in acc[0]:
            vals = np.array([a.get(k, np.nan) for a in acc], dtype=float)
            row[f"draw_{k}"] = float(np.nanmean(vals)) if np.any(~np.isnan(vals)) else np.nan
        row["draw_stratified"] = stratified
        rows.append(row)
    return pd.DataFrame(rows)


def n2b_consensus(blocks: pd.DataFrame, human_units: pd.DataFrame, n_boot: int, seed: int) -> Dict[str, Any]:
    """N2b: 1-B 합의율(사후 SD ≤ 1 / 범위 ≤ 2)과 SD 감소량, 조건별 평균과 블록 안 짝 차이(A−B, B−C, 상태−기준선).
    재표집: AI 문항 → 문항 안 블록, 인간 소집단"""
    metrics = ["consensus_sd", "consensus_range", "sd_drop", "mean_abs_move", "movers", "gap_change"]
    wide = blocks.pivot_table(index=["item", "block"], columns="label", values=metrics)
    items = wide.index.get_level_values("item").to_numpy()
    rng = np.random.default_rng(seed)

    def ai_means(idx):
        w = wide.iloc[idx]
        res = {}
        for m in metrics:
            for lab in A1R_LABELS:
                res[(m, lab)] = float(w[(m, lab)].mean())
            res[(m, "A-stateful - A-baseline")] = float((w[(m, "A-stateful")] - w[(m, "A-baseline")]).mean())
            res[(m, "A-baseline - B-materials")] = float((w[(m, "A-baseline")] - w[(m, "B-materials")]).mean())
            res[(m, "B-materials - C-reanswer")] = float((w[(m, "B-materials")] - w[(m, "C-reanswer")]).mean())
        return res

    def ai_idx():
        parts = []
        for it in np.unique(items):
            pos = np.flatnonzero(items == it)
            parts.append(rng.choice(pos, len(pos), replace=True))
        return np.concatenate(parts)

    groups = human_units["group"].to_numpy()
    ug = np.unique(groups)

    def human_means(sel_groups):
        pos = np.concatenate([np.flatnonzero(groups == g) for g in sel_groups])
        h = human_units.iloc[pos]
        return {m: float(h[f"draw_{m}"].mean()) for m in metrics} | {f"full_{m}": float(h[f"full_{m}"].mean()) for m in metrics}

    point_ai, point_h = ai_means(np.arange(len(wide))), human_means(ug)
    d_ai, d_h = [], []
    for _ in range(n_boot):
        d_ai.append(ai_means(ai_idx()))
        d_h.append(human_means(_resample(ug, rng)))
    out = {"n_blocks": int(len(wide)), "n_items": int(len(np.unique(items))), "n_human_units": int(len(human_units)),
           "human_groups": int(len(ug)), "resample": {"ai": "item > block ×%d" % n_boot, "human": "small group ×%d" % n_boot},
           "definitions": {"consensus_sd": f"post SD (population) <= {CONSENSUS_SD}", "consensus_range": f"post range <= {CONSENSUS_RANGE}",
                           "human": f"5-member stratified draws ×{HUMAN_DRAWS} per small group × item (size standardization)"},
           "ai": {}, "human": {}, "ai_minus_human": {}}
    for m in metrics:
        out["ai"][m] = {k[1]: _summ(point_ai[k], [d[k] for d in d_ai]) for k in point_ai if k[0] == m}
        out["human"][m] = {"draw5": _summ(point_h[m], [d[m] for d in d_h]),
                           "full_group": _summ(point_h[f"full_{m}"], [d[f"full_{m}"] for d in d_h])}
        for lab in A1R_LABELS:
            out["ai_minus_human"][f"{m}: {lab} - human(draw5)"] = _summ(
                point_ai[(m, lab)] - point_h[m], [a[(m, lab)] - h[m] for a, h in zip(d_ai, d_h)])
    return out


# ---------------- N3: 숙의군−통제군 (문항별) ----------------

N3_INDICATORS = ["sd_drop", "gap_change", "movers", "direction_agree", "mean_shift", "mean_abs_move", "sd_pre", "gap_pre"]


def _item_metrics_matrix(pre: np.ndarray, post: np.ndarray, party: np.ndarray) -> Dict[str, np.ndarray]:
    """참가자 × 문항 행렬(결측 NaN)에서 문항별 지표를 한 번에 계산 (_metrics와 같은 정의, 벡터화)"""
    with np.errstate(invalid="ignore", divide="ignore"):
        d = post - pre
        sd_pre, sd_post = np.nanstd(pre, axis=0), np.nanstd(post, axis=0)
        mv = np.abs(d) >= MOVER
        pos, neg = np.nansum(d >= MOVER, axis=0), np.nansum(d <= -MOVER, axis=0)
        tot = pos + neg
        agree = np.where(tot > 0, np.maximum(pos, neg) / np.where(tot > 0, tot, 1), np.nan)
        dem, rep = party == "1", party == "2"
        gap_pre = np.abs(np.nanmean(pre[dem], axis=0) - np.nanmean(pre[rep], axis=0))
        gap_post = np.abs(np.nanmean(post[dem], axis=0) - np.nanmean(post[rep], axis=0))
        return {"sd_pre": sd_pre, "sd_drop": sd_pre - sd_post, "gap_pre": gap_pre, "gap_change": gap_pre - gap_post,
                "movers": np.nanmean(np.where(np.isnan(d), np.nan, mv.astype(float)), axis=0), "direction_agree": agree,
                "mean_shift": np.nanmean(d, axis=0), "mean_abs_move": np.nanmean(np.abs(d), axis=0)}


def _matrices(frame: pd.DataFrame, items: List[str]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """참가자 × 문항 행렬: (pre, post, party, 참가자 row id, 참가자 group)"""
    pre = frame.pivot_table(index="row", columns="item", values="pre", aggfunc="first").reindex(columns=items)
    post = frame.pivot_table(index="row", columns="item", values="post", aggfunc="first").reindex(columns=items)
    post = post.reindex(index=pre.index)
    meta = frame.drop_duplicates("row").set_index("row").reindex(pre.index)
    return (pre.to_numpy(float), post.to_numpy(float), meta["party"].astype(str).to_numpy(), pre.index.to_numpy(),
            meta["group"].astype(str).to_numpy())


def n3_human_did(delib: pd.DataFrame, control: pd.DataFrame, n_boot: int, seed: int
                 ) -> Tuple[pd.DataFrame, Dict[str, np.ndarray], Dict[str, Any]]:
    """N3 인간: 문항별 팔(숙의군·통제군) 지표와 차이(숙의군 − 통제군). 숙의군은 소집단, 통제군은 참가자를 한 번에 재추출해
    30문항 추정치를 함께 계산한다 (같은 참가자의 문항 응답이 함께 이동 → 문항 간 공분산 보존, N4의 Σ).
    반환: (문항 표, 복제 배열 {지표: [n_boot × 문항]}, 요약)"""
    items = sorted(set(delib["item"]) & set(control["item"]))
    rng = np.random.default_rng(seed)
    d_pre, d_post, d_party, _, d_group = _matrices(delib, items)
    c_pre, c_post, c_party, _, _ = _matrices(control, items)
    ug = np.unique(d_group)
    g_pos = {g: np.flatnonzero(d_group == g) for g in ug}
    c_ids = np.arange(len(c_pre))

    def small_group_sd_drop(idx_groups: Iterable[np.ndarray]) -> np.ndarray:
        """소집단 안 SD 감소량의 문항별 평균 (집단당 유효 응답 3명 이상인 문항만)"""
        vals = []
        for pos in idx_groups:
            p, q = d_pre[pos], d_post[pos]
            ok = (~np.isnan(p) & ~np.isnan(q)).sum(axis=0) >= 3
            with np.errstate(invalid="ignore"):
                v = np.nanstd(np.where(np.isnan(q), np.nan, p), axis=0) - np.nanstd(np.where(np.isnan(p), np.nan, q), axis=0)
            vals.append(np.where(ok, v, np.nan))
        return np.nanmean(np.vstack(vals), axis=0)

    def one(d_idx, c_idx):
        return (_item_metrics_matrix(d_pre[d_idx], d_post[d_idx], d_party[d_idx]),
                _item_metrics_matrix(c_pre[c_idx], c_post[c_idx], c_party[c_idx]))

    all_d = np.arange(len(d_pre))
    pa, pc = one(all_d, c_ids)
    sg = small_group_sd_drop(g_pos.values())
    reps = {f"{arm}_{ind}": np.full((n_boot, len(items)), np.nan) for arm in ("delib", "control", "did") for ind in N3_INDICATORS}
    reps["delib_group_sd_drop"] = np.full((n_boot, len(items)), np.nan)
    for b in range(n_boot):
        groups = [g_pos[g] for g in _resample(ug, rng)]
        a, c = one(np.concatenate(groups), _resample(c_ids, rng))
        for ind in N3_INDICATORS:
            reps[f"delib_{ind}"][b], reps[f"control_{ind}"][b] = a[ind], c[ind]
            reps[f"did_{ind}"][b] = a[ind] - c[ind]
        reps["delib_group_sd_drop"][b] = small_group_sd_drop(groups)
    rows = []
    for j, it in enumerate(items):
        r = {"item": it, "n_delib": int((~np.isnan(d_pre[:, j]) & ~np.isnan(d_post[:, j])).sum()),
             "n_control": int((~np.isnan(c_pre[:, j]) & ~np.isnan(c_post[:, j])).sum()),
             "delib_group_sd_drop": float(sg[j])}
        r["delib_group_sd_drop_lo"], r["delib_group_sd_drop_hi"] = _ci(reps["delib_group_sd_drop"][:, j])
        for ind in N3_INDICATORS:
            r[f"delib_{ind}"], r[f"control_{ind}"] = float(pa[ind][j]), float(pc[ind][j])
            r[f"did_{ind}"] = r[f"delib_{ind}"] - r[f"control_{ind}"]
            for arm in ("delib", "control", "did"):
                r[f"{arm}_{ind}_lo"], r[f"{arm}_{ind}_hi"] = _ci(reps[f"{arm}_{ind}"][:, j])
        rows.append(r)
    table = pd.DataFrame(rows)
    summary = {"items": items, "n_delib_participants": int(len(d_pre)), "n_delib_groups": int(len(ug)),
               "n_control_participants": int(len(c_pre)),
               "resample": {"delib": "small group ×%d" % n_boot, "control": "participant ×%d (no groups)" % n_boot,
                            "note": "joint resampling across items; replicate arrays saved for N4 covariance"},
               "mean_over_items": {}}
    for ind in N3_INDICATORS:
        for arm in ("delib", "control", "did"):
            col = table[f"{arm}_{ind}"]
            summary["mean_over_items"][f"{arm}_{ind}"] = _summ(float(col.mean()), np.nanmean(reps[f"{arm}_{ind}"], axis=1))
    summary["mean_over_items"]["delib_group_sd_drop"] = _summ(float(table["delib_group_sd_drop"].mean()),
                                                              np.nanmean(reps["delib_group_sd_drop"], axis=1))
    return table, reps, summary


def n3_ai_items(blocks: pd.DataFrame, n_boot: int, seed: int) -> Tuple[pd.DataFrame, Dict[str, np.ndarray]]:
    """N3 AI: 문항별 조건 지표(블록 평균)와 A−C 조건 차이, 문항 안 블록 재추출을 한 번에 (복제 배열 저장).
    한계: 같은 페르소나가 여러 문항 블록에 등장하는 의존은 이 재표집이 보존하지 못한다"""
    inds = ["sd_drop", "gap_change", "movers", "direction_agree", "mean_shift", "mean_abs_move"]
    wide = blocks.pivot_table(index=["item", "block"], columns="label", values=inds)
    items = sorted(wide.index.get_level_values("item").unique())
    iv = wide.index.get_level_values("item").to_numpy()
    pos = {it: np.flatnonzero(iv == it) for it in items}
    rng = np.random.default_rng(seed)
    keys = [(ind, lab) for ind in inds for lab in A1R_LABELS] + [(ind, f"{a} - {b}") for ind in inds
                                                                 for a, b in (("A-baseline", "C-reanswer"), ("A-stateful", "C-reanswer"),
                                                                              ("A-stateful", "A-baseline"), ("A-baseline", "B-materials"),
                                                                              ("B-materials", "C-reanswer"))]

    def values(w):
        out = {}
        for ind, lab in keys:
            if " - " in lab:
                a, b = lab.split(" - ")
                out[(ind, lab)] = float(np.nanmean(w[(ind, a)] - w[(ind, b)]))
            else:
                out[(ind, lab)] = float(np.nanmean(w[(ind, lab)]))
        return out

    point = {it: values(wide.iloc[pos[it]]) for it in items}
    reps = {f"{ind}|{lab}": np.full((n_boot, len(items)), np.nan) for ind, lab in keys}
    for b in range(n_boot):
        for j, it in enumerate(items):
            v = values(wide.iloc[rng.choice(pos[it], len(pos[it]), replace=True)])
            for ind, lab in keys:
                reps[f"{ind}|{lab}"][b, j] = v[(ind, lab)]
    rows = []
    for j, it in enumerate(items):
        r = {"item": it, "n_blocks": int(len(pos[it]))}
        for ind, lab in keys:
            r[f"{ind}|{lab}"] = point[it][(ind, lab)]
            r[f"{ind}|{lab}_lo"], r[f"{ind}|{lab}_hi"] = _ci(reps[f"{ind}|{lab}"][:, j])
        rows.append(r)
    return pd.DataFrame(rows), reps


# ---------------- N12: 심은 입장의 유지 ----------------

def n12_retention(agents: pd.DataFrame, wason_surveys: pd.DataFrame, plans: Dict[str, Dict[str, dict]],
                  argq_surveys: pd.DataFrame, n_boot: int, seed: int) -> Dict[str, Any]:
    """N12: 1-B C 재응답(|post−pre| ≥ 3 비율, D 쪽 회귀 기울기), B 조건 같은 값, 1-A B 재풀이가 심은 답과 같은 비율,
    1-C C 재응답 |Δ| 분포. 재표집: 1-B 블록, 1-A 집단, 1-C 세트"""
    rng = np.random.default_rng(seed)
    out = {}
    # 1-B
    for lab in ("C-reanswer", "B-materials", "A-baseline", "A-stateful"):
        a = agents[(agents["label"] == lab)].dropna(subset=["pre", "post"]).copy()
        a["d"] = a["post"] - a["pre"]
        a["toward_D"] = a["D"] - a["pre"]
        blocks = a["block"].to_numpy()
        ub = np.unique(blocks)
        bpos = {b: np.flatnonzero(blocks == b) for b in ub}

        def stats(f):
            ok = f["toward_D"].notna() & (f["toward_D"].abs() > 0)
            slope = float(np.polyfit(f.loc[ok, "toward_D"], f.loc[ok, "d"], 1)[0]) if ok.sum() > 10 else np.nan
            return {"gap3": float((f["d"].abs() >= RETENTION_GAP).mean()), "gap1": float((f["d"].abs() >= 1).mean()),
                    "mean_abs": float(f["d"].abs().mean()), "mean_shift": float(f["d"].mean()), "slope_toward_D": slope,
                    "corr_toward_D": float(f.loc[ok, "d"].corr(f.loc[ok, "toward_D"])) if ok.sum() > 10 else np.nan}
        p = stats(a)
        draws = [stats(a.iloc[np.concatenate([bpos[b] for b in _resample(ub, rng)])]) for b_ in range(n_boot)]
        out[f"1-B {lab}"] = {k: _summ(p[k], [d[k] for d in draws]) for k in p} | {"n_agents": int(len(a)), "n_blocks": int(len(ub)),
                                                                              "resample": "block"}
    # 1-A B-resolve: 심은 답 유지
    s = wason_surveys[(wason_surveys["study"] == "wason") & wason_surveys["topic_key"].str.startswith("deli-")
                      & (wason_surveys["phase"] == "post") & (wason_surveys["label"] == "B-resolve")]
    rows = []
    for (key, batch), g in s.groupby(["topic_key", "batch"]):
        topic = plans[batch][key]
        corr = set(c.upper() for c in topic["survey"]["items"][0]["correct"])
        for p, c in zip(g["participant"], g["choices"]):
            cs = _choice_set(c)
            seed_set = set(x.upper() for x in topic["seeds"][p]["cards"])
            if cs is None:
                continue
            rows.append({"block": key, "same_as_seed": float(set(cs) == seed_set), "seed_correct": float(seed_set == corr),
                         "now_correct": float(set(cs) == corr)})
    r = pd.DataFrame(rows)
    ub = r["block"].unique()
    bpos = {b: np.flatnonzero(r["block"].to_numpy() == b) for b in ub}

    def wst(f):
        wrong = f[f["seed_correct"] == 0]
        return {"same_as_seed": float(f["same_as_seed"].mean()),
                "seeded_wrong_stay_wrong": float((wrong["now_correct"] == 0).mean()) if len(wrong) else np.nan,
                "seeded_wrong_same_answer": float(wrong["same_as_seed"].mean()) if len(wrong) else np.nan}
    p = wst(r)
    draws = [wst(r.iloc[np.concatenate([bpos[b] for b in _resample(ub, rng)])]) for _ in range(n_boot)]
    out["1-A B-resolve"] = {k: _summ(p[k], [d[k] for d in draws]) for k in p} | {"n_agents": int(len(r)), "n_blocks": int(len(ub)),
                                                                             "resample": "group"}
    # 1-C C-reanswer
    c = argq_surveys[(argq_surveys["study"] == "argq") & (argq_surveys["label"] == "C-reanswer")]
    pp = _post_pre(c).dropna(subset=["pre", "post"])
    pro = pp["topic_key"].str.endswith("-pro")
    pp["delta"] = np.where(pro, pp["pre"] - pp["post"], pp["post"] - pp["pre"])
    sets = pp["topic_key"].to_numpy()
    us = np.unique(sets)
    spos = {x: np.flatnonzero(sets == x) for x in us}

    def cst(f):
        return {"abs_ge_10": float((f["delta"].abs() >= 10).mean()), "abs_ge_30": float((f["delta"].abs() >= 30).mean()),
                "mean_abs": float(f["delta"].abs().mean()), "mean_delta_toward_opposite": float(f["delta"].mean())}
    p = cst(pp)
    draws = [cst(pp.iloc[np.concatenate([spos[x] for x in _resample(us, rng)])]) for _ in range(n_boot)]
    out["1-C C-reanswer"] = {k: _summ(p[k], [d[k] for d in draws]) for k in p} | {"n_targets": int(len(pp)), "n_sets": int(len(us)),
                                                                              "resample": "set"}
    return out
