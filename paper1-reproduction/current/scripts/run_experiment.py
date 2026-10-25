"""
배치 실험 실행 CLI

사용 예:
  python scripts/run_experiment.py config/experiments/example.yaml --db data/experiments.db --dry-run
  python scripts/run_experiment.py config/experiments/example.yaml --db data/experiments.db

- --db: 실험 전용 SQLite 파일 (필수, 웹 서버 DB와 분리). 없으면 만들고 마이그레이션을 적용한다.
- --dry-run: 실행할 건수, 건너뛸 건수(이미 완료), 예상 토큰·비용만 출력하고 끝낸다.
- 같은 명령을 다시 실행하면 완료된 (주제, 조건, 반복)은 건너뛰고 나머지만 실행한다.
- 결과 추출: python scripts/export_dataset.py --label <조건 label> --out <폴더>  (같은 --db 환경에서)
API 키·SECRET_KEY는 .env에서 읽는다.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="배치 실험 실행")
    parser.add_argument("plan", help="실험 계획 YAML")
    parser.add_argument("--db", required=True, help="실험 전용 DB 파일 경로 (웹 서버 DB에 섞이지 않도록 필수)")
    parser.add_argument("--dry-run", action="store_true", help="추정만 하고 실행하지 않음")
    parser.add_argument("--until-fraction", type=float,
                        help="실행 순서의 앞에서부터 전체의 이 비율까지만 실행 (단계별 실행, 예: 0.05). 이어 돌리면 완료분은 건너뜀")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    # api 모듈을 불러오기 전에 DB를 정해야 한다
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(args.db).resolve()}"
    Path(args.db).resolve().parent.mkdir(parents=True, exist_ok=True)

    from api.database import init_db
    from api.services.experiment_runner import estimate, existing_runs, load_plan, plan_runs, run_batch, runs_until

    init_db()
    plan = load_plan(args.plan)
    done = existing_runs(plan.name)
    target = runs_until(plan, args.until_fraction)
    pending = [r for r in target if (done.get(r.key) or {}).get("status") != "completed"]
    completed = sum((done.get(r.key) or {}).get("status") == "completed" for r in plan_runs(plan))
    print(f"plan {plan.name}: {len(plan.topics)} topics x {len(plan.conditions)} conditions x {plan.repetitions} reps "
          f"= {len(plan_runs(plan))} runs, already completed {completed}"
          + (f", this stage up to {len(target)} ({args.until_fraction:.0%})" if args.until_fraction is not None else ""))
    print("estimate:", json.dumps(estimate(plan, pending, done), ensure_ascii=False))
    if args.dry_run:
        return 0

    result = asyncio.run(run_batch(plan, until_fraction=args.until_fraction))
    cost = result.cost(plan.prices)
    print(f"completed {len(result.completed)}, failed {len(result.failed)}, skipped {result.skipped}, "
          f"not started {result.not_started}{' (limit reached)' if result.stopped_by_limit else ''}, "
          f"network retries {result.network_retries}, final failures skipped {result.final_failed}")
    print(f"tokens in {result.prompt_tokens}, out {result.completion_tokens}"
          + (f", cost ${cost:.2f}" if cost is not None else ""))
    if result.aborted:
        print(f"ABORTED: {result.aborted}")
        return 3
    return 0 if not result.failed else 2


if __name__ == "__main__":
    sys.exit(main())
