"""
탐색 분석 B단계 (study1-exploratory-plan.md 5절·7절): 장치 발현 3층과 과정 지표. [탐색]

- 발언 표: 메시지 `meta`(분석기 판정, 이동 기록, 입장값, 토론 상태 스냅숏, 프롬프트 안내 문자열)를 발언 1행으로 압축
- N6 ①  장치 지시: 트리거형 발화 행위 수, 안내 문자열 수, 이동 기록 종류, 열린 반박의 생성·해소
- N6 ③  장치 뒤 변화(연관): 응답 의무 뒤 반박 해소, 반대 검토·중재 뒤 입장 분산·열린 반박 변화
- N7     엔진 입장값 x 대 텍스트 입장(분석기) 대 사후 설문; 문턱 전환 전후
- S5     합의 시점: 입장값 분산이 임계 아래로 가는 발언 순번
- S3     소수 의견자: 집단에서 먼 구성원의 이동 (AI 조건별, 인간 소집단)
- E2     상태 기반 단독 실패 집단의 과정 지표
- N8     장치 발생량–결과 연관 (혼합 모형, 부록)
②(텍스트 관찰)는 독립 코딩(D단계)에서 한다. 분석기 필드는 엔진 입장값을 만든 같은 분석기의 산출이라 보조로만 쓴다.
"""
import json
import sqlite3
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from src.analysis.data import a1r_set, study_of
from src.analysis.exploratory import _ci, _resample, _summ
from src.analysis.study1 import _fit, _post_pre

NOTES = {"moved": "Since your last turn you moved", "grounds": "Your supporting grounds", "defend": "Defend your position",
         "switched": "your position has shifted to", "reciprocity": "acknowledged these points",
         "commitments": "Arguments you have already made", "mediation_pair": "keep disagreeing"}
TRIGGER_ACTIONS = ["respond_challenge", "mediate", "third_option", "devils_advocate"]
SCHEDULED_ACTIONS = ["rebut", "undercut", "agree_extend", "example"]
CONSENSUS_SPREAD = 0.3  # config discussion.consensus_spread (run_info 에도 기록됨)


def _survey_x(score: float) -> float:
    """0~10 설문 점수 → 엔진 입장값 척도 [-1, 1] (심은 값과 같은 변환: (점수 − 5) / 5)"""
    return (score - 5.0) / 5.0


def load_utterances(db: str, runs: pd.DataFrame) -> pd.DataFrame:
    """kept 실행의 AI 발언 1행(모더레이터는 action 집계용으로만). 메타를 압축해 돌려준다"""
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    meta = runs.set_index("discussion_id")
    rows = []
    for d in runs["discussion_id"]:
        info = meta.loc[d]
        for r in con.execute("select seq, speaker, speaker_type, action, length(content) as chars, meta from messages where discussion_id=? order by seq", (d,)):
            m = json.loads(r["meta"]) if r["meta"] else {}
            base = {"discussion_id": d, "block": info["block"], "topic_key": info["topic_key"], "study": info["study"], "label": info["label"],
                    "mode": info["mode"], "replicate": info["replicate"], "seq": r["seq"], "speaker": r["speaker"], "speaker_type": r["speaker_type"],
                    "action": r["action"], "chars": r["chars"], "subtopic_idx": m.get("subtopic_idx")}
            if r["speaker_type"] == "moderator":
                rows.append(base)
                continue
            an = m.get("analysis") or {}
            targets = an.get("targets") or []
            rel = {k: sum(1 for t in targets if t.get("relation") == k) for k in ("support", "attack", "concede", "question")}
            moves = m.get("moves") or []
            stances = {k: v for k, v in (m.get("stances") or {}).items() if v is not None}
            deb = m.get("debate") or {}
            st = deb.get("state") or {}
            parts = st.get("participants") or {}
            prompt = m.get("prompt") or ""
            me = parts.get(r["speaker"], {})
            rows.append({**base, "analyzed": bool(an), "text_stance": an.get("stance"), "analyzer_move": an.get("move"),
                         "n_targets": len(targets), **{f"rel_{k}": v for k, v in rel.items()},
                         "n_addressed": len(an.get("addressed") or []), "n_concessions_text": len(an.get("concessions") or []),
                         "n_undermined": len(an.get("undermined") or []),
                         "moves": json.dumps([{"l": mv.get("listener"), "by": mv.get("by"), "d": mv.get("delta"), "k": mv.get("kind") or "persuasion"} for mv in moves]),
                         "n_move_persuasion": sum(1 for mv in moves if not mv.get("kind")),
                         "n_move_concession": sum(1 for mv in moves if mv.get("kind") == "concession"),
                         "n_move_pressure": sum(1 for mv in moves if mv.get("kind") == "pressure"),
                         "n_move_switch": sum(1 for mv in moves if mv.get("kind") == "switch"),
                         "switch_listeners": json.dumps([mv.get("listener") for mv in moves if mv.get("kind") == "switch"]),
                         "stances": json.dumps(stances), "x_self": stances.get(r["speaker"]),
                         "spread": float(np.std(list(stances.values()))) if stances else np.nan,
                         "n_open_challenges": len(st.get("challenges") or []),
                         "challenges": json.dumps([(c.get("challenger"), c.get("target"), c.get("seq"), c.get("kind")) for c in (st.get("challenges") or [])]),
                         "n_switched": sum(1 for p in parts.values() if p.get("switched")),
                         "switched": json.dumps({n: bool(p.get("switched")) for n, p in parts.items()}),
                         "my_pressure": me.get("pressure_applied"), "my_grounds": len(me.get("grounds") or []),
                         "my_commitments": len(me.get("commitments") or []), "my_stubbornness": me.get("stubbornness"),
                         "devils_advocate_used": bool(deb.get("devils_advocate_used")), "has_prompt": bool(prompt),
                         **{f"note_{k}": prompt.count(v) for k, v in NOTES.items()}})
    return pd.DataFrame(rows)


# ---------------- N6 ① 지시 ----------------

def n6_instructed(utt: pd.DataFrame, n_boot: int, seed: int) -> Dict[str, Any]:
    """실행당 장치 지시 수 (연구 × 모드). 트리거형 행위 / 스케줄형 행위 / 모더레이터 중재 / 안내 문자열 / 이동 종류 / 반박 생성·해소 / θ 도달.
    재표집: 블록"""
    rng = np.random.default_rng(seed)
    out = {}
    ai = utt[utt["speaker_type"] != "moderator"]
    mod = utt[utt["speaker_type"] == "moderator"]
    for (study, mode), g in ai.groupby(["study", "mode"]):
        if study == "a1r":
            g = g[g["topic_key"].map(a1r_set).eq("groups")]
        per_run = []
        for d, r in g.groupby("discussion_id"):
            created = set()
            for cj in r["challenges"]:
                created.update(tuple(c) for c in json.loads(cj))
            last = r.sort_values("seq").iloc[-1]
            open_end = len(json.loads(last["challenges"]))
            row = {"discussion_id": d, "block": r["block"].iloc[0], "n_utt": len(r), "n_analyzed": int(r["analyzed"].sum())}
            for a in TRIGGER_ACTIONS + SCHEDULED_ACTIONS + ["position", "closing", "reply"]:
                row[f"act_{a}"] = int((r["action"] == a).sum())
            row["mod_mediation"] = int(((mod["discussion_id"] == d) & (mod["action"] == "mediation")).sum())
            for k in NOTES:
                row[f"note_{k}"] = int(r[f"note_{k}"].sum())
            for k in ("persuasion", "concession", "pressure", "switch"):
                row[f"move_{k}"] = int(r[f"n_move_{k}"].sum())
            row["challenges_created"] = len(created)
            row["challenges_open_end"] = open_end
            row["challenge_resolution"] = 1 - open_end / len(created) if created else np.nan
            row["theta_reached"] = int(last["n_switched"])
            row["devils_advocate_used"] = float(last["devils_advocate_used"])
            per_run.append(row)
        t = pd.DataFrame(per_run)
        cols = [c for c in t.columns if c not in ("discussion_id", "block")]
        blocks = t["block"].to_numpy()
        ub = np.unique(blocks)
        pos = {b: np.flatnonzero(blocks == b) for b in ub}
        p = {c: float(t[c].mean()) for c in cols}
        draws = [{c: float(t[c].iloc[np.concatenate([pos[b] for b in _resample(ub, rng)])].mean()) for c in cols} for _ in range(n_boot)]
        out[f"{study}/{mode}"] = {c: _summ(p[c], [d[c] for d in draws]) for c in cols} | {"n_runs": int(len(t)), "n_blocks": int(len(ub)), "resample": "block"}
        out[f"{study}/{mode}"]["share_runs_with_any_switch"] = _summ(float((t["move_switch"] > 0).mean()),
                                                                     [float((t["move_switch"].iloc[np.concatenate([pos[b] for b in _resample(ub, rng)])] > 0).mean()) for _ in range(n_boot)])
    return out


# ---------------- N6 ③ 장치 뒤 변화 (연관) ----------------

def _own_prev_next(r: pd.DataFrame, speaker: str, seq: int):
    own = r[(r["speaker"] == speaker) & r["text_stance"].notna()].sort_values("seq")
    prev = own[own["seq"] < seq]
    nxt = own[own["seq"] > seq]
    return (prev.iloc[-1] if len(prev) else None), (nxt.iloc[0] if len(nxt) else None)


def n6_after_device(utt: pd.DataFrame, n_boot: int, seed: int, window: int = 3) -> Dict[str, Any]:
    """상태 기반 실행에서 장치 발언 뒤의 변화. 모두 연관이며 인과가 아니다(계획 5절).
    - 응답 의무: 직전 스냅숏에서 발언자를 겨냥한 열린 반박이 이 발언 뒤 사라진 비율; 분석기 판정에서 도전자를 겨냥한 관계가 있는 비율(보조)
    - 반대 검토·중재/제3안: 발언 시점 대 window 발언 뒤의 입장값 분산·열린 반박 수 변화, 같은 실행의 임의 시점 대비"""
    rng = np.random.default_rng(seed)
    ai = utt[(utt["speaker_type"] != "moderator") & (utt["mode"] == "stateful")]
    out = {}
    for study, g in ai.groupby("study"):
        if study == "a1r":
            g = g[g["topic_key"].map(a1r_set).eq("groups")]
        ev = {"respond_challenge": [], "devils_advocate": [], "mediation": [], "random": []}
        for d, r in g.groupby("discussion_id"):
            r = r.sort_values("seq").reset_index(drop=True)
            spreads = r["spread"].to_numpy()
            opens = r["n_open_challenges"].to_numpy()
            for i, row in r.iterrows():
                if row["action"] == "respond_challenge" and i > 0:
                    prev_ch = [c for c in json.loads(r.iloc[i - 1]["challenges"]) if c[1] == row["speaker"]]
                    now_ch = set(tuple(c) for c in json.loads(row["challenges"]))
                    if prev_ch:
                        resolved = np.mean([tuple(c) not in now_ch for c in prev_ch])
                        challengers = {c[0] for c in prev_ch}
                        ev["respond_challenge"].append({"block": row["block"], "resolved": float(resolved),
                                                        "addressed_challenger_in_analysis": float(row["n_targets"] > 0 and row["rel_attack"] + row["rel_concede"] + row["rel_support"] + row["rel_question"] > 0)})
                if i + window < len(r):
                    rec = {"block": row["block"], "d_spread": float(spreads[i + window] - spreads[i]), "d_open": float(opens[i + window] - opens[i])}
                    if row["action"] == "devils_advocate":
                        ev["devils_advocate"].append(rec)
                    elif row["action"] in ("mediate", "third_option"):
                        ev["mediation"].append(rec)
                    elif row["action"] in ("rebut", "undercut", "agree_extend", "example", "position"):
                        ev["random"].append(rec)
        res = {}
        for name, lst in ev.items():
            if not lst:
                continue
            t = pd.DataFrame(lst)
            blocks = t["block"].to_numpy()
            ub = np.unique(blocks)
            pos = {b: np.flatnonzero(blocks == b) for b in ub}
            cols = [c for c in t.columns if c != "block"]
            p = {c: float(t[c].mean()) for c in cols}
            draws = [{c: float(t[c].iloc[np.concatenate([pos[b] for b in _resample(ub, rng)])].mean()) for c in cols} for _ in range(n_boot)]
            res[name] = {c: _summ(p[c], [d[c] for d in draws]) for c in cols} | {"n_events": int(len(t)), "n_blocks": int(len(ub)), "resample": "block"}
        out[study] = res
    out["window"] = window
    return out


# ---------------- N7 ----------------

def n7_engine_vs_text_vs_survey(utt: pd.DataFrame, surveys: pd.DataFrame, n_boot: int, seed: int) -> Dict[str, Any]:
    """참가자 × 실행: 엔진 최종 x, 마지막 자기 발언의 텍스트 입장(분석기), 사후 설문(척도 변환). 모드별 상관과 평균 절대 차.
    실행 안 발언 수준: x 대 텍스트 입장의 상관(실행별 평균). 전환 사건: 전환 전후 텍스트 입장·엔진 x·설문. 재표집: 블록. 1-B만 (1-A는 카드 선택이라 입장값 비교 불가)"""
    rng = np.random.default_rng(seed)
    ai = utt[(utt["speaker_type"] != "moderator") & (utt["study"] == "a1r") & utt["topic_key"].map(a1r_set).eq("groups")]
    pp = _post_pre(surveys[(surveys["study"] == "a1r")])
    post = pp.dropna(subset=["post"]).set_index(["discussion_id", "participant"])
    rows, within, switch_rows = [], [], []
    for d, r in ai.groupby("discussion_id"):
        r = r.sort_values("seq").reset_index(drop=True)
        last = json.loads(r.iloc[-1]["stances"])
        mode, block = r["mode"].iloc[0], r["block"].iloc[0]
        first_x = json.loads(r.iloc[0]["stances"])
        for name, x_final in last.items():
            own = r[(r["speaker"] == name) & r["text_stance"].notna()]
            if (d, name) not in post.index or len(own) == 0:
                continue
            s = post.loc[(d, name)]
            rows.append({"block": block, "mode": mode, "x_final": x_final, "x0": first_x.get(name), "text_final": float(own.iloc[-1]["text_stance"]),
                         "post_x": _survey_x(float(s["post"])), "pre_x": _survey_x(float(s["pre"])) if not np.isnan(s["pre"]) else np.nan,
                         "switched": bool(json.loads(r.iloc[-1]["switched"]).get(name, False))})
            xs = [json.loads(sj).get(name) for sj in own["stances"]]
            ts = own["text_stance"].to_numpy(float)
            if len(own) >= 3 and np.std(xs) > 0 and np.std(ts) > 0:
                within.append({"block": block, "mode": mode, "corr_x_text": float(np.corrcoef(xs, ts)[0, 1])})
        if mode == "stateful":
            for i, row in r.iterrows():
                for name in json.loads(row["switch_listeners"]):
                    prev, nxt = _own_prev_next(r, name, int(row["seq"]))
                    mv = [m for m in json.loads(row["moves"]) if m["k"] == "switch" and m["l"] == name]
                    if prev is None or nxt is None or not mv:
                        continue
                    others = [n for n in last if n != name]
                    other_deltas = []
                    for o in others:
                        po, no = _own_prev_next(r, o, int(row["seq"]))
                        if po is not None and no is not None:
                            other_deltas.append(float(no["text_stance"] - po["text_stance"]) * np.sign(mv[0]["d"]))
                    switch_rows.append({"block": block, "engine_delta": float(mv[0]["d"]), "text_before": float(prev["text_stance"]), "text_after": float(nxt["text_stance"]),
                                        "text_delta_signed": float(nxt["text_stance"] - prev["text_stance"]) * np.sign(mv[0]["d"]),
                                        "others_text_delta_signed": float(np.mean(other_deltas)) if other_deltas else np.nan,
                                        "post_x": _survey_x(float(post.loc[(d, name)]["post"])) if (d, name) in post.index else np.nan,
                                        "x_final": last.get(name), "seq_frac": float(i / max(len(r) - 1, 1))})
    t = pd.DataFrame(rows)
    w = pd.DataFrame(within)
    sw = pd.DataFrame(switch_rows)
    out = {"participants": {}, "within_run_corr_x_text": {}, "switch_events": {}}
    for mode, g in t.groupby("mode"):
        blocks = g["block"].to_numpy()
        ub = np.unique(blocks)
        pos = {b: np.flatnonzero(blocks == b) for b in ub}

        def stats(f):
            dx = f["x_final"] - f["x0"]
            dp = f["post_x"] - f["pre_x"]
            return {"corr_xfinal_post": float(f["x_final"].corr(f["post_x"])), "corr_textfinal_post": float(f["text_final"].corr(f["post_x"])),
                    "corr_xfinal_textfinal": float(f["x_final"].corr(f["text_final"])),
                    "corr_change_x_vs_change_post": float(dx.corr(dp)), "mean_abs_xfinal_minus_post": float((f["x_final"] - f["post_x"]).abs().mean()),
                    "mean_abs_textfinal_minus_post": float((f["text_final"] - f["post_x"]).abs().mean()),
                    "mean_abs_xfinal_minus_textfinal": float((f["x_final"] - f["text_final"]).abs().mean())}
        p = stats(g)
        draws = [stats(g.iloc[np.concatenate([pos[b] for b in _resample(ub, rng)])]) for _ in range(n_boot)]
        out["participants"][mode] = {k: _summ(p[k], [d[k] for d in draws]) for k in p} | {"n": int(len(g)), "n_blocks": int(len(ub)), "resample": "block",
                                                                                         "scale": "survey (score−5)/5 to match engine x in [-1,1]"}
    for mode, g in (w.groupby("mode") if len(w) else []):
        blocks = g["block"].to_numpy()
        ub = np.unique(blocks)
        pos = {b: np.flatnonzero(blocks == b) for b in ub}
        p = float(g["corr_x_text"].mean())
        draws = [float(g["corr_x_text"].iloc[np.concatenate([pos[b] for b in _resample(ub, rng)])].mean()) for _ in range(n_boot)]
        out["within_run_corr_x_text"][mode] = _summ(p, draws, len(g), "block")
    if len(sw):
        blocks = sw["block"].to_numpy()
        ub = np.unique(blocks)
        pos = {b: np.flatnonzero(blocks == b) for b in ub}
        cols = ["engine_delta", "text_delta_signed", "others_text_delta_signed", "post_x", "x_final"]

        def sstats(f):
            return {c: float(np.nanmean(f[c])) for c in cols} | {
                "share_text_moved_same_direction_ge_0.2": float((f["text_delta_signed"] >= 0.2).mean()),
                "share_text_moved_opposite": float((f["text_delta_signed"] < 0).mean()),
                "corr_xfinal_post_switchers": float(f["x_final"].corr(f["post_x"]))}
        p = sstats(sw)
        draws = [sstats(sw.iloc[np.concatenate([pos[b] for b in _resample(ub, rng)])]) for _ in range(n_boot)]
        out["switch_events"] = {k: _summ(p[k], [d[k] for d in draws]) for k in p} | {"n_events": int(len(sw)), "n_blocks": int(len(ub)), "resample": "block",
                                                                                    "note": "text_delta_signed = (text after − text before) × sign(engine switch); others = same window, same run"}
    return out, t, sw


# ---------------- S5 합의 시점 ----------------

def s5_consensus_timing(utt: pd.DataFrame, n_boot: int, seed: int, threshold: float = CONSENSUS_SPREAD) -> Dict[str, Any]:
    """실행별: 입장값 분산(표준편차)이 처음으로 threshold 아래로 가는 발언 순번(정규화 0~1, 없으면 결측), 시작·끝 분산, 모드별. 1-B·1-A"""
    rng = np.random.default_rng(seed)
    ai = utt[(utt["speaker_type"] != "moderator")]
    out = {}
    for (study, mode), g in ai.groupby(["study", "mode"]):
        if study == "a1r":
            g = g[g["topic_key"].map(a1r_set).eq("groups")]
        rows = []
        for d, r in g.groupby("discussion_id"):
            r = r.sort_values("seq")
            n_st = r["stances"].map(lambda j: len(json.loads(j)))
            r = r[n_st == n_st.max()]  # 전원이 입장값을 가진 스냅숏만 (1-A는 발언 전 입장값이 없음)
            sp = r["spread"].to_numpy()
            if len(sp) == 0 or np.isnan(sp).all():
                continue
            below = np.flatnonzero(sp < threshold)
            rows.append({"block": r["block"].iloc[0], "spread_start": float(sp[0]), "spread_end": float(sp[-1]),
                         "reached": float(len(below) > 0), "t_first_below": float(below[0] / max(len(sp) - 1, 1)) if len(below) else np.nan,
                         "spread_mid": float(sp[len(sp) // 2])})
        t = pd.DataFrame(rows)
        blocks = t["block"].to_numpy()
        ub = np.unique(blocks)
        pos = {b: np.flatnonzero(blocks == b) for b in ub}
        cols = ["spread_start", "spread_mid", "spread_end", "reached", "t_first_below"]
        p = {c: float(np.nanmean(t[c])) for c in cols}
        draws = [{c: float(np.nanmean(t[c].iloc[np.concatenate([pos[b] for b in _resample(ub, rng)])])) for c in cols} for _ in range(n_boot)]
        out[f"{study}/{mode}"] = {c: _summ(p[c], [d[c] for d in draws]) for c in cols} | {"n_runs": int(len(t)), "threshold": threshold, "resample": "block",
                                                                                          "note": "engine stance values x (analyzer-updated in both modes; baseline shows no directives); only snapshots where all participants have x (1-A: after everyone spoke once)"}
    return out


# ---------------- S3 소수 의견자 ----------------

DIST_BINS = [(0, 1), (1, 3), (3, 5), (5, 11)]


def _minority_rows(frame: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = []
    for g_id, g in frame.groupby(group_col):
        pre = g["pre"].to_numpy(float)
        post = g["post"].to_numpy(float)
        n = len(g)
        if n < 3:
            continue
        for i in range(n):
            others = (pre.sum() - pre[i]) / (n - 1)
            dist = pre[i] - others
            toward = (post[i] - pre[i]) * np.sign(others - pre[i]) if dist != 0 else np.nan
            rows.append({"unit": g_id, "abs_dist": abs(dist), "toward": toward, "abs_move": abs(post[i] - pre[i]),
                         "moved_toward": float(toward > 0) if not np.isnan(toward) else np.nan})
    return pd.DataFrame(rows)


def s3_minority(agents: pd.DataFrame, delib: pd.DataFrame, n_boot: int, seed: int) -> Dict[str, Any]:
    """구성원의 사전 점수가 나머지 평균에서 먼 정도(|거리|)별로 상대 쪽 이동량·이동 비율. AI 조건별(블록 재표집), 인간 소집단(소집단 재표집)"""
    rng = np.random.default_rng(seed)
    out = {"bins": [f"{a}-{b}" for a, b in DIST_BINS], "ai": {}, "human": {}}

    def summarize(t: pd.DataFrame, unit_col: str):
        units = t[unit_col].to_numpy()
        uu = np.unique(units)
        pos = {u: np.flatnonzero(units == u) for u in uu}

        def stats(f):
            res = {}
            for a, b in DIST_BINS:
                sub = f[(f["abs_dist"] >= a) & (f["abs_dist"] < b)]
                res[f"toward_{a}-{b}"] = float(np.nanmean(sub["toward"])) if len(sub) else np.nan
                res[f"share_toward_{a}-{b}"] = float(np.nanmean(sub["moved_toward"])) if len(sub) else np.nan
                res[f"n_{a}-{b}"] = int(len(sub))
            ok = f["toward"].notna()
            res["slope_toward_per_dist"] = float(np.polyfit(f.loc[ok, "abs_dist"], f.loc[ok, "toward"], 1)[0]) if ok.sum() > 10 else np.nan
            return res
        p = stats(t)
        draws = [stats(t.iloc[np.concatenate([pos[u] for u in _resample(uu, rng)])]) for _ in range(n_boot)]
        return {k: (_summ(p[k], [d[k] for d in draws]) if not isinstance(p[k], int) else p[k]) for k in p} | {"n_units": int(len(uu))}

    for lab in ("A-baseline", "A-stateful", "B-materials", "C-reanswer"):
        a = agents[agents["label"] == lab].dropna(subset=["pre", "post"])
        t = _minority_rows(a.assign(unit=a["discussion_id"]), "unit")
        out["ai"][lab] = summarize(t, "unit")
    h = delib.assign(unit=delib["group"].astype(str) + "|" + delib["item"])
    th = _minority_rows(h, "unit")
    th["group"] = th["unit"].str.split("|").str[0]
    out["human"]["delib_small_group"] = summarize(th, "group")
    return out


# ---------------- E2 상태 기반 단독 실패 집단의 과정 ----------------

def e2_failure_process(utt: pd.DataFrame, wruns: pd.DataFrame) -> Dict[str, Any]:
    """1-A 상태 기반 실행을 (기준선 3회 모두 과반 정답 & 상태 기반 과반 오답) 집단과 (k=0 이면서 상태 기반 과반 정답) 집단으로 나눠 과정 지표 비교"""
    base_all = wruns[wruns["label"] == "A-baseline"].groupby("block")["majority_correct"].apply(lambda s: float(s.min() == 1))
    st = wruns[wruns["label"] == "A-stateful"].set_index("block")
    fail = set(st.index[(st["majority_correct"] == 0) & base_all.reindex(st.index).fillna(0).eq(1)])
    succ_k0 = set(st.index[(st["majority_correct"] == 1) & (st["k"] == "0")])
    ai = utt[(utt["speaker_type"] != "moderator") & (utt["study"] == "wason") & (utt["mode"] == "stateful") & utt["topic_key"].str.startswith("deli-")]
    rows = []
    for d, r in ai.groupby("discussion_id"):
        b = r["topic_key"].iloc[0]
        grp = "stateful_only_failure" if b in fail else ("k0_stateful_success" if b in succ_k0 else "other")
        last = r.sort_values("seq").iloc[-1]
        rows.append({"group": grp, "n_switch": int(r["n_move_switch"].sum()), "any_switch": float(r["n_move_switch"].sum() > 0),
                     "n_respond_challenge": int((r["action"] == "respond_challenge").sum()), "n_mediation": int(r["action"].isin(["mediate", "third_option"]).sum()),
                     "devils_advocate": float(last["devils_advocate_used"]), "theta_reached": int(last["n_switched"]),
                     "spread_end": float(last["spread"]), "n_concession_moves": int(r["n_move_concession"].sum()), "n_pressure_moves": int(r["n_move_pressure"].sum())})
    t = pd.DataFrame(rows)
    return {g: {c: float(v) for c, v in d.mean(numeric_only=True).items()} | {"n_runs": int(len(d))} for g, d in t.groupby("group")}


# ---------------- N8 장치 발생량–결과 연관 (부록) ----------------

def n8_association(utt: pd.DataFrame, blocks: pd.DataFrame, wruns: pd.DataFrame) -> Dict[str, Any]:
    """상태 기반 실행 안에서 결과 ~ 장치 수 + 사전 조건 + (1|문항/카드세트). 연관이며 인과가 아니다(되먹임·역인과)"""
    ai = utt[(utt["speaker_type"] != "moderator") & (utt["mode"] == "stateful")]
    counts = ai.groupby("discussion_id").agg(n_rc=("action", lambda s: int((s == "respond_challenge").sum())),
                                              n_med=("action", lambda s: int(s.isin(["mediate", "third_option"]).sum())),
                                              n_switch=("n_move_switch", "sum"), n_conc=("n_move_concession", "sum"),
                                              da=("devils_advocate_used", lambda x: float(x.max())), block=("block", "first"), study=("study", "first"))
    out = {}
    b = blocks[blocks["label"] == "A-stateful"].copy()
    key = ai[ai["study"] == "a1r"].drop_duplicates("discussion_id").set_index("topic_key")["discussion_id"]
    b["discussion_id"] = b["block"].map(key)
    b = b.join(counts.drop(columns=["block", "study"]), on="discussion_id").dropna(subset=["n_rc"])
    for ycol in ("sd_drop", "consensus_sd", "gap_change"):
        f = b[[ycol, "n_rc", "n_med", "n_switch", "n_conc", "da", "sd_pre", "item"]].rename(columns={ycol: "y"}).dropna()
        r = _fit(f, "y ~ n_rc + n_med + n_switch + n_conc + da + sd_pre + (1 | item)", ["n_rc", "n_med", "n_switch", "n_conc", "da", "sd_pre"], ["item"])
        out[f"1-B {ycol}"] = {k: {kk: v[kk] for kk in ("estimate", "ci", "p")} for k, v in r.items()} | {"n": int(len(f))}
    w = wruns[wruns["label"] == "A-stateful"].set_index("discussion_id").join(counts.drop(columns=["block", "study"]), how="inner")
    w["k_raw"] = w["k_raw"].astype(float)
    f = w[["acc", "n_rc", "n_med", "n_switch", "n_conc", "da", "k_raw", "size", "card_set"]].dropna()
    r = _fit(f, "acc ~ n_rc + n_med + n_switch + n_conc + da + k_raw + size + (1 | card_set)", ["n_rc", "n_med", "n_switch", "n_conc", "da", "k_raw"], ["card_set"])
    out["1-A acc"] = {k: {kk: v[kk] for kk in ("estimate", "ci", "p")} for k, v in r.items()} | {"n": int(len(f))}
    out["note"] = "association only: device counts respond to the discussion state (feedback), so coefficients are not causal effects"
    return out
