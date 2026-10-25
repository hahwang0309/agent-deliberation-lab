"""Post-hoc within-party dispersion, pooling discussion groups within each item.

The target is the equally weighted mean over a fixed set of policy items.
Population SD (ddof=0) and complete paired pre/post observations are used.
"""
from itertools import combinations

import numpy as np
import pandas as pd

PARTIES = ("1", "2")
ARMS = ("C-reanswer", "B-materials", "A-baseline", "A-stateful")
METRICS = ("sd_dem", "sd_rep", "party_gap", "within_party_variance", "between_party_variance", "total_variance")


def metrics(moments):
    """Input (..., party=2, time=2, [n,sum,sum_sq]); output (...,time,metric)."""
    n = moments[..., 0]
    if np.any(n <= 0):
        raise ValueError("Each item/time must contain both parties")
    mean = moments[..., 1] / n
    var = np.maximum(moments[..., 2] / n - mean**2, 0)
    weights = n / n.sum(axis=-2, keepdims=True)
    within = (weights * var).sum(axis=-2)
    gap = np.abs(mean[..., 0, :] - mean[..., 1, :])
    between = weights[..., 0, :] * weights[..., 1, :] * gap**2
    return np.stack([np.sqrt(var[..., 0, :]), np.sqrt(var[..., 1, :]), gap,
                     within, between, within + between], axis=-1)


def summary(point, draws):
    return {"estimate": float(point), "ci": np.quantile(draws, [.025, .975]).tolist()}


def package(arms, point, draws):
    """point=(arm,time,metric); draws=(bootstrap,arm,time,metric)."""
    out = {"levels": {}, "contrasts": {}}
    for a, arm in enumerate(arms):
        out["levels"][arm] = {}
        for m, name in enumerate(METRICS):
            out["levels"][arm][name] = {
                "pre": summary(point[a, 0, m], draws[:, a, 0, m]),
                "post": summary(point[a, 1, m], draws[:, a, 1, m]),
                "change": summary(point[a, 1, m] - point[a, 0, m], draws[:, a, 1, m] - draws[:, a, 0, m]),
            }
    for first, second in combinations(range(len(arms)), 2):
        # Later arm minus earlier arm; all AI contrasts use matched data/draws.
        key = arms[second] + " - " + arms[first]
        pc = (point[second, 1] - point[second, 0]) - (point[first, 1] - point[first, 0])
        dc = (draws[:, second, 1] - draws[:, second, 0]) - (draws[:, first, 1] - draws[:, first, 0])
        out["contrasts"][key] = {name: summary(pc[m], dc[:, m]) for m, name in enumerate(METRICS)}
    return out


def prepare_ai(frame, items):
    f = frame[frame.label.isin(ARMS) & frame.item_id.isin(items)].copy()
    f["party"] = f.party.astype(str)
    f = f[f.party.isin(PARTIES)]
    keys = ["block", "participant", "item_id"]
    if f.duplicated(keys + ["label"]).any():
        raise ValueError("Duplicate agent/condition records")
    total = len(f)
    f = f.dropna(subset=["pre", "post"])
    valid = f.groupby(keys).label.nunique()
    valid = valid[valid == len(ARMS)].index
    f = f.set_index(keys).loc[lambda x: x.index.isin(valid)].reset_index()
    if f.empty:
        raise ValueError("No complete paired agents")
    if not f.groupby(keys)["pre"].nunique().eq(1).all():
        raise ValueError("Initial positions differ across conditions")
    if not f.groupby(keys)["party"].nunique().eq(1).all():
        raise ValueError("Party changes across conditions")
    return f, total - len(f)


def analyze_ai(frame, items, n_boot=2000, seed=2026):
    f, excluded = prepare_ai(frame, items)
    if not f[["pre", "post"]].apply(lambda c: c.between(0, 10).all()).all():
        raise ValueError("Scores outside 0-10")
    rng = np.random.default_rng(seed)
    point = np.zeros((len(ARMS), 2, len(METRICS)))
    draws = np.zeros((n_boot, len(ARMS), 2, len(METRICS)))
    by_item, counts = [], []
    for item in items:
        g = f[f.item_id == item]
        blocks = sorted(g.block.unique())
        if not blocks:
            raise ValueError(f"Missing item: {item}")
        bi = {b: i for i, b in enumerate(blocks)}
        tensor = np.zeros((len(blocks), len(ARMS), 2, 2, 3))
        ix = (g.block.map(bi).to_numpy(), g.label.map(dict(zip(ARMS, range(len(ARMS))))).to_numpy(),
              g.party.map({"1": 0, "2": 1}).to_numpy())
        for t, col in enumerate(["pre", "post"]):
            v = g[col].to_numpy(float)
            for k, val in enumerate([np.ones(len(g)), v, v**2]):
                np.add.at(tensor, ix + (t, k), val)
        pm = metrics(tensor.sum(axis=0))
        # Resample the same whole discussion blocks in every condition.
        w = rng.multinomial(len(blocks), np.ones(len(blocks))/len(blocks), size=n_boot)
        sampled = (w @ tensor.reshape(len(blocks), -1)).reshape(n_boot, len(ARMS), 2, 2, 3)
        bm = metrics(sampled)
        point += pm / len(items)
        draws += bm / len(items)
        for a, arm in enumerate(ARMS):
            for m, name in enumerate(METRICS):
                by_item.append({"item": item, "arm": arm, "metric": name,
                                "pre": float(pm[a, 0, m]), "post": float(pm[a, 1, m]),
                                "change": float(pm[a, 1, m] - pm[a, 0, m])})
        counts.append({"item": item, "blocks": len(blocks), "agents_per_party":
                       g[g.label == ARMS[0]].groupby("party").size().to_dict()})
    result = package(ARMS, point, draws)
    result["sample"] = {"items": len(items), "blocks": int(f.block.nunique()),
                        "excluded_condition_rows_for_pairing": excluded,
                        "agent_item_records_per_condition": int(len(f)/len(ARMS)),
                        "distinct_personas": int(f.persona.nunique()), "by_item": counts}
    result["resampling"] = "Fixed 30 items; paired whole-block bootstrap independently within item; percentile CI"
    return result, by_item


def human_arm(frame, items, unit, n_boot, rng):
    f = frame[frame.item.isin(items)].copy()
    f["party"] = f.party.astype(str)
    f = f[f.party.isin(PARTIES)].dropna(subset=["pre", "post"])
    clusters = sorted(f[unit].unique())
    tensor = np.zeros((len(clusters), len(items), 2, 2, 3))
    ix = (f[unit].map(dict(zip(clusters, range(len(clusters))))).to_numpy(),
          f.item.map(dict(zip(items, range(len(items))))).to_numpy(),
          f.party.map({"1": 0, "2": 1}).to_numpy())
    for t, col in enumerate(["pre", "post"]):
        v = f[col].to_numpy(float)
        for k, val in enumerate([np.ones(len(f)), v, v**2]):
            np.add.at(tensor, ix + (t, k), val)
    pm = metrics(tensor.sum(axis=0))
    w = rng.multinomial(len(clusters), np.ones(len(clusters))/len(clusters), size=n_boot)
    sampled = (w @ tensor.reshape(len(clusters), -1)).reshape(n_boot, len(items), 2, 2, 3)
    bm = metrics(sampled)
    counts = {"clusters": len(clusters), "people": int(f.row.nunique()), "person_item_records": len(f),
              "people_by_party": f.drop_duplicates("row").groupby("party").size().to_dict()}
    per_item = [{"item": item, "metric": name, "pre": float(pm[i,0,m]), "post": float(pm[i,1,m]),
                 "change": float(pm[i,1,m]-pm[i,0,m])} for i,item in enumerate(items) for m,name in enumerate(METRICS)]
    return pm.mean(axis=0), bm.mean(axis=1), counts, per_item


def analyze_human(delib, control, items, n_boot=2000, seed=2026):
    rng = np.random.default_rng(seed)
    c, cb, cn, ci = human_arm(control, items, "row", n_boot, rng)
    d, db, dn, di = human_arm(delib, items, "group", n_boot, rng)
    result = package(["control", "deliberation"], np.stack([c,d]), np.stack([cb,db], axis=1))
    result["sample"] = {"control": cn, "deliberation": dn, "items": len(items)}
    result["resampling"] = "Fixed 30 items; all-item participant bootstrap for control, all-item discussion-group bootstrap for deliberation; percentile CI"
    return result, [{**r,"arm":arm} for arm,rows in [("control",ci),("deliberation",di)] for r in rows]
