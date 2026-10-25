"""
탐색 분석 A단계 (study1-exploratory-plan.md 7절): 합의가 어디로 모였는가와 관련 확장.

- N1  H2c 모형(β 기본 입장, γ 집단 평균)을 A-기준선·A-상태에 각각 적합, 페르소나 무선 효과 민감도, 엔진 상호작용, 합의점 위치
- S1  모델 기본 입장 D(문항)와 인간 사후·사전 평균의 관계
- S2  세 모델의 D·합의점 일치 (모델별 표를 받아 교차 계산)
- E4  문항별 기본 입장 끌림(기울기·상관)과 합의율
- E6  정당 격차 감소의 분해 (민주·공화 각각의 이동, 상대 정당 쪽 이동)
- E7  이동 방향 일치 (direction_agree) 인간 대 AI
- E9  집단 평균에서 멀어지는 이동의 비율 (Gemini 기준선 발산 점검)
- E10 이름 제거(debranded) 문항의 기본 입장 끌림·합의율
- E8  A1R 가중치 민감도 (숙의군·통제군 지표의 가중 점추정)
모든 결과는 [탐색]. 재표집 단위는 계획 2-2 표.
"""
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.analysis import mixed
from src.analysis.data import a1r_set
from src.analysis.exploratory import A1R_LABELS, _ci, _metrics, _party_map, _resample, _summ
from src.analysis.study1 import _fit, _post_pre

H2C_FORMULA = "y ~ x_default + x_group + (1 | block) + (1 | item)"
H2C_PERSONA = "y ~ x_default + x_group + (1 | block) + (1 | item) + (1 | persona)"
H2C_ENGINE = "y ~ (x_default + x_group) * eng + (1 | block) + (1 | item)"


def _h2c_frame(agents: pd.DataFrame, label: str) -> pd.DataFrame:
    a = agents[agents["label"] == label].dropna(subset=["pre", "post", "D"]).copy()
    a["groupmean_pre"] = a.groupby("discussion_id")["pre"].transform("mean")
    return pd.DataFrame({"y": a["post"] - a["pre"], "x_default": a["D"] - a["pre"],
                         "x_group": a["groupmean_pre"] - a["pre"], "block": a["block"], "item": a["item_id"],
                         "persona": "r" + a["persona"].astype(str), "label": label})


def n1_direction(agents: pd.DataFrame, human: pd.DataFrame, n_boot: int, seed: int) -> Dict[str, Any]:
    """N1: β(D − pre)·γ(집단 평균 − pre)를 조건별로, 페르소나 무선 효과 민감도, 엔진 상호작용. 합의점 c_g의 위치"""
    out = {"models": {}, "consensus_location": {}}
    frames = {lab: _h2c_frame(agents, lab) for lab in ("A-baseline", "A-stateful")}
    for lab, f in frames.items():
        r = _fit(f, H2C_FORMULA, ["x_default", "x_group"], ["item", "block"])
        rp = _fit(f, H2C_PERSONA, ["x_default", "x_group"], ["item", "block"])
        out["models"][lab] = {"beta": r["x_default"], "gamma": r["x_group"],
                              "persona_sensitivity": {"beta": rp["x_default"], "gamma": rp["x_group"]},
                              "n": int(len(f)), "personas": int(f["persona"].nunique())}
    both = pd.concat(frames.values(), ignore_index=True)
    both["eng"] = np.where(both["label"] == "A-stateful", 0.5, -0.5)
    ri = _fit(both, H2C_ENGINE, ["x_default", "x_group", "x_default:eng", "x_group:eng"], ["item", "block"])
    out["models"]["engine_interaction"] = {"beta_x_engine": ri["x_default:eng"], "gamma_x_engine": ri["x_group:eng"],
                                           "formula": H2C_ENGINE, "coding": "eng = +0.5 stateful, −0.5 baseline"}
    # 합의점 위치: 블록 사후 평균 c_g 가 D(블록 페르소나 D 평균) / 사전 평균 / 인간 사후 평균 중 어디에 가장 가까운가
    hpost = human.groupby("item")["post"].mean()
    hpre = human.groupby("item")["pre"].mean()
    rows = []
    for lab in ("A-baseline", "A-stateful", "B-materials", "C-reanswer"):
        a = agents[agents["label"] == lab].dropna(subset=["pre", "post"])
        for block, g in a.groupby("block"):
            item = g["item_id"].iloc[0]
            if item not in hpost.index or g["D"].isna().all():
                continue
            c = g["post"].mean()
            d = {"D": abs(c - g["D"].mean()), "pre_mean": abs(c - g["pre"].mean()), "human_post": abs(c - hpost[item])}
            rows.append({"block": block, "item": item, "label": lab, "c": c, "pre_mean": g["pre"].mean(), "D_mean": g["D"].mean(),
                         "human_post": hpost[item], "human_pre": hpre[item], **{f"dist_{k}": v for k, v in d.items()},
                         "dist_human_pre": abs(c - hpre[item]),
                         "closer_to_human_post_than_pre": float(abs(c - hpost[item]) < abs(c - hpre[item])),
                         "nearest": min(d, key=d.get),
                         "moved_toward_D": float(abs(c - g["D"].mean()) < abs(g["pre"].mean() - g["D"].mean())),
                         "moved_toward_human_post": float(abs(c - hpost[item]) < abs(g["pre"].mean() - hpost[item]))})
    loc = pd.DataFrame(rows)
    rng = np.random.default_rng(seed)
    for lab, g in loc.groupby("label"):
        items = g["item"].to_numpy()
        pos = {it: np.flatnonzero(items == it) for it in np.unique(items)}

        def stats(f):
            return {"share_nearest_D": float((f["nearest"] == "D").mean()), "share_nearest_pre_mean": float((f["nearest"] == "pre_mean").mean()),
                    "share_nearest_human_post": float((f["nearest"] == "human_post").mean()),
                    "mean_dist_D": float(f["dist_D"].mean()), "mean_dist_pre_mean": float(f["dist_pre_mean"].mean()),
                    "mean_dist_human_post": float(f["dist_human_post"].mean()),
                    "share_moved_toward_D": float(f["moved_toward_D"].mean()), "share_moved_toward_human_post": float(f["moved_toward_human_post"].mean()),
                    "mean_dist_human_pre": float(f["dist_human_pre"].mean()),
                    "share_closer_to_human_post_than_pre": float(f["closer_to_human_post_than_pre"].mean())}
        p = stats(g)
        draws = []
        for _ in range(n_boot):
            idx = np.concatenate([rng.choice(pos[it], len(pos[it]), replace=True) for it in pos])
            draws.append(stats(g.iloc[idx]))
        out["consensus_location"][lab] = {k: _summ(p[k], [d[k] for d in draws]) for k in p} | {"n_blocks": int(len(g)), "resample": "item > block"}
    return out, loc


def s1_default_vs_human(agents: pd.DataFrame, human: pd.DataFrame, blocks: pd.DataFrame, n_boot: int, seed: int) -> Dict[str, Any]:
    """S1: 문항별 모델 기본 입장 D 평균 대 인간 사후·사전 평균. 상관, 거리, 인간 이동 방향과의 일치. 재표집: 문항(30)"""
    d = agents[agents["label"] == "D-prior"].dropna(subset=["post"]).groupby("item_id")["post"].mean().rename("D")
    h = human.groupby("item").agg(human_pre=("pre", "mean"), human_post=("post", "mean"))
    ai_post = blocks.pivot_table(index="item", columns="label", values="mean_post")
    t = h.join(d).join(ai_post.add_prefix("post_")).dropna(subset=["D"])
    t["human_shift"] = t["human_post"] - t["human_pre"]
    t["D_minus_human_pre"] = t["D"] - t["human_pre"]
    t["dist_D_human_post"] = (t["D"] - t["human_post"]).abs()
    t["dist_D_human_pre"] = (t["D"] - t["human_pre"]).abs()
    items = t.index.to_numpy()
    rng = np.random.default_rng(seed)

    def stats(f):
        big = f[f["human_shift"].abs() >= 0.5]
        return {"spearman_D_human_post": float(f["D"].corr(f["human_post"], method="spearman")),
                "spearman_D_human_pre": float(f["D"].corr(f["human_pre"], method="spearman")),
                "pearson_D_human_post": float(f["D"].corr(f["human_post"])),
                "mean_abs_D_minus_human_post": float(f["dist_D_human_post"].mean()),
                "mean_abs_D_minus_human_pre": float(f["dist_D_human_pre"].mean()),
                "share_D_closer_to_human_post_than_pre": float((f["dist_D_human_post"] < f["dist_D_human_pre"]).mean()),
                "sign_agreement_human_shift_vs_D_direction": float((np.sign(big["human_shift"]) == np.sign(big["D_minus_human_pre"])).mean()) if len(big) else np.nan,
                "n_items_human_shift_ge_0.5": int(len(big)),
                "spearman_D_vs_post_A_stateful": float(f["D"].corr(f["post_A-stateful"], method="spearman")) if "post_A-stateful" in f else np.nan,
                "spearman_D_vs_post_A_baseline": float(f["D"].corr(f["post_A-baseline"], method="spearman")) if "post_A-baseline" in f else np.nan}
    p = stats(t)
    draws = [stats(t.iloc[rng.choice(len(items), len(items), replace=True)]) for _ in range(n_boot)]
    return {k: _summ(p[k], [x[k] for x in draws]) if not isinstance(p[k], int) else p[k] for k in p} | {"n_items": int(len(t)), "resample": "item"}, t.reset_index()


def s2_cross_model(tables: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """S2: 모델 간 D(문항)와 합의점(A-상태·A-기준선 문항 사후 평균)의 일치. tables = {model: s1 문항 표}"""
    models = list(tables)
    out = {"D": {}, "post_A-stateful": {}, "post_A-baseline": {}, "within_model_D_vs_post_stateful": {}}
    for i, a in enumerate(models):
        ta = tables[a].set_index("item")
        out["within_model_D_vs_post_stateful"][a] = {"spearman": float(ta["D"].corr(ta["post_A-stateful"], method="spearman")),
                                                     "mean_abs_diff": float((ta["D"] - ta["post_A-stateful"]).abs().mean())}
        for b in models[i + 1:]:
            tb = tables[b].set_index("item")
            common = ta.index.intersection(tb.index)
            for col in ("D", "post_A-stateful", "post_A-baseline"):
                out[col][f"{a} vs {b}"] = {"spearman": float(ta.loc[common, col].corr(tb.loc[common, col], method="spearman")),
                                          "pearson": float(ta.loc[common, col].corr(tb.loc[common, col])),
                                          "mean_abs_diff": float((ta.loc[common, col] - tb.loc[common, col]).abs().mean()), "n_items": int(len(common))}
    return out


def e4_item_pull(agents: pd.DataFrame, blocks: pd.DataFrame) -> Dict[str, Any]:
    """E4: 문항별 기본 입장 끌림(Δ ~ D − pre 기울기·상관)과 합의율·SD 감소량의 관계 (기술 통계, 문항 30)"""
    rows = []
    for (item, lab), g in agents.dropna(subset=["pre", "post", "D"]).groupby(["item_id", "label"]):
        if lab == "D-prior" or len(g) < 10:
            continue
        x, y = (g["D"] - g["pre"]).to_numpy(float), (g["post"] - g["pre"]).to_numpy(float)
        ok = np.abs(x) > 0
        slope = float(np.polyfit(x[ok], y[ok], 1)[0]) if ok.sum() > 10 else np.nan
        rows.append({"item": item, "label": lab, "slope_toward_D": slope, "corr_toward_D": float(np.corrcoef(x[ok], y[ok])[0, 1]) if ok.sum() > 10 else np.nan,
                     "n": int(len(g))})
    t = pd.DataFrame(rows).pivot_table(index="item", columns="label", values=["slope_toward_D", "corr_toward_D"])
    cons = blocks.pivot_table(index="item", columns="label", values=["consensus_sd", "sd_drop"])
    out = {"n_items": int(len(t)), "spearman": {}}
    for lab in ("A-baseline", "A-stateful"):
        s = t[("slope_toward_D", "C-reanswer")]
        out["spearman"][f"slope_C vs consensus_sd {lab}"] = float(s.corr(cons[("consensus_sd", lab)], method="spearman"))
        out["spearman"][f"slope_C vs sd_drop {lab}"] = float(s.corr(cons[("sd_drop", lab)], method="spearman"))
        out["spearman"][f"slope_{lab} vs consensus_sd {lab}"] = float(t[("slope_toward_D", lab)].corr(cons[("consensus_sd", lab)], method="spearman"))
    out["item_slope_range"] = {lab: [float(t[("slope_toward_D", lab)].min()), float(t[("slope_toward_D", lab)].max())] for lab in A1R_LABELS}
    flat = t.copy()
    flat.columns = [f"{a}|{b}" for a, b in flat.columns]
    return out, flat.join(cons.pipe(lambda c: c.set_axis([f"{a}|{b}" for a, b in c.columns], axis=1))).reset_index()


def _toward_other_party(g: pd.DataFrame) -> Dict[str, float]:
    """민주·공화 각각: 평균 이동과 '상대 정당 사전 평균 쪽' 이동 (양수 = 상대 쪽)"""
    out = {}
    pre_d, pre_r = g.loc[g["party"] == "1", "pre"].mean(), g.loc[g["party"] == "2", "pre"].mean()
    if np.isnan(pre_d) or np.isnan(pre_r):
        return out
    for party, own, other in (("D", pre_d, pre_r), ("R", pre_r, pre_d)):
        sub = g[g["party"] == ("1" if party == "D" else "2")]
        shift = (sub["post"] - sub["pre"]).mean()
        out[f"shift_{party}"] = float(shift)
        out[f"toward_other_{party}"] = float(shift * np.sign(other - own)) if other != own else np.nan
    return out


def e6_party_decomposition(agents: pd.DataFrame, delib: pd.DataFrame, control: pd.DataFrame, n_boot: int, seed: int) -> Dict[str, Any]:
    """E6: 정당 격차 감소가 어느 정당의 이동으로 생기는가. AI 블록별(조건별), 인간 숙의군−통제군(문항별, 응답자 전체).
    재표집: AI 문항 > 블록, 인간 소집단 / 참가자"""
    rng = np.random.default_rng(seed)
    out = {"ai": {}, "human": {}}
    a = agents.dropna(subset=["pre", "post"]).copy()
    a["party"] = a["party"].astype(str)
    for lab in A1R_LABELS:
        rows = [{"block": b, "item": g["item_id"].iloc[0], **_toward_other_party(g)} for b, g in a[a["label"] == lab].groupby("block")]
        t = pd.DataFrame(rows).dropna()
        items = t["item"].to_numpy()
        pos = {it: np.flatnonzero(items == it) for it in np.unique(items)}
        cols = ["shift_D", "shift_R", "toward_other_D", "toward_other_R"]
        p = {c: float(t[c].mean()) for c in cols}
        draws = []
        for _ in range(n_boot):
            idx = np.concatenate([rng.choice(pos[it], len(pos[it]), replace=True) for it in pos])
            draws.append({c: float(t[c].iloc[idx].mean()) for c in cols})
        out["ai"][lab] = {c: _summ(p[c], [d[c] for d in draws]) for c in cols} | {"n_blocks": int(len(t))}
    # 인간: 문항별 팔 지표 → 문항 평균, 숙의군−통제군
    for arm, frame, unit in (("delib", delib, "group"), ("control", control, "row")):
        f = frame.copy()
        f["party"] = f["party"].astype(str)
        ids = f[unit].to_numpy()
        uid = np.unique(ids)
        pos = {u: np.flatnonzero(ids == u) for u in uid}

        def stats(ff):
            vals = [_toward_other_party(g) for _, g in ff.groupby("item")]
            vals = [v for v in vals if v]
            return {c: float(np.nanmean([v.get(c, np.nan) for v in vals])) for c in ("shift_D", "shift_R", "toward_other_D", "toward_other_R")}
        p = stats(f)
        draws = [stats(f.iloc[np.concatenate([pos[u] for u in _resample(uid, rng)])]) for _ in range(n_boot)]
        out["human"][arm] = {c: _summ(p[c], [d[c] for d in draws]) for c in p} | {"resample": unit, "n_units": int(len(uid))}
        out["human"][f"{arm}_draws"] = draws
    dd, dc = out["human"].pop("delib_draws"), out["human"].pop("control_draws")
    out["human"]["delib - control"] = {c: _summ(out["human"]["delib"][c]["estimate"] - out["human"]["control"][c]["estimate"],
                                               [x[c] - y[c] for x, y in zip(dd, dc)]) for c in ("shift_D", "shift_R", "toward_other_D", "toward_other_R")}
    return out


def e7_direction_agree(blocks: pd.DataFrame, human_units: pd.DataFrame, n_boot: int, seed: int) -> Dict[str, Any]:
    """E7: 이동자(|Δ| ≥ 2) 중 최빈 방향 비율. AI 조건별, 인간 5명 추출·소집단 전원"""
    rng = np.random.default_rng(seed)
    out = {"ai": {}, "human": {}}
    for lab in A1R_LABELS:
        g = blocks[blocks["label"] == lab].dropna(subset=["direction_agree"])
        items = g["item"].to_numpy()
        pos = {it: np.flatnonzero(items == it) for it in np.unique(items)}
        p = float(g["direction_agree"].mean())
        draws = [float(g["direction_agree"].iloc[np.concatenate([rng.choice(pos[it], len(pos[it]), replace=True) for it in pos])].mean()) for _ in range(n_boot)]
        out["ai"][lab] = _summ(p, draws, len(g), "item > block")
    groups = human_units["group"].to_numpy()
    ug = np.unique(groups)
    for col, name in (("draw_direction_agree", "draw5"), ("full_direction_agree", "full_group")):
        p = float(human_units[col].mean())
        draws = [float(human_units[col].iloc[np.concatenate([np.flatnonzero(groups == g) for g in _resample(ug, rng)])].mean()) for _ in range(n_boot)]
        out["human"][name] = _summ(p, draws, len(human_units), "small group")
    return out


def e9_away_from_group(agents: pd.DataFrame, blocks: pd.DataFrame, n_boot: int, seed: int) -> Dict[str, Any]:
    """E9: 집단 평균(사전)에서 멀어지는 쪽으로 움직인 에이전트 비율(|Δ| ≥ 1 중), 조건별; 문항별 SD 변화 음수 비율"""
    rng = np.random.default_rng(seed)
    a = agents.dropna(subset=["pre", "post"]).copy()
    a["gm"] = a.groupby("discussion_id")["pre"].transform("mean")
    a["d"] = a["post"] - a["pre"]
    a["away"] = np.sign(a["d"]) == -np.sign(a["gm"] - a["pre"])
    out = {}
    for lab in A1R_LABELS:
        g = a[(a["label"] == lab) & (a["d"].abs() >= 1) & ((a["gm"] - a["pre"]).abs() > 0)]
        blocks_arr = g["block"].to_numpy()
        ub = np.unique(blocks_arr)
        pos = {b: np.flatnonzero(blocks_arr == b) for b in ub}
        p = float(g["away"].mean())
        draws = [float(g["away"].iloc[np.concatenate([pos[b] for b in _resample(ub, rng)])].mean()) for _ in range(n_boot)]
        sdneg = blocks[blocks["label"] == lab].groupby("item")["sd_drop"].mean()
        out[lab] = {"share_moving_away_from_group_mean": _summ(p, draws, len(g), "block"),
                    "items_with_negative_mean_sd_drop": int((sdneg < 0).sum()), "n_items": int(len(sdneg))}
    return out


def e10_debranded(surveys: pd.DataFrame, plans, parties, n_boot: int, seed: int) -> Dict[str, Any]:
    """E10: 이름 제거 문항(3문항 × 8집단)과 같은 문항의 원 버전(groups 세트)에서 합의율·SD 감소·기본 입장 끌림 비교"""
    rng = np.random.default_rng(seed)
    out = {}
    for setname in ("debranded", "groups"):
        s = surveys[(surveys["study"] == "a1r") & surveys["topic_key"].map(a1r_set).eq(setname)]
        pp = _post_pre(s)
        pm = _party_map(s, plans, parties)
        pp["party"] = [pm[(d, p)][0] for d, p in zip(pp["discussion_id"], pp["participant"])]
        dmean = pp[pp["label"] == "D-prior"].dropna(subset=["post"]).groupby(["topic_key", "participant"])["post"].mean().rename("D")
        pp = pp.join(dmean, on=["topic_key", "participant"])
        if setname == "debranded":
            items = set(pp["item_id"])
        pp = pp[pp["item_id"].isin(items)]
        res = {}
        for lab in A1R_LABELS:
            g = pp[pp["label"] == lab].dropna(subset=["pre", "post"])
            rows = []
            for b, gg in g.groupby("topic_key"):
                if len(gg) < 3:
                    continue
                m = _metrics(gg["pre"].to_numpy(float), gg["post"].to_numpy(float), gg["party"].astype(str).to_numpy())
                x, y = (gg["D"] - gg["pre"]).to_numpy(float), (gg["post"] - gg["pre"]).to_numpy(float)
                rows.append({"block": b, "consensus_sd": m["consensus_sd"], "sd_drop": m["sd_drop"], "mean_abs_move": m["mean_abs_move"],
                             "toward_D_corr": float(np.corrcoef(x, y)[0, 1]) if np.nanstd(x) > 0 and np.nanstd(y) > 0 else np.nan})
            t = pd.DataFrame(rows)
            cols = ["consensus_sd", "sd_drop", "mean_abs_move", "toward_D_corr"]
            p = {c: float(t[c].mean()) for c in cols}
            draws = [{c: float(t[c].iloc[rng.choice(len(t), len(t), replace=True)].mean()) for c in cols} for _ in range(n_boot)]
            res[lab] = {c: _summ(p[c], [d[c] for d in draws]) for c in cols} | {"n_blocks": int(len(t)), "resample": "block"}
        out[setname] = res
    out["items"] = sorted(items)
    return out


def _wstd(x: np.ndarray, w: np.ndarray) -> float:
    m = np.average(x, weights=w)
    return float(np.sqrt(np.average((x - m) ** 2, weights=w)))


def e8_weighted(delib: pd.DataFrame, control: pd.DataFrame) -> Dict[str, Any]:
    """E8: A1R 가중치(WEIGHT_DELEGATE / WEIGHT_CONTROL)를 적용한 팔별 지표의 문항 평균 (점추정만, 민감도)"""
    out = {}
    for arm, f in (("delib", delib), ("control", control)):
        f = f.dropna(subset=["weight"]).copy()
        f["party"] = f["party"].astype(str)
        rows = []
        for item, g in f.groupby("item"):
            w, pre, post = g["weight"].to_numpy(float), g["pre"].to_numpy(float), g["post"].to_numpy(float)
            d = post - pre
            dem, rep = g["party"] == "1", g["party"] == "2"
            gap_pre = abs(np.average(pre[dem], weights=w[dem]) - np.average(pre[rep], weights=w[rep]))
            gap_post = abs(np.average(post[dem], weights=w[dem]) - np.average(post[rep], weights=w[rep]))
            rows.append({"sd_drop": _wstd(pre, w) - _wstd(post, w), "gap_change": gap_pre - gap_post,
                         "movers": float(np.average(np.abs(d) >= 2, weights=w)), "mean_shift": float(np.average(d, weights=w))})
        out[arm] = pd.DataFrame(rows).mean().to_dict() | {"n": int(f["row"].nunique()), "mean_weight": float(f.drop_duplicates("row")["weight"].mean())}
    out["delib - control"] = {k: out["delib"][k] - out["control"][k] for k in ("sd_drop", "gap_change", "movers", "mean_shift")}
    out["note"] = "weighted point estimates only; compare with unweighted N3 mean_over_items"
    return out


def e5_materials_lean(agents: pd.DataFrame, human: pd.DataFrame, briefing_path: str) -> Dict[str, Any]:
    """E5: 자료집 논거의 찬반 분량 균형(lean = (찬성 글자 − 반대 글자)/(합))과 B 조건 이동 방향·D 위치의 관계 (문항 30, 기술 통계)"""
    import yaml
    b = yaml.safe_load(open(briefing_path, encoding="utf-8"))["items"]
    lean = pd.Series({k: (len(v["arguments_for"]) - len(v["arguments_against"])) / (len(v["arguments_for"]) + len(v["arguments_against"])) for k, v in b.items()}, name="lean")
    shift = {}
    for lab in ("B-materials", "C-reanswer", "A-baseline", "A-stateful"):
        a = agents[agents["label"] == lab].dropna(subset=["pre", "post"])
        shift[f"shift_{lab}"] = a.groupby("item_id").apply(lambda g: float((g["post"] - g["pre"]).mean()))
    d = agents[agents["label"] == "D-prior"].dropna(subset=["post"]).groupby("item_id")["post"].mean().rename("D")
    h = human.groupby("item").agg(human_pre=("pre", "mean"), human_post=("post", "mean"))
    t = pd.DataFrame(shift).join(lean).join(d).join(h).dropna()
    t["shift_B_minus_C"] = t["shift_B-materials"] - t["shift_C-reanswer"]
    t["D_minus_human_pre"] = t["D"] - t["human_pre"]
    t["human_shift"] = t["human_post"] - t["human_pre"]
    out = {"n_items": int(len(t)), "lean_range": [float(t["lean"].min()), float(t["lean"].max())],
           "spearman": {"lean vs B−C shift": float(t["lean"].corr(t["shift_B_minus_C"], method="spearman")),
                        "lean vs B shift": float(t["lean"].corr(t["shift_B-materials"], method="spearman")),
                        "lean vs D − human pre": float(t["lean"].corr(t["D_minus_human_pre"], method="spearman")),
                        "lean vs human shift": float(t["lean"].corr(t["human_shift"], method="spearman")),
                        "B−C shift vs D − human pre": float(t["shift_B_minus_C"].corr(t["D_minus_human_pre"], method="spearman"))},
           "sign_agreement_lean_vs_B_minus_C": float((np.sign(t["lean"]) == np.sign(t["shift_B_minus_C"])).mean())}
    return out, t.reset_index().rename(columns={"index": "item"})
