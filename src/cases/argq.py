"""
연구 1-C 사례: 논증의 질 × 사회적 지지 (IBM ArgQ 30k, Gretz et al. 2020, CC-BY 3.0)

- 표적 1명(입장을 심음)과 공모자 3명(대본). 공모자는 표적과 반대 입장의 논거 3개를 말한다.
- 강한 논거: 그 주제·입장에서 품질 점수(WA) 상위 25%, 약한 논거: 하위 25%.
  강·약 세트의 총 토큰 수 차이가 작은 쪽의 10% 이내가 되도록 뽑는다(토큰 = 단어·문장부호 단위의 근사).
- 사회적 지지: 다수 = 공모자 3명이 논거 1개씩, 소수 = 1명이 3개를 모두 말하고 2명은 표적 쪽 동의만 짧게.
  두 조건의 반대 논거 내용과 양은 같고 지지자 수만 다르다.
- 발언 순서: 표적 → 공모자 3명 → 표적 (기준선 모드, 종결 라운드 없음), 그다음 표적만 사후 설문.
"""
import csv
import random
import re
from pathlib import Path
from statistics import quantiles
from typing import Any, Dict, List, Tuple

from src.cases import texts

TOKEN = re.compile(r"\w+|[^\w\s]")
MAX_TRIES = 20000


def tokens(text: str) -> int:
    return len(TOKEN.findall(text))


def load_arguments(directory: str) -> List[Dict[str, Any]]:
    rows = []
    for name in ("train.csv", "dev.csv", "test.csv"):
        path = Path(directory) / name
        if path.exists():
            with path.open(encoding="utf-8") as f:
                rows += [{"argument": r["argument"].strip(), "topic": r["topic"], "wa": float(r["WA"]),
                          "stance": int(r["stance_WA"])} for r in csv.DictReader(f)]
    return rows


def quartile_pools(rows: List[Dict[str, Any]], topic: str, stance: int) -> Tuple[List[dict], List[dict]]:
    """(상위 25%, 하위 25%)"""
    pool = [r for r in rows if r["topic"] == topic and r["stance"] == stance]
    if len(pool) < 8:
        raise ValueError(f"too few arguments for {topic} / stance {stance}: {len(pool)}")
    q1, _, q3 = quantiles([r["wa"] for r in pool], n=4)
    return [r for r in pool if r["wa"] >= q3], [r for r in pool if r["wa"] <= q1]


def matched_sets(strong: List[dict], weak: List[dict], rng: random.Random, k: int = 3,
                 tolerance: float = 0.10) -> Tuple[List[dict], List[dict]]:
    """총 토큰 수가 tolerance 안으로 맞는 강·약 논거 k개씩"""
    for _ in range(MAX_TRIES):
        s, w = rng.sample(strong, k), rng.sample(weak, k)
        ts, tw = sum(tokens(r["argument"]) for r in s), sum(tokens(r["argument"]) for r in w)
        if abs(ts - tw) <= tolerance * min(ts, tw):
            return s, w
    raise ValueError("could not match strong and weak sets within the token tolerance")


def topics_and_conditions(rows: List[Dict[str, Any]], seed: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    t = texts()["argq"]
    rng = random.Random(seed)
    target, conf = t["target"], t["confederates"]
    names = conf["names"]
    order = [target["name"], *names, target["name"]]
    base = {"mode": "baseline", "mechanisms": {"closing_round": False}, "turn_order": order}
    conditions = [{"label": f"{q}-{s}", "experiment": base} for q in ("strong", "weak") for s in ("minority", "majority")]
    topics = []
    for i, topic in enumerate(t["topics"]):
        for side in ("pro", "con"):
            opposing = -1 if side == "pro" else 1
            strong, weak = matched_sets(*quartile_pools(rows, topic, opposing), rng)
            agree = t["agree_line"].format(target=target["name"], side=t["side_words"][side])
            by_condition, meta = {}, {}
            for quality, args in (("strong", strong), ("weak", weak)):
                lines = [a["argument"] for a in args]
                meta[quality] = [{"argument": a["argument"], "wa": a["wa"], "tokens": tokens(a["argument"])} for a in args]
                by_condition[f"{quality}-majority"] = {"participants": {
                    n: {"script": [line]} for n, line in zip(names, lines)}}
                by_condition[f"{quality}-minority"] = {"participants": {
                    names[0]: {"script": [t["joiner"].join(lines)]},
                    names[1]: {"script": [agree]}, names[2]: {"script": [agree]}}}
            persona = lambda n, p: {"name": n, "role": p["role"], "background": p["background"],
                                    "communication_style": p["communication_style"]}
            topics.append({
                "key": f"argq{i}-{side}",
                "topic": topic,
                "language": "en",
                "max_statements": len(order),
                "use_moderator": False,
                "propositions": [topic],
                "personas": [persona(target["name"], target)] + [persona(n, conf) for n in names],
                "survey": {"scale": t["scale"], "items": [{"id": "stance", "text": topic}]},
                "seeds": {target["name"]: {"stance": t["target_seed"][side]}},
                "by_condition": by_condition,
                "meta": {"target_side": side, "arguments": meta},
            })
    return topics, conditions
