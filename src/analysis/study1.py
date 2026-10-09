"""
연구 1 가설 검정 (docs/research/study1-analysis-plan.md 0-3, 3~5절)

가족과 보정:
- 질문 1 (엔진 효과): E1~E5, Holm
- 질문 2 (인간과의 거리): H5 단독, α = 0.05
- 기준점: H1, H2, H2b, H2c, H3a~c, Holm
모든 함수는 한 모델의 자료를 받는다(주 검정은 주 모델, 비교 모델은 같은 함수로 재현).
"""
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.analysis import fidelity, mixed
from src.analysis.data import a1r_set
from src.analysis.humans import initial_correct_bin

ALPHA = 0.05


# ---------------- 공통 ----------------

def holm(pvalues: Dict[str, Optional[float]], alpha: float = ALPHA) -> Dict[str, Dict[str, Any]]:
    """Holm 단계 하향 보정: {가설: {p, p_holm, reject}}. p가 없는 가설은 보정에서 뺀다"""
    valid = sorted(((p, k) for k, p in pvalues.items() if p is not None and not np.isnan(p)))
    m, running, out = len(valid), 0.0, {}
    for i, (p, k) in enumerate(valid):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = {"p": p, "p_holm": running}
    for k in out:
        out[k]["reject"] = out[k]["p_holm"] < alpha
    for k, p in pvalues.items():
        out.setdefault(k, {"p": p, "p_holm": None, "reject": None})
    return out


BOOT = {"n_boot": 2000, "seed": 2026}  # 부트스트랩 반복·시드 (스크립트가 바꾼다)


def _term(res: Dict[str, Any], term: str) -> Dict[str, Any]:
    c = res["coefficients"][term]
    return {"estimate": c["estimate"], "ci": [c["ci_low"], c["ci_high"]], "p": c["p"], "se": c["se"], "df": c["df"],
            "n": res["n"], "groups": res["groups"], "singular": res["singular"], "messages": res["messages"],
            "formula": res["formula"], "method": "lme4 glmer (Wald z)" if res["family"] == "binomial"
            else "lmerTest lmer (REML, Satterthwaite)"}


def _fit(data: pd.DataFrame, formula: str, terms: List[str], clusters: List[str],
         family: str = "gaussian") -> Dict[str, Dict[str, Any]]:
    """혼합 모형을 적합하고, 수렴하지 않으면 분석 계획 2절대로 다수준 군집 부트스트랩으로 대체한다"""
    res = mixed.fit(data, formula, family)
    if mixed.converged(res) and all(t in res["coefficients"] for t in terms):
        return {t: _term(res, t) for t in terms}
    fallback = mixed.cluster_bootstrap(data, formula, terms, family, clusters, BOOT["n_boot"], BOOT["seed"])
    for t in terms:
        fallback[t]["mixed_model_messages"] = res["messages"]
        fallback[t]["formula"] = formula
    return fallback


def _need(frame: pd.DataFrame, labels: List[str], what: str) -> None:
    """검정에 필요한 조건이 자료에 있는지 확인 (없으면 그 가설만 실패로 기록)"""
    missing = [lab for lab in labels if lab not in set(frame["label"])]
    if frame.empty or missing:
        raise ValueError(f"{what}: no data for conditions {missing or labels}")


def _post_pre(surveys: pd.DataFrame) -> pd.DataFrame:
    """참가자 × 실행 1행: pre, post (둘 다 있는 경우만, 6절: 무응답은 그 문항 분석에서 제외)"""
    s = surveys[surveys["score"].notna()]
    wide = s.pivot_table(index=["discussion_id", "participant", "item_id"], columns="phase", values="score",
                         aggfunc="first").reset_index()
    meta = surveys.drop_duplicates("discussion_id").set_index("discussion_id")
    wide = wide.join(meta[["topic_key", "label", "mode", "replicate", "block"]], on="discussion_id")
    return wide


# ---------------- 질문 1: E1~E5 ----------------

def e1(surveys: pd.DataFrame) -> Dict[str, Any]:
    """E1 정답 추적 (1-A 원 과제): 실행 단위 정답 비율 ~ 엔진 + (1 | 복제 집단). 기준선은 1회째(replicate 0)와 짝"""
    s = surveys[(surveys["study"] == "wason") & surveys["topic_key"].str.startswith("deli-")
                & (surveys["phase"] == "post") & surveys["label"].isin(["A-baseline", "A-stateful"])
                & (surveys["replicate"] == 0) & surveys["correct"].notna()]
    runs = (s.assign(correct=s["correct"].astype(float))
            .groupby(["discussion_id", "topic_key", "label"])["correct"].mean().reset_index(name="acc"))
    runs["engine"] = (runs["label"] == "A-stateful").astype(int)
    paired = runs.groupby("topic_key")["engine"].transform("nunique") == 2
    return _fit(runs[paired], "acc ~ engine + (1 | topic_key)", ["engine"], ["topic_key"])["engine"]


def _a1r_block_metrics(surveys: pd.DataFrame) -> pd.DataFrame:
    """1-B 반복 집단(개발·잠금 세트)의 블록 × 조건별 순수 이동량(평균 |post − pre|)과 표준편차 감소량"""
    s = surveys[(surveys["study"] == "a1r") & surveys["topic_key"].map(a1r_set).eq("groups")
                & surveys["label"].isin(["A-baseline", "A-stateful"])]
    pp = _post_pre(s).dropna(subset=["pre", "post"])
    rows = []
    for (block, label), g in pp.groupby(["block", "label"]):
        if len(g) < 3:
            continue
        rows.append({"block": block, "item": g["item_id"].iloc[0], "label": label,
                     "move": float(np.mean(np.abs(g["post"] - g["pre"]))),
                     "sd_drop": float(np.std(g["pre"]) - np.std(g["post"]))})
    m = pd.DataFrame(rows)
    wide = m.pivot_table(index=["block", "item"], columns="label", values=["move", "sd_drop"]).dropna().reset_index()
    return pd.DataFrame({"block": wide["block"], "item": wide["item"],
                         "E2": wide[("move", "A-stateful")] - wide[("move", "A-baseline")],
                         "E3": wide[("sd_drop", "A-stateful")] - wide[("sd_drop", "A-baseline")]})


def e2_e3(surveys: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """E2 순수 이동량, E3 집단 내 표준편차 감소량: 블록별 상태 기반 − 기준선 차이 d ~ 1 + (1 | 문항).
    E2의 'A − C'에서 C는 두 모드에 공통이라 차이에서 상쇄된다"""
    d = _a1r_block_metrics(surveys)
    return {h: _fit(d[["item", "block", h]].rename(columns={h: "d"}), "d ~ 1 + (1 | item)", ["(Intercept)"],
                    ["item", "block"])["(Intercept)"] for h in ("E2", "E3")}


def _argq_deltas(surveys: pd.DataFrame) -> pd.DataFrame:
    """1-C 표적(설문 대상은 표적 1명)의 입장 변화 Δ (반대 입장 방향 +, 0~100), 효과 코딩 ±0.5"""
    s = surveys[(surveys["study"] == "argq") & surveys["label"].str.count("-").eq(2)]
    pp = _post_pre(s).dropna(subset=["pre", "post"])
    parts = pp["label"].str.split("-", expand=True)
    pro = pp["topic_key"].str.endswith("-pro")
    return pd.DataFrame({
        "set": pp["topic_key"], "replicate": pp["replicate"],
        "delta": np.where(pro, pp["pre"] - pp["post"], pp["post"] - pp["pre"]),
        "q": np.where(parts[0] == "strong", 0.5, -0.5), "sup": np.where(parts[1] == "majority", 0.5, -0.5),
        "eng": np.where(parts[2] == "stateful", 0.5, -0.5), "side": np.where(pro, 0.5, -0.5)})


def e4_e5(surveys: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """E4 질 × 엔진, E5 지지 × 엔진: Δ ~ q × sup × eng + side + (1 + q | set)"""
    r = _fit(_argq_deltas(surveys), "delta ~ q * sup * eng + side + (1 + q | set)", ["q:eng", "sup:eng"], ["set"])
    return {"E4": r["q:eng"], "E5": r["sup:eng"]}


# ---------------- 질문 2: H5, 기준점 H2 (충실도) ----------------

def a1r_ai_rows(surveys: pd.DataFrame, plans: Dict[str, Dict[str, dict]], parties: Dict[int, str],
                items: List[str], labels: List[str]) -> Dict[str, pd.DataFrame]:
    """조건별 AI 표: item, party(페르소나의 A1R 응답자 정당), pre(심은 값), post, block"""
    s = surveys[(surveys["study"] == "a1r") & surveys["topic_key"].map(a1r_set).eq("groups")
                & surveys["label"].isin(labels)]
    pp = _post_pre(s).dropna(subset=["pre", "post"])
    pp = pp[pp["item_id"].isin(items)]
    _need(pp, labels, "1-B items " + ",".join(items[:3]) + "...")
    batch = s.drop_duplicates("discussion_id").set_index("discussion_id")["batch"]
    pp["party"] = [parties[plans[batch[d]][k]["meta"]["respondent_rows"][p]]
                   for d, k, p in zip(pp["discussion_id"], pp["topic_key"], pp["participant"])]
    pp = pp.rename(columns={"item_id": "item"})
    # 조건 간 같은 블록·같은 참가자만 (짝지은 비교)
    common = set.intersection(*[set(zip(g["block"], g["participant"])) for _, g in pp.groupby("label")])
    pp = pp[[x in common for x in zip(pp["block"], pp["participant"])]]
    return {lab: pp[pp["label"] == lab][["item", "party", "pre", "post", "block"]].reset_index(drop=True)
            for lab in labels}


def _ci(values: np.ndarray) -> List[float]:
    return [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]


def h5(ais: Dict[str, pd.DataFrame], human: pd.DataFrame, n_boot: int, seed: int) -> Dict[str, Any]:
    """H5: ΔD = D(상태, 인간 전체) − D(기준선, 인간 전체), 잠금 세트. 지지 = ΔD < 0이고 95% 구간이 0을 제외.
    보고용 ΔFR. 부트스트랩: 문항 × 블록(조건 간 같은 블록) × 인간 소집단"""
    pair = {"base": ais["A-baseline"], "state": ais["A-stateful"]}
    point = fidelity.fidelity(pair, human, np.random.default_rng(seed))
    boot = fidelity.bootstrap(pair, human, n_boot, seed + 1)
    w = boot.pivot(index="rep", columns="condition", values=["D_full", "FR"])
    dd = (w[("D_full", "state")] - w[("D_full", "base")]).to_numpy()
    dfr = (w[("FR", "state")] - w[("FR", "base")]).to_numpy()
    est = point["state"]["D_full"] - point["base"]["D_full"]
    ci = _ci(dd)
    return {"estimate": est, "ci": ci, "p_boot": float(min(1.0, 2 * min(np.mean(dd >= 0), np.mean(dd <= 0)))),
            "supported": bool(est < 0 and ci[1] < 0), "farther": bool(est > 0 and ci[0] > 0),
            "delta_FR": point["state"]["FR"] - point["base"]["FR"], "delta_FR_ci": _ci(dfr),
            "FR": {"base": point["base"]["FR"], "state": point["state"]["FR"]},
            "D_full": {"base": point["base"]["D_full"], "state": point["state"]["D_full"]},
            "n_ai": {k: len(v) for k, v in pair.items()}, "n_items": int(pair["base"]["item"].nunique()),
            "n_boot": n_boot, "splits": point["_splits"]["used"]}


def h2(ai_base: pd.DataFrame, human: pd.DataFrame, n_boot: int, seed: int) -> Dict[str, Any]:
    """H2: FR(A-기준선) ≠ 1. 95% 부트스트랩 구간(문항 × 블록 × 인간 소집단)이 1을 포함하는가"""
    point = fidelity.fidelity({"base": ai_base}, human, np.random.default_rng(seed))
    boot = fidelity.bootstrap({"base": ai_base}, human, n_boot, seed + 1)
    fr = boot["FR"].to_numpy()
    ci = _ci(fr)
    return {"estimate": point["base"]["FR"], "ci": ci,
            "p_boot": float(min(1.0, 2 * min(np.mean(fr >= 1), np.mean(fr <= 1)))),
            "reject": bool(ci[0] > 1 or ci[1] < 1), "n_ai": len(ai_base), "n_items": int(ai_base["item"].nunique()),
            "n_boot": n_boot}


# ---------------- 기준점: H1, H2b, H2c, H3 ----------------

def h1(surveys: pd.DataFrame, plans: Dict[str, Dict[str, dict]], human: pd.DataFrame) -> Dict[str, Any]:
    """H1 truth wins의 인간·AI 차이: correct ~ k × agent_type + group_size + (1 | block) + (1 | run) + (1 | card_set),
    로지스틱. 검정: k(1 vs 0) × agent_type. AI는 원 과제 A-기준선 전체 반복, 인간은 run = block"""
    s = surveys[(surveys["study"] == "wason") & surveys["topic_key"].str.startswith("deli-")
                & (surveys["phase"] == "post") & (surveys["label"] == "A-baseline") & surveys["correct"].notna()]
    rows = []
    for (d, key, batch, rep), g in s.groupby(["discussion_id", "topic_key", "batch", "replicate"]):
        topic = plans[batch][key]
        item = topic["survey"]["items"][0]
        corr = set(item["correct"])
        k = sum(set(v["cards"]) == corr for v in topic["seeds"].values())
        for c in g["correct"]:
            rows.append({"block": key, "run": f"{key}#r{rep}", "card_set": ",".join(sorted(item["options"])),
                         "group_size": len(topic["personas"]), "k": initial_correct_bin(k),
                         "ai": 1, "correct": int(bool(c))})
    ai = pd.DataFrame(rows)
    if ai.empty:
        raise ValueError("H1: no A-baseline runs of the original task")
    hum = human[human["block"].isin(set(ai["block"]))].assign(ai=0)
    hum = hum.assign(run=hum["block"] + "#h")
    data = pd.concat([hum, ai], ignore_index=True)
    # 초기 정답자 수 0 / 1 / 2+를 기준 범주 0의 지시 변수로 (R과 대체 방법의 계수 이름을 같게)
    data["k1"], data["k2p"] = (data["k"] == "1").astype(int), (data["k"] == "2+").astype(int)
    formula = ("correct ~ k1 + k2p + ai + k1:ai + k2p:ai + group_size"
               " + (1 | block) + (1 | run) + (1 | card_set)")
    return _fit(data.drop(columns="k"), formula, ["k1:ai"], ["block"], "binomial")["k1:ai"]


def h2b(surveys: pd.DataFrame, plans: Dict[str, Dict[str, dict]], parties: Dict[int, str]) -> Dict[str, Any]:
    """H2b 상호작용 효과 A-기준선 − B: post ~ condition × pre_c + party + (1 + condition | block) + (1 | item) + (1 | persona).
    block = 복제 집단(주제). B는 반복이 없어 A의 모든 반복과 같은 블록으로 묶는다"""
    s = surveys[(surveys["study"] == "a1r") & surveys["topic_key"].map(a1r_set).eq("groups")
                & surveys["label"].isin(["A-baseline", "B-materials"])]
    pp = _post_pre(s).dropna(subset=["pre", "post"])
    _need(pp, ["A-baseline", "B-materials"], "H2b")
    batch = s.drop_duplicates("discussion_id").set_index("discussion_id")["batch"]
    pp["persona"] = [plans[batch[d]][k]["meta"]["respondent_rows"][p]
                     for d, k, p in zip(pp["discussion_id"], pp["topic_key"], pp["participant"])]
    pp["party"] = "p" + pp["persona"].map(parties)
    pp["block"] = pp["topic_key"]
    pp["condition"] = (pp["label"] == "A-baseline").astype(int)
    pp["pre_c"] = pp["pre"] - pp["pre"].mean()
    pp["persona"] = "r" + pp["persona"].astype(str)
    pp = pp.rename(columns={"item_id": "item"})
    return _fit(pp[["post", "condition", "pre_c", "party", "block", "item", "persona"]],
                "post ~ condition * pre_c + party + (1 + condition | block) + (1 | item) + (1 | persona)",
                ["condition"], ["item", "block"])["condition"]


def h2c(surveys: pd.DataFrame) -> Dict[str, Any]:
    """H2c 모델 기본 입장 끌림: post_A − pre ~ β(D − pre) + γ(집단 평균 pre − pre) + (1 | block) + (1 | item). 검정 β"""
    s = surveys[(surveys["study"] == "a1r") & surveys["topic_key"].map(a1r_set).eq("groups")
                & surveys["label"].isin(["A-baseline", "D-prior"])]
    pp = _post_pre(s)
    _need(pp, ["A-baseline", "D-prior"], "H2c")
    a = pp[(pp["label"] == "A-baseline")].dropna(subset=["pre", "post"])
    d = pp[(pp["label"] == "D-prior")].dropna(subset=["post"])[["topic_key", "participant", "post"]]
    d = d.groupby(["topic_key", "participant"])["post"].mean().rename("D").reset_index()
    a = a.merge(d, on=["topic_key", "participant"])
    a["groupmean_pre"] = a.groupby("discussion_id")["pre"].transform("mean")
    data = pd.DataFrame({"y": a["post"] - a["pre"], "x_default": a["D"] - a["pre"],
                         "x_group": a["groupmean_pre"] - a["pre"], "block": a["block"], "item": a["item_id"]})
    r = _fit(data, "y ~ x_default + x_group + (1 | block) + (1 | item)", ["x_default", "x_group"], ["item", "block"])
    return {"beta": r["x_default"], "gamma": r["x_group"]}


def h3(surveys: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """H3a 질, H3b 지지, H3c 질 × 지지 (기준선 모드 안): Δ ~ q × sup + side + (1 + q | set)"""
    d = _argq_deltas(surveys)
    r = _fit(d[d["eng"] < 0], "delta ~ q * sup + side + (1 + q | set)", ["q", "sup", "q:sup"], ["set"])
    return {"H3a": r["q"], "H3b": r["sup"], "H3c": r["q:sup"]}
