"""
혼합 모형 적합: lme4/lmerTest를 Rscript로 호출 (분석 계획: 로지스틱·선형 혼합 모형)

R에 lme4, lmerTest, jsonlite가 있어야 한다.
"""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

R_SCRIPT = Path(__file__).with_name("fit_mixed.R")


def available() -> bool:
    return shutil.which("Rscript") is not None


def fit(data: pd.DataFrame, formula: str, family: str = "gaussian") -> Dict[str, Any]:
    """{n, singular, messages, coefficients: {term: {estimate, se, df, p, ci_low, ci_high}}, groups}"""
    with tempfile.TemporaryDirectory() as tmp:
        csv, out = Path(tmp) / "data.csv", Path(tmp) / "out.json"
        data.to_csv(csv, index=False)
        proc = subprocess.run(["Rscript", str(R_SCRIPT), str(csv), formula, family, str(out)],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"R model failed ({formula}): {proc.stderr.strip()[-800:]}")
        res = json.loads(out.read_text())
    res["coefficients"] = {c["term"]: {k: v for k, v in c.items() if k != "term"} for c in res["coefficients"]}
    res["formula"], res["family"] = formula, family
    return res


# 수렴 실패로 보는 lme4 경고 (경계 적합 singular는 분산이 0으로 추정된 것이라 수렴 실패가 아님)
NONCONVERGENCE = ("failed to converge", "Hessian is numerically singular", "unable to evaluate scaled gradient",
                  "Model is nearly unidentifiable")


def converged(res: Dict[str, Any]) -> bool:
    msgs = res.get("messages") or []
    msgs = [msgs] if isinstance(msgs, str) else msgs
    return not any(k in m for m in msgs for k in NONCONVERGENCE)


def fixed_part(formula: str) -> str:
    """'y ~ a + b + (1 | g)' → 'y ~ a + b'"""
    out = re.sub(r"\+\s*\([^)]*\|[^)]*\)", "", formula)
    return re.sub(r"\s+", " ", out).strip()


def cluster_bootstrap(data: pd.DataFrame, formula: str, terms: List[str], family: str, clusters: List[str],
                      n_boot: int, seed: int) -> Dict[str, Dict[str, Any]]:
    """분석 계획 2절의 대체 방법: 고정 효과 모형(OLS / 로지스틱)의 추정치 + 다수준 군집 부트스트랩 구간.
    clusters = [상위, 하위]: 상위 군집을 복원 추출하고, 그 안에서 하위 군집을 다시 복원 추출한다"""
    import statsmodels.formula.api as smf
    fixed = fixed_part(formula)
    model = smf.logit if family == "binomial" else smf.ols

    def est(frame):
        return model(fixed, frame).fit(disp=0).params if family == "binomial" else model(fixed, frame).fit().params

    point = est(data)
    rng = np.random.default_rng(seed)
    top = data[clusters[0]].unique()
    draws = {t: [] for t in terms}
    for _ in range(n_boot):
        parts = []
        for i, c in enumerate(rng.choice(top, len(top), replace=True)):
            sub = data[data[clusters[0]] == c]
            if len(clusters) > 1:
                inner = sub[clusters[1]].unique()
                sub = pd.concat([sub[sub[clusters[1]] == b] for b in rng.choice(inner, len(inner), replace=True)])
            parts.append(sub.assign(**{clusters[0]: f"{c}#{i}"}))
        try:
            params = est(pd.concat(parts)).rename({"Intercept": "(Intercept)"})
        except Exception:
            continue
        for t in terms:
            if t in params:
                draws[t].append(params[t])
    point = point.rename({"Intercept": "(Intercept)"})
    out = {}
    for t in terms:
        d = np.asarray(draws[t])
        out[t] = {"estimate": float(point[t]), "ci": [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))],
                  "p": float(min(1.0, 2 * min(np.mean(d <= 0), np.mean(d >= 0)))), "se": float(d.std(ddof=1)),
                  "df": None, "n": int(len(data)), "n_boot_ok": int(len(d)),
                  "method": f"cluster bootstrap ({' > '.join(clusters)}), fixed effects {fixed}"}
    return out
