"""
연구 1 검정력 시뮬레이션 (분석 계획 7절)

- 효과 크기: 분석 계획의 표본 크기 계획 가정(외부 근거)만 쓴다. 파일럿에서 가져오지 않는다.
- 분산: 인간 쪽은 DeliData·A1R 실제 자료, AI 쪽은 인간 분산의 0.5·1·2배 시나리오.
  1-C는 인간 자료가 없어 분산 추정 파일럿(variance estimation / variance calibration)의 분산 성분을 쓴다.
- 검정: 분석 계획의 모형을 시뮬레이션에서 돌리기 쉬운 근사로 적합한다(근사 방식은 각 함수 주석).

사용 예:
  python scripts/power_simulation.py h1 --sims 300
  python scripts/power_simulation.py h3 --pilot-db data/pilot8/pilot8-claude.db data/pilot8/pilot8-gemini.db
  python scripts/power_simulation.py h2b
"""
import argparse
import json
import sqlite3
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

ALPHA = 0.05  # --alpha로 바꾼다 (Holm 보정의 보수적 하한: 가족 검정 수 k에 대해 0.05/k)
SCENARIOS = (0.5, 1.0, 2.0)


def expit(x):
    return 1 / (1 + np.exp(-x))


# ---------------- H1: truth wins의 인간·AI 차이 (1-A) ----------------

def human_wason_groups():
    """DeliData 집단(2~6명, 복제 대상과 같음): 초기 정답자 수 k(0/1/2+)와 토론 후 개인 정답"""
    from src.cases import wason
    groups = [g for g in wason.load_delidata(str(ROOT / "data/raw/delidata"))
              if len(g.solo) >= 2 and all(v is not None for v in g.solo.values())]
    out = []
    for i, g in enumerate(groups):
        corr = set(wason.correct_cards(g.cards))
        k = min(2, sum(set(v) == corr for v in g.solo.values()))
        out.append((i, k, [int(set(g.final[m]) == corr) for m in g.solo]))
    return out


def fit_human_h1(groups, rng, grid=np.linspace(0.5, 6.0, 23)):
    """집단 무작위 절편 로지스틱: 개인 정답률과 '전원 정답 또는 전원 오답' 비율을 맞추는 (a_k, s)"""
    obs_rate = {k: np.mean([y for _, kk, ys in groups if kk == k for y in ys]) for k in (0, 1, 2)}
    obs_aon = np.mean([sum(ys) in (0, len(ys)) for _, _, ys in groups])
    best = None
    for s in grid:
        a = {}
        for k in (0, 1, 2):  # 주변 정답률을 맞추는 절편 (이분 탐색)
            lo, hi = -10.0, 10.0
            z = rng.normal(0, s, 20000)
            for _ in range(40):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if expit(mid + z).mean() < obs_rate[k] else (lo, mid)
            a[k] = (lo + hi) / 2
        sim = []
        for _, k, ys_obs in groups:
            p = expit(a[k] + rng.normal(0, s))
            ys = rng.random(len(ys_obs)) < p
            sim.append(ys.sum() in (0, len(ys_obs)))
        err = abs(np.mean(sim) - obs_aon)
        if best is None or err < best[0]:
            best = (err, s, a)
    return best[1], best[2], obs_rate, obs_aon


def majority_prob(a, s, n=40000, rng=None):
    z = rng.normal(0, s, n)
    ys = rng.random((n, 3)) < expit(a + z)[:, None]
    return (ys.sum(1) >= 2).mean()


def h1(args):
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    rng = np.random.default_rng(args.seed)
    groups = human_wason_groups()
    s_h, a_h, rate, aon = fit_human_h1(groups, rng)
    print(f"human fit: block SD {s_h:.2f}, intercepts { {k: round(v, 2) for k, v in a_h.items()} }, "
          f"observed individual correct {dict((k, round(v, 3)) for k, v in rate.items())}, all-or-none {aon:.2f}")
    target_h, target_ai = 0.61, 0.45  # 분석 계획 7절: 초기 정답자 1명 집단의 과반 정답 확률
    print(f"model majority-correct P(k=1): human {majority_prob(a_h[1], s_h, rng=rng):.3f} (assumption {target_h})")
    rows = []
    for scen in SCENARIOS:
        s_ai = s_h * np.sqrt(scen)
        # AI 절편: k=0, 2는 인간과 같은 주변(개인) 정답률이 되도록(가정에 없는 차이는 0),
        # k=1은 과반 정답 확률이 0.45가 되도록. 분산이 다르면 같은 절편이라도 주변 확률이 달라지므로 다시 맞춘다
        a_ai = {}
        z = rng.normal(0, s_ai, 40000)
        for k in (0, 2):
            lo, hi = -12.0, 12.0
            for _ in range(40):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if expit(mid + z).mean() < rate[k] else (lo, mid)
            a_ai[k] = (lo + hi) / 2
        lo, hi = -6.0, 6.0
        for _ in range(30):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if majority_prob(mid, s_ai, rng=rng) < target_ai else (lo, mid)
        a_ai[1] = (lo + hi) / 2
        for reps in args.reps:
            hits = 0
            for _ in range(args.sims):
                data = []
                for b, k, ys_obs in groups:
                    n = len(ys_obs)
                    zh = rng.normal(0, s_h)
                    data += [(b, k, 0, int(rng.random() < expit(a_h[k] + zh))) for _ in range(n)]
                    v = rng.normal(0, s_ai * np.sqrt(0.5))  # AI 블록 효과와 실행 효과를 반씩
                    for r in range(reps):
                        w = rng.normal(0, s_ai * np.sqrt(0.5))
                        data += [(b, k, 1, int(rng.random() < expit(a_ai[k] + v + w))) for _ in range(n)]
                df = pd.DataFrame(data, columns=["block", "k", "ai", "y"])
                df["k"] = df["k"].astype("category")
                # 근사: 로지스틱 혼합 모형 대신 블록 군집 GEE(교환 상관). 검정 대상은 k(1 vs 0) × agent 상호작용
                m = smf.gee("y ~ C(k) * ai", "block", df, family=sm.families.Binomial(),
                            cov_struct=sm.cov_struct.Exchangeable()).fit()
                hits += m.pvalues["C(k)[T.1]:ai"] < ALPHA
            rows.append({"hypothesis": "H1", "ai_variance_x_human": scen, "ai_reps_per_group": reps,
                         "groups": len(groups), "power": hits / args.sims})
            print(rows[-1], flush=True)
    return rows


# ---------------- H3: 논증의 질 × 지지 (1-C) ----------------

def pilot_argq_variance(dbs):
    """분산 추정 파일럿에서 1-C 분산 성분: 세트(주제 × 표적 입장) 절편, 세트별 질 기울기, 잔차 (점수 0~100)"""
    import statsmodels.formula.api as smf
    out = []
    for db in dbs:
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        rows = []
        for d in con.execute("select id, config from discussions where status='completed'"):
            e = json.loads(d["config"])["experiment"]
            if "argq" not in e["batch"] or e["label"] in ("C-reanswer", "positive-control"):
                continue
            sv = {r["phase"]: r["score"] for r in con.execute(
                "select phase, score from survey_responses where discussion_id=? and participant='Jordan'", (d["id"],))}
            if None in (sv.get("pre"), sv.get("post")):
                continue
            delta = (sv["pre"] - sv["post"]) if e["topic_key"].endswith("pro") else (sv["post"] - sv["pre"])
            q, s = e["label"].split("-")
            rows.append({"set": e["topic_key"], "q": 0.5 if q == "strong" else -0.5,
                         "sup": 0.5 if s == "majority" else -0.5, "delta": delta})
        df = pd.DataFrame(rows)
        m = smf.mixedlm("delta ~ q * sup", df, groups="set", re_formula="~q").fit()
        sd_set = float(np.sqrt(max(m.cov_re.iloc[0, 0], 0)))
        sd_slope = float(np.sqrt(max(m.cov_re.iloc[1, 1], 0)))
        out.append({"db": Path(db).name, "n": len(df), "sd_set": round(sd_set, 2), "sd_q_slope": round(sd_slope, 2),
                    "sd_resid": round(float(np.sqrt(m.scale)), 2)})
    return out


def h3(args):
    import statsmodels.formula.api as smf
    rng = np.random.default_rng(args.seed)
    comps = pilot_argq_variance(args.pilot_db)
    for c in comps:
        print("variance calibration:", c)
    effect = 0.3 / 6 * 100  # 분석 계획 7절: 7점 척도 0.3점 = 0~100 척도 5점
    rows = []
    for c in comps:
        for scen in SCENARIOS:  # 파일럿 분산의 0.5·1·2배
            sd_set, sd_slope, sd_res = (np.sqrt(scen) * c[k] for k in ("sd_set", "sd_q_slope", "sd_resid"))
            for reps in args.reps:
                hits = {"H3a": 0, "H3b": 0, "H3c": 0}
                for _ in range(args.sims):
                    data = []
                    for s in range(args.sets):
                        u, slope = rng.normal(0, sd_set), rng.normal(0, sd_slope)
                        for q in (-0.5, 0.5):
                            for sup in (-0.5, 0.5):
                                mu = u + (effect + slope) * q + effect * sup + effect * q * sup
                                data += [(s, q, sup, mu + rng.normal(0, sd_res)) for _ in range(reps)]
                    df = pd.DataFrame(data, columns=["set", "q", "sup", "delta"])
                    try:
                        m = smf.mixedlm("delta ~ q * sup", df, groups="set", re_formula="~q").fit()
                    except Exception:
                        continue
                    hits["H3a"] += m.pvalues["q"] < ALPHA
                    hits["H3b"] += m.pvalues["sup"] < ALPHA
                    hits["H3c"] += m.pvalues["q:sup"] < ALPHA
                rows.append({"hypothesis": "H3", "variance_from": c["db"], "x_pilot_variance": scen, "sets": args.sets,
                             "reps_per_cell": reps, **{k: v / args.sims for k, v in hits.items()}})
                print(rows[-1], flush=True)
    return rows


# ---------------- H2b: 상호작용 효과 A − B (1-B) ----------------

def human_a1r_residual_sd(items):
    """A1R 숙의 참가자의 사후 점수에서 사전 점수·정당·문항으로 설명되지 않는 잔차 SD (0~10)"""
    import csv
    import statsmodels.formula.api as smf
    rows = []
    with open(ROOT / "data/raw/a1r/dataset.tab", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["CONDITION"] != "1" or r["POST"] != "1":
                continue
            for q in items:
                try:
                    a, b = float(r[q]), float(r["T2" + q])
                except ValueError:
                    continue
                if 0 <= a <= 10 and 0 <= b <= 10:
                    rows.append({"item": q, "party": r["PARTYID3"], "pre": a, "post": b})
    df = pd.DataFrame(rows)
    m = smf.ols("post ~ pre * C(item) + C(party)", df).fit()
    return float(np.sqrt(m.scale)), len(df)


def h2b(args):
    import statsmodels.formula.api as smf
    from src.cases import texts
    rng = np.random.default_rng(args.seed)
    t = texts()["a1r"]
    items = t["development"] + t["locked"]
    sd_h, n = human_a1r_residual_sd(items)
    print(f"human residual SD of post given pre/party/item: {sd_h:.2f} (n={n})")
    effect = 0.3  # 분석 계획 7절: A − B = 0.3점
    rows = []
    for scen in SCENARIOS:
        sd = sd_h * np.sqrt(scen)
        for blocks in args.blocks:
            hits = 0
            for _ in range(args.sims):
                data = []
                for it in range(len(items)):
                    item_u = rng.normal(0, 0.3 * sd)
                    for b in range(blocks):
                        blk = rng.normal(0, 0.5 * sd)
                        slope = rng.normal(0, 0.3 * sd)  # 블록별 조건 효과의 이질성
                        for p in range(5):  # 같은 페르소나가 두 조건에 복제됨
                            person = rng.normal(0, 0.5 * sd)
                            for cond in (0, 1):
                                y = item_u + blk + person + cond * (effect + slope) + rng.normal(0, sd)
                                data.append((f"{it}-{b}", it, cond, y))
                df = pd.DataFrame(data, columns=["block", "item", "cond", "post"])
                # 근사: 계획의 (1 + condition | block) + (1 | item) + (1 | persona) 중 블록 무작위 절편·기울기만 두고
                # 문항은 고정 효과로 흡수 (같은 페르소나 쌍의 상관은 블록 효과로 일부 반영)
                try:
                    m = smf.mixedlm("post ~ cond + C(item)", df, groups="block", re_formula="~cond").fit()
                except Exception:
                    continue
                hits += m.pvalues["cond"] < ALPHA
            rows.append({"hypothesis": "H2b", "ai_variance_x_human": scen, "items": len(items),
                         "groups_per_item": blocks, "power": hits / args.sims})
            print(rows[-1], flush=True)
    return rows


# ---------------- H2·H5: 충실도 비율 FR (1-B) ----------------

def a1r_delegates(items):
    """숙의 참가자: 문항별 (소집단, 정당, 사전, 사후)"""
    import csv
    rows = []
    with open(ROOT / "data/raw/a1r/dataset.tab", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["CONDITION"] != "1" or r["POST"] != "1" or r["PARTYID3"] not in ("1", "2", "3"):
                continue
            for q in items:
                try:
                    a, b = float(r[q]), float(r["T2" + q])
                except ValueError:
                    continue
                if 0 <= a <= 10 and 0 <= b <= 10:
                    rows.append({"item": q, "group": r["GROUP"], "party": r["PARTYID3"], "pre": a, "post": b})
    df = pd.DataFrame(rows)
    df["bin"] = pd.cut(df["pre"], [-0.5, 1.5, 3.5, 6.5, 8.5, 10.5], labels=False)  # 0~1, 2~3, 4~6, 7~8, 9~10
    return df


def _w(a, b):
    from scipy.stats import wasserstein_distance
    return wasserstein_distance(a, b) / 10 if len(a) and len(b) else np.nan


class FidelityModel:
    """충실도 비율 FR (재설계, 2026-10-08).

    - 값: 사후 점수 − 문항의 인간 사후 평균 (문항 효과 제거)
    - 셀: 정당 × 사전 구간을 문항에 걸쳐 합침 (문항 × 정당 × 구간 셀은 AI 사례가 2~3개라 표본 잡음이 지배)
    - 분자: AI 표본과 인간 반쪽 B의 셀별 Wasserstein 거리, 인간 빈도 가중
    - 분모: 인간 반쪽 A에서 AI와 같은 구조(문항마다 집단 수 × 민주2·공화2·무당1)로 비복원 추출한 유사 AI와 반쪽 B의 거리
    - 반분은 소집단 단위, 여러 번 반복해 평균. 귀무(AI = 인간 생성 과정)에서 FR ≈ 1 (시뮬레이션으로 확인)
    시뮬레이션: 인간 숙의 참가자 자료로 생성 모형(문항·정당·사전 + 소집단 효과)을 적합해 인간·AI를 함께 생성.
    AI는 문항 인간 평균 쪽으로 κ만큼 끌어당긴다(과잉 수렴, FR 가정의 근거가 DEBATE의 수렴 차이)."""
    MIX = (("1", 2), ("2", 2), ("3", 1))

    def __init__(self, items, rng):
        import statsmodels.formula.api as smf
        self.rng = rng
        df = a1r_delegates(items)
        df["ig"] = df["item"] + "_" + df["group"]
        m = smf.mixedlm("post ~ pre * C(item) + C(party)", df, groups="ig").fit()
        self.tau, self.sig = float(np.sqrt(m.cov_re.iloc[0, 0])), float(np.sqrt(m.scale))
        df["mu"] = m.predict(df)
        self.df = df
        self.center = df.groupby("item")["post"].mean().to_dict()

    def gen(self, frame, groupcol, scen=1.0, kappa=0.0):
        g = {k: self.rng.normal(0, self.tau * np.sqrt(scen)) for k in frame[groupcol].unique()}
        y = frame["mu"].to_numpy() + frame[groupcol].map(g).to_numpy() + self.rng.normal(0, self.sig, len(frame))
        y = (1 - kappa) * y + kappa * frame["item"].map(self.center).to_numpy()
        return np.clip(np.round(y), 0, 10)

    def blocks(self, frame, n_blocks, replace):
        out = []
        for q, fq in frame.groupby("item"):
            pools = {p: fq[fq["party"] == p] for p, _ in self.MIX}
            used = set()
            for b in range(n_blocks):
                for party, n in self.MIX:
                    pool = pools[party] if replace else pools[party][~pools[party].index.isin(used)]
                    if len(pool) < n:
                        return None
                    pick = pool.sample(n, random_state=int(self.rng.integers(1e9)))
                    used |= set(pick.index)
                    out.append(pick.assign(blk=f"{q}_{b}"))
        return pd.concat(out)

    def dist(self, sample, ref, col):
        from scipy.stats import wasserstein_distance
        rv = ref[col] - ref["item"].map(self.center)
        sv = sample[col] - sample["item"].map(self.center)
        rc = {c: rv[g.index].to_numpy() for c, g in ref.groupby(["party", "bin"])}
        num = wsum = 0.0
        for c, g in sample.groupby(["party", "bin"]):
            if c in rc:
                w = len(rc[c])
                num += w * wasserstein_distance(sv[g.index].to_numpy(), rc[c])
                wsum += w
        return num / wsum

    def fr_pair(self, n_blocks, scen, kappas, nsplit=4):
        """같은 인간 자료·반분·AI 페르소나에서 κ별 FR (H5는 두 조건이 같은 집단을 공유)"""
        human = self.df.copy()
        human["sim"] = self.gen(human, "ig")
        personas = self.blocks(self.df, n_blocks, True)
        ais = []
        for k in kappas:
            a = personas.copy()
            a["sim"] = self.gen(a, "blk", scen, k)
            ais.append(a)
        groups = human["group"].unique()
        nums, den = [[] for _ in kappas], []
        for _ in range(nsplit):
            side = dict(zip(groups, self.rng.random(len(groups)) < 0.5))
            mask = human["group"].map(side)
            a_half, b_half = human[mask], human[~mask]
            pseudo = self.blocks(a_half, n_blocks, False)
            if pseudo is None:
                continue
            den.append(self.dist(pseudo, b_half, "sim"))
            for i, a in enumerate(ais):
                nums[i].append(self.dist(a, b_half, "sim"))
        return [np.mean(n) / np.mean(den) for n in nums]


def h2h5(args):
    """H2: FR = 1.5 (분석 계획 7절). H5: 기준선 FR 1.5 → 상태 기반 1.3 (ΔFR = −0.2, 같은 집단 복제).
    검정: 귀무(κ 같음)에서 시뮬레이션한 분포의 임계값과 비교 (H2 양측 0.05, H5 지지는 ΔFR이 귀무 2.5% 분위수 미만)"""
    from src.cases import texts
    rng = np.random.default_rng(args.seed)
    t = texts()["a1r"]
    items = {"h2": t["development"] + t["locked"], "h5": t["locked"]}[args.target]
    fm = FidelityModel(items, rng)
    print(f"fitted human model: group SD {fm.tau:.2f}, residual SD {fm.sig:.2f}", flush=True)

    def kappa_for(target, blocks, scen):
        """FR(κ) 곡선을 격자에서 평균 내 보간해 목표 FR의 κ를 구한다 (이분 탐색은 표본 잡음에 흔들림)"""
        grid = np.linspace(0.0, 0.5, 11)
        curve = [np.mean([fm.fr_pair(blocks, scen, [k])[0] for _ in range(args.calib)]) for k in grid]
        curve = np.maximum.accumulate(curve)  # 단조 증가로 정리
        return float(np.interp(target, curve, grid))

    rows = []
    for scen in args.scenarios:
        for blocks in args.blocks:
            if args.target == "h2":
                k = kappa_for(1.5, blocks, scen)
                null = [fm.fr_pair(blocks, scen, [0.0])[0] for _ in range(args.sims)]
                lo_c, hi_c = np.percentile(null, [ALPHA / 2 * 100, 100 - ALPHA / 2 * 100])
                alt = [fm.fr_pair(blocks, scen, [k])[0] for _ in range(args.sims)]
                power = float(np.mean([(v < lo_c) or (v > hi_c) for v in alt]))
                rows.append({"hypothesis": "H2", "ai_variance_x_human": scen, "items": len(items),
                             "groups_per_item": blocks, "kappa": round(k, 3), "null_95": [round(lo_c, 3), round(hi_c, 3)],
                             "power": power})
            else:
                # FR의 척도는 표본 크기에 따라 달라진다(AI 표본이 클수록 표본 잡음이 줄어 같은 실제 차이도 FR 차이가 커짐).
                # 그래서 효과는 실제 수렴 차이(κ)로 고정한다: 문항당 8집단에서 FR 1.5 → 1.3에 해당하는 κ (SESOI).
                # 검정은 두 조건의 인간 전체 기준 거리 차이 ΔD (분모가 같아 ΔFR과 부호가 같음), 같은 집단 복제
                key = ("kappas", scen)
                if key not in fm.__dict__:
                    fm.__dict__[key] = (kappa_for(1.5, 8, scen), kappa_for(1.3, 8, scen))
                kb, ks = fm.__dict__[key]

                def delta(kb_, ks_):
                    human = fm.df.copy()
                    human["sim"] = fm.gen(human, "ig")
                    personas = fm.blocks(fm.df, blocks, True)
                    a, b = personas.copy(), personas.copy()
                    a["sim"], b["sim"] = fm.gen(a, "blk", scen, kb_), fm.gen(b, "blk", scen, ks_)
                    return fm.dist(b, human, "sim") - fm.dist(a, human, "sim")
                null = [delta(kb, kb) for _ in range(args.sims)]
                crit = np.percentile(null, ALPHA / 2 * 100)
                power = float(np.mean([delta(kb, ks) < crit for _ in range(args.sims)]))
                rows.append({"hypothesis": "H5", "ai_variance_x_human": scen, "items": len(items),
                             "groups_per_item": blocks, "kappa_base": round(kb, 3), "kappa_state": round(ks, 3),
                             "alpha": ALPHA, "null_crit": round(crit, 3), "power": power})
            print(rows[-1], flush=True)
    return rows


# ---------------- 주 검정: 엔진 효과 E1~E5 (분산은 분산 추정 파일럿 2차, 효과는 SESOI) ----------------

def _pilot_rows(dbs, batch_word):
    """분산 추정 파일럿의 완료 토론: (실험 조건, 설문 행)"""
    out = []
    for db in dbs:
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        for d in con.execute("select id, config from discussions where status='completed'"):
            e = json.loads(d["config"])["experiment"]
            if batch_word not in e["batch"]:
                continue
            sv = [dict(r) for r in con.execute(
                "select phase, participant, score, correct from survey_responses where discussion_id=?", (d["id"],))]
            out.append((Path(db).name, e, sv))
    return out


def e1(args):
    """E1: 1-A 정답 추적. 실행 단위 정답 비율 ~ 모드, 블록(복제 집단) 무작위 절편·모드 기울기. SESOI 10%p"""
    import statsmodels.formula.api as smf
    rng = np.random.default_rng(args.seed)
    rows = []
    for db, e, sv in _pilot_rows(args.pilot_db, "wason"):
        post = [x["correct"] for x in sv if x["phase"] == "post"]
        if post and None not in post:
            rows.append({"db": db, "block": e["topic_key"], "mode": 1.0 if e["label"] == "A-stateful" else 0.0,
                         "acc": float(np.mean([bool(c) for c in post]))})
    df = pd.DataFrame(rows)
    out = []
    for db, g in df.groupby("db"):
        m = smf.mixedlm("acc ~ mode", g, groups="block", re_formula="~mode").fit()
        sd_b, sd_s, sd_r = (float(np.sqrt(max(v, 0))) for v in (m.cov_re.iloc[0, 0], m.cov_re.iloc[1, 1], m.scale))
        print(f"variance calibration {db}: block SD {sd_b:.3f}, mode-slope SD {sd_s:.3f}, run SD {sd_r:.3f} (n={len(g)})")
        for blocks in args.blocks:
            for reps in args.reps:
                hits = 0
                for _ in range(args.sims):
                    data = []
                    for b in range(blocks):
                        u, sl = rng.normal(0, sd_b), rng.normal(0, sd_s)
                        for mode in (0.0, 1.0):
                            for _ in range(reps):
                                data.append((b, mode, 0.5 + u + mode * (0.10 + sl) + rng.normal(0, sd_r)))
                    sim = pd.DataFrame(data, columns=["block", "mode", "acc"])
                    try:
                        r = smf.mixedlm("acc ~ mode", sim, groups="block", re_formula="~mode").fit()
                    except Exception:
                        continue
                    hits += r.pvalues["mode"] < ALPHA
                out.append({"hypothesis": "E1", "variance_from": db, "groups": blocks, "reps_per_mode": reps,
                            "power": hits / args.sims})
                print(out[-1], flush=True)
    return out


def e23(args):
    """E2(순수 이동량)·E3(집단 내 표준편차 감소): 1-B 블록별 상태 기반 − 기준선 차이 ~ 1 + (1 | 문항). SESOI 0.3점"""
    import statsmodels.formula.api as smf
    rng = np.random.default_rng(args.seed)
    per = {}
    for db, e, sv in _pilot_rows(args.pilot_db, "a1r"):
        if e["label"] not in ("A-baseline", "A-stateful"):
            continue
        pre = {x["participant"]: x["score"] for x in sv if x["phase"] == "pre"}
        post = {x["participant"]: x["score"] for x in sv if x["phase"] == "post"}
        both = [p for p in post if p in pre and None not in (pre[p], post[p])]
        if len(both) < 3:
            continue
        key = (db, e["topic_key"], e["replicate"])
        per.setdefault(key, {})[e["label"]] = {
            "E2": float(np.mean([abs(post[p] - pre[p]) for p in both])),
            "E3": float(np.std([pre[p] for p in both]) - np.std([post[p] for p in both]))}
    rows = [{"db": k[0], "item": k[1][:3], "E2": v["A-stateful"]["E2"] - v["A-baseline"]["E2"],
             "E3": v["A-stateful"]["E3"] - v["A-baseline"]["E3"]}
            for k, v in per.items() if len(v) == 2]
    df = pd.DataFrame(rows)
    out = []
    for (db, g) in df.groupby("db"):
        for h in ("E2", "E3"):
            sd_item = float(g.groupby("item")[h].mean().std(ddof=1)) if g["item"].nunique() > 1 else 0.0
            sd_res = float(g[h].std(ddof=1))
            print(f"variance calibration {db} {h}: block-difference SD {sd_res:.3f}, item SD {sd_item:.3f} (n={len(g)})")
            for blocks in args.blocks:
                hits = 0
                for _ in range(args.sims):
                    data = []
                    for it in range(30):
                        iu = rng.normal(0, sd_item)
                        data += [(it, 0.3 + iu + rng.normal(0, sd_res)) for _ in range(blocks)]
                    sim = pd.DataFrame(data, columns=["item", "d"])
                    r = smf.mixedlm("d ~ 1", sim, groups="item").fit()
                    hits += r.pvalues["Intercept"] < ALPHA
                out.append({"hypothesis": h, "variance_from": db, "items": 30, "groups_per_item": blocks,
                            "power": hits / args.sims})
                print(out[-1], flush=True)
    return out


def e45(args):
    """E4(질 × 엔진)·E5(지지 × 엔진): 1-C Δ ~ q × sup × engine + (1 + q | set). SESOI 5점 (0~100)"""
    import statsmodels.formula.api as smf
    rng = np.random.default_rng(args.seed)
    rows = []
    for db, e, sv in _pilot_rows(args.pilot_db, "argq"):
        parts = e["label"].split("-")
        if len(parts) != 3 or parts[0] not in ("strong", "weak"):
            continue
        sc = {x["phase"]: x["score"] for x in sv if x["participant"] == "Jordan"}
        if None in (sc.get("pre"), sc.get("post")):
            continue
        delta = (sc["pre"] - sc["post"]) if e["topic_key"].endswith("pro") else (sc["post"] - sc["pre"])
        rows.append({"db": db, "set": e["topic_key"], "q": 0.5 if parts[0] == "strong" else -0.5,
                     "sup": 0.5 if parts[1] == "majority" else -0.5, "eng": 0.5 if parts[2] == "stateful" else -0.5,
                     "delta": delta})
    df = pd.DataFrame(rows)
    out = []
    for db, g in df.groupby("db"):
        m = smf.mixedlm("delta ~ q * sup * eng", g, groups="set", re_formula="~q").fit()
        sd_set = float(np.sqrt(max(m.cov_re.iloc[0, 0], 0)))
        sd_q = float(np.sqrt(max(m.cov_re.iloc[1, 1], 0)))
        sd_res = float(np.sqrt(m.scale))
        print(f"variance calibration {db}: set SD {sd_set:.2f}, q-slope SD {sd_q:.2f}, residual SD {sd_res:.2f} (n={len(g)})")
        eff = 5.0
        for reps in args.reps:
            hits = {"E4": 0, "E5": 0}
            for _ in range(args.sims):
                data = []
                for s_ in range(args.sets):
                    u, sl = rng.normal(0, sd_set), rng.normal(0, sd_q)
                    for q in (-0.5, 0.5):
                        for sup in (-0.5, 0.5):
                            for eng in (-0.5, 0.5):
                                mu = u + (eff + sl) * q + eff * sup + eff * q * eng + eff * sup * eng
                                data += [(s_, q, sup, eng, mu + rng.normal(0, sd_res)) for _ in range(reps)]
                sim = pd.DataFrame(data, columns=["set", "q", "sup", "eng", "delta"])
                try:
                    r = smf.mixedlm("delta ~ q * sup * eng", sim, groups="set", re_formula="~q").fit()
                except Exception:
                    continue
                hits["E4"] += r.pvalues["q:eng"] < ALPHA
                hits["E5"] += r.pvalues["sup:eng"] < ALPHA
            out.append({"hypothesis": "E4/E5", "variance_from": db, "sets": args.sets, "reps_per_cell": reps,
                        **{k: v / args.sims for k, v in hits.items()}})
            print(out[-1], flush=True)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="연구 1 검정력 시뮬레이션")
    parser.add_argument("hypothesis", choices=("h1", "h3", "h2b", "h2", "h5", "e1", "e23", "e45"))
    parser.add_argument("--sims", type=int, default=200)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--reps", type=int, nargs="+", default=[1, 2, 3], help="H1: AI 반복, H3: 셀당 반복")
    parser.add_argument("--sets", type=int, default=16, help="H3: 주제 × 표적 입장 세트 수")
    parser.add_argument("--blocks", type=int, nargs="+", default=[4, 8, 12], help="H2b: 문항당 집단 수")
    parser.add_argument("--pilot-db", nargs="+", default=[str(ROOT / "data/pilot8/pilot8-claude.db"),
                                                          str(ROOT / "data/pilot8/pilot8-gemini.db")])
    parser.add_argument("--scenarios", type=float, nargs="+", default=[0.5, 1.0], help="H2·H5: AI 집단 분산 / 인간")
    parser.add_argument("--calib", type=int, default=8, help="H2·H5: κ 보정 격자점당 반복")
    parser.add_argument("--alpha", type=float, default=0.05, help="유의수준 (Holm 보수적 하한: 0.05/가족 검정 수)")
    parser.add_argument("--out", help="결과 CSV")
    args = parser.parse_args(argv)
    global ALPHA
    ALPHA = args.alpha
    if args.hypothesis in ("h2", "h5"):
        args.target = args.hypothesis
    rows = {"h1": h1, "h3": h3, "h2b": h2b, "h2": h2h5, "h5": h2h5,
            "e1": e1, "e23": e23, "e45": e45}[args.hypothesis](args)
    if args.out:
        pd.DataFrame(rows).to_csv(args.out, index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
