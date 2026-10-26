"""
N6 ②: 장치 수행 판정 (docs/research/study1-exploratory-plan.md 5절 ②·7절 D단계). 상태 기반 엔진이 지시한 장치가 발언 텍스트에서 실제로 수행됐는지를
독립 코더(Claude 분석기와 다른 계열)가 판정한다. 장치 발언 4종 × 300 + 기준선 대조 발언 300 (Claude, 시드 고정).

  python scripts/code_devices.py sample --db data/study1/claude.db --utterances data/study1/results/exploratory/claude/utterances.csv \
      --out data/study1/results/exploratory/coding/devices_sample.csv
  python scripts/code_devices.py code --sample data/study1/results/exploratory/coding/devices_sample.csv --out data/study1/results/exploratory/coding/devices_large.csv
  python scripts/code_devices.py code ... --model mistral-small-2603 --out .../devices_small.csv     # 제2 코더
  python scripts/code_devices.py summarize --coded data/study1/results/exploratory/coding/devices_large.csv data/study1/results/exploratory/coding/devices_small.csv \
      --out data/study1/results/exploratory/claude/n6b.json

장치 정의(발언 행의 출처): respond_challenge = action; mediate = action mediate 또는 third_option; devils_advocate = action; switched = 프롬프트에
"your position has shifted to" 안내가 있던 발언; control = A-기준선 reply 발언(지시 없음). 지시 발췌는 메시지 meta.prompt에서 정규식으로 뽑는다.
"""
import argparse
import asyncio
import csv
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Literal, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.config_loader import config_loader  # noqa: E402
from src.models.personas import LLMProvider  # noqa: E402
from src.utils.llm_provider import EmptyStructuredOutput, LLMFactory, structured_output  # noqa: E402

CONTEXT_N = 3
ITEMS = ["addresses_specific_claim", "concedes_part", "names_disagreement_between_others", "proposes_third_option", "objects_to_shared_view", "states_position_change"]
YPN = Literal["yes", "partial", "no"]
DEVICES = ["respond_challenge", "mediate", "devils_advocate", "switched", "control"]
# 장치별로 "지시가 요구한 것"에 해당하는 관찰 항목 (장치 발언 대 대조 발언 비교에 쓴다)
DEVICE_ITEM = {"respond_challenge": "addresses_specific_claim", "mediate": "names_disagreement_between_others",
               "devils_advocate": "objects_to_shared_view", "switched": "states_position_change"}


class DeviceLabel(BaseModel):
    addresses_specific_claim: YPN
    concedes_part: YPN
    names_disagreement_between_others: YPN
    proposes_third_option: YPN
    objects_to_shared_view: YPN
    states_position_change: YPN
    instruction_followed: Literal["yes", "partial", "no", "none"]


def instruction_excerpt(device: str, prompt: str) -> str:
    """메시지 프롬프트에서 장치 지시 부분만 뽑는다 (지시 문구는 config/prompts.yaml 의 turn_actions)"""
    if device == "respond_challenge":
        m = list(re.finditer(r"([A-Z][\w ]*?) said \(#\d+\):\n<<<\n(.*?)\n>>>\n\n\1 challenged you\.(.*?)(?:\n\n|$)", prompt, re.S))
        if m:
            who, claim, rest = m[-1].group(1), m[-1].group(2), m[-1].group(3)
            return f"{who} said:\n<<<\n{claim}\n>>>\n{who} challenged you.{rest.strip()}"
    if device == "mediate":
        m = re.search(r"([A-Z][\w ]*? and [A-Z][\w ]*? keep disagreeing\..*?)(?:\n\n|$)", prompt, re.S) or re.search(r"([A-Z][\w ]*? and [A-Z][\w ]*? are stuck between two positions\..*?)(?:\n\n|$)", prompt, re.S)
        if m:
            return m.group(1).strip()
    if device == "devils_advocate":
        m = re.search(r"(The group is converging quickly\..*?)(?:\n\n|$)", prompt, re.S)
        if m:
            return m.group(1).strip()
    if device == "switched":
        m = re.search(r"([^\n]*your position has shifted to[^\n]*)", prompt)
        if m:
            return m.group(1).strip()
    return ""


def build_sample(db: str, utterances: str, per: int, seed: int) -> pd.DataFrame:
    utt = pd.read_csv(utterances, low_memory=False)
    ai = utt[utt["speaker_type"] != "moderator"]
    st = ai[ai["label"] == "A-stateful"]
    pools = {"respond_challenge": st[st["action"] == "respond_challenge"],
             "mediate": st[st["action"].isin(["mediate", "third_option"])],
             "devils_advocate": st[st["action"] == "devils_advocate"],
             "switched": st[st["note_switched"] == 1],
             "control": ai[(ai["label"] == "A-baseline") & (ai["action"] == "reply")]}
    rng = np.random.default_rng(seed)
    parts = []
    for dev, pool in pools.items():
        idx = rng.choice(len(pool), min(per, len(pool)), replace=False)
        p = pool.iloc[sorted(idx)][["discussion_id", "seq", "speaker", "study", "label", "action", "topic_key", "block"]].copy()
        p.insert(0, "device", dev)
        parts.append(p)
    s = pd.concat(parts, ignore_index=True)
    con = sqlite3.connect(db)
    texts, instr, ctxs = [], [], []
    for r in s.itertuples(index=False):
        rows = con.execute("select seq, speaker, speaker_type, content, meta from messages where discussion_id=? and seq<=? order by seq", (r.discussion_id, int(r.seq))).fetchall()
        me = rows[-1]
        prev = [x for x in rows[:-1] if x[2] != "moderator"][-CONTEXT_N:]
        ctxs.append("\n".join(f"{x[1]}: {x[3]}" for x in prev))
        texts.append(me[3])
        instr.append(instruction_excerpt(r.device, (json.loads(me[4]) or {}).get("prompt") or "") if r.device != "control" else "")
    s["context"], s["instruction"], s["text"] = ctxs, instr, texts
    missing = s[(s["device"] != "control") & (s["instruction"] == "")]
    print(f"sample {len(s)} rows; instruction excerpt missing in {len(missing)} device rows", flush=True)
    return s


async def code(items: pd.DataFrame, out: Path, model: str) -> None:
    cfg = config_loader.get_coding_config()
    llm = LLMFactory.create_llm(LLMProvider(cfg.provider), model=model, temperature=cfg.temperature, max_tokens=cfg.max_tokens)
    runnable = structured_output(llm, DeviceLabel)
    system = config_loader.prompts.get("coding.device_coding.system")
    done = set()
    if out.exists():
        prev = pd.read_csv(out).dropna(subset=ITEMS)  # 실패(빈 라벨) 행은 버리고 다시 코딩한다
        prev.to_csv(out, index=False)
        done = set(zip(prev["discussion_id"], prev["seq"]))
    items = items[[(d, q) not in done for d, q in zip(items["discussion_id"], items["seq"])]]
    print(f"model {model}: {len(items)} to code (skipping {len(done)})", flush=True)
    new = not out.exists()
    fh = open(out, "a", newline="", encoding="utf-8")
    w = csv.writer(fh)
    keys = ["device", "discussion_id", "seq", "speaker", "study", "label", "action", "block"]
    if new:
        w.writerow(keys + ITEMS + ["instruction_followed", "model", "attempts"])
    sem = asyncio.Semaphore(cfg.concurrency)
    lock = asyncio.Lock()
    stats = {"ok": 0, "fail": 0}

    async def one(row):
        user = config_loader.prompts.render("coding.device_coding.user", context=row["context"] or "(none)", instruction=row["instruction"] or "(none)",
                                            speaker=row["speaker"], text=row["text"])
        lab, attempts = None, 0
        async with sem:
            for attempts in range(1, cfg.max_attempts + 1):
                try:
                    lab = await runnable.ainvoke([("system", system), ("human", user)])
                    break
                except EmptyStructuredOutput:
                    continue
                except Exception as e:
                    await asyncio.sleep(min(60, 3 * 2 ** attempts) if "429" in str(e) else 2 * attempts)
        async with lock:
            w.writerow([row[k] for k in keys] + ([getattr(lab, i) for i in ITEMS] + [lab.instruction_followed] if lab else [""] * (len(ITEMS) + 1)) + [model, attempts])
            fh.flush()
            stats["ok" if lab else "fail"] += 1

    t0 = time.time()
    rows = [r for _, r in items.iterrows()]
    for i in range(0, len(rows), 200):
        await asyncio.gather(*(one(r) for r in rows[i:i + 200]))
        print(f"{min(i + 200, len(rows))}/{len(rows)} ok {stats['ok']} fail {stats['fail']} {time.time() - t0:.0f}s", flush=True)
    fh.close()


def _share(s: pd.Series) -> Dict[str, float]:
    return {k: float((s == k).mean()) for k in ("yes", "partial", "no")}


def _kappa(a: pd.Series, b: pd.Series) -> float:
    cats = sorted(set(a) | set(b))
    po = float((a == b).mean())
    pe = sum((a == c).mean() * (b == c).mean() for c in cats)
    return float((po - pe) / (1 - pe)) if pe < 1 else float("nan")


def summarize(coded: List[str]) -> dict:
    """코더별 장치 × 항목 yes/partial/no 비율, 지시 수행 비율, 코더 간 일치율·κ (장치 발언 대 대조 발언 비교는 DEVICE_ITEM 열)"""
    frames = {Path(p).stem: pd.read_csv(p).dropna(subset=ITEMS) for p in coded}
    out = {"n_items": {k: int(len(v)) for k, v in frames.items()}, "coders": {}, "agreement": {}}
    for name, t in frames.items():
        c = {"model": str(t["model"].iloc[0]), "fail_rate": float(1 - len(t) / len(pd.read_csv([p for p in coded if Path(p).stem == name][0]))), "by_device": {}}
        for dev, g in t.groupby("device"):
            d = {"n": int(len(g)), "items": {i: _share(g[i]) for i in ITEMS}}
            if dev != "control":
                d["instruction_followed"] = _share(g["instruction_followed"])
                d["device_item"] = DEVICE_ITEM[dev]
            c["by_device"][dev] = d
        out["coders"][name] = c
    names = list(frames)
    if len(names) >= 2:
        a, b = frames[names[0]], frames[names[1]]
        m = a.merge(b, on=["discussion_id", "seq"], suffixes=("_a", "_b"))
        ag = {}
        for i in ITEMS + ["instruction_followed"]:
            x, y = m[f"{i}_a"].astype(str), m[f"{i}_b"].astype(str)
            ag[i] = {"exact": float((x == y).mean()), "kappa": _kappa(x, y),
                     "yes_vs_not": float(((x == "yes") == (y == "yes")).mean()), "kappa_yes_vs_not": _kappa(x == "yes", y == "yes")}
        out["agreement"] = {"coders": names, "n": int(len(m)), "items": ag}
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--db", required=True)
    s.add_argument("--utterances", required=True)
    s.add_argument("--per", type=int, default=300)
    s.add_argument("--seed", type=int, default=2026)
    s.add_argument("--out", required=True)
    c = sub.add_parser("code")
    c.add_argument("--sample", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--model")
    c.add_argument("--limit", type=int, default=0, help="시험용: 앞 n건만")
    z = sub.add_parser("summarize")
    z.add_argument("--coded", nargs="+", required=True)
    z.add_argument("--out", required=True)
    args = p.parse_args(argv)
    if args.mode == "sample":
        build_sample(args.db, args.utterances, args.per, args.seed).to_csv(args.out, index=False)
    elif args.mode == "code":
        items = pd.read_csv(args.sample).fillna({"context": "", "instruction": "", "text": ""})
        if args.limit:
            items = items.groupby("device").head(max(1, args.limit // len(DEVICES)))
        model = args.model or config_loader.get_coding_config().device_coding_model
        asyncio.run(code(items, Path(args.out), model))
    else:
        Path(args.out).write_text(json.dumps(summarize(args.coded), ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(summarize(args.coded)["agreement"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
