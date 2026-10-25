"""
연구 1 탐색 분석 (docs/research/study1-exploratory-plan.md). 등록 분석을 대체하지 않는다.

  python scripts/analyze_study1_exploratory.py --db data/study1/*.db --plans data/study1/plans/*.yaml \
      --out data/study1/results/exploratory [--only N0 N2 N3 N5 N12 N1 S1 S2 E4 E6 E7 E9 E10 E8 N4] [--models claude gemini mistral]

출력(모델별 <out>/<model>/): n0, n2a, n2b, n3(+items csv, replicates npz), n5, n12, n1(+consensus_location csv), s1(+items csv), e4(+csv), e6, e7, e9, e10, n4 (JSON),
a1r_blocks.csv, a1r_agents.csv, wason_runs.csv. 인간 자료는 <out>/human/ 에 한 번(N3, E8). 모델 교차(S2)는 <out>/s2_cross_model.json.
"""
import argparse
import json
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.config_loader import config_loader  # noqa: E402
from scripts.analyze_study1 import REQUIRED  # noqa: E402
from src.analysis import coding, data as adata, direction, exploratory as ex, followup, heterogeneity as het, humans, process, reasons, trajectory  # noqa: E402
from src.cases import texts  # noqa: E402

N4_INDICATORS = ["sd_drop", "gap_change", "movers"]
N4_AI_LABELS = ["A-baseline - C-reanswer", "A-stateful - C-reanswer", "A-baseline", "A-stateful"]


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def n4_heterogeneity(hdir: Path, mdir: Path, max_reps: int) -> dict:
    """N4: 문항 간 이질성 τ²(인간 팔·AI 조건), 분산비(규칙), 순위 상관, 사전 갈등 조건부 (계획 2-4)"""
    hz = np.load(hdir / "n3_human_replicates.npz")
    az = np.load(mdir / "n3_ai_replicates.npz")
    hitems, aitems = list(hz["items"]), list(az["items"])
    ht = pd.read_csv(hdir / "n3_human_items.csv").set_index("item").loc[hitems]
    at = pd.read_csv(mdir / "n3_ai_items.csv").set_index("item").loc[aitems]
    assert hitems == aitems, "item order differs between human and AI tables"
    out = {"items": hitems, "indicators": {}, "note": "AI covariance from block resampling within item does not preserve persona cross-item dependence"}
    for ind in N4_INDICATORS:
        res = {"human": {}, "ai": {}, "ratio_tau2_ai_over_human_did": {}, "naive_vr_sensitivity": {}, "spearman_human_did_vs_ai": {}}
        draws = {}
        for arm in ("delib", "did"):
            reps = hz[f"{arm}_{ind}"]
            sig = het.covariance(reps)
            theta = ht[f"{arm}_{ind}"].to_numpy(float)
            r = het.reml_tau2(theta, sig)
            d = het.bootstrap_tau2(reps, sig, max_reps)
            r["boot_ci"] = [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]
            r["naive"] = het.naive_vr_component(theta, sig, reps)
            res["human"][arm] = r
            draws[("human", arm)] = d
        for lab in N4_AI_LABELS:
            key = f"{ind}|{lab}"
            reps = az[key]
            sig = het.covariance(reps)
            theta = at[key].to_numpy(float)
            r = het.reml_tau2(theta, sig)
            d = het.bootstrap_tau2(reps, sig, max_reps)
            r["boot_ci"] = [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]
            r["naive"] = het.naive_vr_component(theta, sig, reps)
            res["ai"][lab] = r
            draws[("ai", lab)] = d
            res["ratio_tau2_ai_over_human_did"][lab] = het.ratio_with_rules(r, res["human"]["did"], d, draws[("human", "did")])
            res["naive_vr_sensitivity"][lab] = het.naive_ratio_with_rules(r["naive"], res["human"]["did"]["naive"])
            res["spearman_human_did_vs_ai"][lab] = het.spearman_with_boot(ht[f"did_{ind}"].to_numpy(float), theta, hz[f"did_{ind}"], reps)
        # 사전 갈등 조건부: 인간 DiD ~ 사전 SD(숙의군), AI A−C ~ 같은 사전 SD
        x = ht["delib_sd_pre"].to_numpy(float)
        res["conditional_on_pre_sd"] = {}
        for name, y in (("human_did", ht[f"did_{ind}"].to_numpy(float)),
                        ("ai_A-baseline - C", at[f"{ind}|A-baseline - C-reanswer"].to_numpy(float)),
                        ("ai_A-stateful - C", at[f"{ind}|A-stateful - C-reanswer"].to_numpy(float))):
            ok = ~np.isnan(x) & ~np.isnan(y)
            slope, intercept = np.polyfit(x[ok], y[ok], 1)
            res["conditional_on_pre_sd"][name] = {"slope_per_pre_sd": float(slope), "pearson": float(np.corrcoef(x[ok], y[ok])[0, 1]), "n": int(ok.sum())}
        out["indicators"][ind] = res
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", nargs="+", required=True)
    p.add_argument("--plans", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--models", nargs="+", default=["claude", "gemini", "mistral"], help="프로바이더 키 (config llm.default_models)")
    p.add_argument("--only", nargs="+", help="예: N0 N2 N3 N5 N12 N1 S1 S2 E4 E6 E7 E9 E10 E8 N4 N6 N7 S5 S3 E2 E5 N8 N9 E1 E3 S7 S6 N10 N6B L3 S4 S8")
    p.add_argument("--briefing", default=str(ROOT / "data/cases/a1r_briefing.yaml"))
    p.add_argument("--skip-human", action="store_true", help="인간 쪽 재표집(N3)을 건너뛴다 (이미 <out>/human 에 있을 때)")
    p.add_argument("--boot", type=int, default=2000)
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--delidata", default=str(ROOT / "data/raw/delidata"))
    p.add_argument("--a1r", default=str(ROOT / "data/raw/a1r/dataset.tab"))
    p.add_argument("--argq-d-db", default=str(ROOT / "data/study1/argq-dprior-claude.db"), help="S4: 1-C 주제의 D-prior 추가 측정 DB (계획 argq-dprior-*.yaml 을 --plans 에 포함)")
    args = p.parse_args(argv)
    want = lambda h: not args.only or h in args.only  # noqa: E731
    out = Path(args.out)
    defaults = config_loader.get_llm_config().default_models
    plans = adata.load_plans(args.plans)
    runs_all, surveys_all = adata.load_runs(args.db, plans, defaults)
    t = texts()["a1r"]
    items = t["development"] + t["locked"]
    parties = humans.a1r_parties(args.a1r, items)
    errors = {}

    # 인간 자료 (모델과 무관)
    human_ind = humans.delidata_groups(args.delidata)
    human_grp = ex.human_groups(human_ind)
    delib = humans.a1r_delegates(args.a1r, items, "1")
    control = humans.a1r_delegates(args.a1r, items, "0")
    hdir = out / "human"
    hdir.mkdir(parents=True, exist_ok=True)
    human_units = None
    if want("N2") or want("E7"):
        human_units = ex.human_a1r_units(delib, seed=args.seed)
        human_units.to_csv(hdir / "a1r_units.csv", index=False)
    if want("N3") and not args.skip_human:
        try:
            table, reps, summary = ex.n3_human_did(delib, control, args.boot, args.seed)
            table.to_csv(hdir / "n3_human_items.csv", index=False)
            np.savez_compressed(hdir / "n3_human_replicates.npz", items=np.array(summary["items"]), **reps)
            dump(hdir / "n3_human.json", summary)
        except Exception as e:
            errors["human:N3"] = f"{type(e).__name__}: {e}"
            traceback.print_exc()
    if want("E8"):
        try:
            dump(hdir / "e8_weighted.json", direction.e8_weighted(delib, control))
        except Exception as e:
            errors["human:E8"] = f"{type(e).__name__}: {e}"
            traceback.print_exc()
    human_grp.to_csv(hdir / "delidata_groups.csv", index=False)

    s1_tables = {}
    for key in args.models:
        model = defaults[key]
        runs = runs_all[runs_all["model"] == model]
        surveys = surveys_all[surveys_all["model"] == model]
        kept, excluded = adata.exclusions(runs, REQUIRED)
        surveys = surveys[surveys["discussion_id"].isin(set(kept["discussion_id"]))]
        mdir = out / key
        mdir.mkdir(parents=True, exist_ok=True)
        info = {"model": model, "runs_kept": int(len(kept)), "excluded_blocks": excluded, "boot": args.boot, "seed": args.seed}
        wruns = ex.wason_runs(surveys, plans)
        wruns.to_csv(mdir / "wason_runs.csv", index=False)
        blocks = ex.a1r_block_metrics(surveys, plans, parties)
        blocks.to_csv(mdir / "a1r_blocks.csv", index=False)
        agents = ex.a1r_agent_rows(surveys, plans, parties)
        agents.to_csv(mdir / "a1r_agents.csv", index=False)

        def run(name, fn):
            try:
                res = fn()
                if isinstance(res, dict):
                    dump(mdir / f"{name.lower()}.json", {"info": info, **res})
                print(key, name, "ok", flush=True)
            except Exception as e:
                errors[f"{key}:{name}"] = f"{type(e).__name__}: {e}"
                traceback.print_exc()

        if want("N0"):
            run("N0", lambda: ex.n0_truth_wins(wruns, human_grp, args.boot, args.seed))
        if want("N2"):
            run("N2a", lambda: ex.n2a_unanimity(wruns, human_grp, args.boot, args.seed))
            run("N2b", lambda: ex.n2b_consensus(blocks, human_units, args.boot, args.seed))
        if want("N3"):
            def n3_ai():
                table, reps = ex.n3_ai_items(blocks, args.boot, args.seed)
                table.to_csv(mdir / "n3_ai_items.csv", index=False)
                np.savez_compressed(mdir / "n3_ai_replicates.npz", items=np.array(sorted(table["item"])), **reps)
                return {"n_items": int(len(table)), "resample": "item > block ×%d (persona cross-item dependence not preserved)" % args.boot}
            run("N3", n3_ai)
        if want("N5"):
            run("N5", lambda: ex.n5_group_correspondence(wruns, human_grp))
        if want("N12"):
            run("N12", lambda: ex.n12_retention(agents, surveys, plans, surveys, args.boot, args.seed))
        # ---- A단계 ----
        if want("N1"):
            def n1():
                res, loc = direction.n1_direction(agents, delib, args.boot, args.seed)
                loc.to_csv(mdir / "n1_consensus_location.csv", index=False)
                return res
            run("N1", n1)
        if want("S1") or want("S2"):
            def s1():
                res, table = direction.s1_default_vs_human(agents, delib, blocks, args.boot, args.seed)
                table.to_csv(mdir / "s1_items.csv", index=False)
                s1_tables[key] = table
                return res
            run("S1", s1)
        if want("E4"):
            def e4():
                res, table = direction.e4_item_pull(agents, blocks)
                table.to_csv(mdir / "e4_items.csv", index=False)
                return res
            run("E4", e4)
        if want("E6"):
            run("E6", lambda: direction.e6_party_decomposition(agents, delib, control, args.boot, args.seed))
        if want("E7"):
            run("E7", lambda: direction.e7_direction_agree(blocks, human_units, args.boot, args.seed))
        if want("E9"):
            run("E9", lambda: direction.e9_away_from_group(agents, blocks, args.boot, args.seed))
        if want("E10"):
            run("E10", lambda: direction.e10_debranded(surveys, plans, parties, args.boot, args.seed))
        if want("N4"):
            run("N4", lambda: n4_heterogeneity(hdir, mdir, args.boot))
        # ---- B단계 ----
        if want("E5"):
            def e5():
                res, table = direction.e5_materials_lean(agents, delib, args.briefing)
                table.to_csv(mdir / "e5_items.csv", index=False)
                return res
            run("E5", e5)
        if want("S3"):
            run("S3", lambda: process.s3_minority(agents, delib, args.boot, args.seed))
        needs_utt = any(want(h) for h in ("N6", "N7", "S5", "E2", "N8", "N9", "S7", "S8"))
        if needs_utt:
            cache = mdir / "utterances.csv"
            db = next(d for d in args.db if Path(d).name == kept["db"].iloc[0])
            if cache.exists():
                utt = pd.read_csv(cache, low_memory=False)
            else:
                sel = kept[(kept["study"] != "a1r") | kept["topic_key"].map(adata.a1r_set).eq("groups")]
                sel = sel[sel["label"].isin(["A-baseline", "A-stateful"]) | (sel["study"] == "argq")]
                sel = sel[~sel["label"].isin(["C-reanswer", "B-materials", "D-prior", "B-resolve", "C-unseeded"])]
                utt = process.load_utterances(db, sel)
                utt.to_csv(cache, index=False)
            print(key, "utterances", len(utt), flush=True)
            if want("N6"):
                run("N6_instructed", lambda: process.n6_instructed(utt, args.boot, args.seed))
                run("N6_after", lambda: process.n6_after_device(utt, args.boot, args.seed))
            if want("N7"):
                def n7():
                    res, t, sw = process.n7_engine_vs_text_vs_survey(utt, surveys, args.boot, args.seed)
                    t.to_csv(mdir / "n7_participants.csv", index=False)
                    sw.to_csv(mdir / "n7_switch_events.csv", index=False)
                    return res
                run("N7", n7)
            if want("S5"):
                run("S5", lambda: process.s5_consensus_timing(utt, args.boot, args.seed))
            if want("E2"):
                run("E2", lambda: process.e2_failure_process(utt, wruns))
            if want("N8"):
                run("N8", lambda: process.n8_association(utt, blocks, wruns))
            # ---- C단계 ----
            if want("N9"):
                def n9():
                    h_ev, h_sum = trajectory.human_trajectories(args.delidata, set(human_grp["block"]), set(zip(human_ind["block"], human_ind["member"])))
                    h_sum = h_sum.merge(human_ind[["block", "member", "solo_correct"]].rename(columns={"solo_correct": "seed_correct"}), on=["block", "member"], how="left")
                    llm_path = mdir / "n9_llm_choices.csv"
                    choices = trajectory.load_llm_choices(llm_path) if llm_path.exists() else None
                    a_ev, a_sum, qual = trajectory.ai_trajectories(utt, surveys, plans, db, choices)
                    h_ev.to_csv(hdir / "n9_human_events.csv", index=False)
                    a_ev.to_csv(mdir / "n9_ai_events.csv", index=False)
                    a_sum.to_csv(mdir / "n9_ai_participants.csv", index=False)
                    res = {"extraction_quality": qual, "human": trajectory.n9_summary(h_ev, h_sum, "block", args.boot, args.seed),
                           "human_retention": trajectory.retention(h_sum, "block", args.boot, args.seed), "ai": {}, "ai_retention": {}}
                    for lab in ("A-baseline", "A-stateful"):
                        res["ai"][lab] = trajectory.n9_summary(a_ev[a_ev["label"] == lab], a_sum[a_sum["label"] == lab], "block", args.boot, args.seed)
                        res["ai_retention"][lab] = trajectory.retention(a_sum[a_sum["label"] == lab], "block", args.boot, args.seed)
                    return res
                run("N9", n9)
            if want("E1") or want("E3"):
                def e1e3():
                    hg = trajectory.human_group_sets(human_ind, args.delidata)
                    res = {"E1": {"human": trajectory.wrong_consensus_types(hg, args.boot, args.seed)}, "E3": {"human": trajectory.truth_wins_process(hg, args.boot, args.seed)}}
                    for lab, rep in (("A-baseline", 0), ("A-stateful", None)):
                        g = trajectory.ai_group_sets(surveys, plans, lab, rep)
                        res["E1"][lab] = trajectory.wrong_consensus_types(g, args.boot, args.seed)
                        res["E3"][lab] = trajectory.truth_wins_process(g, args.boot, args.seed)
                    return res
                run("E1E3", e1e3)
            if want("S7"):
                run("S7", lambda: trajectory.s7_variants(surveys, plans, utt, db))
        # ---- D단계 ----
        if want("S6"):
            def s6():
                r = reasons.load_reasons(next(d for d in args.db if Path(d).name == kept["db"].iloc[0]), agents)
                r.to_csv(mdir / "s6_reasons.csv", index=False)
                return reasons.s6_reason_mentions(r, args.boot, args.seed)
            run("S6", s6)
        cdir = out / "coding"
        if want("N10") and key == "claude" and (cdir / "n10_comparison_glm.csv").exists():
            def n10():
                parts = [pd.read_csv(cdir / f) for f in ("n10_comparison_glm.csv", "n10_explanatory_glm.csv") if (cdir / f).exists()]
                ai = pd.concat(parts, ignore_index=True)
                res = coding.n10_summary(coding.human_labels(args.delidata), ai, args.boot, args.seed)
                second = [pd.read_csv(cdir / f) for f in ("n10_comparison_large.csv", "n10_explanatory_large.csv") if (cdir / f).exists()]
                if second:
                    res["coder_agreement"] = coding.coder_agreement(ai.drop_duplicates(["discussion_id", "seq"]), pd.concat(second, ignore_index=True).drop_duplicates(["discussion_id", "seq"]))
                return res
            run("N10", n10)
        if want("N6B") and key == "claude" and (cdir / "devices_large.csv").exists():
            sys.path.insert(0, str(ROOT / "scripts"))
            from code_devices import summarize as dev_summarize
            run("N6B", lambda: dev_summarize([str(cdir / f) for f in ("devices_large.csv", "devices_small.csv") if (cdir / f).exists()]))
        # ---- E단계 ----
        if want("S8") and key == "claude":
            def s8():
                res = {"network": followup.s8_network(utt, wruns, plans, db, args.boot, args.seed)}
                if (cdir / "devices_large.csv").exists():
                    res["analyzer_vs_coders"] = followup.analyzer_vs_coders(pd.read_csv(cdir / "devices_large.csv").dropna(subset=["objects_to_shared_view"]), utt)
                return res
            run("S8", s8)
        if want("S4") and key == "claude" and Path(args.argq_d_db).exists():
            def s4():
                _, sd = adata.load_runs([args.argq_d_db], plans, defaults)
                return followup.s4_direction_split(surveys, followup.argq_default_stance(sd))
            run("S4", s4)
        if want("L3") and key == "claude" and (cdir / "evidence_glm.csv").exists():
            sys.path.insert(0, str(ROOT / "scripts"))
            from code_evidence import summarize as ev_summarize
            run("L3", lambda: ev_summarize([str(cdir / f) for f in ("evidence_glm.csv", "evidence_sonnet.csv") if (cdir / f).exists()], args.boot, args.seed))
    if want("S2") and len(s1_tables) > 1:
        try:
            dump(out / "s2_cross_model.json", direction.s2_cross_model(s1_tables))
            print("S2 ok", flush=True)
        except Exception as e:
            errors["S2"] = f"{type(e).__name__}: {e}"
            traceback.print_exc()
    dump(out / "errors.json", errors)
    print(json.dumps(errors, ensure_ascii=False, indent=1))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
