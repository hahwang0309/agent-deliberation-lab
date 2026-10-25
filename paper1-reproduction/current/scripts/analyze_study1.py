"""
연구 1 본 분석 (docs/research/study1-analysis-plan.md)

  python scripts/analyze_study1.py --db data/study1/*.db --plans data/study1/*.yaml --out data/study1/results-claude.json
  python scripts/analyze_study1.py ... --model gemini-3.5-flash-lite      # 비교 모델 재현
  python scripts/analyze_study1.py ... --blind                            # 형식·오류 점검: 추정치를 출력하지 않음

결과 JSON: 제외 기록, 무응답률, 가설별 추정치·95% 구간·p·보정 p, 1-C 순열 검정(permutation),
결측 민감도 분석(sensitivity: 조건 간 무응답률 차이 > 5%p인 연구를 완전 블록만으로 재분석). --blind는 표본 수와 적합 상태만 화면에 보이고
JSON에도 추정치를 쓰지 않는다(파일럿·점검 자료로 스크립트를 검증할 때).
"""
import argparse
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.config_loader import config_loader  # noqa: E402
from src.analysis import data as adata, humans, study1  # noqa: E402
from src.cases import texts  # noqa: E402

REQUIRED = {  # 블록마다 있어야 하는 조건 (6절: 하나라도 최종 실패하면 그 블록 제외)
    "wason": ["A-baseline", "A-stateful", "B-resolve", "C-unseeded"],
    "a1r": ["A-baseline", "A-stateful", "B-materials", "C-reanswer", "D-prior"],
    "argq": [f"{q}-{s}-{e}" for q in ("strong", "weak") for s in ("minority", "majority")
             for e in ("baseline", "stateful")] + ["C-reanswer"],
}
ESTIMATE_KEYS = {"estimate", "ci", "p", "se", "p_boot", "p_holm", "reject", "supported", "farther", "delta_FR",
                 "delta_FR_ci", "FR", "D_full", "t", "p_perm"}


def blind(obj):
    """추정치·검정 결과를 지운 사본 (표본 수, 적합 상태, 경고만 남김)"""
    if isinstance(obj, dict):
        return {k: blind(v) for k, v in obj.items() if k not in ESTIMATE_KEYS}
    if isinstance(obj, list):
        return [blind(v) for v in obj]
    return obj


def run(name, fn, results, errors):
    try:
        results[name] = fn()
    except Exception as e:  # 한 가설의 실패가 다른 가설을 막지 않게 하고, 기록에 남긴다
        errors[name] = f"{type(e).__name__}: {e}"
        traceback.print_exc()


STUDY_HYPOTHESES = {"wason": ["E1", "H1"], "a1r": ["E2", "E3", "H5", "H2", "H2b", "H2c"],
                    "argq": ["E4", "E5", "H3"]}


def hypotheses(surveys, plans, parties, t, args, want):
    """가설 검정 (0-3절). want(h)가 참인 가설만. 반환: (결과, 오류)"""
    res, errors = {}, {}
    present = set(surveys["study"])
    if "wason" in present:
        if want("E1"):
            run("E1", lambda: study1.e1(surveys), res, errors)
        if want("H1"):
            human = humans.delidata_individuals(args.delidata)
            run("H1", lambda: study1.h1(surveys, plans, human), res, errors)
    if "a1r" in present:
        if want("E2") or want("E3"):
            run("E2E3", lambda: study1.e2_e3(surveys), res, errors)
            if "E2E3" in res:
                res.update(res.pop("E2E3"))
        if want("H5"):
            items = t["locked"]
            human = humans.a1r_delegates(args.a1r, items)
            run("H5", lambda: study1.h5(study1.a1r_ai_rows(surveys, plans, parties, items, ["A-baseline", "A-stateful"]),
                                        human[human["item"].isin(items)], args.boot, args.seed), res, errors)
        if want("H2"):
            items = t["development"] + t["locked"]
            human = humans.a1r_delegates(args.a1r, items)
            run("H2", lambda: study1.h2(study1.a1r_ai_rows(surveys, plans, parties, items, ["A-baseline"])["A-baseline"],
                                        human, args.boot, args.seed), res, errors)
        if want("H2b"):
            run("H2b", lambda: study1.h2b(surveys, plans, parties), res, errors)
        if want("H2c"):
            run("H2c", lambda: study1.h2c(surveys), res, errors)
    if "argq" in present:
        if want("E4") or want("E5"):
            run("E4E5", lambda: study1.e4_e5(surveys), res, errors)
            if "E4E5" in res:
                res.update(res.pop("E4E5"))
        if want("H3"):
            run("H3", lambda: study1.h3(surveys), res, errors)
            if "H3" in res:
                res.update(res.pop("H3"))
    return res, errors


def families(res):
    """가족별 보정 (0-3절)"""
    q1 = {h: res[h]["p"] for h in ("E1", "E2", "E3", "E4", "E5") if h in res}
    ref = {h: res[h]["p"] for h in ("H1", "H2b", "H3a", "H3b", "H3c") if h in res}
    if "H2" in res:
        ref["H2"] = res["H2"]["p_boot"]
    if "H2c" in res:
        ref["H2c"] = res["H2c"]["beta"]["p"]
    return {"question1_holm": study1.holm(q1), "question2_single": "H5 (α = 0.05, 단독)",
            "reference_holm": study1.holm(ref)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", nargs="+", required=True)
    p.add_argument("--plans", nargs="+", required=True, help="실행한 계획 YAML (주제 메타)")
    p.add_argument("--model", help="분석할 참가자 모델 (기본: 주 모델 = llm.default_models.claude)")
    p.add_argument("--out", required=True)
    p.add_argument("--boot", type=int, default=2000, help="부트스트랩 반복 (분석 계획 2절: 2,000)")
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--perm", type=int, default=5000, help="1-C 순열 검정 반복 (5절 강건성 점검)")
    p.add_argument("--blind", action="store_true")
    p.add_argument("--only", nargs="+", help="이 가설만 (예: E1 H5)")
    p.add_argument("--delidata", default=str(ROOT / "data/raw/delidata"))
    p.add_argument("--a1r", default=str(ROOT / "data/raw/a1r/dataset.tab"))
    args = p.parse_args(argv)

    study1.BOOT.update(n_boot=args.boot, seed=args.seed)
    study1.PERM.update(n_perm=args.perm, seed=args.seed)
    defaults = config_loader.get_llm_config().default_models
    model = args.model or defaults["claude"]
    plans = adata.load_plans(args.plans)
    runs, surveys = adata.load_runs(args.db, plans, defaults)
    runs, surveys = runs[runs["model"] == model], surveys[surveys["model"] == model]
    kept, excluded = adata.exclusions(runs, REQUIRED)
    surveys = surveys[surveys["discussion_id"].isin(set(kept["discussion_id"]))]
    out = {"model": model, "runs": int(len(runs)), "runs_kept": int(len(kept)), "excluded_blocks": excluded,
           "missing_rates": adata.missing_rates(surveys).to_dict("records") if len(surveys) else [],
           "studies": runs["study"].value_counts().to_dict()}
    t = texts()["a1r"]
    parties = humans.a1r_parties(args.a1r, t["development"] + t["locked"])
    want = lambda h: not args.only or h in args.only  # noqa: E731
    res, errors = hypotheses(surveys, plans, parties, t, args, want)
    out["families"] = families(res)
    robust = {}
    if "argq" in set(surveys["study"]):  # 5절: 1-C 순열 검정 (강건성 점검, 보정 가족에 넣지 않음)
        if want("E4") or want("E5"):
            run("E4E5", lambda: study1.e4_e5_permutation(surveys), robust, errors)
        if want("H3"):
            run("H3", lambda: study1.h3_permutation(surveys), robust, errors)
    out["permutation"] = {h: r for k in list(robust) for h, r in robust.pop(k).items()}

    # 6절: 조건 간 무응답률 차이가 5%p를 넘는 연구는 완전 블록만으로 다시 분석 (해당 연구의 가설만)
    flagged = adata.sensitivity_studies(adata.missing_rates(surveys)) if len(surveys) else {}
    sens = {"rule": "condition missing-rate gap > 5 percentage points -> reanalysis on complete blocks",
            "studies": flagged}
    if flagged:
        sub, dropped = adata.complete_blocks(surveys, flagged)
        sens["topics_dropped"] = dropped
        sel = {h for s in flagged for h in STUDY_HYPOTHESES[s]}
        s_res, s_err = hypotheses(sub, plans, parties, t, args, lambda h: want(h) and h in sel)
        sens["hypotheses"], sens["errors"] = s_res, s_err
        sens["families"] = families({**res, **s_res})  # 해당 연구의 가설만 바꾼 보정
        errors.update({f"sensitivity:{k}": v for k, v in s_err.items()})
    out["sensitivity"] = sens
    out["hypotheses"], out["errors"] = res, errors

    if args.blind:
        out = blind(out)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    summary = blind(out)
    print(json.dumps({k: summary[k] for k in ("model", "runs", "runs_kept", "studies", "excluded_blocks", "errors")},
                     ensure_ascii=False, indent=1, default=str))
    for h, r in summary.get("hypotheses", {}).items():
        print(h, json.dumps(r, ensure_ascii=False, default=str)[:300])
    for h, r in summary.get("permutation", {}).items():
        print("perm", h, json.dumps(r, ensure_ascii=False, default=str)[:200])
    sens = summary.get("sensitivity", {})
    print("sensitivity", json.dumps({k: sens.get(k) for k in ("studies", "topics_dropped")}, ensure_ascii=False))
    for h, r in sens.get("hypotheses", {}).items():
        print("sens", h, json.dumps(r, ensure_ascii=False, default=str)[:200])
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
