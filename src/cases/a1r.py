"""
연구 1-B 사례: America in One Room (Fishkin et al. 2021, Harvard Dataverse doi:10.7910/DVN/KJ8IH2)

- 숙의 참가자: CONDITION 1 이고 사후 응답이 있는(POST 1) 사람. 사전 점수 Q*, 사후 점수 T2Q* (0~10).
- 반복 집단: 문항마다 민주 2 + 공화 2 + 무당층 1을 정당별 층화 무작위로 뽑는다(그 문항 사전 점수가 있는 사람만).
  한 번 뽑은 집단을 모든 조건에 복제한다(계획의 주제 1개 = 집단 1개).
- 실제 소집단: GROUP이 같은 숙의 참가자 전원(약 13명)을 그대로 복제한다.
- 페르소나: 실제 프로필(정당, 이념, 나이, 성별, 인종, 학력)과 시점 지시. 이름은 프로필과 무관한 중립 이름.
- 자료: 확정한 자료 상자 파일(정책안 찬반 논거 + 영역 배경). 이름 제거 문항은 문안과 자료를 치환한다.
"""
import csv
import random
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.cases import texts

PARTIES = {"1": "D", "2": "R", "3": "I"}
DEFAULT_MIX = {"D": 2, "R": 2, "I": 1}


@dataclass
class Respondent:
    row: int        # 데이터셋 행 번호 (응답자 식별용, 0부터)
    group: str
    party: str      # PARTYID3 코드
    profile: Dict[str, str]
    pre: Dict[str, Optional[int]]
    post: Dict[str, Optional[int]]


def _score(value: str) -> Optional[int]:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return int(x) if 0 <= x <= 10 and x == int(x) else None


def load_items(codebook_path: str) -> Dict[str, str]:
    """문항 id → 정책안 문구 (코드북 라벨의 대괄호 안)"""
    with open(codebook_path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    items = {}
    for row in rows[1:]:
        name = row[0].strip('"') if row and row[0] else ""
        if re.fullmatch(r"Q[2-6][A-J]", name):
            m = re.match(r"\[(.*?)\]", row[1])
            if m:
                items[name] = m.group(1).strip()
    return items


def load_delegates(dataset_path: str, items: List[str]) -> List[Respondent]:
    with open(dataset_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter="\t")
        out = []
        for i, d in enumerate(reader):
            if d.get("CONDITION") != "1" or d.get("POST") != "1" or d.get("PARTYID3") not in PARTIES:
                continue
            profile = {k: d.get(c, "") for k, c in (("gender", "GENDER"), ("age", "AGE4"), ("race", "RACETHNICITY"),
                                                     ("education", "EDUC4"), ("party", "PARTYID3"), ("ideology", "LIBCONV"))}
            out.append(Respondent(i, d.get("GROUP", ""), d["PARTYID3"], profile,
                                  {q: _score(d.get(q)) for q in items}, {q: _score(d.get("T2" + q)) for q in items}))
    return out


def persona(respondent: Respondent, name: str, t: Dict[str, Any]) -> Dict[str, Any]:
    labels = t["labels"]
    fields = {k: labels[k].get(v, labels[k].get("0", "unknown")) if k in labels else v
              for k, v in respondent.profile.items()}
    background = t["persona"]["background"].format(time_instruction=t["time_instruction"], **{
        k: fields.get(k, "unknown") for k in ("age", "gender", "race", "education", "party", "ideology")})
    return {"name": name, "role": t["persona"]["role"], "background": background,
            "communication_style": t["persona"]["communication_style"]}


def domain_of(item_id: str, t: Dict[str, Any]) -> str:
    return t["domains"][item_id[1]]


def materials(item_id: str, proposal: str, briefing: Dict[str, Any], t: Dict[str, Any],
              replace: Optional[Dict[str, str]] = None) -> str:
    box = briefing["items"][item_id]
    domain = domain_of(item_id, t)
    parts = [t["materials_header"],
             t["materials_issue"].format(domain=domain, issue=briefing["issues"][domain]),
             t["materials_box"].format(proposal=proposal, arguments_for=box["arguments_for"],
                                       arguments_against=box["arguments_against"])]
    text = "\n\n".join(parts)
    for old in sorted(replace or {}, key=len, reverse=True):  # 긴 표현부터 (부분 치환이 겹치지 않도록)
        text = text.replace(old, replace[old])
    return text


def _topic(key: str, item_id: str, proposal: str, members: List[Respondent], t: Dict[str, Any],
           briefing: Optional[Dict[str, Any]], max_statements: int, rng: random.Random,
           replace: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    names = rng.sample(t["names"], len(members))
    topic = {
        "key": key,
        "topic": t["topic"].format(domain=domain_of(item_id, t)),
        "description": t["survey_text"].format(proposal=proposal),
        "language": "en",
        "max_statements": max_statements,
        "use_moderator": True,
        "propositions": [proposal],
        "personas": [persona(r, n, t) for r, n in zip(members, names)],
        "survey": {"scale": 10, "scale_min": 0,
                   "items": [{"id": item_id, "text": t["survey_text"].format(proposal=proposal)}]},
        "seeds": {n: {item_id: r.pre[item_id]} for r, n in zip(members, names)},
        "meta": {"item": item_id, "respondent_rows": {n: r.row for r, n in zip(members, names)},
                 "groups": sorted({r.group for r in members})},
    }
    if briefing is not None:
        topic["materials"] = materials(item_id, proposal, briefing, t, replace)
    return topic


def sample_groups(delegates: List[Respondent], item_id: str, count: int, rng: random.Random,
                  mix: Dict[str, int] = DEFAULT_MIX) -> List[List[Respondent]]:
    """정당별 층화 무작위 집단 count개 (한 집단 안에서 중복 없음, 집단 사이 중복은 허용)"""
    pools = {p: [r for r in delegates if PARTIES[r.party] == p and r.pre.get(item_id) is not None] for p in mix}
    for p, n in mix.items():
        if len(pools[p]) < n:
            raise ValueError(f"{item_id}: not enough {p} delegates with a pre score ({len(pools[p])} < {n})")
    groups = []
    for _ in range(count):
        members = [r for p, n in mix.items() for r in rng.sample(pools[p], n)]
        rng.shuffle(members)
        groups.append(members)
    return groups


def sampled_topics(delegates: List[Respondent], items: Dict[str, str], item_ids: List[str], groups_per_item: int,
                   seed: int, briefing: Optional[Dict[str, Any]] = None, max_statements: int = 15,
                   debranded: bool = False) -> List[Dict[str, Any]]:
    """반복 집단 주제. debranded=True면 cases.yaml의 이름 제거 문항만 그 문안·치환으로 만든다"""
    t = texts()["a1r"]
    rng = random.Random(seed)
    topics = []
    for item_id in item_ids:
        proposal, replace, suffix = items[item_id], None, ""
        if debranded:
            spec = t["debranded"][item_id]
            proposal, replace, suffix = spec["proposal"], spec.get("replace"), "-debranded"
        for g, members in enumerate(sample_groups(delegates, item_id, groups_per_item, rng)):
            topics.append(_topic(f"{item_id}{suffix}-g{g:02d}", item_id, proposal, members, t, briefing,
                                 max_statements, rng, replace))
    return topics


def small_group_topics(delegates: List[Respondent], items: Dict[str, str], item_ids: List[str], seed: int,
                       briefing: Optional[Dict[str, Any]] = None, max_statements: int = 39,
                       groups: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """실제 소집단 복제: GROUP별로 그 문항 사전 점수가 있는 숙의 참가자 전원"""
    t = texts()["a1r"]
    rng = random.Random(seed)
    topics = []
    for item_id in item_ids:
        by_group: Dict[str, List[Respondent]] = {}
        for r in delegates:
            if r.group and r.pre.get(item_id) is not None:
                by_group.setdefault(r.group, []).append(r)
        for group in sorted(by_group, key=lambda g: (len(g), g)):
            if groups and group not in groups:
                continue
            members = by_group[group]
            if len(members) > len(t["names"]):
                raise ValueError(f"group {group} has {len(members)} members; add names in cases.yaml")
            topics.append(_topic(f"{item_id}-group{group}", item_id, items[item_id], members, t, briefing,
                                 max_statements, rng))
    return topics


CONDITIONS = [
    {"label": "A-baseline", "experiment": {"mode": "baseline"}},
    {"label": "A-stateful", "experiment": {"mode": "stateful"}},
    {"label": "B-materials", "experiment": {"mode": "survey_only"}},
    {"label": "C-reanswer", "experiment": {"mode": "survey_only"}, "use_materials": False},
    {"label": "D-prior", "experiment": {"mode": "survey_only"}, "use_seeds": False, "use_materials": False},
]
