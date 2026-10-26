"""
N10: 발언 유형 코딩 (DeliData 체계: type ∈ probing/non_probing/none, target ∈ solution/reasoning/agree/disagree/moderation/none).
계획: docs/research/study1-exploratory-plan.md 4절 (조정용·검증용 표본 분리, 라벨별 허용 기준, 비교용·설명용 표본 구분).

  # 1) 사람 주석 대비 코더 검증: DeliData 메시지 표본 (조정용 tune / 검증용 validate, 서로 다른 집단)
  python scripts/code_utterances.py delidata --split validate --n 600 --out data/study1/results/exploratory/coding/delidata_validate.csv
  # 2) AI 발언 코딩: 비교용 표본(결과와 무관한 층화 무작위) 또는 설명용 표본(집단 목록 파일)
  python scripts/code_utterances.py ai --db data/study1/claude.db --utterances data/study1/results/exploratory/claude/utterances.csv \
      --groups data/study1/results/exploratory/coding/comparison_groups.csv --out data/study1/results/exploratory/coding/ai_claude.csv
  # 공통: --model 로 config [coding].utterance_coding_model 을 바꿀 수 있다(제2 코더). 출력은 재개 가능(이미 있는 행 건너뜀).

출력 열: source(delidata|ai), unit(discussion_id|group_id), seq/row, speaker, type, target, model, attempts, (delidata: gold_type, gold_target).
"""
import argparse
import asyncio
import csv
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Literal, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.config_loader import config_loader  # noqa: E402
from src.models.personas import LLMProvider  # noqa: E402
from src.utils.llm_provider import EmptyStructuredOutput, LLMFactory, structured_output  # noqa: E402

CONTEXT_N = 3  # 라벨할 메시지 앞의 문맥 메시지 수


class UtteranceLabel(BaseModel):
    type: Literal["probing", "non_probing", "none"]
    target: Literal["solution", "reasoning", "agree", "disagree", "moderation", "none"]


GOLD_TYPE = {"Probing": "probing", "Non-probing-deliberation": "non_probing", "None": "none", "0": "none"}
GOLD_TARGET = {"Solution": "solution", "Reasoning": "reasoning", "Agree": "agree", "Disagree": "disagree", "Moderation": "moderation", "0": "none", "None": "none"}


def delidata_messages(directory: str) -> pd.DataFrame:
    rows = []
    for path in sorted(Path(directory).glob("*.tsv")):
        if path.name == "sample.tsv":
            continue
        with path.open(encoding="utf-8") as f:
            data = list(csv.DictReader(f, delimiter="\t"))
        msgs = [r for r in data if r["message_type"] == "MESSAGE"]
        for i, r in enumerate(msgs):
            rows.append({"group_id": r["group_id"], "idx": i, "speaker": r["origin"], "text": r["original_text"],
                         "gold_type": GOLD_TYPE.get(r["annotation_type"], "none"), "gold_target": GOLD_TARGET.get(r["annotation_target"], "none"),
                         "context": "\n".join(f"{m['origin']}: {m['original_text']}" for m in msgs[max(0, i - CONTEXT_N):i])})
    return pd.DataFrame(rows)


def delidata_sample(df: pd.DataFrame, split: str, n: int, seed: int) -> pd.DataFrame:
    """조정용/검증용은 서로 다른 집단에서. 집단을 시드로 반으로 나누고(tune = 앞 절반, validate = 뒤 절반), target 라벨로 층화 추출"""
    rng = np.random.default_rng(seed)
    groups = np.array(sorted(df["group_id"].unique()))
    rng.shuffle(groups)
    half = len(groups) // 2
    pool = df[df["group_id"].isin(groups[:half] if split == "tune" else groups[half:])]
    per = max(1, n // pool["gold_target"].nunique())
    parts = [g.sample(min(len(g), per), random_state=seed) for _, g in pool.groupby("gold_target")]
    out = pd.concat(parts)
    if len(out) > n:
        out = out.sample(n, random_state=seed)
    return out.sort_values(["group_id", "idx"])


def ai_messages(db: str, utterances: str, groups_csv: Optional[str], labels: List[str], per_label_groups: int, seed: int) -> pd.DataFrame:
    """AI 발언 (1-A 원 과제). groups_csv(열: topic_key, stratum)가 있으면 그 집단만(설명용), 없으면 k × 집단 크기 층화 무작위(비교용)"""
    utt = pd.read_csv(utterances, low_memory=False)
    a = utt[(utt["study"] == "wason") & (utt["speaker_type"] != "moderator") & utt["topic_key"].str.startswith("deli-") & utt["label"].isin(labels)
            & ((utt["label"] == "A-stateful") | (utt["replicate"] == 0))]
    wr = pd.read_csv(Path(utterances).with_name("wason_runs.csv"))
    meta = wr.drop_duplicates("block").set_index("block")[["k", "size"]]
    a = a.join(meta, on="topic_key")
    if groups_csv:
        g = pd.read_csv(groups_csv)
        a = a[a["topic_key"].isin(set(g["topic_key"]))].merge(g[["topic_key", "stratum"]], on="topic_key", how="left")
    else:
        rng = np.random.default_rng(seed)
        a["stratum"] = a["k"].astype(str) + "|" + np.where(a["size"] <= 3, "2-3", "4-6")
        keep = []
        for st, grp in a.drop_duplicates("topic_key").groupby("stratum"):
            keys = grp["topic_key"].to_numpy()
            keep.extend(rng.choice(keys, min(per_label_groups, len(keys)), replace=False))
        a = a[a["topic_key"].isin(set(keep))]
    con = sqlite3.connect(db)
    rows = []
    for d, r in a.sort_values(["discussion_id", "seq"]).groupby("discussion_id"):
        texts = dict(con.execute("select seq, content from messages where discussion_id=? and speaker_type!='moderator' order by seq", (d,)).fetchall())
        seqs = sorted(texts)
        spk = dict(zip(r["seq"], r["speaker"]))
        for seq in r["seq"]:
            i = seqs.index(seq)
            ctx = "\n".join(f"{spk.get(s, '?')}: {texts[s]}" for s in seqs[max(0, i - CONTEXT_N):i])
            rows.append({"discussion_id": d, "topic_key": r["topic_key"].iloc[0], "label": r["label"].iloc[0], "stratum": r["stratum"].iloc[0],
                         "seq": seq, "speaker": spk[seq], "text": texts[seq], "context": ctx})
    return pd.DataFrame(rows)


async def code(items: pd.DataFrame, out: Path, model: str, key_cols: List[str]) -> None:
    cfg = config_loader.get_coding_config()
    llm = LLMFactory.create_llm(LLMProvider(cfg.provider), model=model, temperature=cfg.temperature, max_tokens=cfg.max_tokens)
    runnable = structured_output(llm, UtteranceLabel)
    system = config_loader.prompts.get("coding.utterance_coding.system")
    done = set()
    if out.exists():
        prev = pd.read_csv(out)
        prev = prev.dropna(subset=["type", "target"])  # 실패(빈 라벨) 행은 버리고 다시 코딩한다
        prev.to_csv(out, index=False)
        done = set(tuple(x) for x in prev[key_cols].astype(str).to_numpy())
    items = items[[tuple(map(str, x)) not in done for x in items[key_cols].to_numpy()]]
    print(f"model {model}: {len(items)} to code (skipping {len(done)})", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    new = not out.exists()
    fh = open(out, "a", newline="", encoding="utf-8")
    w = csv.writer(fh)
    cols = list(items.columns.drop(["text", "context"])) + ["type", "target", "model", "attempts"]
    if new:
        w.writerow(cols)
    sem = asyncio.Semaphore(cfg.concurrency)
    lock = asyncio.Lock()
    stats = {"ok": 0, "fail": 0}

    async def one(row):
        user = config_loader.prompts.render("coding.utterance_coding.user", context=row["context"] or "(none)", speaker=row["speaker"], text=row["text"])
        lab, attempts = None, 0
        async with sem:
            for attempts in range(1, cfg.max_attempts + 1):
                try:
                    res = await runnable.ainvoke([("system", system), ("human", user)])
                    lab = (res.type, res.target)
                    break
                except EmptyStructuredOutput:
                    continue
                except Exception as e:
                    await asyncio.sleep(min(60, 3 * 2 ** attempts) if "429" in str(e) else 2 * attempts)
        async with lock:
            w.writerow([row[c] for c in cols[:-4]] + ([lab[0], lab[1]] if lab else ["", ""]) + [model, attempts])
            fh.flush()
            stats["ok" if lab else "fail"] += 1

    t0 = time.time()
    rows = [r for _, r in items.iterrows()]
    for i in range(0, len(rows), 200):
        await asyncio.gather(*(one(r) for r in rows[i:i + 200]))
        print(f"{min(i + 200, len(rows))}/{len(rows)} ok {stats['ok']} fail {stats['fail']} {time.time() - t0:.0f}s", flush=True)
    fh.close()


def report_validation(path: Path) -> None:
    """검증용 표본: 라벨별 정밀도·재현율, 혼동행렬, 일치율 (사람 주석 대비 = 정확성)"""
    t = pd.read_csv(path).dropna(subset=["type", "target"])
    for col in ("type", "target"):
        gold, pred = t[f"gold_{col}"], t[col]
        print(f"\n[{col}] agreement {(gold == pred).mean():.3f} (n {len(t)})")
        print(pd.crosstab(gold, pred, rownames=["gold"], colnames=["pred"]))
        for lab in sorted(set(gold)):
            tp = ((gold == lab) & (pred == lab)).sum()
            p = tp / max((pred == lab).sum(), 1)
            r = tp / max((gold == lab).sum(), 1)
            print(f"  {lab:12s} precision {p:.2f} recall {r:.2f} n_gold {(gold == lab).sum()}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)
    d = sub.add_parser("delidata")
    d.add_argument("--delidata", default=str(ROOT / "data/raw/delidata"))
    d.add_argument("--split", choices=["tune", "validate"], required=True)
    d.add_argument("--n", type=int, required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--model")
    d.add_argument("--seed", type=int, default=2026)
    d.add_argument("--report-only", action="store_true")
    a = sub.add_parser("ai")
    a.add_argument("--db", required=True)
    a.add_argument("--utterances", required=True)
    a.add_argument("--groups", help="설명용 표본: 열 topic_key, stratum 의 CSV")
    a.add_argument("--labels", nargs="+", default=["A-baseline", "A-stateful"])
    a.add_argument("--per-stratum", type=int, default=12, help="비교용 표본: k × 집단 크기 층마다 뽑을 집단 수")
    a.add_argument("--out", required=True)
    a.add_argument("--model")
    a.add_argument("--seed", type=int, default=2026)
    args = p.parse_args(argv)
    cfg = config_loader.get_coding_config()
    model = args.model or cfg.utterance_coding_model
    if args.mode == "delidata":
        out = Path(args.out)
        if not args.report_only:
            df = delidata_sample(delidata_messages(args.delidata), args.split, args.n, args.seed)
            df = df.rename(columns={"group_id": "unit"})
            asyncio.run(code(df, out, model, ["unit", "idx"]))
        report_validation(out)
    else:
        df = ai_messages(args.db, args.utterances, args.groups, args.labels, args.per_stratum, args.seed)
        asyncio.run(code(df, Path(args.out), model, ["discussion_id", "seq"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
