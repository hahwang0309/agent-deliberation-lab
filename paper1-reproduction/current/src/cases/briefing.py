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
    if right.lower() in ("or", "and", "to", "nor"):  # 공유 하이픈 (over- or under-pay)은 원문 그대로
        return f"{left}- {right}"
    word = (left + right).lower()
    stems = [word] + [word[:-len(end)] for end in ("s", "es", "ed", "d", "ing", "ly") if word.endswith(end)]
    stems += [word[:-3] + "e" for _ in [0] if word.endswith("ing")] + [word[:-3] + "y" for _ in [0] if word.endswith("ies")]
    return left + right if any(s in _dictionary() for s in stems) else f"{left}-{right}"


def _columns(header_line: str):
    return header_line.index("PROPOSALS"), header_line.index("ARGUMENTS FOR"), header_line.index("ARGUMENTS AGAINST")


def _cut(line: str, start: int, end: Optional[int]) -> str:
    return line[start:end].strip() if len(line) > start else ""


CONTINUED_MARK = re.compile(r"\s*\(continued\)\s*$", re.I)
NAVIGATION_LINE = re.compile(r"^\s*Continued on next page\s*$", re.I)


def parse_tables(text: str) -> List[Dict[str, str]]:
    """표 행 목록 [{proposal, arguments_for, arguments_against}] (자료집 전체, 요약편 포함)

    - 표 머리글 바로 위 줄(다음 표의 절 제목)은 앞 행에 붙지 않게 되돌린다.
    - 쪽 안내 'Continued on next page'는 버린다.
    - 다음 쪽에서 '(continued)'로 이어지는 행은 같은 정책안의 앞 행에 합친다."""
    rows: List[Dict[str, List[str]]] = []
    cols = None
    blank = 0
    last_added: List[tuple] = []  # 직전 줄이 어느 행의 어느 칸에 붙었는지 (절 제목 되돌리기용)
    for line in text.splitlines():
        if HEADER.search(line):
            if blank == 0 and last_added:  # 머리글 바로 위 줄 = 다음 표의 절 제목
                for row, key in last_added:
                    row[key].pop()
            cols, blank, last_added = _columns(line), 0, []
            rows.append(None)  # 표 경계
            continue
        if cols is None:
            continue
        if not line.strip():
            blank += 1
            continue
        if NAVIGATION_LINE.match(line):
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
                                          and re.search(r"[.?](\s*\(continued\))?$", current["proposal"][-1], re.I)))
        if starts_new:
            current = {"proposal": [], "arguments_for": [], "arguments_against": []}
            rows.append(current)
        last_added = []
        for key, part in (("proposal", proposal), ("arguments_for", pro), ("arguments_against", con)):
            if part:
                current[key].append(part)
                last_added.append((current, key))
        blank = 0
    merged: List[Dict[str, str]] = []
    for r in rows:
        if not r or not r["proposal"]:
            continue
        row = {k: _join(v) for k, v in r.items()}
        if CONTINUED_MARK.search(row["proposal"]):
            base = CONTINUED_MARK.sub("", row["proposal"])
            prev = next((m for m in reversed(merged) if m["proposal"] == base), None)
            if prev is not None:
                for key in ("arguments_for", "arguments_against"):
                    prev[key] = f"{prev[key]} {row[key]}".strip()
                continue
        merged.append(row)
    return merged


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


NEAR_TIE = 0.15  # 최고 유사도와 이만큼 안쪽이면 같은 정책안의 다른 판(요약편·본편)으로 본다


def match_items(rows: List[Dict[str, str]], items: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """문항 id → 문구가 가장 비슷한 표 행 (유사도 match_score 0~1).
    요약편(Executive Summary)에도 같은 정책안의 짧은 판이 있으므로, 유사도가 비슷한 후보 중 논거가 가장 긴 행(본편)을 고른다"""
    out = {}
    for item_id, label in items.items():
        scored = [(difflib.SequenceMatcher(None, _norm(label), _norm(r["proposal"])).ratio(), r) for r in rows]
        if not scored:
            continue
        top = max(s for s, _ in scored)
        score, best = max(((s, r) for s, r in scored if s >= top - NEAR_TIE),
                          key=lambda x: len(x[1]["arguments_for"]) + len(x[1]["arguments_against"]))
        out[item_id] = {**best, "match_score": round(score, 3)}
    return out


# ---------- 검증: 다른 방식으로 뽑은 원문과 대조 ----------
# 추출은 `pdftotext -layout`(열 위치)로 했으므로, 검증은 `pdftotext` 기본 모드(읽기 순서) 결과와 비교한다.
# 기본 모드는 표의 칸을 한 단락으로 내고, 쪽이 넘어간 칸도 이어 붙인다. 두 방식이 같은 글을 내면 통과다.

def _words(text: str) -> str:
    """비교용 정규화: 소문자, 하이픈 제거(기본 모드는 줄 끝 하이픈을 없앰), 문자·숫자만"""
    text = text.lower().replace("­", "").replace("-", "")
    return " ".join(re.findall(r"[a-z0-9$%]+", text))


def raw_paragraphs(raw_text: str) -> List[Dict[str, Any]]:
    """기본 모드 텍스트 → 단락 목록 [{page, text, norm}] (쪽은 폼피드로 셈, 1부터)"""
    out = []
    for page, page_text in enumerate(raw_text.split("\f"), 1):
        for block in re.split(r"\n\s*\n", page_text):
            text = " ".join(l.strip() for l in block.splitlines() if l.strip())
            if text:
                out.append({"page": page, "text": text, "norm": _words(text)})
    return out


NAVIGATION = ("continued on next page", "america in one room")  # 원문 내용이 아닌 쪽 안내·머리글


def _compose(norm: str, paragraphs: List[Dict[str, Any]], start: int, max_skip: int = 8):
    """start 단락부터 이어지는 단락들을 이어 붙여 필드와 같아지는지 (사이의 다른 칸·쪽 번호 단락은 건너뜀)"""
    acc, used, skipped = "", [], []
    for p in paragraphs[start:start + 40]:
        cand = f"{acc} {p['norm']}".strip()
        if norm.startswith(cand):
            acc = cand
            used.append(p)
            if acc == norm:
                return used, skipped
        else:
            skipped.append(p)
            if len(skipped) > max_skip:
                break
    return None


def _sentences(text: str) -> List[str]:
    return [s for s in (_words(x) for x in re.split(r"(?<=[.?!])\s+", text)) if s]


def _sentence_check(field: str, paragraphs: List[Dict[str, Any]], min_page: int) -> Optional[Dict[str, Any]]:
    """여러 단락으로 나뉜 칸: 모든 문장이 본편에 순서대로 있고, 그 문장을 담은 원문 단락에 빠진 문장이 없으면 통과"""
    ours = _sentences(field)
    body = [p for p in paragraphs if p["page"] >= min_page]
    hits = []
    for sentence in ours:
        idx = next((i for i, p in enumerate(body) if sentence in p["norm"]), None)
        if idx is None:
            return None
        hits.append(idx)
    if hits != sorted(hits):
        return None
    covered = set()
    for i in sorted(set(hits)):
        covered.update(_sentences(body[i]["text"]))
    missing = [s for s in covered if s not in ours]
    if missing:
        return {"status": "incomplete", "page": body[hits[0]]["page"], "missing_from_ours": missing}
    return {"status": "sentences", "page": body[hits[0]]["page"], "paragraphs": len(set(hits))}


def _locate(field: str, paragraphs: List[Dict[str, Any]], min_page: int) -> Dict[str, Any]:
    """필드가 원문 단락(또는 이어지는 여러 단락)과 같은지. 같지 않으면 가장 가까운 단락과의 차이를 돌려준다"""
    norm = _words(field)
    junk = [n for n in NAVIGATION if n in norm]
    if junk:
        return {"status": "navigation_text", "junk": junk, "page": None}
    exact = [p for p in paragraphs if p["norm"] == norm]
    full = [p for p in exact if p["page"] >= min_page]
    if full:
        return {"status": "exact", "page": full[0]["page"]}
    for i, p in enumerate(paragraphs):
        if p["page"] >= min_page and len(p["norm"].split()) >= 3 and norm.startswith(p["norm"] + " "):
            found = _compose(norm, paragraphs, i)
            if found:
                used, skipped = found
                return {"status": "joined", "page": used[0]["page"], "parts": len(used),
                        "skipped_between": [s["text"][:80] for s in skipped]}
    by_sentence = _sentence_check(field, paragraphs, min_page)
    if by_sentence:
        return by_sentence
    if exact:
        return {"status": "summary_only", "page": exact[0]["page"]}
    candidates = [p for p in paragraphs if p["page"] >= min_page] or paragraphs
    best = max(candidates, key=lambda p: difflib.SequenceMatcher(None, norm, p["norm"]).ratio())
    a, b = norm.split(), best["norm"].split()
    diff = [f"{op}: ours={' '.join(a[i1:i2])!r} pdf={' '.join(b[j1:j2])!r}"
            for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes() if op != "equal"]
    return {"status": "mismatch", "page": best["page"], "pdf_text": best["text"], "diff": diff}


def _hyphen_cases(field: str, raw_text: str) -> List[str]:
    """하이픈 단어 중 원문 기본 모드에 하이픈 없이 붙어 있는 것 (= 줄 끝에서 나뉘어 원래 표기를 기본 모드로 알 수 없음)"""
    flat = re.sub(r"\s+", " ", raw_text)
    cases = []
    for word in sorted(set(re.findall(r"\b\w+(?:-\w+)+\b", field))):
        if word not in flat and word.replace("-", "") in flat:
            cases.append(word)
    return cases


def verify(briefing: Dict[str, Any], raw_text: str, min_page: int) -> Dict[str, Any]:
    """자료 상자 전체 검증. min_page: 본편이 시작하는 쪽 (그 앞은 요약편)"""
    paragraphs = raw_paragraphs(raw_text)
    report = {"items": {}, "issues": {}}
    for item_id, box in briefing["items"].items():
        fields = {k: _locate(box[k], paragraphs, min_page) for k in ("proposal", "arguments_for", "arguments_against")}
        hyphens = sorted({h for k in fields for h in _hyphen_cases(box[k], raw_text)})
        report["items"][item_id] = {"fields": fields, "hyphen_check": hyphens}
    for domain, text in briefing["issues"].items():
        report["issues"][domain] = _locate_issue(text, paragraphs)
    return report


def _locate_issue(text: str, paragraphs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """영역 배경: 원문 단락에서 머리글('HEALTH CARE The Issue')과 끝의 안내 문장을 뺀 본문과 같은지"""
    norm = _words(text)
    for p in paragraphs:
        body = re.sub(r"^.*?\bthe issue\b ", "", p["norm"], count=1)
        body = re.split(r" ?below are examples of policy proposals", body)[0].strip()
        if body == norm:
            return {"status": "exact", "page": p["page"]}
    return _locate(text, paragraphs, 1)
