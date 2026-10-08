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

ALPHA = 0.05
SCENARIOS = (0.5, 1.0, 2.0)


def expit(x):
    return 1 / (1 + np.exp(-x))


# ---------------- H1: truth wins의 인간·AI 차이 (1-A) ----------------

def human_wason_groups():
    """DeliData 3명 집단: 초기 정답자 수 k(0/1/2+)와 토론 후 개인 정답"""
    from src.cases import wason
    groups = [g for g in wason.load_delidata(str(ROOT / "data/raw/delidata"))
              if len(g.solo) == 3 and all(v is not None for v in g.solo.values())]
    out = []
    for i, g in enumerate(groups):
        corr = set(wason.correct_cards(g.cards))
        k = min(2, sum(set(v) == corr for v in g.solo.values()))
        out.append((i, k, [int(set(g.final[m]) == corr) for m in g.solo]))
    return out


def fit_human_h1(groups, rng, grid=np.linspace(0.5, 6.0, 23)):
    """집단 무작위 절편 로지스틱: 개인 정답률과 '전원 정답 또는 전원 오답' 비율을 맞추는 (a_k, s)"""
    obs_rate = {k: np.mean([y for _, kk, ys in groups if kk == k for y in ys]) for k in (0, 1, 2)}
    obs_aon = np.mean([sum(ys) in (0, 3) for _, _, ys in groups])
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
        for _, k, _ in groups:
            p = expit(a[k] + rng.normal(0, s))
            ys = rng.random(3) < p
            sim.append(ys.sum() in (0, 3))
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
                for b, k, _ in groups:
                    zh = rng.normal(0, s_h)
                    data += [(b, k, 0, int(rng.random() < expit(a_h[k] + zh))) for _ in range(3)]
                    v = rng.normal(0, s_ai * np.sqrt(0.5))  # AI 블록 효과와 실행 효과를 반씩
                    for r in range(reps):
                        w = rng.normal(0, s_ai * np.sqrt(0.5))
                        data += [(b, k, 1, int(rng.random() < expit(a_ai[k] + v + w))) for _ in range(3)]
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


def h2h5(args):
    """FR = Σw·W(AI, 인간) / Σw·E[W(인간 반분)], 반분 거리는 AI 셀 사례 수에 맞춘 부표본 (분석 계획 4-2).

    AI 생성: 같은 셀(문항 × 정당 × 사전 구간) 인간의 사전→사후 이동을 뽑아 인간과 같은 전이를 만든 뒤,
    문항의 인간 사후 평균 쪽으로 κ만큼 끌어당긴다(과잉 수렴: 분석 계획의 FR 가정 근거가 DEBATE의 수렴 차이).
    κ는 목표 FR(H2 1.5, H5 기준선 1.5 / 상태 기반 1.3)에 맞춘다.
    검정: 문항 안에서 AI 집단(블록) 단위 부트스트랩. H5는 두 조건이 같은 페르소나를 공유(복제)해 짝지어 재표집."""
    from scipy.stats import wasserstein_distance
    from src.cases import texts
    rng = np.random.default_rng(args.seed)
    t = texts()["a1r"]
    items = {"h2": t["development"] + t["locked"], "h5": t["locked"]}[args.target]
    df = a1r_delegates(items)
    cells = {c: g for c, g in df.groupby(["item", "party", "bin"])}
    human = {c: g["post"].to_numpy() for c, g in cells.items()}
    weights = {c: len(g) / len(df) for c, g in cells.items()}
    shift = {c: (g["post"] - g["pre"]).to_numpy() for c, g in cells.items()}
    center = df.groupby("item")["post"].mean().to_dict()
    groups = df["group"].unique()

    # 분모 캐시: 셀별로 AI 사례 수 n일 때 인간 반분 거리의 기대값 (소집단 단위 반분 30회)
    splits = [dict(zip(groups, rng.random(len(groups)) < 0.5)) for _ in range(30)]
    den_cache = {}

    def den(c, n):
        key = (c, n)
        if key not in den_cache:
            g = cells[c]
            vals = []
            for side in splits:
                m = g["group"].map(side).to_numpy()
                h1, h2 = g["post"].to_numpy()[m], g["post"].to_numpy()[~m]
                if len(h1) and len(h2):
                    vals.append(wasserstein_distance(rng.choice(h1, min(n, len(h1)), replace=False), h2) / 10)
            den_cache[key] = float(np.mean(vals)) if vals else np.nan
        return den_cache[key]

    def fr(records, kappa):
        """records: [(cell, pre, draw)] → FR"""
        by = {}
        for c, pre, d in records:
            post = (1 - kappa) * (pre + d) + kappa * center[c[0]]
            by.setdefault(c, []).append(round(float(np.clip(post, 0, 10))))
        num = dn = 0.0
        for c, v in by.items():
            w, d = weights[c], den(c, len(v))
            if np.isnan(d):
                continue
            num += w * wasserstein_distance(v, human[c]) / 10
            dn += w * d
        return num / dn

    pools = {(q, p): g for (q, p), g in df.groupby(["item", "party"])}

    def draw(blocks):
        """페르소나 표본: 문항마다 blocks개 집단 × (민주 2, 공화 2, 무당층 1). 블록별 레코드 목록"""
        out = []
        for q in items:
            for b in range(blocks):
                recs = []
                for party, n in (("1", 2), ("2", 2), ("3", 1)):
                    g = pools[(q, party)].sample(n, random_state=int(rng.integers(1e9)))
                    for _, r in g.iterrows():
                        c = (q, party, r["bin"])
                        recs.append((c, r["pre"]))
                out.append((q, recs))
        return out

    def responses(blocks_drawn):
        return [(q, [(c, pre, float(rng.choice(shift[c]))) for c, pre in recs]) for q, recs in blocks_drawn]

    def flat(resp):
        return [x for _, recs in resp for x in recs]

    def kappa_for(target, blocks):
        lo, hi = 0.0, 1.0
        for _ in range(14):
            mid = (lo + hi) / 2
            val = np.mean([fr(flat(responses(draw(blocks))), mid) for _ in range(6)])
            lo, hi = (mid, hi) if val < target else (lo, mid)
        return (lo + hi) / 2

    def boot_idx(resp):
        """문항 안에서 블록 재표집 인덱스"""
        by_item = {}
        for i, (q, _) in enumerate(resp):
            by_item.setdefault(q, []).append(i)
        return [j for idx in by_item.values() for j in rng.choice(idx, len(idx))]

    rows = []
    for blocks in args.blocks:
        if args.target == "h2":
            k = kappa_for(1.5, blocks)  # 분석 계획 7절: FR = 1.5
            hits = 0
            for _ in range(args.sims):
                resp = responses(draw(blocks))
                boot = []
                for _ in range(args.boot):
                    idx = boot_idx(resp)
                    boot.append(fr(flat([resp[j] for j in idx]), k))
                lo_ci, hi_ci = np.nanpercentile(boot, [2.5, 97.5])
                hits += not (lo_ci <= 1 <= hi_ci)
            rows.append({"hypothesis": "H2", "items": len(items), "groups_per_item": blocks, "kappa": round(k, 3),
                         "power": hits / args.sims})
        else:
            k_base, k_state = kappa_for(1.5, blocks), kappa_for(1.3, blocks)  # ΔFR = −0.2
            hits = 0
            for _ in range(args.sims):
                personas = draw(blocks)  # 같은 집단을 두 조건에 복제
                base, state = responses(personas), responses(personas)  # 응답은 조건마다 따로
                boot = []
                for _ in range(args.boot):
                    idx = boot_idx(base)  # 같은 블록을 두 조건에서 함께 재표집
                    boot.append(fr(flat([state[j] for j in idx]), k_state) - fr(flat([base[j] for j in idx]), k_base))
                lo_ci, hi_ci = np.nanpercentile(boot, [2.5, 97.5])
                hits += hi_ci < 0  # H5 지지: ΔFR < 0이고 신뢰구간이 0을 제외
            rows.append({"hypothesis": "H5", "items": len(items), "groups_per_item": blocks,
                         "kappa_base": round(k_base, 3), "kappa_state": round(k_state, 3), "power": hits / args.sims})
        print(rows[-1], flush=True)
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="연구 1 검정력 시뮬레이션")
    parser.add_argument("hypothesis", choices=("h1", "h3", "h2b", "h2", "h5"))
    parser.add_argument("--sims", type=int, default=200)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--reps", type=int, nargs="+", default=[1, 2, 3], help="H1: AI 반복, H3: 셀당 반복")
    parser.add_argument("--sets", type=int, default=16, help="H3: 주제 × 표적 입장 세트 수")
    parser.add_argument("--blocks", type=int, nargs="+", default=[4, 8, 12], help="H2b: 문항당 집단 수")
    parser.add_argument("--pilot-db", nargs="+", default=[str(ROOT / "data/pilot8/pilot8-claude.db"),
                                                          str(ROOT / "data/pilot8/pilot8-gemini.db")])
    parser.add_argument("--boot", type=int, default=100, help="H2·H5: 부트스트랩 횟수")
    parser.add_argument("--out", help="결과 CSV")
    args = parser.parse_args(argv)
    if args.hypothesis in ("h2", "h5"):
        args.target = args.hypothesis
    rows = {"h1": h1, "h3": h3, "h2b": h2b, "h2": h2h5, "h5": h2h5}[args.hypothesis](args)
    if args.out:
        pd.DataFrame(rows).to_csv(args.out, index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
