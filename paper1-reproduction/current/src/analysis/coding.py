"""
D단계 N10: 발언 유형 구성 (DeliData 체계) — 사람 주석(DeliData 원자료) 대 AI 발언 코딩(scripts/code_utterances.py 산출).

- 단위: 집단(토론) 1개의 구성비(type 중 probing 비율, target 6종 비율). 재표집: 집단.
- 사람: DeliData 주석 전수(해당 집단). AI: 코더 1차(GLM) 라벨; 제2 코더는 일관성 보고에만.
- 비교용 표본(k × 집단 크기 층화)과 설명용 표본(결과를 보고 고른 층)을 구분해 보고한다. 같은 집단의 사람 대 AI 차이는 집단 쌍 재표집.
"""
import csv
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from src.analysis.exploratory import _resample, _summ

TARGETS = ["solution", "reasoning", "agree", "disagree", "moderation", "none"]
GOLD_TYPE = {"Probing": "probing", "Non-probing-deliberation": "non_probing", "None": "none", "0": "none"}
GOLD_TARGET = {"Solution": "solution", "Reasoning": "reasoning", "Agree": "agree", "Disagree": "disagree", "Moderation": "moderation", "0": "none", "None": "none"}


def human_labels(directory: str) -> pd.DataFrame:
    rows = []
    for path in sorted(Path(directory).glob("*.tsv")):
        if path.name == "sample.tsv":
            continue
        with path.open(encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                if r["message_type"] == "MESSAGE":
                    rows.append({"topic_key": "deli-" + r["group_id"][:8], "type": GOLD_TYPE.get(r["annotation_type"], "none"),
                                 "target": GOLD_TARGET.get(r["annotation_target"], "none")})
    return pd.DataFrame(rows)


def composition(labels: pd.DataFrame, unit: str) -> pd.DataFrame:
    """단위(집단/토론)별 구성비: probing 비율, target별 비율, 발언 수"""
    rows = []
    for u, g in labels.dropna(subset=["type", "target"]).groupby(unit):
        row = {unit: u, "n": len(g), "probing": float((g["type"] == "probing").mean())}
        for t in TARGETS:
            row[t] = float((g["target"] == t).mean())
        rows.append(row)
    return pd.DataFrame(rows)


def _mean_ci(t: pd.DataFrame, cols: List[str], boot: int, rng) -> Dict[str, Any]:
    ids = t.index.to_numpy()
    draws = {c: [] for c in cols}
    for _ in range(boot):
        s = t.loc[_resample(ids, rng)]
        for c in cols:
            draws[c].append(float(s[c].mean()))
    return {c: _summ(float(t[c].mean()), draws[c], len(t), "group") for c in cols}


def n10_summary(human: pd.DataFrame, ai: pd.DataFrame, boot: int, seed: int) -> Dict[str, Any]:
    """ai: 코딩 CSV(열 discussion_id, topic_key, label, stratum, type, target). 표본(stratum)별 × 조건별 구성비와, 같은 집단의 사람 구성비, 쌍 차이"""
    rng = np.random.default_rng(seed)
    cols = ["probing"] + TARGETS
    hc = composition(human, "topic_key").set_index("topic_key")
    out: Dict[str, Any] = {"targets": TARGETS, "by_sample": {}}
    ai = ai.copy()
    ai["sample"] = np.where(ai["stratum"].astype(str).str.contains(r"\|"), "comparison", ai["stratum"].astype(str))
    for sample, s in ai.groupby("sample"):
        res: Dict[str, Any] = {"n_groups": int(s["topic_key"].nunique()), "n_utterances": int(len(s)), "conditions": {}}
        keys = sorted(set(s["topic_key"]) & set(hc.index))
        res["human_same_groups"] = _mean_ci(hc.loc[keys], cols, boot, rng) | {"n_groups": len(keys)}
        for lab, g in s.groupby("label"):
            ac = composition(g, "topic_key").set_index("topic_key")
            res["conditions"][lab] = _mean_ci(ac, cols, boot, rng)
            common = sorted(set(ac.index) & set(hc.index))
            diff = (ac.loc[common, cols] - hc.loc[common, cols])
            res["conditions"][lab]["ai_minus_human_paired"] = _mean_ci(diff, cols, boot, rng) | {"n_pairs": len(common)}
        if {"A-baseline", "A-stateful"} <= set(s["label"]):
            b = composition(s[s["label"] == "A-baseline"], "topic_key").set_index("topic_key")
            t = composition(s[s["label"] == "A-stateful"], "topic_key").set_index("topic_key")
            common = sorted(set(b.index) & set(t.index))
            res["stateful_minus_baseline_paired"] = _mean_ci(t.loc[common, cols] - b.loc[common, cols], cols, boot, rng) | {"n_pairs": len(common)}
        out["by_sample"][sample] = res
    return out


def coder_agreement(a: pd.DataFrame, b: pd.DataFrame) -> Dict[str, Any]:
    """두 코더의 같은 발언 라벨 일치율과 κ (코더 간 일관성; 정확성이 아님)"""
    m = a.merge(b, on=["discussion_id", "seq"], suffixes=("_a", "_b")).dropna(subset=["type_a", "type_b", "target_a", "target_b"])
    out = {"n": int(len(m))}
    for col in ("type", "target"):
        x, y = m[f"{col}_a"], m[f"{col}_b"]
        po = float((x == y).mean())
        pe = sum(float((x == c).mean() * (y == c).mean()) for c in set(x) | set(y))
        out[col] = {"exact": po, "kappa": float((po - pe) / (1 - pe)) if pe < 1 else float("nan"),
                    "per_label_exact": {c: float((y[x == c] == c).mean()) for c in sorted(set(x))}}
    return out
