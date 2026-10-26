"""
층 3: 근거–결론 연결 코딩 (docs/research/study1-exploratory-plan.md 3절 "층 3 코딩 범위"). 1-B A-기준선·A-상태의 에이전트 1명(전사 + 사후 점수·이유)을
단위로, 사후 이유가 토론의 논거를 참조하는지·관련 있는지·실제로 지지하는지·반박됐는지를 코딩한다. Claude만, 문항 30 × 엔진 2 × 블록 2(문항당 무작위) × 에이전트 5 = 600건.

  python scripts/code_evidence.py sample --db data/study1/claude.db --agents data/study1/results/exploratory/claude/a1r_agents.csv \
      --out data/study1/results/exploratory/coding/evidence_sample.csv
  python scripts/code_evidence.py code --sample .../evidence_sample.csv --out .../evidence_glm.csv
  python scripts/code_evidence.py code --sample .../evidence_sample.csv --second --out .../evidence_sonnet.csv     # 제2 코더 (config evidence_coding_second_*)
  python scripts/code_evidence.py summarize --coded .../evidence_glm.csv .../evidence_sonnet.csv --out data/study1/results/exploratory/claude/layer3.json
"""
import argparse
import asyncio
import csv
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.config_loader import config_loader  # noqa: E402
from src.models.personas import LLMProvider  # noqa: E402
from src.utils.llm_provider import EmptyStructuredOutput, LLMFactory, structured_output  # noqa: E402

YNU = Literal["yes", "no", "undeterminable"]
YNUN = Literal["yes", "no", "undeterminable", "none"]
ITEMS = ["references_argument", "argument_source", "relevant", "supports", "rebutted", "rebuttal_resolved"]


class EvidenceLabel(BaseModel):
    references_argument: YNU
    argument_source: Literal["own", "peer", "both", "none"]
    argument_seqs: List[int] = Field(default_factory=list)
    relevant: YNUN
    supports: YNUN
    rebutted: YNUN
    rebuttal_resolved: Literal["yes", "no", "not_rebutted", "undeterminable"]


def parse_text_label(resp) -> EvidenceLabel:
    """응답 본문(문자열 또는 블록 목록)의 마지막 JSON 객체를 EvidenceLabel 로 파싱"""
    c = resp.content
    text = c if isinstance(c, str) else "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    i, j = text.rfind("{"), text.rfind("}")
    return EvidenceLabel.model_validate(json.loads(text[i:j + 1]))


def build_sample(agents: str, blocks_per_item: int, seed: int) -> pd.DataFrame:
    a = pd.read_csv(agents)
    a = a[a["label"].isin(["A-baseline", "A-stateful"]) & a["topic_key"].str.contains("-g") & ~a["topic_key"].str.contains("debranded")]
    rng = np.random.default_rng(seed)
    keep = []
    for item, g in a.groupby("item_id"):
        both = sorted(set(g[g["label"] == "A-baseline"]["topic_key"]) & set(g[g["label"] == "A-stateful"]["topic_key"]))
        keep.extend(rng.choice(both, blocks_per_item, replace=False))
    s = a[a["topic_key"].isin(set(keep))].sort_values(["item_id", "topic_key", "label", "participant"])
    return s[["discussion_id", "participant", "item_id", "topic_key", "label", "block", "pre", "post"]].reset_index(drop=True)


async def code(items: pd.DataFrame, db: str, out: Path, provider: str, model: str, max_tokens: int = 0) -> None:
    cfg = config_loader.get_coding_config()
    llm = LLMFactory.create_llm(LLMProvider(provider), model=model, temperature=cfg.temperature, max_tokens=max_tokens or cfg.evidence_max_tokens)
    runnable = structured_output(llm, EvidenceLabel)
    system = config_loader.prompts.get("coding.evidence_coding.system")
    con = sqlite3.connect(db)
    done = set()
    if out.exists():
        prev = pd.read_csv(out).dropna(subset=["references_argument"])  # 실패(빈 라벨) 행은 버리고 다시 코딩한다
        prev.to_csv(out, index=False)
        done = set(zip(prev["discussion_id"], prev["participant"]))
    items = items[[(d, p) not in done for d, p in zip(items["discussion_id"], items["participant"])]]
    print(f"model {provider}/{model}: {len(items)} to code (skipping {len(done)})", flush=True)
    transcripts, proposals, reasons = {}, {}, {}
    for d in items["discussion_id"].unique():
        rows = con.execute("select seq, speaker, speaker_type, content from messages where discussion_id=? order by seq", (d,)).fetchall()
        transcripts[d] = "\n\n".join(f"#{s} {sp}{' (moderator)' if st == 'moderator' else ''}: {c}" for s, sp, st, c in rows)
        proposals[d] = con.execute("select topic from discussions where id=?", (d,)).fetchone()[0]
        for p, r in con.execute("select participant, reason from survey_responses where discussion_id=? and phase='post' and participant_type='ai'", (d,)):
            reasons[(d, p)] = r or ""
    new = not out.exists()
    fh = open(out, "a", newline="", encoding="utf-8")
    w = csv.writer(fh)
    keys = ["discussion_id", "participant", "item_id", "topic_key", "label", "block", "pre", "post"]
    if new:
        w.writerow(keys + ITEMS + ["argument_seqs", "model", "attempts"])
    sem = asyncio.Semaphore(cfg.concurrency)
    lock = asyncio.Lock()
    stats = {"ok": 0, "fail": 0}

    async def one(row):
        d = row["discussion_id"]
        user = config_loader.prompts.render("coding.evidence_coding.user", proposal=proposals[d], transcript=transcripts[d], speaker=row["participant"],
                                            pre=row["pre"], post=row["post"], reason=reasons.get((d, row["participant"]), "") or "(empty)")
        lab, attempts = None, 0
        async with sem:
            for attempts in range(1, cfg.max_attempts + 1):
                try:
                    lab = await runnable.ainvoke([("system", system), ("human", user)])
                    break
                except EmptyStructuredOutput:
                    # 추론형 모델(GLM)은 도구 호출 대신 본문에 JSON을 쓴다: 본문에서 파싱
                    try:
                        lab = parse_text_label(await llm.ainvoke([("system", system), ("human", user)]))
                        break
                    except Exception as e:
                        if attempts == cfg.max_attempts:
                            print("fail", d, row["participant"], "text-parse", type(e).__name__, str(e)[:120], flush=True)
                        continue
                except Exception as e:
                    if attempts == cfg.max_attempts:
                        print("fail", d, row["participant"], type(e).__name__, str(e)[:160], flush=True)
                    await asyncio.sleep(min(60, 3 * 2 ** attempts) if "429" in str(e) else 2 * attempts)
        async with lock:
            w.writerow([row[k] for k in keys] + ([getattr(lab, i) for i in ITEMS] + [json.dumps(lab.argument_seqs)] if lab else [""] * (len(ITEMS) + 1)) + [model, attempts])
            fh.flush()
            stats["ok" if lab else "fail"] += 1

    t0 = time.time()
    rows = [r for _, r in items.iterrows()]
    for i in range(0, len(rows), 100):
        await asyncio.gather(*(one(r) for r in rows[i:i + 100]))
        print(f"{min(i + 100, len(rows))}/{len(rows)} ok {stats['ok']} fail {stats['fail']} {time.time() - t0:.0f}s", flush=True)
    fh.close()


def _share(s: pd.Series) -> dict:
    return {str(k): float(v) for k, v in s.value_counts(normalize=True).sort_index().items()}


def _kappa(a: pd.Series, b: pd.Series) -> float:
    cats = sorted(set(a) | set(b))
    po = float((a == b).mean())
    pe = sum(float((a == c).mean() * (b == c).mean()) for c in cats)
    return float((po - pe) / (1 - pe)) if pe < 1 else float("nan")


def summarize(coded: List[str], boot: int = 2000, seed: int = 2026) -> dict:
    """코더별 조건 × 항목 비율(블록 재표집 구간은 1차 코더만), 코더 간 일치율·κ. 사람 60건 검증은 별도 파일로 붙인다."""
    sys.path.insert(0, str(ROOT))
    from src.analysis.exploratory import _resample, _summ
    frames = {Path(p).stem: pd.read_csv(p) for p in coded}
    out = {"coders": {}, "agreement": {}}
    rng = np.random.default_rng(seed)
    for name, t in frames.items():
        ok = t.dropna(subset=["references_argument"])
        c = {"model": str(t["model"].iloc[0]), "n": int(len(ok)), "fail_rate": float(1 - len(ok) / len(t)), "by_label": {}}
        for lab, g in ok.groupby("label"):
            d = {"n": int(len(g)), "items": {i: _share(g[i]) for i in ITEMS}}
            d["peer_or_both_among_referencing"] = float(g[g["references_argument"] == "yes"]["argument_source"].isin(["peer", "both"]).mean()) if (g["references_argument"] == "yes").any() else float("nan")
            # 핵심 비율 4개의 블록 재표집 구간 (yes 비율; 분모는 전체, supports·rebutted는 참조한 것 중)
            blocks = g["block"].unique()
            bb = {b: x for b, x in g.groupby("block")}
            def stat(s):
                ref = s["references_argument"] == "yes"
                return {"references": float(ref.mean()), "supports_given_ref": float((s[ref]["supports"] == "yes").mean()) if ref.any() else np.nan,
                        "rebutted_given_ref": float((s[ref]["rebutted"] == "yes").mean()) if ref.any() else np.nan,
                        "peer_given_ref": float(s[ref]["argument_source"].isin(["peer", "both"]).mean()) if ref.any() else np.nan}
            point = stat(g)
            draws = [stat(pd.concat([bb[b] for b in _resample(blocks, rng)])) for _ in range(boot)]
            d["key"] = {k: _summ(point[k], [x[k] for x in draws if not np.isnan(x[k])], len(g), "block") for k in point}
            c["by_label"][lab] = d
        out["coders"][name] = c
    names = list(frames)
    if len(names) >= 2:
        m = frames[names[0]].merge(frames[names[1]], on=["discussion_id", "participant"], suffixes=("_a", "_b")).dropna(subset=["references_argument_a", "references_argument_b"])
        out["agreement"] = {"coders": names, "n": int(len(m)),
                            "items": {i: {"exact": float((m[f"{i}_a"].astype(str) == m[f"{i}_b"].astype(str)).mean()), "kappa": _kappa(m[f"{i}_a"].astype(str), m[f"{i}_b"].astype(str))} for i in ITEMS}}
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--agents", required=True)
    s.add_argument("--blocks-per-item", type=int, default=2)
    s.add_argument("--seed", type=int, default=2026)
    s.add_argument("--out", required=True)
    c = sub.add_parser("code")
    c.add_argument("--db", required=True)
    c.add_argument("--sample", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--second", action="store_true", help="제2 코더(config evidence_coding_second_model/provider)")
    c.add_argument("--limit", type=int, default=0)
    c.add_argument("--max-tokens", type=int, default=0, help="config evidence_max_tokens 대신 쓸 한도 (사고 토큰이 한도를 넘겨 본문이 빈 건의 재시도용)")
    z = sub.add_parser("summarize")
    z.add_argument("--coded", nargs="+", required=True)
    z.add_argument("--out", required=True)
    args = p.parse_args(argv)
    if args.mode == "sample":
        df = build_sample(args.agents, args.blocks_per_item, args.seed)
        df.to_csv(args.out, index=False)
        print(f"sample {len(df)} rows, items {df['item_id'].nunique()}, groups {df['topic_key'].nunique()}")
    elif args.mode == "code":
        cfg = config_loader.get_coding_config()
        provider, model = (cfg.evidence_coding_second_provider, cfg.evidence_coding_second_model) if args.second else (cfg.provider, cfg.evidence_coding_model)
        items = pd.read_csv(args.sample)
        if args.limit:
            items = items.head(args.limit)
        asyncio.run(code(items, args.db, Path(args.out), provider, model, args.max_tokens))
    else:
        res = summarize(args.coded)
        Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({k: v["by_label"] for k, v in res["coders"].items()}, indent=1)[:3000])
        print(json.dumps(res["agreement"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
