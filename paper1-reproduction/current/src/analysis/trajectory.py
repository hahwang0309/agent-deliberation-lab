"""
탐색 분석 C단계 (study1-exploratory-plan.md 7절): 1-A 와슨 과제의 답 변경 궤적과 오답 유형. [탐색]

- N9  누가 언제 답을 바꾸나: 사람은 DeliData `sol_tracker_all`(메시지마다 전원의 현재 답), AI는 발언 텍스트에서 카드 선택을 정규식으로 추출.
      변경 시점(정규화 0~1), 방향(오→정, 정→오, 오→오), 초기 정답자의 유지율·초기 오답자의 전환율(설문 기준).
- E1  틀린 합의의 답 유형(카드 역할 조합), 사람 대 AI, 심은 오답과의 일치
- E3  k=1 집단: 최종 과반 답이 처음 정답자의 답과 같은 비율 (truth wins 의 과정판)
- S7  새 변형 과제의 오답 유형, 원 과제 대 비교; 발언에서 "Wason" 언급 비율(오염 지표)
카드 역할: P=모음(전건), notP=자음, Q=짝수(후건), notQ=홀수. 정답 = P+notQ.
"""
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.analysis.exploratory import _ci, _resample, _summ
from src.cases import wason

ROLE_ORDER = ("P", "notP", "Q", "notQ")
VERB = r"(?:turn(?:ing)?(?: over)?|flip(?:ping)?(?: over)?|check(?:ing)?|pick(?:ing)?|select(?:ing)?|choos(?:e|ing)|examin(?:e|ing)|look(?:ing)? at|test(?:ing)?)"


def pattern_of(cards: List[str], roles: Optional[Dict[str, str]] = None) -> str:
    """카드 집합 → 역할 조합 문자열 (예: 'P+Q'). roles = {카드: 역할} (새 변형 과제의 meta.roles 를 뒤집은 것); 없으면 원 과제 규칙(모음/짝수)"""
    role = (lambda c: roles.get(c, roles.get(c.lower(), "?"))) if roles else wason.card_role
    return "+".join(sorted({role(c) for c in cards}, key=lambda r: ROLE_ORDER.index(r) if r in ROLE_ORDER else 9)) or "none"


def roles_of(topic: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """plan 주제의 카드 → 역할 매핑 (새 변형만; 원 과제는 None)"""
    r = (topic.get("meta") or {}).get("roles")
    return {str(card).upper(): role for role, card in r.items()} if r else None


# ---------------- 사람: DeliData 궤적 ----------------

def human_trajectories(directory: str, blocks: Optional[set] = None, members_keep: Optional[set] = None) -> pd.DataFrame:
    """참가자 × 변경 사건 1행 (+ 참가자당 요약). 집단 필터는 humans.delidata_groups 와 같고,
    members_keep = {(block, member)} 가 주어지면 그 참가자만(혼자 답과 최종 제출이 모두 있는 사람) 센다.
    반환 열: block, member, k, n_rows, event_index, t, from_pattern, to_pattern, from_correct, to_correct"""
    rows, summary = [], []
    for path in sorted(Path(directory).glob("*.tsv")):
        if path.name == "sample.tsv":
            continue
        with path.open(encoding="utf-8") as f:
            data = list(csv.DictReader(f, delimiter="\t"))
        init = next((r for r in data if r["message_type"] == "INITIAL"), None)
        if init is None:
            continue
        block = f"deli-{init['group_id'][:8]}"
        if blocks is not None and block not in blocks:
            continue
        cards = [c.strip().upper() for c in init["original_text"].split("&&")[1].split(",")]
        corr = set(wason.correct_cards(cards))
        seq_rows = [r for r in data if r["message_type"] in ("MESSAGE", "SUBMIT")]
        n = len(seq_rows)
        prev = {m: wason._valid(sel, cards) for m, sel in json.loads(init["sol_tracker_all"] or "{}").items()}
        members = [m for m, v in prev.items() if v is not None]
        if len(members) < 2 or any(prev[m] is None for m in prev):
            continue
        if sorted(wason.card_role(c) for c in cards) != sorted(wason.ROLES):
            continue
        k = sum(set(v) == corr for v in prev.values())
        if members_keep is not None:
            members = [m for m in members if (block, m) in members_keep]
            if len(members) < 2:
                continue
        changes = {m: 0 for m in members}
        for i, r in enumerate(seq_rows):
            cur = json.loads(r["sol_tracker_all"] or "{}")
            for m in members:
                sel = wason._valid(cur.get(m, []), cards) if m in cur else None
                if sel is None or set(sel) == set(prev[m]):
                    continue
                rows.append({"block": block, "member": m, "k": k, "n_rows": n, "event_index": i, "t": i / max(n - 1, 1),
                             "from_pattern": pattern_of(prev[m]), "to_pattern": pattern_of(sel),
                             "from_correct": int(set(prev[m]) == corr), "to_correct": int(set(sel) == corr)})
                changes[m] += 1
                prev[m] = sel
        for m in members:
            summary.append({"block": block, "member": m, "k": k, "n_changes": changes[m], "final_correct": int(set(prev[m]) == corr)})
    return pd.DataFrame(rows), pd.DataFrame(summary)


# ---------------- AI: 발언에서 카드 선택 추출 ----------------

SEP = r"\s*(?:,\s*(?:and|&|or)?|and|&|\+|/|or)\s*"
NEG = re.compile(r"(?:\bnot\b|n't|\bno need\b|\bneedn't\b|\bwithout\b|\brather than\b|\binstead of\b|\bavoid\b|\bskip\b|\bleave\b)[^.;]{0,25}$", re.IGNORECASE)


def _card_regex(options: List[str]) -> re.Pattern:
    toks = "|".join(re.escape(o) for o in sorted(options, key=len, reverse=True))
    item = rf"(?:the\s+)?(?:card\s+)?(?:{toks})"
    seq = rf"{item}(?:{SEP}{item})*"
    return re.compile(rf"(?:{VERB})\s+(?:over\s+)?(?:only\s+|just\s+|both\s+|all\s+(?:three|four)\s+)?(?:the\s+)?(?:cards?\s+)?({seq})(?![A-Za-z0-9])", re.IGNORECASE)


def _summary_regex(options: List[str]) -> re.Pattern:
    toks = "|".join(re.escape(o) for o in sorted(options, key=len, reverse=True))
    seq = rf"(?:{toks})(?:{SEP}(?:{toks}))*"
    return re.compile(rf"(?:(?:answer|choice|selection|picks?)\s*(?:is|are|:|would be|should be|remains)\s*(?:to\s+(?:turn|flip)\s+)?(?:only\s+|just\s+)?(?:the\s+)?(?:cards?\s+)?({seq})(?![A-Za-z0-9])"
                      rf"|\b({seq})\s+(?:are|is)\s+(?:the\s+)?(?:(?:only|two|three|four)\s+)?cards?\s+(?:to|that|we|you|I)"
                      rf"|cards?\s+to\s+(?:turn|flip)(?:\s+over)?\s+(?:are|is|:)\s*(?:only\s+)?({seq})(?![A-Za-z0-9]))", re.IGNORECASE)


def _tokens(s: str, options: List[str]) -> List[str]:
    toks = set(options)
    found = re.findall(r"[A-Za-z0-9]+", s)
    return [f.upper() for f in found if f.upper() in toks or f in toks]


def extract_choice(text: str, options: List[str]) -> Optional[Tuple[str, ...]]:
    """발언에서 '뒤집을 카드' 목록을 뽑는다.
    1) 요약형 문장("X and Y are the cards to turn", "answer is X, Y", "cards to turn are X")이 있으면 마지막 것
    2) 없으면 부정어("not turn", "no need to flip") 뒤가 아닌 동사+카드 목록을 모두 합집합. 못 찾으면 None"""
    text = text.replace("\u2014", " - ")
    summ = None
    for m in _summary_regex(options).finditer(text):
        grp = next((g for g in m.groups() if g), None)
        toks = _tokens(grp, options) if grp else []
        if toks:
            summ = tuple(sorted(set(toks)))
    if summ:
        return summ
    picked = set()
    for m in _card_regex(options).finditer(text):
        if NEG.search(text[max(0, m.start() - 40):m.start()]):
            continue
        picked.update(_tokens(m.group(1), options))
    return tuple(sorted(picked)) if picked else None


def ai_trajectories(utt: pd.DataFrame, surveys: pd.DataFrame, plans: Dict[str, Dict[str, dict]], db: str,
                    choices: Optional[Dict[Tuple[str, int], Optional[tuple]]] = None) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """AI 참가자 × 변경 사건 + 추출 품질(마지막 발언 추출 대 사후 설문 일치).
    choices가 주어지면(LLM 추출, scripts/extract_cards.py 출력) 그 값을 쓰고, 없으면 정규식 추출."""
    import sqlite3
    con = sqlite3.connect(db)
    a = utt[(utt["study"] == "wason") & (utt["speaker_type"] != "moderator") & utt["topic_key"].str.startswith("deli-")
            & (utt["label"].isin(["A-baseline", "A-stateful"])) & ((utt["label"] == "A-stateful") | (utt["replicate"] == 0))]
    post = surveys[(surveys["study"] == "wason") & (surveys["phase"] == "post")].set_index(["discussion_id", "participant"])["choices"]
    rows, summary, quality = [], [], []
    for d, r in a.groupby("discussion_id"):
        r = r.sort_values("seq")
        key, batch = r["topic_key"].iloc[0], None
        for b, topics in plans.items():
            if key in topics:
                batch = b
                break
        t = plans[batch][key]
        options = [o.upper() for o in t["survey"]["items"][0]["options"]]
        corr = set(c.upper() for c in t["survey"]["items"][0]["correct"])
        texts = dict(con.execute("select seq, content from messages where discussion_id=?", (d,)).fetchall())
        n = len(r)
        state = {p: tuple(sorted(c.upper() for c in v["cards"])) for p, v in t["seeds"].items()}
        k = sum(set(v) == corr for v in state.values())
        found = {p: 0 for p in state}
        changes = {p: 0 for p in state}
        last_extracted = {}
        for i, (_, row) in enumerate(r.iterrows()):
            p = row["speaker"]
            if choices is not None:
                sel = choices.get((d, int(row["seq"])))
            else:
                sel = extract_choice(texts.get(row["seq"], ""), options)
            if sel is None:
                continue
            found[p] += 1
            last_extracted[p] = sel
            if set(sel) != set(state.get(p, ())):
                rows.append({"discussion_id": d, "block": key, "label": row["label"], "member": p, "k": k, "n_rows": n, "event_index": i,
                             "t": i / max(n - 1, 1), "from_pattern": pattern_of(list(state[p])), "to_pattern": pattern_of(list(sel)),
                             "from_correct": int(set(state[p]) == corr), "to_correct": int(set(sel) == corr)})
                changes[p] += 1
                state[p] = sel
        for p in state:
            ch = post.get((d, p))
            final = tuple(sorted(x.upper() for x in json.loads(ch))) if isinstance(ch, str) and json.loads(ch) is not None else None
            summary.append({"discussion_id": d, "block": key, "label": r["label"].iloc[0], "member": p, "k": k, "n_changes": changes[p],
                            "n_utts": int((r["speaker"] == p).sum()), "n_extracted": found[p],
                            "final_correct": int(set(final) == corr) if final else np.nan, "seed_correct": int(set(t["seeds"][p]["cards"]) == corr)})
            if p in last_extracted and final is not None:
                quality.append({"label": r["label"].iloc[0], "match": float(set(last_extracted[p]) == set(final))})
    q = pd.DataFrame(quality)
    s = pd.DataFrame(summary)
    qual = {"source": "llm" if choices is not None else "regex", "share_utterances_with_extraction": float(s["n_extracted"].sum() / s["n_utts"].sum()) if len(s) else np.nan,
            "share_participants_with_any_extraction": float((s["n_extracted"] > 0).mean()) if len(s) else np.nan,
            "last_extraction_matches_survey": {lab: {"share": float(g["match"].mean()), "n": int(len(g))} for lab, g in q.groupby("label")} if len(q) else {}}
    return pd.DataFrame(rows), s, qual


# ---------------- N9 요약 ----------------

T_BINS = [(0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01)]


def n9_summary(events: pd.DataFrame, summary: pd.DataFrame, groups_col: str, n_boot: int, seed: int) -> Dict[str, Any]:
    """변경 사건의 시점 분포(사분위 구간), 방향 유형 비율, 참가자당 변경 수; 재표집: 집단"""
    rng = np.random.default_rng(seed)
    out = {}
    if len(events) == 0:
        return {"n_events": 0}
    ev = events.copy()
    ev["kind"] = np.select([(ev["from_correct"] == 0) & (ev["to_correct"] == 1), (ev["from_correct"] == 1) & (ev["to_correct"] == 0)],
                           ["wrong_to_correct", "correct_to_wrong"], "wrong_to_wrong")
    blocks = ev[groups_col].to_numpy()
    ub = np.unique(blocks)
    pos = {b: np.flatnonzero(blocks == b) for b in ub}
    sblocks = summary[groups_col].to_numpy()
    sub = np.unique(sblocks)
    spos = {b: np.flatnonzero(sblocks == b) for b in sub}

    def stats(e, s):
        res = {f"share_t_{a:.2f}-{b:.2f}": float(((e["t"] >= a) & (e["t"] < b)).mean()) for a, b in T_BINS}
        res.update({f"share_{k}": float((e["kind"] == k).mean()) for k in ("wrong_to_correct", "correct_to_wrong", "wrong_to_wrong")})
        res["mean_t"] = float(e["t"].mean())
        res["median_t"] = float(e["t"].median())
        res["changes_per_participant"] = float(s["n_changes"].mean())
        res["share_participants_changing"] = float((s["n_changes"] > 0).mean())
        return res
    p = stats(ev, summary)
    draws = [stats(ev.iloc[np.concatenate([pos[b] for b in _resample(ub, rng)])], summary.iloc[np.concatenate([spos[b] for b in _resample(sub, rng)])]) for _ in range(n_boot)]
    out = {k: _summ(p[k], [d[k] for d in draws]) for k in p} | {"n_events": int(len(ev)), "n_participants": int(len(summary)), "n_groups": int(len(ub)), "resample": groups_col}
    return out


def retention(summary: pd.DataFrame, groups_col: str, n_boot: int, seed: int) -> Dict[str, Any]:
    """초기 정답자가 끝까지 정답인 비율, 초기 오답자가 정답으로 끝나는 비율 (설문·최종 답 기준), k별"""
    rng = np.random.default_rng(seed)
    s = summary.dropna(subset=["final_correct"])
    blocks = s[groups_col].to_numpy()
    ub = np.unique(blocks)
    pos = {b: np.flatnonzero(blocks == b) for b in ub}

    def stats(f):
        res = {}
        for kk, sub in (("all", f), ("k1", f[f["k"] == 1]), ("k0", f[f["k"] == 0])):
            ic, iw = sub[sub["seed_correct"] == 1], sub[sub["seed_correct"] == 0]
            res[f"{kk}_initially_correct_stay_correct"] = float(ic["final_correct"].mean()) if len(ic) else np.nan
            res[f"{kk}_initially_wrong_end_correct"] = float(iw["final_correct"].mean()) if len(iw) else np.nan
        return res
    p = stats(s)
    draws = [stats(s.iloc[np.concatenate([pos[b] for b in _resample(ub, rng)])]) for _ in range(n_boot)]
    return {k: _summ(p[k], [d[k] for d in draws]) for k in p} | {"n": int(len(s)), "resample": groups_col}


# ---------------- E1 오답 유형, E3 정답자 설득 ----------------

def _majority(sets: List[tuple]) -> Optional[tuple]:
    if not sets:
        return None
    top, n = Counter(sets).most_common(1)[0]
    return top if n > len(sets) / 2 else None


def wrong_consensus_types(final_sets_by_group: Dict[str, Tuple[List[tuple], set, List[tuple]]], n_boot: int, seed: int) -> Dict[str, Any]:
    """집단 → (최종 답 집합 목록, 정답 집합, 심은/혼자 답 목록). 과반 오답인 집단의 답 유형 분포와 '초기 오답과 같음' 비율"""
    rng = np.random.default_rng(seed)
    rows = []
    for g, (finals, corr, seeds) in final_sets_by_group.items():
        maj = _majority(finals)
        if maj is None or set(maj) == corr:
            continue
        seed_list = list(seeds.values()) if isinstance(seeds, dict) else list(seeds)
        rows.append({"group": g, "pattern": pattern_of(list(maj)), "same_as_seed": float(pattern_of(list(maj)) in {pattern_of(list(s)) for s in seed_list}),
                     "unanimous": float(len(set(finals)) == 1)})
    t = pd.DataFrame(rows)
    if len(t) == 0:
        return {"n_wrong_majority_groups": 0}
    ub = t["group"].unique()
    pos = {b: np.flatnonzero(t["group"].to_numpy() == b) for b in ub}
    pats = ["P+Q", "P", "P+Q+notQ", "P+notP+Q+notQ", "P+notP", "P+notP+notQ", "notP+notQ"]

    def stats(f):
        return {f"share_{p}": float((f["pattern"] == p).mean()) for p in pats} | {"share_same_as_initial_wrong": float(f["same_as_seed"].mean()), "share_unanimous": float(f["unanimous"].mean())}
    p = stats(t)
    draws = [stats(t.iloc[np.concatenate([pos[b] for b in _resample(ub, rng)])]) for _ in range(n_boot)]
    return {k: _summ(p[k], [d[k] for d in draws]) for k in p} | {"n_wrong_majority_groups": int(len(t)), "counts": t["pattern"].value_counts().to_dict()}


def truth_wins_process(groups: Dict[str, Tuple[List[tuple], set, Dict[str, tuple]]], n_boot: int, seed: int) -> Dict[str, Any]:
    """k=1 집단: 최종 과반 답이 처음 정답자의 답(=정답)과 같은 비율, 과반이 다른 오답으로 간 비율, 과반 없음 비율. groups: 집단 → (최종 답 목록, 정답, {구성원: 초기 답})"""
    rng = np.random.default_rng(seed)
    rows = []
    for g, (finals, corr, initial) in groups.items():
        k = sum(set(v) == corr for v in initial.values())
        if k != 1:
            continue
        maj = _majority(finals)
        rows.append({"group": g, "majority_is_correct": float(maj is not None and set(maj) == corr), "no_majority": float(maj is None),
                     "majority_other_wrong": float(maj is not None and set(maj) != corr)})
    t = pd.DataFrame(rows)
    if len(t) == 0:
        return {"n_k1_groups": 0}
    ub = t["group"].unique()
    pos = {b: np.flatnonzero(t["group"].to_numpy() == b) for b in ub}
    cols = ["majority_is_correct", "no_majority", "majority_other_wrong"]
    p = {c: float(t[c].mean()) for c in cols}
    draws = [{c: float(t[c].iloc[np.concatenate([pos[b] for b in _resample(ub, rng)])].mean()) for c in cols} for _ in range(n_boot)]
    return {c: _summ(p[c], [d[c] for d in draws]) for c in cols} | {"n_k1_groups": int(len(t))}


def ai_group_sets(surveys: pd.DataFrame, plans: Dict[str, Dict[str, dict]], label: str, replicate: Optional[int] = None,
                  prefix: str = "deli-") -> Dict[str, Tuple[List[tuple], set, Dict[str, tuple]]]:
    """AI 실행 → (최종 답 목록, 정답, {참가자: 심은 답}). label 조건, replicate 지정 가능"""
    s = surveys[(surveys["study"] == "wason") & surveys["topic_key"].str.startswith(prefix) & (surveys["phase"] == "post") & (surveys["label"] == label)]
    if replicate is not None:
        s = s[s["replicate"] == replicate]
    out = {}
    for (d, key, batch), g in s.groupby(["discussion_id", "topic_key", "batch"]):
        t = plans[batch][key]
        corr = set(c.upper() for c in t["survey"]["items"][0]["correct"])
        finals = [tuple(sorted(x.upper() for x in json.loads(c))) for c in g["choices"] if isinstance(c, str) and json.loads(c) is not None]
        initial = {p: tuple(sorted(x.upper() for x in v["cards"])) for p, v in t["seeds"].items()}
        out[d] = (finals, corr, initial)
    return out


def human_group_sets(individuals: pd.DataFrame, directory: str) -> Dict[str, Tuple[List[tuple], set, Dict[str, tuple]]]:
    """humans.delidata_groups 출력 + 혼자 답 → 같은 구조"""
    solo = {}
    for g in wason.load_delidata(directory):
        solo[f"deli-{g.group_id[:8]}"] = (g.cards, {m: tuple(sorted(v)) for m, v in g.solo.items() if v is not None})
    out = {}
    for block, g in individuals.groupby("block"):
        cards, init = solo[block]
        corr = set(wason.correct_cards(cards))
        out[block] = ([tuple(sorted(f)) for f in g["final"]], corr, {m: init[m] for m in g["member"] if m in init})
    return out


# ---------------- S7 새 변형 ----------------

def s7_variants(surveys: pd.DataFrame, plans: Dict[str, Dict[str, dict]], utt: pd.DataFrame, db: str) -> Dict[str, Any]:
    """새 변형(60문항) 대 원 과제: 모드별 과반 오답 유형 분포, 개인 오답 유형 분포; 발언에서 'Wason' 언급 비율(오염 지표)"""
    import sqlite3
    out = {}
    for prefix, name in (("deli-", "original"), ("variant-", "variant")):
        for label in ("A-baseline", "A-stateful"):
            grp = ai_group_sets(surveys, plans, label, replicate=0 if label == "A-baseline" else None, prefix=prefix)
            topic_roles = {}
            for b, topics in plans.items():
                for key, tp in topics.items():
                    topic_roles[key] = roles_of(tp)
            keys = surveys.drop_duplicates("discussion_id").set_index("discussion_id")["topic_key"]
            indiv = Counter()
            maj_wrong = Counter()
            n_groups = 0
            for d, (finals, corr, _) in grp.items():
                roles = topic_roles.get(keys.get(d))
                n_groups += 1
                for f in finals:
                    if set(f) != corr:
                        indiv[pattern_of(list(f), roles)] += 1
                maj = _majority(finals)
                if maj is not None and set(maj) != corr:
                    maj_wrong[pattern_of(list(maj), roles)] += 1
            tot = sum(indiv.values())
            out[f"{name}/{label}"] = {"n_groups": n_groups, "n_wrong_individuals": tot,
                                     "individual_wrong_patterns": {k: round(v / tot, 3) for k, v in indiv.most_common(6)} if tot else {},
                                     "majority_wrong_groups": sum(maj_wrong.values()), "majority_wrong_patterns": dict(maj_wrong.most_common(6))}
    con = sqlite3.connect(db)
    a = utt[(utt["study"] == "wason") & (utt["speaker_type"] != "moderator")]
    mention = {}
    for prefix, name in (("deli-", "original"), ("variant-", "variant")):
        ids = a[a["topic_key"].str.startswith(prefix)]["discussion_id"].unique().tolist()
        n_utt, n_hit, runs_hit = 0, 0, 0
        for d in ids:
            hits = 0
            for (content,) in con.execute("select content from messages where discussion_id=? and speaker_type!='moderator'", (d,)):
                n_utt += 1
                if re.search(r"\bWason\b|selection task", content, re.IGNORECASE):
                    n_hit += 1
                    hits += 1
            runs_hit += hits > 0
        mention[name] = {"share_utterances_mentioning_wason": n_hit / n_utt if n_utt else np.nan, "share_runs_mentioning": runs_hit / len(ids) if ids else np.nan, "n_runs": len(ids)}
    out["wason_mentions"] = mention
    return out


def load_llm_choices(path: str) -> Dict[Tuple[str, int], Optional[tuple]]:
    """scripts/extract_cards.py 출력 → {(discussion_id, seq): 카드 튜플 또는 None}"""
    t = pd.read_csv(path)
    out = {}
    for d, seq, c in zip(t["discussion_id"], t["seq"], t["cards"]):
        if isinstance(c, str) and c != "null":
            vals = json.loads(c)
            out[(d, int(seq))] = tuple(sorted(v.upper() for v in vals)) if vals else None
        else:
            out[(d, int(seq))] = None
    return out
