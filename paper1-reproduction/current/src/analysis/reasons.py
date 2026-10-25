"""
D단계 S6: 1-B 사후 설문의 이유(reason) 텍스트에서 동료 이름·자료·토론 언급을 어휘 기반으로 센다 (층 3 선행 지표).

- 단위: 에이전트 1명의 사후 이유 (조건 A-기준선·A-상태·B-자료·C-재응답·D-기본). 블록 재표집.
- 동료 언급: 같은 토론의 다른 참가자 이름(단어 경계, 대소문자 구분). 자기 이름은 제외. B·C·D는 동료가 없으므로 이름 목록이 비어 0.
- 자료 언급: 고정 어휘(briefing, materials, the box, arguments for/against 등). 토론 언급: discussion, conversation, others, raised, persuad 등.
- 어휘 일치이므로 "언급"일 뿐 "근거로 삼음"이 아니다(층 3이 판정).
"""
import re
import sqlite3
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from src.analysis.exploratory import _resample, _summ

MATERIAL_WORDS = ["briefing", "material", "the box", "arguments for", "arguments against", "the passage", "the text",
                  "the document", "the reading", "the summary provided", "background information", "the data provided",
                  "the statistics", "the figures", "according to the"]
DISCUSSION_WORDS = ["discussion", "conversation", "debate", "the others", "the group", "colleague", "peer",
                    "raised", "pointed out", "persua", "convinc", "argued", "their point", "their argument",
                    "hearing", "listening", "we agreed", "consensus"]
CONDITIONS = ["A-baseline", "A-stateful", "B-materials", "C-reanswer", "D-prior"]


def _has_any(text: str, words: List[str]) -> bool:
    t = text.lower()
    return any(w in t for w in words)


def _mentions_peer(text: str, peers: List[str]) -> bool:
    return any(re.search(rf"\b{re.escape(p)}\b", text) for p in peers)


def load_reasons(db: str, agents: pd.DataFrame) -> pd.DataFrame:
    """a1r_agents 행에 사후 이유와 같은 토론의 다른 참가자 이름을 붙인다"""
    con = sqlite3.connect(db)
    rows = con.execute("select discussion_id, participant, reason from survey_responses where phase='post' and participant_type='ai'").fetchall()
    reason = {(d, p): (r or "") for d, p, r in rows}
    members = agents.groupby("discussion_id")["participant"].apply(lambda s: sorted(set(s))).to_dict()
    a = agents[["discussion_id", "participant", "label", "block", "topic_key"]].copy()
    a["reason"] = [reason.get((d, p), "") for d, p in zip(a["discussion_id"], a["participant"])]
    a["peers"] = [[m for m in members.get(d, []) if m != p] for d, p in zip(a["discussion_id"], a["participant"])]
    a["mention_peer"] = [_mentions_peer(r, ps) for r, ps in zip(a["reason"], a["peers"])]
    a["mention_materials"] = [_has_any(r, MATERIAL_WORDS) for r in a["reason"]]
    a["mention_discussion"] = [_has_any(r, DISCUSSION_WORDS) for r in a["reason"]]
    a["n_words"] = [len(r.split()) for r in a["reason"]]
    a["empty"] = a["reason"].str.strip() == ""
    return a.drop(columns=["peers"])


def s6_reason_mentions(reasons: pd.DataFrame, boot: int, seed: int) -> Dict[str, Any]:
    """조건별 언급 비율 (블록 재표집 백분위 구간). 빈 이유는 분모에서 뺀다."""
    rng = np.random.default_rng(seed)
    out: Dict[str, Any] = {"vocab": {"materials": MATERIAL_WORDS, "discussion": DISCUSSION_WORDS}, "by_condition": {}}
    for lab in CONDITIONS:
        g = reasons[(reasons["label"] == lab) & ~reasons["empty"]]
        if g.empty:
            continue
        blocks = g["block"].unique()
        by_block = {b: x for b, x in g.groupby("block")}
        cols = ["mention_peer", "mention_materials", "mention_discussion"]
        draws = {c: [] for c in cols + ["n_words"]}
        for _ in range(boot):
            s = pd.concat([by_block[b] for b in _resample(blocks, rng)])
            for c in cols:
                draws[c].append(s[c].mean())
            draws["n_words"].append(s["n_words"].mean())
        res = {c: _summ(g[c].mean(), draws[c], len(g), "block") for c in cols}
        res["n_words"] = _summ(g["n_words"].mean(), draws["n_words"], len(g), "block")
        res["n_empty"] = int((reasons["label"] == lab).sum() - len(g))
        out["by_condition"][lab] = res
    return out
