"""
A1R 브리핑 자료집에서 정책안별 자료 상자(찬성·반대 논거)와 영역 배경을 뽑는다

입력은 `pdftotext -layout` 결과다. 표는 "PROPOSALS / ARGUMENTS FOR / ARGUMENTS AGAINST" 머리글의
열 위치로 나누고, 빈 줄로 구분된 행을 한 정책안으로 묶는다. 쪽이 바뀌며 끊긴 행은 앞 행의 정책안 문장이
마침표·물음표로 끝나지 않았으면 이어 붙인다. 오른쪽 여백의 쪽 번호·머리글은 열 범위 밖이라 버린다.

자동 추출은 초안이다. 데이터셋 문항 문구와의 유사도(match_score)를 함께 적으므로, 연구자가 낮은 점수와
열이 섞인 행을 원문과 대조해 고친 뒤 확정본으로 쓴다.
"""
import difflib
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

HEADER = re.compile(r"PROPOSALS\s+ARGUMENTS FOR\s+ARGUMENTS AGAINST")
COLUMN_WIDTH = 48  # 반대 논거 열 시작 뒤 이 폭을 넘는 글자는 여백(쪽 번호·머리글)
WORDS_FILE = Path("/usr/share/dict/words")  # 줄 끝 하이픈 판별용 (없으면 하이픈을 그대로 둠)


@lru_cache(maxsize=1)
def _dictionary() -> frozenset:
    try:
        return frozenset(w.strip().lower() for w in WORDS_FILE.read_text(encoding="utf-8").splitlines())
    except OSError:
        return frozenset()


def _dehyphen(match: re.Match) -> str:
    """줄 끝에서 끊긴 단어(com- bat → combat)는 붙이고, 원래 하이픈 단어(high- tax → high-tax)는 하이픈 유지"""
    left, right = match.group(1), match.group(2)
    return left + right if (left + right).lower() in _dictionary() else f"{left}-{right}"


def _columns(header_line: str):
    return header_line.index("PROPOSALS"), header_line.index("ARGUMENTS FOR"), header_line.index("ARGUMENTS AGAINST")


def _cut(line: str, start: int, end: Optional[int]) -> str:
    return line[start:end].strip() if len(line) > start else ""


def parse_tables(text: str) -> List[Dict[str, str]]:
    """표 행 목록 [{proposal, arguments_for, arguments_against}] (자료집 전체, 요약편 포함)"""
    rows: List[Dict[str, List[str]]] = []
    cols = None
    blank = 0
    for line in text.splitlines():
        if HEADER.search(line):
            cols, blank = _columns(line), 0
            rows.append(None)  # 표 경계
            continue
        if cols is None:
            continue
        if not line.strip():
            blank += 1
            continue
        p0, f0, a0 = cols
        lead = len(line) - len(line.lstrip())
        if lead < p0 - 2 and not line[p0 - 2:].strip():
            continue
        proposal = _cut(line, max(0, p0 - 2), f0 - 1)
        pro = _cut(line, f0 - 1, a0 - 1)
        con = re.split(r"\s{3,}", _cut(line, a0 - 1, a0 + COLUMN_WIDTH))[0]  # 열 안 공백 3칸 이상 뒤는 여백 글자
        if not (proposal or pro or con):
            continue
        if not proposal and not pro and lead > a0 + COLUMN_WIDTH - 10:
            continue  # 여백 글자만 있는 줄
        current = rows[-1] if rows else None
        starts_new = (current is None or (proposal and blank >= 1 and current["proposal"]
                                          and re.search(r"[.?]$", current["proposal"][-1])))
        if starts_new:
            current = {"proposal": [], "arguments_for": [], "arguments_against": []}
            rows.append(current)
        for key, part in (("proposal", proposal), ("arguments_for", pro), ("arguments_against", con)):
            if part:
                current[key].append(part)
        blank = 0
    return [{k: _join(v) for k, v in r.items()} for r in rows if r and r["proposal"]]


def _join(parts: List[str]) -> str:
    text = " ".join(parts)
    text = re.sub(r"(\w+)- (\w+)", _dehyphen, text)
    return re.sub(r"\s+", " ", text).strip()


def parse_issues(text: str, domains: List[str]) -> Dict[str, str]:
    """요약편의 영역별 'The Issue' 단락 {영역 대문자 이름: 단락}"""
    issues = {}
    lines = [l.strip() for l in text.splitlines()]
    for i, line in enumerate(lines):
        if line != "The Issue":
            continue
        title = next((lines[j] for j in range(i - 1, max(-1, i - 6), -1) if lines[j]), "")
        domain = next((d for d in domains if d.upper() in title.upper()), None)
        if domain is None or domain in issues:
            continue
        body = []
        for l in lines[i + 1:]:
            if HEADER.search(l):
                break
            if l:
                body.append(l)
        paragraph = _join(body)
        paragraph = re.split(r"\s*Below are examples of policy proposals", paragraph)[0]
        issues[domain] = paragraph
    return issues


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower())


def match_items(rows: List[Dict[str, str]], items: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """문항 id → 문구가 가장 비슷한 표 행 (유사도 match_score 0~1)"""
    out = {}
    for item_id, label in items.items():
        scored = [(difflib.SequenceMatcher(None, _norm(label), _norm(r["proposal"])).ratio(), r) for r in rows]
        score, best = max(scored, key=lambda x: x[0]) if scored else (0.0, None)
        if best is not None:
            out[item_id] = {**best, "match_score": round(score, 3)}
    return out
