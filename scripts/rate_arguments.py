"""
연구 1-C 조작 확인 - 모델이 강한 논거(ArgQ 품질 상위 25%)를 약한 논거(하위 25%)보다 높게 평가하는지

사용 예:
  python scripts/rate_arguments.py data/cases/argq.yaml --provider claude --out data/pilot/ratings-claude.csv
  (모델은 config/config.yaml llm.default_models, temperature 0)

토론과 분리된 단독 호출로 논거마다 질을 0~1로 묻는다(프롬프트: config/prompts.yaml manipulation_check).
요약: 모델 평가의 강·약 평균, 세트별(주제 × 표적 입장) 강 − 약 차이, 강 > 약인 세트 비율, 군중 평정(WA)과의 상관.
"""
import argparse
import asyncio
import csv
import statistics as st
import sys
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.config_loader import config_loader  # noqa: E402
from src.models.personas import LLMProvider  # noqa: E402
from src.utils.llm_provider import LLMFactory, structured_output  # noqa: E402


class ArgumentRating(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0, description="argument quality from 0 (very weak) to 1 (very strong)")


async def rate_all(plan_path: str, provider: LLMProvider, concurrency: int):
    plan = yaml.safe_load(Path(plan_path).read_text(encoding="utf-8"))
    llm = LLMFactory.create_llm(provider, temperature=0.0)
    rater = structured_output(llm, ArgumentRating)
    semaphore = asyncio.Semaphore(concurrency)
    jobs = [(t["key"], t["topic"], quality, a) for t in plan["topics"]
            for quality, args in t["meta"]["arguments"].items() for a in args]

    async def one(key, topic, quality, a):
        async with semaphore:
            prompt = config_loader.prompts.render("manipulation_check.argument_quality", topic=topic, argument=a["argument"])
            try:
                score = (await rater.ainvoke(prompt)).score
            except Exception as e:  # 실패는 비워 두고 보고한다 (채우지 않음)
                print(f"rating failed for {key}/{quality}: {e}", file=sys.stderr)
                score = None
            return {"topic_key": key, "quality": quality, "wa": a["wa"], "tokens": a["tokens"],
                    "model": getattr(llm, "model", None) or getattr(llm, "model_name", ""), "rating": score}

    return await asyncio.gather(*(one(*j) for j in jobs))


def summarize(rows):
    ok = [r for r in rows if r["rating"] is not None]
    strong = [r["rating"] for r in ok if r["quality"] == "strong"]
    weak = [r["rating"] for r in ok if r["quality"] == "weak"]
    diffs = []
    for key in sorted({r["topic_key"] for r in ok}):
        s = [r["rating"] for r in ok if r["topic_key"] == key and r["quality"] == "strong"]
        w = [r["rating"] for r in ok if r["topic_key"] == key and r["quality"] == "weak"]
        if s and w:
            diffs.append(st.mean(s) - st.mean(w))
    corr = st.correlation([r["wa"] for r in ok], [r["rating"] for r in ok]) if len(ok) > 2 else None
    return {"rated": len(ok), "failed": len(rows) - len(ok), "mean_strong": round(st.mean(strong), 3),
            "mean_weak": round(st.mean(weak), 3), "mean_set_diff": round(st.mean(diffs), 3),
            "sets_strong_gt_weak": f"{sum(d > 0 for d in diffs)}/{len(diffs)}",
            "corr_with_wa": round(corr, 3) if corr is not None else None}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="1-C 조작 확인: 논거 질 평가")
    parser.add_argument("plan", help="build_cases.py argq로 만든 계획 YAML")
    parser.add_argument("--provider", required=True, choices=[p.value for p in LLMProvider])
    parser.add_argument("--out", required=True, help="평가 CSV")
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args(argv)
    rows = asyncio.run(rate_all(args.plan, LLMProvider(args.provider), args.concurrency))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(summarize(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
