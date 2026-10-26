"""
인간 기준 자료 (분석 계획 2절, 6절 마지막 행)

- DeliData: 혼자 답과 토론 후 답이 모두 있고, 혼자 답이 유효한 참가자 (사례 생성과 같은 기준)
- America in One Room: 숙의 참가자, 사전·사후 모두 0~10 유효 응답
"""
from typing import Dict, List

import pandas as pd

from src.cases import a1r, wason


def initial_correct_bin(n_correct: int) -> str:
    """초기 정답자 수 범주 0 / 1 / 2+ (H1)"""
    return "2+" if n_correct >= 2 else str(n_correct)


def delidata_individuals(directory: str) -> pd.DataFrame:
    """참가자 1행: block(= 복제 주제 키), 집단 크기, 카드 세트, 초기 정답자 수 범주, 토론 후 정답"""
    rows = []
    for g in wason.load_delidata(directory):
        if len(g.solo) < 2 or any(v is None for v in g.solo.values()):
            continue
        if sorted(wason.card_role(c) for c in g.cards) != sorted(wason.ROLES):
            continue
        corr = set(wason.correct_cards(g.cards))
        k = sum(set(v) == corr for v in g.solo.values())
        for member in g.solo:
            rows.append({"block": f"deli-{g.group_id[:8]}", "group_size": len(g.solo),
                         "card_set": ",".join(sorted(g.cards)), "k": initial_correct_bin(k),
                         "correct": int(set(g.final[member]) == corr)})
    return pd.DataFrame(rows)


def delidata_groups(directory: str) -> pd.DataFrame:
    """참가자 1행 + 토론 후 최종 카드 집합(final, 정렬 튜플). 집단 필터는 delidata_individuals와 같다 (탐색 분석 N2a·N5용)"""
    rows = []
    for g in wason.load_delidata(directory):
        if len(g.solo) < 2 or any(v is None for v in g.solo.values()):
            continue
        if sorted(wason.card_role(c) for c in g.cards) != sorted(wason.ROLES):
            continue
        corr = set(wason.correct_cards(g.cards))
        k = sum(set(v) == corr for v in g.solo.values())
        for member in g.solo:
            rows.append({"block": f"deli-{g.group_id[:8]}", "member": member, "group_size": len(g.solo),
                         "card_set": ",".join(sorted(g.cards)), "k": initial_correct_bin(k), "k_raw": k,
                         "solo_correct": int(set(g.solo[member]) == corr),
                         "correct": int(set(g.final[member]) == corr), "final": tuple(sorted(g.final[member]))})
    return pd.DataFrame(rows)


def a1r_delegates(dataset_path: str, items: List[str], condition: str = "1") -> pd.DataFrame:
    """A1R 응답자 × 문항 1행: row(데이터셋 행), group(소집단; 통제집단은 공백), party(PARTYID3), pre, post.
    condition "1" = 숙의 참가자(기본), "0" = 통제집단"""
    rows = []
    for r in a1r.load_delegates(dataset_path, items, condition):
        for q in items:
            if r.pre.get(q) is not None and r.post.get(q) is not None:
                rows.append({"row": r.row, "group": r.group, "party": r.party, "item": q,
                             "pre": r.pre[q], "post": r.post[q], "weight": r.weight})
    return pd.DataFrame(rows)


def a1r_parties(dataset_path: str, items: List[str]) -> Dict[int, str]:
    """데이터셋 행 → PARTYID3 (AI 페르소나의 정당)"""
    return {r.row: r.party for r in a1r.load_delegates(dataset_path, items)}
