"""
실험 데이터셋 추출 CLI

사용 예 (DATABASE_URL·SECRET_KEY는 서버와 같은 .env 또는 환경변수):
  python scripts/export_dataset.py --db data/experiments.db --label no-latitude --out data/no-latitude
  python scripts/export_dataset.py --db data/experiments.db --batch example-death-penalty --out data/example
  python scripts/export_dataset.py --ids disc_a disc_b --out data/pair --format jsonl
  python scripts/export_dataset.py --label pilot --out data/pilot --coding-sample 100 --seed 7

출력: 표마다 파일 1개 (discussions, utterances, stances, moves, concessions, attacks, surveys).
--coding-sample N이면 사람 코딩용 coding_blind.csv(코더용)와 coding_key.csv(LLM 판정, 코더에게 주지 않음)도 만든다.
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _cell(value: Any) -> Any:
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value


def write_rows(path: Path, rows: List[Dict[str, Any]], fmt: str) -> None:
    if fmt == "jsonl":
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return
    columns = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # BOM: 엑셀에서 한글이 깨지지 않도록
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _cell(v) for k, v in row.items()})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="실험 데이터셋 추출")
    parser.add_argument("--label", help="실험 조건 label이 같은 토론")
    parser.add_argument("--batch", help="배치 이름이 같은 토론 (scripts/run_experiment.py의 plan name)")
    parser.add_argument("--ids", nargs="+", help="토론 id 목록 (--label·--batch 대신)")
    parser.add_argument("--out", required=True, help="출력 폴더")
    parser.add_argument("--format", choices=("csv", "jsonl"), default="csv")
    parser.add_argument("--coding-sample", type=int, default=0, help="사람 코딩용 표본 발언 수")
    parser.add_argument("--seed", type=int, default=0, help="표본 추출 시드")
    parser.add_argument("--db", help="실험 DB 파일 경로 (scripts/run_experiment.py --db와 같은 파일)")
    args = parser.parse_args(argv)
    if not (args.ids or args.label or args.batch):
        parser.error("--label, --batch, --ids 중 하나는 필요합니다")

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    if args.db:  # api 모듈을 불러오기 전에 DB를 정해야 한다
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(args.db).resolve()}"
    from api.runtime import persistence
    from src.services.experiment_export import coding_sample, merge_tables

    ids = args.ids or persistence.experiment_discussion_ids(label=args.label, batch=args.batch)
    if not ids:
        print("추출할 토론이 없습니다.", file=sys.stderr)
        return 1
    bundles = [persistence.export_bundle(i) for i in ids]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in merge_tables(bundles).items():
        write_rows(out / f"{name}.{args.format}", rows, args.format)
        print(f"{name}: {len(rows)} rows")
    if args.coding_sample:
        blind, key = coding_sample(bundles, args.coding_sample, seed=args.seed)
        write_rows(out / "coding_blind.csv", blind, "csv")
        write_rows(out / "coding_key.csv", key, "csv")
        print(f"coding sample: {len(blind)} utterances (coding_blind.csv for coders, coding_key.csv withheld)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
