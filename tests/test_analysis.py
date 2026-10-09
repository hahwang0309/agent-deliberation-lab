"""연구 1 분석 모듈 (src/analysis): 보정, 충실도 지표, 제외 기준, 혼합 모형 연결"""
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from src.analysis import data as adata, fidelity, mixed, study1


def test_holm_step_down():
    res = study1.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": None})
    assert res["a"]["p_holm"] == pytest.approx(0.03) and res["a"]["reject"]
    assert res["c"]["p_holm"] == pytest.approx(0.06) and not res["c"]["reject"]
    assert res["b"]["p_holm"] == pytest.approx(0.06)  # 단조성: 앞 단계보다 작아지지 않음
    assert res["d"]["p_holm"] is None


def _human(rng, n_groups=40, per_group=12, items=("Q1", "Q2", "Q3")):
    rows = []
    for g in range(n_groups):
        for i in range(per_group):
            party = "123"[i % 3]
            for q in items:
                pre = int(rng.integers(0, 11))
                post = int(np.clip(round(pre * 0.6 + {"1": 1, "2": 7, "3": 4}[party] * 0.4 + rng.normal(0, 1.5)), 0, 10))
                rows.append({"group": f"g{g}", "party": party, "item": q, "pre": pre, "post": post})
    return pd.DataFrame(rows)


def _ai_from(human, rng, blocks=6, shift=0.0):
    """인간과 같은 과정에서 나온 AI 표본 (블록당 정당 2·2·1). shift만큼 사후 점수를 문항 평균 쪽으로 당김"""
    parts = []
    for q, hq in human.groupby("item"):
        center = hq["post"].mean()
        for b in range(blocks):
            for party, n in (("1", 2), ("2", 2), ("3", 1)):
                pool = hq[hq["party"] == party]
                pick = pool.iloc[rng.choice(len(pool), n, replace=False)].copy()
                pick["post"] = (1 - shift) * pick["post"] + shift * center
                parts.append(pick.assign(block=f"{q}-{b}"))
    return pd.concat(parts)[["item", "party", "pre", "post", "block"]]


def test_fidelity_ratio_is_near_one_under_null_and_rises_with_overconvergence():
    rng = np.random.default_rng(0)
    human = _human(rng)
    null = [fidelity.fidelity({"a": _ai_from(human, rng)}, human, rng)["a"]["FR"] for _ in range(6)]
    assert 0.75 < np.mean(null) < 1.25
    conv = fidelity.fidelity({"a": _ai_from(human, rng, shift=0.6)}, human, rng)["a"]["FR"]
    assert conv > np.mean(null) + 0.4


def test_fidelity_uses_only_items_the_ai_answered_and_bootstrap_pairs_conditions():
    rng = np.random.default_rng(1)
    human = _human(rng, items=("Q1", "Q2", "Q3", "Q4"))
    ai = _ai_from(human[human["item"] != "Q4"], rng, blocks=4)
    res = fidelity.fidelity({"base": ai, "state": ai}, human, rng)
    assert res["base"]["D_full"] == res["state"]["D_full"] and res["base"]["FR"] == res["state"]["FR"]
    boot = fidelity.bootstrap({"base": ai, "state": ai}, human, 5, seed=2)
    w = boot.pivot(index="rep", columns="condition", values="D_full")
    assert np.allclose(w["base"], w["state"])  # 같은 블록을 두 조건에 똑같이 재표집


def test_fixed_part_and_convergence_flags():
    assert mixed.fixed_part("y ~ a * b + side + (1 + q | set)") == "y ~ a * b + side"
    assert mixed.fixed_part("d ~ 1 + (1 | item)") == "d ~ 1"
    assert not mixed.converged({"messages": ["Model failed to converge with 1 negative eigenvalue"]})
    assert mixed.converged({"messages": "boundary (singular) fit: see help('isSingular')"})


def test_cluster_bootstrap_recovers_a_fixed_effect():
    rng = np.random.default_rng(3)
    rows = [{"block": f"b{b}", "item": f"i{b % 5}", "engine": e, "y": u + 0.8 * e + rng.normal(0, 0.3)}
            for b, u in enumerate(rng.normal(0, 1, 40)) for e in (0, 1)]
    res = mixed.cluster_bootstrap(pd.DataFrame(rows), "y ~ engine + (1 | block)", ["engine"], "gaussian",
                                  ["item", "block"], n_boot=200, seed=4)["engine"]
    assert res["ci"][0] < 0.8 < res["ci"][1] and res["p"] < 0.05 and "cluster bootstrap" in res["method"]


def test_study_keys_and_block_exclusion():
    assert adata.study_of("deli-1a2b3c4d") == "wason" and adata.study_of("variant-003") == "wason"
    assert adata.study_of("argq3-pro") == "argq" and adata.study_of("Q5A-g01") == "a1r"
    assert adata.a1r_set("Q5A-debranded-g00") == "debranded" and adata.a1r_set("Q5A-group13") == "small"
    runs = pd.DataFrame([
        {"model": "m", "study": "a1r", "topic_key": "Q5A-g00", "label": "A-baseline", "status": "completed"},
        {"model": "m", "study": "a1r", "topic_key": "Q5A-g00", "label": "B-materials", "status": "failed"},
        {"model": "m", "study": "a1r", "topic_key": "Q5A-g01", "label": "A-baseline", "status": "completed"},
    ])
    kept, log = adata.exclusions(runs, {"a1r": ["A-baseline", "B-materials"]})
    assert list(kept["topic_key"]) == ["Q5A-g01"] and log[0]["missing"] == ["B-materials"]


def _lme4_available():
    if not shutil.which("Rscript"):
        return False
    return subprocess.run(["Rscript", "-e", "library(lmerTest)"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _lme4_available(), reason="R lme4/lmerTest가 없음")
def test_r_mixed_model_bridge():
    rng = np.random.default_rng(5)
    rows = [{"block": f"b{b}", "engine": e, "y": u + 0.5 * e + rng.normal(0, 0.5)}
            for b, u in enumerate(rng.normal(0, 1, 30)) for e in (0, 1)]
    res = mixed.fit(pd.DataFrame(rows), "y ~ engine + (1 | block)")
    c = res["coefficients"]["engine"]
    assert c["ci_low"] < 0.5 < c["ci_high"] and c["df"] > 0 and res["groups"] == {"block": 30}
