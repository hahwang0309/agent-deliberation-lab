"""
연구 1-C 사례: 논증의 질 × 사회적 지지 (IBM ArgQ 30k, Gretz et al. 2020, CC-BY 3.0)

- 표적 1명(입장을 심음)과 공모자 3명(대본). 공모자는 표적과 반대 입장의 논거 3개를 말한다.
- 강한 논거: 그 주제·입장에서 품질 점수(WA) 상위 25%, 약한 논거: 하위 25%.
  강·약 세트의 총 토큰 수 차이가 작은 쪽의 10% 이내가 되도록 뽑는다(토큰 = 단어·문장부호 단위의 근사).
- 사회적 지지: 다수 = 공모자 3명이 라운드마다 논거 1개씩, 소수 = 1명이 라운드마다 3개를 모두 말하고 2명은
  어느 편도 들지 않는 중립 발화만. 두 조건의 반대 논거 내용과 양은 같고 반대 목소리의 수만 다르다.
- 발언 순서: 표적 → 공모자 3명 × 라운드 수 → 표적 (종결 라운드 없음), 그다음 표적만 사후 설문.
  표적의 첫 발언이 지지 근거를 만들고(모래성 문턱 모델), 마지막 발언에서 상태 기반 엔진의 안내가 작용한다.
  자기 발언에 의한 공약 효과는 모든 셀·모드에 같은 상수다.
- 엔진: 기준선(선행 연구 방식) / 상태 기반(새 장치). 2(논증 질) × 2(지지자 수) × 2(엔진) + C(토론 없이 다시 답함).
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


def topics_and_conditions(rows: List[Dict[str, Any]], seed: int,
                          positive_control: bool = False) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """주제 × 표적 입장마다 강·약 논거 세트(라운드 수 × 라운드당 논거 수)와 조건별 공모자 대본.

    조건: 2×2(강·약 × 소수·다수) + C(토론 없이 다시 답함, 측정 잡음). positive_control이면 입장을 심지 않은
    표적에 강한 논거·다수를 들려주는 양성 대조를 더한다(모델이 움직일 수 있는지 확인, 파일럿용)."""
    t = texts()["argq"]
    rng = random.Random(seed)
    target, conf = t["target"], t["confederates"]
    names = conf["names"]
    per_round, rounds = t["arguments_per_round"], t["rounds"]
    order = [target["name"]] + names * rounds + [target["name"]]
    cells = [(q, s, m) for q in ("strong", "weak") for s in ("minority", "majority") for m in ("baseline", "stateful")]
    conditions = [{"label": f"{q}-{s}-{m}", "experiment": {"mode": m, "mechanisms": {"closing_round": False},
                                                            "turn_order": order}} for q, s, m in cells]
    conditions.append({"label": "C-reanswer", "experiment": {"mode": "survey_only"}})
    if positive_control:
        conditions += [{"label": f"positive-control-{m}", "use_seeds": False,
                        "experiment": {"mode": m, "mechanisms": {"closing_round": False}, "turn_order": order}}
                       for m in ("baseline", "stateful")]
    topics = []
    for i, topic in enumerate(t["topics"]):
        for side in ("pro", "con"):
            opposing = -1 if side == "pro" else 1
            strong, weak = matched_sets(*quartile_pools(rows, topic, opposing), rng, k=per_round * rounds)
            filler = t["filler_line"]
            by_condition, meta = {}, {}
            for quality, args in (("strong", strong), ("weak", weak)):
                lines = [a["argument"] for a in args]
                chunks = [lines[r * per_round:(r + 1) * per_round] for r in range(rounds)]
                meta[quality] = [{"argument": a["argument"], "wa": a["wa"], "tokens": tokens(a["argument"])} for a in args]
                # 다수: 라운드마다 공모자 3명이 논거 1개씩 / 소수: 1명이 라운드마다 3개, 2명은 중립 발화만
                majority = {"participants": {n: {"script": [chunk[j] for chunk in chunks]} for j, n in enumerate(names)}}
                minority = {"participants": {
                    names[0]: {"script": [t["joiner"].join(chunk) for chunk in chunks]},
                    **{n: {"script": [filler] * rounds} for n in names[1:]}}}
                for mode in ("baseline", "stateful"):
                    by_condition[f"{quality}-majority-{mode}"] = majority
                    by_condition[f"{quality}-minority-{mode}"] = minority
            # C: 공모자는 말하지 않고 설문에서만 빠지도록 대본만 둔다
            by_condition["C-reanswer"] = {"participants": {n: {"script": [filler]} for n in names}}
            if positive_control:
                for mode in ("baseline", "stateful"):
                    by_condition[f"positive-control-{mode}"] = by_condition["strong-majority-baseline"]
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
                "survey": {"scale": t["scale"], "scale_min": 0, "items": [{"id": "stance", "text": topic}]},
                "seeds": {target["name"]: {"stance": t["target_seed"][side]}},
                "by_condition": by_condition,
                "meta": {"target_side": side, "arguments": meta},
            })
    return topics, conditions
