"""
코딩 일치도 - 사람 코딩과 LLM 판정, 또는 코더 두 명 사이의 일치도

입력은 scripts/export_dataset.py --coding-sample로 만든 파일이다.
  coding_blind.csv: 코더가 code_* 칸을 채운 파일 (코더마다 1개)
  coding_key.csv:   LLM 판정 (llm_concession 등)
지표: 일치율과 Cohen's kappa (우연 일치를 뺀 일치도). 빈칸은 제외한다.
"""
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

YES = {"1", "y", "yes", "true", "o", "예", "네", "있음"}
NO = {"0", "n", "no", "false", "x", "아니오", "아니요", "없음"}


def to_bool(value: Any) -> Optional[bool]:
    text = str(value).strip().lower()
    if text in YES:
        return True
    if text in NO:
        return False
    return None


def cohen_kappa(a: Sequence[Any], b: Sequence[Any]) -> Optional[float]:
    """두 평가자의 범주형 판정 일치도. 기대 일치가 1이면(한 범주만 나옴) 정의되지 않아 None"""
    n = len(a)
    if n == 0 or n != len(b):
        return None
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return None if expected == 1 else round((observed - expected) / (1 - expected), 3)


def _pairs(xs: List[Any], ys: List[Any]):
    return [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]


def compare(a: List[Any], b: List[Any]) -> Dict[str, Any]:
    pairs = _pairs(a, b)
    if not pairs:
        return {"n": 0, "agreement": None, "kappa": None}
    xs, ys = zip(*pairs)
    return {"n": len(pairs), "agreement": round(sum(x == y for x, y in pairs) / len(pairs), 3),
            "kappa": cohen_kappa(xs, ys), "confusion": {f"{x}/{y}": c for (x, y), c in Counter(pairs).items()}}


def human_vs_llm(coded: List[Dict[str, Any]], key: List[Dict[str, Any]], repeat_threshold: float = 0.4) -> Dict[str, Any]:
    """사람 코딩과 자동 판정의 일치도: 양보(LLM 분석), 자기 논거 반복(문자 2-gram 유사도 ≥ 기준)"""
    keys = {k["sample_id"]: k for k in key}
    rows = [r for r in coded if r["sample_id"] in keys]

    def auto_repeat(k):
        return None if k.get("repeat_score") in (None, "") else float(k["repeat_score"]) >= repeat_threshold

    return {
        "concession": compare([to_bool(r.get("code_concession", "")) for r in rows],
                              [to_bool(keys[r["sample_id"]]["llm_concession"]) for r in rows]),
        "repeats_own_argument": compare([to_bool(r.get("code_repeats_own_argument", "")) for r in rows],
                                        [auto_repeat(keys[r["sample_id"]]) for r in rows]),
    }


CODE_COLUMNS = ("code_concession", "code_responds_to_previous", "code_repeats_own_argument",
                "code_justification_level", "code_respect_level")
BOOL_COLUMNS = ("code_concession", "code_responds_to_previous", "code_repeats_own_argument")


def coder_vs_coder(first: List[Dict[str, Any]], second: List[Dict[str, Any]]) -> Dict[str, Any]:
    """두 코더의 코딩 일치도 (항목별). 예/아니오 항목은 정규화하고 수준 항목은 값 그대로 비교"""
    other = {r["sample_id"]: r for r in second}
    shared = [r for r in first if r["sample_id"] in other]
    result = {}
    for column in CODE_COLUMNS:
        norm = to_bool if column in BOOL_COLUMNS else (
            lambda v: str(v).strip() or None)
        result[column] = compare([norm(r.get(column, "")) for r in shared],
                                 [norm(other[r["sample_id"]].get(column, "")) for r in shared])
    return result
