"""
E단계 (study1-exploratory-plan.md 7절 E): S4 1-C 공모자 논거 방향 × 기본 입장(D), S8 설득 연결망. [탐색, 부록]

- S4: 1-C 세트(주제 × 표적 입장)를 "공모자 논거 방향이 모델 기본 입장 D와 같은 세트"와 "반대 세트"로 나눠 질(q)·지지(sup) 효과를 재추정한다.
  D는 1-C 주제에 대해 사후 측정한 D-prior 조건(심은 값 없이 설문만; 2026-10-19 추가 측정)의 표적 응답 평균. Δ는 세트별 C-재응답 평균 Δ를 뺀 보정값.
- S8: 분석기(`meta.analysis`)의 targets(support/attack/concede/question)·influence로 발언자 → 상대 연결망을 만들고, k=1 집단에서 처음 정답자가
  받은 지지·반박·양보를 다른 구성원과 비교한다. 분석기 신뢰도는 N6 ② 코더 판정과의 일치로 먼저 확인한다(같은 발언).
"""
import json
import sqlite3
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.analysis.exploratory import _resample, _summ
from src.analysis.study1 import _argq_deltas, _fit, _post_pre


# ---------------- S4 ----------------

def argq_default_stance(surveys_d: pd.DataFrame) -> pd.Series:
    """D-prior 실행의 표적(설문 대상) 사후 응답 평균을 주제별로 (0~100). 세트(pro/con)는 심은 값이 없으므로 합친다"""
    s = surveys_d[(surveys_d["study"] == "argq") & (surveys_d["label"] == "D-prior") & (surveys_d["phase"] == "post") & surveys_d["score"].notna()]
    topic = s["topic_key"].str.replace(r"-(pro|con)$", "", regex=True)
    return s.groupby(topic)["score"].mean()


def s4_direction_split(surveys: pd.DataFrame, d_hat: pd.Series) -> Dict[str, Any]:
    """세트별 공모자 논거 방향(표적 입장의 반대)이 D와 같은지로 나눠 Δc ~ q × sup × eng + side + (1 + q | set) 재추정"""
    d = _argq_deltas(surveys)
    c = surveys[(surveys["study"] == "argq") & (surveys["label"] == "C-reanswer")]
    cpp = _post_pre(c).dropna(subset=["pre", "post"])
    pro = cpp["topic_key"].str.endswith("-pro")
    c_delta = pd.Series(np.where(pro, cpp["pre"] - cpp["post"], cpp["post"] - cpp["pre"]), index=cpp.index).groupby(cpp["topic_key"]).mean()
    d["delta_c"] = d["delta"] - d["set"].map(c_delta).fillna(0.0)
    topic = d["set"].str.replace(r"-(pro|con)$", "", regex=True)
    d["D"] = topic.map(d_hat)
    seeded_pro = d["set"].str.endswith("-pro")
    # 공모자는 표적의 반대쪽을 주장: 표적 pro → 공모자 con → D < 50 이면 D와 같은 방향
    # Legacy against_D keys below denote NOT aligned, including neutral D == 50;
    # they must not be presented as strictly opposing-direction sets.
    d["confed_with_D"] = np.where(seeded_pro, d["D"] < 50, d["D"] > 50)
    out: Dict[str, Any] = {"n_sets": int(d["set"].nunique()), "d_hat": {k: float(v) for k, v in d_hat.items()},
                           "sets_with_D": sorted(d.loc[d["confed_with_D"], "set"].unique().tolist()),
                           "sets_against_D": sorted(d.loc[~d["confed_with_D"], "set"].unique().tolist()), "by_split": {}}
    for name, g in (("confederates_with_D", d[d["confed_with_D"]]), ("confederates_against_D", d[~d["confed_with_D"]])):
        if g["set"].nunique() < 2:
            out["by_split"][name] = {"n_sets": int(g["set"].nunique()), "note": "too few sets"}
            continue
        res: Dict[str, Any] = {"n_sets": int(g["set"].nunique()), "n": int(len(g)),
                               "mean_delta": float(g["delta"].mean()), "mean_delta_c": float(g["delta_c"].mean()),
                               "cell_means_delta_c": {f"q={'strong' if q > 0 else 'weak'},sup={'majority' if s > 0 else 'minority'},eng={'stateful' if e > 0 else 'baseline'}": float(x["delta_c"].mean())
                                                      for (q, s, e), x in g.groupby(["q", "sup", "eng"])}}
        try:
            res["model_delta_c"] = _fit(g.rename(columns={"delta_c": "y"}), "y ~ q * sup * eng + side + (1 + q | set)", ["q", "sup", "eng", "q:eng", "sup:eng"], ["set"])
        except Exception as e:  # R 미설치 등
            res["model_delta_c"] = {"error": f"{type(e).__name__}: {e}"}
        out["by_split"][name] = res
    return out


# ---------------- S8 ----------------

def analyzer_vs_coders(devices_coded: pd.DataFrame, utt: pd.DataFrame) -> Dict[str, Any]:
    """같은 발언에서 분석기 필드와 N6 ② 코더 판정의 일치 (분석기 신뢰도 점검; 코더가 정확성 기준은 아님)"""
    m = devices_coded.merge(utt[["discussion_id", "seq", "rel_attack", "rel_concede", "rel_support", "n_targets", "n_concessions_text"]], on=["discussion_id", "seq"])
    pairs = {"objects_to_shared_view ~ analyzer attack target": (m["objects_to_shared_view"] == "yes", m["rel_attack"] > 0),
             "concedes_part ~ analyzer concession": (m["concedes_part"] == "yes", m["n_concessions_text"] > 0),
             "addresses_specific_claim ~ analyzer any target": (m["addresses_specific_claim"] == "yes", m["n_targets"] > 0)}
    out = {"n": int(len(m)), "pairs": {}}
    for k, (a, b) in pairs.items():
        a, b = a.astype(bool), b.astype(bool)
        po = float((a == b).mean())
        pe = float(a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean()))
        out["pairs"][k] = {"agreement": po, "kappa": float((po - pe) / (1 - pe)) if pe < 1 else float("nan"),
                           "coder_yes": float(a.mean()), "analyzer_yes": float(b.mean()),
                           "analyzer_yes_given_coder_yes": float(b[a].mean()) if a.any() else float("nan"),
                           "analyzer_yes_given_coder_no": float(b[~a].mean()) if (~a).any() else float("nan")}
    return out


def _edges(db: str, discussion_ids: List[str]) -> pd.DataFrame:
    """발언 → 상대 연결: relation(support/attack/concede/question) 횟수와 influence quality"""
    con = sqlite3.connect(db)
    rows = []
    for d in discussion_ids:
        for seq, sp, meta in con.execute("select seq, speaker, meta from messages where discussion_id=? and speaker_type!='moderator'", (d,)):
            an = (json.loads(meta) if meta else {}).get("analysis") or {}
            for t in an.get("targets") or []:
                rows.append({"discussion_id": d, "seq": seq, "src": sp, "dst": t.get("speaker"), "kind": t.get("relation"), "w": 1.0})
            for i in an.get("influence") or []:
                rows.append({"discussion_id": d, "seq": seq, "src": sp, "dst": i.get("listener"), "kind": "influence", "w": float(i.get("quality") or 0)})
    e = pd.DataFrame(rows)
    return e[e["src"] != e["dst"]] if not e.empty else e


def s8_network(utt: pd.DataFrame, wruns: pd.DataFrame, plans: Dict[str, Dict[str, dict]], db: str, n_boot: int, seed: int) -> Dict[str, Any]:
    """1-A(원 과제) k=1 집단: 처음 정답자가 받은 지지·반박·양보·영향 대 다른 구성원 (발언당), 엔진·결과별. 재표집: 집단"""
    rng = np.random.default_rng(seed)
    runs = wruns[wruns["block"].str.startswith("deli-") & (wruns["k"] == "1") & wruns["label"].isin(["A-baseline", "A-stateful"])]
    runs = runs[(runs["label"] == "A-stateful") | (runs["replicate"] == 0)]
    e = _edges(db, runs["discussion_id"].tolist())
    ai = utt[utt["discussion_id"].isin(set(runs["discussion_id"])) & (utt["speaker_type"] != "moderator")]
    n_utt = ai.groupby(["discussion_id", "speaker"]).size()
    # 처음 정답자: 심은 답이 정답인 참가자
    solver = {}
    for r in runs.itertuples(index=False):
        t = None
        for batch, topics in plans.items():
            if r.block in topics:
                t = topics[r.block]
                break
        corr = set(c.upper() for c in t["survey"]["items"][0]["correct"])
        solver[r.discussion_id] = {p for p, v in t["seeds"].items() if set(x.upper() for x in v["cards"]) == corr}
    rows = []
    for (d, sp), n in n_utt.items():
        rec = e[(e["discussion_id"] == d) & (e["dst"] == sp)] if not e.empty else e
        sent = e[(e["discussion_id"] == d) & (e["src"] == sp)] if not e.empty else e
        row = {"discussion_id": d, "speaker": sp, "is_solver": sp in solver.get(d, set()), "n_utt": int(n)}
        for k in ("support", "attack", "concede", "question"):
            row[f"recv_{k}_per_utt"] = float((rec["kind"] == k).sum() / n) if len(rec) else 0.0
            row[f"sent_{k}_per_utt"] = float((sent["kind"] == k).sum() / n) if len(sent) else 0.0
        inf = rec[rec["kind"] == "influence"] if len(rec) else rec
        row["recv_influence_quality"] = float(inf["w"].mean()) if len(inf) else np.nan
        row["recv_influence_per_utt"] = float(len(inf) / n)
        rows.append(row)
    t = pd.DataFrame(rows).merge(runs[["discussion_id", "block", "label", "majority_correct"]], on="discussion_id")
    cols = [c for c in t.columns if c.startswith(("recv_", "sent_"))]
    out: Dict[str, Any] = {"n_groups": int(runs["block"].nunique()), "n_runs": int(len(runs)), "by_label": {}}
    for lab, g in t.groupby("label"):
        res: Dict[str, Any] = {"n_runs": int(g["discussion_id"].nunique()), "solver": {}, "others": {}, "solver_minus_others": {}, "by_outcome": {}}
        blocks = g["block"].unique()
        bb = {b: x for b, x in g.groupby("block")}
        def stat(x):
            s, o = x[x["is_solver"]], x[~x["is_solver"]]
            return {c: (float(s[c].mean()), float(o[c].mean())) for c in cols}
        p = stat(g)
        draws = [stat(pd.concat([bb[b] for b in _resample(blocks, rng)])) for _ in range(n_boot)]
        for c in cols:
            res["solver"][c] = _summ(p[c][0], [x[c][0] for x in draws], int(g["is_solver"].sum()), "group")
            res["others"][c] = _summ(p[c][1], [x[c][1] for x in draws], int((~g["is_solver"]).sum()), "group")
            res["solver_minus_others"][c] = _summ(p[c][0] - p[c][1], [x[c][0] - x[c][1] for x in draws], None, "group")
        for oc, h in g.groupby("majority_correct"):
            s, o = h[h["is_solver"]], h[~h["is_solver"]]
            res["by_outcome"][f"majority_correct={int(oc)}"] = {"n_runs": int(h["discussion_id"].nunique()),
                                                                 **{c: {"solver": float(s[c].mean()), "others": float(o[c].mean())} for c in cols}}
        out["by_label"][lab] = res
    return out
