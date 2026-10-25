"""
N9 보조: 1-A 발언에서 발언자의 현재 카드 선택을 LLM으로 추출한다 (docs/research/study1-exploratory-plan.md 7절 C단계).

  python scripts/extract_cards.py --db data/study1/claude.db --plans data/study1/plans/*.yaml \
      --utterances data/study1/results/exploratory/claude/utterances.csv --out data/study1/results/exploratory/claude/n9_llm_choices.csv
  python scripts/extract_cards.py ... --validate 300 --model mistral-large-2512   # 검증: 마지막 발언 추출 대 사후 설문 일치율

- 대상: 원 과제(deli-) A-기준선 1회째 + A-상태 기반의 AI 발언. 모델·온도·동시성은 config/config.yaml [coding], 프롬프트는 config/coding_prompts.yaml.
- 출력 CSV: discussion_id, seq, speaker, cards(JSON 또는 null), model, attempts, prompt_tokens, completion_tokens. 이미 있는 행은 건너뛴다(재개 가능).
- 비용·토큰은 로그와 CSV에 남긴다. 결과는 scripts/analyze_study1_exploratory.py --only N9 가 n9_llm_choices.csv 를 읽어 정규식 대신 쓴다.
"""
import argparse
import asyncio
import csv
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Optional

import pandas as pd
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.config_loader import config_loader  # noqa: E402
from src.analysis import data as adata  # noqa: E402
from src.models.personas import LLMProvider  # noqa: E402
from src.utils.llm_provider import EmptyStructuredOutput, LLMFactory, structured_output  # noqa: E402


class CardChoice(BaseModel):
    cards: Optional[List[str]] = Field(None, description="the speaker's own current selection of cards to turn over, or null if not stated")


def targets(utt: pd.DataFrame) -> pd.DataFrame:
    a = utt[(utt["study"] == "wason") & (utt["speaker_type"] != "moderator") & utt["topic_key"].str.startswith("deli-")
            & utt["label"].isin(["A-baseline", "A-stateful"]) & ((utt["label"] == "A-stateful") | (utt["replicate"] == 0))]
    return a[["discussion_id", "topic_key", "seq", "speaker", "label"]].sort_values(["discussion_id", "seq"])


async def main_async(args) -> int:
    cfg = config_loader.get_coding_config()
    model = args.model or cfg.card_extraction_model
    llm = LLMFactory.create_llm(LLMProvider(cfg.provider), model=model, temperature=cfg.temperature, max_tokens=cfg.max_tokens)
    runnable = structured_output(llm, CardChoice)
    system = config_loader.prompts.get("coding.card_extraction.system")
    plans = adata.load_plans(args.plans)
    utt = pd.read_csv(args.utterances, low_memory=False)
    t = targets(utt)
    con = sqlite3.connect(args.db)
    out = Path(args.out)
    done = set()
    if out.exists():
        prev = pd.read_csv(out)
        done = set(zip(prev["discussion_id"], prev["seq"]))
    if args.validate:
        # 각 조건에서 참가자별 마지막 발언만, 사후 설문이 있는 것
        last = t.groupby(["discussion_id", "speaker"]).tail(1)
        t = last.groupby("label").sample(n=args.validate // 2, random_state=args.seed)
        out = out.with_name(out.stem + f"_validate_{model}.csv")
        if out.exists():
            out.unlink()
        done = set()
    t = t[[(d, s) not in done for d, s in zip(t["discussion_id"], t["seq"])]]
    print(f"model {model}, targets {len(t)} (skipping {len(done)} done)", flush=True)
    texts = {}
    for d in t["discussion_id"].unique():
        for seq, content in con.execute("select seq, content from messages where discussion_id=?", (d,)):
            texts[(d, seq)] = content
    sem = asyncio.Semaphore(cfg.concurrency)
    write_lock = asyncio.Lock()
    new_file = not out.exists()
    fh = open(out, "a", newline="", encoding="utf-8")
    writer = csv.writer(fh)
    if new_file:
        writer.writerow(["discussion_id", "seq", "speaker", "label", "cards", "model", "attempts", "prompt_tokens", "completion_tokens"])
    stats = {"ok": 0, "null": 0, "fail": 0, "pt": 0, "ct": 0}

    async def one(row):
        options = None
        for b, topics in plans.items():
            if row.topic_key in topics:
                options = [o.upper() for o in topics[row.topic_key]["survey"]["items"][0]["options"]]
                break
        user = config_loader.prompts.render("coding.card_extraction.user", options=", ".join(options), speaker=row.speaker, text=texts.get((row.discussion_id, row.seq), ""))
        msgs = [("system", system), ("human", user)]
        cards, attempts, pt, ct = None, 0, 0, 0
        async with sem:
            for attempts in range(1, cfg.max_attempts + 1):
                try:
                    res = await runnable.ainvoke(msgs)
                    cards = [c.strip().upper() for c in (res.cards or []) if c and c.strip().upper() in options] if res.cards is not None else None
                    break
                except EmptyStructuredOutput:
                    cards = None
                    if attempts == cfg.max_attempts:
                        stats["fail"] += 1
                except Exception as e:  # 서버 오류·속도 제한(429): 지수 대기 뒤 재시도
                    if attempts == cfg.max_attempts:
                        stats["fail"] += 1
                        print("fail", row.discussion_id, row.seq, type(e).__name__, str(e)[:120], flush=True)
                    await asyncio.sleep(min(60, 3 * 2 ** attempts) if "429" in str(e) else 2 * attempts)
        async with write_lock:
            writer.writerow([row.discussion_id, row.seq, row.speaker, row.label, json.dumps(cards) if cards is not None else "null", model, attempts, pt, ct])
            fh.flush()
            stats["ok" if cards is not None else "null"] += 1

    t0 = time.time()
    rows = list(t.itertuples(index=False))
    for i in range(0, len(rows), 200):
        await asyncio.gather(*(one(r) for r in rows[i:i + 200]))
        print(f"{min(i + 200, len(rows))}/{len(rows)} ok {stats['ok']} null {stats['null']} fail {stats['fail']} {time.time() - t0:.0f}s", flush=True)
    fh.close()
    if args.validate:
        res = pd.read_csv(out)
        post = {(d, p): c for d, p, c in con.execute("select discussion_id, participant, choices from survey_responses where phase='post'")}
        res["survey"] = [post.get((d, p)) for d, p in zip(res["discussion_id"], res["speaker"])]
        res = res[res["survey"].notna()]
        def match(c, s):
            if c == "null" or pd.isna(c):
                return None
            cc, ss = json.loads(c), json.loads(s)
            return ss is not None and set(cc) == set(x.upper() for x in ss)
        res["match"] = [match(c, s) for c, s in zip(res["cards"], res["survey"])]
        for lab, g in res.groupby("label"):
            m = g["match"].dropna()
            print(f"[validate {model}] {lab}: extracted {len(m)}/{len(g)} ({len(m)/len(g):.0%}), match {m.mean():.3f}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", required=True)
    p.add_argument("--plans", nargs="+", required=True)
    p.add_argument("--utterances", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model", help="config [coding].card_extraction_model 대신 쓸 모델")
    p.add_argument("--validate", type=int, default=0, help="검증 표본 크기 (참가자별 마지막 발언, 조건당 절반씩)")
    p.add_argument("--seed", type=int, default=2026)
    args = p.parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
