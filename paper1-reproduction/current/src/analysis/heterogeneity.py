"""
N4: 문항 간 이질성 (study1-exploratory-plan.md 2-4). [탐색]

입력은 문항별 추정치 θ̂ (30,)와 그 표집 공분산 Σ (30×30, 재표집 복제 배열에서 계산). 모형 θ̂ ~ N(μ·1, τ²·I + Σ)의 τ²를 REML로 추정하고,
프로파일 우도 구간과 복제 배열에 같은 추정을 반복한 백분위 구간을 함께 낸다. 분산비는 사전 규칙(불안정 판정)으로만 보고한다.
"""
from typing import Any, Dict, Optional

import numpy as np
from scipy import optimize, stats

CHI2_95 = stats.chi2.ppf(0.95, 1)


def covariance(reps: np.ndarray, ridge: float = 1e-8) -> np.ndarray:
    """복제 배열 [n_boot × 문항] → 공분산 (결측 복제는 제외, 대각에 작은 능선)"""
    r = reps[~np.isnan(reps).any(axis=1)]
    s = np.cov(r, rowvar=False, ddof=1)
    return s + ridge * np.eye(s.shape[0])


def _reml_ll(tau2: float, theta: np.ndarray, sigma: np.ndarray) -> float:
    n = len(theta)
    v = tau2 * np.eye(n) + sigma
    try:
        L = np.linalg.cholesky(v)
    except np.linalg.LinAlgError:
        return -np.inf
    logdet = 2 * np.log(np.diag(L)).sum()
    one = np.ones(n)
    vi_one = np.linalg.solve(v, one)
    vi_theta = np.linalg.solve(v, theta)
    denom = one @ vi_one
    mu = (one @ vi_theta) / denom
    r = theta - mu
    quad = r @ np.linalg.solve(v, r)
    return float(-0.5 * (logdet + np.log(denom) + quad))


def reml_tau2(theta: np.ndarray, sigma: np.ndarray) -> Dict[str, Any]:
    """τ²의 REML 추정, 프로파일 우도 95% 구간, 수치 SE (경계 0이면 None)"""
    theta = np.asarray(theta, float)
    ok = ~np.isnan(theta)
    theta, sigma = theta[ok], sigma[np.ix_(ok, ok)]
    upper = max(10 * np.var(theta, ddof=1), 1e-6) + 10 * np.mean(np.diag(sigma))
    res = optimize.minimize_scalar(lambda t: -_reml_ll(t, theta, sigma), bounds=(0.0, upper), method="bounded",
                                   options={"xatol": 1e-8})
    tau2 = float(res.x)
    ll_max = _reml_ll(tau2, theta, sigma)
    if _reml_ll(0.0, theta, sigma) >= ll_max - 1e-9:
        tau2, ll_max = 0.0, _reml_ll(0.0, theta, sigma)

    def gap(t):
        return 2 * (ll_max - _reml_ll(t, theta, sigma)) - CHI2_95

    lo = 0.0 if gap(0.0) <= 0 else float(optimize.brentq(gap, 0.0, tau2))
    hi_bound = upper
    while gap(hi_bound) < 0 and hi_bound < 1e6:
        hi_bound *= 10
    hi = float(optimize.brentq(gap, tau2, hi_bound)) if gap(hi_bound) >= 0 else float("inf")
    se: Optional[float] = None
    if tau2 > 0:
        h = max(tau2 * 1e-3, 1e-6)
        d2 = (_reml_ll(tau2 + h, theta, sigma) - 2 * ll_max + _reml_ll(max(tau2 - h, 0), theta, sigma)) / (h * h)
        se = float(1 / np.sqrt(-d2)) if d2 < 0 else None
    mu_v = tau2 * np.eye(len(theta)) + sigma
    one = np.ones(len(theta))
    mu = float((one @ np.linalg.solve(mu_v, theta)) / (one @ np.linalg.solve(mu_v, one)))
    return {"tau2": tau2, "tau": float(np.sqrt(tau2)), "profile_ci": [lo, hi], "se_numeric": se, "mu": mu, "n_items": int(ok.sum()),
            "mean_sampling_var": float(np.mean(np.diag(sigma))), "ll": ll_max}


def bootstrap_tau2(reps: np.ndarray, sigma: np.ndarray, max_reps: int = 2000) -> np.ndarray:
    """복제 배열의 각 행에 같은 Σ로 τ²를 다시 추정 → 백분위 구간용 분포"""
    r = reps[~np.isnan(reps).any(axis=1)][:max_reps]
    out = np.empty(len(r))
    for i, th in enumerate(r):
        upper = max(10 * np.var(th, ddof=1), 1e-6) + 10 * np.mean(np.diag(sigma))
        res = optimize.minimize_scalar(lambda t: -_reml_ll(t, th, sigma), bounds=(0.0, upper), method="bounded", options={"xatol": 1e-6})
        out[i] = res.x if _reml_ll(res.x, th, sigma) > _reml_ll(0.0, th, sigma) else 0.0
    return out


def naive_vr_component(theta: np.ndarray, sigma: np.ndarray, reps: np.ndarray) -> Dict[str, Any]:
    """민감도: 관측 문항 간 분산 − 평균 표집 분산, 복제 행마다 같은 값으로 SE"""
    theta = np.asarray(theta, float)
    point = float(np.var(theta[~np.isnan(theta)], ddof=1) - np.mean(np.diag(sigma)))
    r = reps[~np.isnan(reps).any(axis=1)]
    draws = np.var(r, axis=1, ddof=1) - np.mean(np.diag(sigma))
    return {"estimate": point, "se_boot": float(draws.std(ddof=1)), "ci": [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))]}


def ratio_with_rules(num: Dict[str, Any], den: Dict[str, Any], num_draws: np.ndarray, den_draws: np.ndarray) -> Dict[str, Any]:
    """τ²_AI / τ²_H. 규칙(계획 2-4): 분모 0 → 미산출; 분모 구간 하한 0 또는 분모 < 2·SE → 불안정(점추정만 괄호). 음수를 0으로 바꾸지 않음"""
    out: Dict[str, Any] = {"numerator_tau2": num["tau2"], "denominator_tau2": den["tau2"]}
    if den["tau2"] <= 0:
        out.update(ratio=None, status="not_computed (denominator tau2 = 0)")
        return out
    unstable = den["profile_ci"][0] <= 1e-10 or (den.get("se_numeric") is not None and den["tau2"] < 2 * den["se_numeric"])
    out["ratio"] = float(num["tau2"] / den["tau2"])
    n = min(len(num_draws), len(den_draws))
    ok = den_draws[:n] > 0
    if ok.sum() > 10:
        rr = num_draws[:n][ok] / den_draws[:n][ok]
        out["ratio_boot_ci"] = [float(np.percentile(rr, 2.5)), float(np.percentile(rr, 97.5))]
        out["share_boot_denominator_zero"] = float(1 - ok.mean())
    out["status"] = "unstable (report point estimate in parentheses only)" if unstable else "ok"
    return out


def naive_ratio_with_rules(num: Dict[str, Any], den: Dict[str, Any]) -> Dict[str, Any]:
    """민감도 VR: 분모 ≤ 0 → 미산출; 분모 < 2 × 부트스트랩 SE → 불안정"""
    if den["estimate"] <= 0:
        return {"ratio": None, "status": "not_computed (denominator <= 0)"}
    status = "unstable" if den["estimate"] < 2 * den["se_boot"] else "ok"
    return {"ratio": float(num["estimate"] / den["estimate"]), "status": status}


def spearman_with_boot(x: np.ndarray, y: np.ndarray, x_reps: np.ndarray, y_reps: np.ndarray) -> Dict[str, Any]:
    """문항 30개의 순위 상관과, 인간·AI 복제 행을 짝지어 다시 계산한 백분위 구간 (두 재표집은 독립)"""
    ok = ~np.isnan(x) & ~np.isnan(y)
    rho = float(stats.spearmanr(x[ok], y[ok]).correlation)
    n = min(len(x_reps), len(y_reps))
    draws = []
    for i in range(n):
        a, b = x_reps[i], y_reps[i]
        m = ~np.isnan(a) & ~np.isnan(b)
        if m.sum() > 3:
            draws.append(stats.spearmanr(a[m], b[m]).correlation)
    draws = np.asarray(draws)
    return {"rho": rho, "ci": [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))], "n_items": int(ok.sum()),
            "note": "CI pairs independent human and AI resamples; 30 items are the effective sample"}
