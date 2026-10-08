"""
연구 1-A 사례: Wason 선택 과제

- DeliData 읽기: 집단별 카드 4장, 참가자별 혼자 답(INITIAL의 sol_tracker_all)과 토론 후 답(마지막 SUBMIT).
  분석 대상은 혼자 답과 토론 후 답이 모두 있는 참가자다(인간 기준값 계산과 같은 정의).
  혼자 답이 ["N", "/", "A"](기록 없음)이거나 카드에 없는 값이면 None(무효)으로 둔다.
- 원 과제 복제: 3명 집단마다 같은 카드, 인간 3명의 혼자 답을 AI 3명에게 심는다.
- 새 변형: 같은 논리 구조(P, not-P, Q, not-Q)의 표면 내용을 무작위로 만들고, 초기 답은
  DeliData 혼자 답의 역할 유형 분포(P/not-P/Q/not-Q 조합)에서 뽑는다.
"""
import csv
import json
import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.cases import texts

VOWELS = set("AEIOU")
ROLES = ("P", "notP", "Q", "notQ")  # 원 과제: 모음, 자음, 짝수, 홀수


@dataclass
class Group:
    group_id: str
    cards: List[str]
    solo: Dict[str, Optional[List[str]]] = field(default_factory=dict)   # 참가자 → 혼자 답 (무효면 None)
    final: Dict[str, List[str]] = field(default_factory=dict)  # 참가자 → 토론 후 답


def card_role(card: str) -> str:
    if card.isdigit():
        return "notQ" if int(card) % 2 else "Q"
    return "P" if card in VOWELS else "notP"


def correct_cards(cards: List[str]) -> List[str]:
    """모음 + 홀수"""
    return [c for c in cards if card_role(c) in ("P", "notQ")]


def _clean(selection: List[str]) -> List[str]:
    return [c.strip().upper() for c in selection if c.strip()]


def _valid(selection: List[str], cards: List[str]) -> Optional[List[str]]:
    """카드 목록 안의 값으로만 된 답이면 카드 순서로 정리, 아니면 None (예: N/A 기록)"""
    chosen = _clean(selection)
    if not chosen or any(c not in cards for c in chosen):
        return None
    return [c for c in cards if c in chosen]


def load_delidata(directory: str) -> List[Group]:
    groups = []
    for path in sorted(Path(directory).glob("*.tsv")):
        if path.name == "sample.tsv":
            continue
        with path.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        init = next((r for r in rows if r["message_type"] == "INITIAL"), None)
        if init is None:
            continue
        cards = [c.strip().upper() for c in init["original_text"].split("&&")[1].split(",")]
        solo = {m: _valid(sel, cards) for m, sel in json.loads(init["sol_tracker_all"] or "{}").items()}
        final = {}
        for r in rows:
            if r["message_type"] == "SUBMIT":
                final[r["origin"]] = _clean(r["original_text"].split(","))
        members = [m for m in solo if m in final]
        groups.append(Group(init["group_id"], cards, {m: solo[m] for m in members}, {m: final[m] for m in members}))
    return groups


def solo_role_distribution(groups: List[Group]) -> Counter:
    """혼자 답의 역할 조합 분포 (빈 답 제외). 예: ('P', 'Q') = 모음 + 짝수"""
    dist = Counter()
    for g in groups:
        for sel in g.solo.values():
            if sel:
                dist[tuple(sorted({card_role(c) for c in sel}, key=ROLES.index))] += 1
    return dist


def _persona(name: str, t: Dict[str, Any]) -> Dict[str, Any]:
    p = t["persona"]
    return {"name": name, "role": p["role"], "background": p["background"],
            "communication_style": p["communication_style"]}


def _topic(key: str, cards: List[str], correct: List[str], question: str, setup: str,
           members: List[str], seeds: Dict[str, List[str]], max_statements: int, t: Dict[str, Any],
           meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "key": key,
        "topic": t["topic"],
        "description": f"{setup}\n{question}",
        "language": "en",
        "max_statements": max_statements,
        "use_moderator": False,
        "propositions": [t["proposition"]],
        "personas": [_persona(m, t) for m in members],
        "survey": {"items": [{"id": "cards", "type": "choice", "multi": True, "options": cards,
                              "correct": correct, "text": f"{setup} {question}"}]},
        "seeds": {m: {"cards": seeds[m]} for m in members},
        "meta": meta,
    }


def replica_topics(groups: List[Group], size: Optional[int] = None,
                   per_member: int = 5) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """원 과제 복제 주제. size를 비우면 모든 크기(2명 이상)의 집단을 복제한다.
    발언 수 = 1인당 per_member (3명이면 15: 입장 표명 3 + 상호작용 9 + 종결 3). (주제 목록, 제외 사유별 집단 수)"""
    t = texts()["wason"]
    topics, excluded = [], Counter()
    for g in groups:
        if (size is not None and len(g.solo) != size) or len(g.solo) < 2:
            continue
        if len(g.cards) != 4 or sorted(card_role(c) for c in g.cards) != sorted(ROLES):
            excluded["card set is not one P / not-P / Q / not-Q"] += 1
            continue
        if any(sel is None for sel in g.solo.values()):
            excluded["a member has no valid solo answer (e.g. N/A)"] += 1
            continue
        members = list(g.solo)
        topics.append(_topic(f"deli-{g.group_id[:8]}", g.cards, correct_cards(g.cards), t["question"],
                             t["setup"].format(cards=", ".join(g.cards)), members,
                             {m: g.solo[m] for m in members}, per_member * len(members), t,
                             {"group_id": g.group_id, "human_final": {m: g.final[m] for m in members}}))
    return topics, dict(excluded)


def variant_topics(n: int, distribution: Counter, seed: int, size: int = 3,
                   max_statements: int = 15) -> List[Dict[str, Any]]:
    """같은 논리 구조의 새 변형 n개. 면 이름은 cases.yaml의 차원 2개에서 무작위로 고른다"""
    t = texts()["wason"]
    rng = random.Random(seed)
    types, weights = zip(*sorted(distribution.items()))
    topics = []
    for i in range(n):
        dim_a, dim_b = rng.sample(t["dimensions"], 2)
        p, not_p = rng.sample(dim_a["values"], 2)
        q, not_q = rng.sample(dim_b["values"], 2)
        faces = {"P": p["face"], "notP": not_p["face"], "Q": q["face"], "notQ": not_q["face"]}
        cards = [faces[r] for r in rng.sample(ROLES, 4)]
        question = t["variant"]["question"].format(p=p["phrase"], q=q["phrase"])
        setup = t["variant"]["setup"].format(cards=", ".join(cards), side_a=dim_a["side"], side_b=dim_b["side"])
        members = rng.sample(t["variant_names"], size)
        seeds = {}
        for m in members:
            roles = rng.choices(types, weights=weights)[0]
            seeds[m] = [c for c in cards if any(faces[r] == c for r in roles)]
        topics.append(_topic(f"variant-{i:03d}", cards, [faces["P"], faces["notQ"]], question, setup,
                             members, seeds, max_statements, t, {"variant": i, "roles": faces}))
    return topics


CONDITIONS = [
    {"label": "A-baseline", "experiment": {"mode": "baseline"}, "repetitions": 2},
    {"label": "A-stateful", "experiment": {"mode": "stateful"}, "repetitions": 2},
    {"label": "B-resolve", "experiment": {"mode": "survey_only"}, "repetitions": 1},
    {"label": "C-unseeded", "experiment": {"mode": "survey_only"}, "use_seeds": False, "repetitions": 1},
]
