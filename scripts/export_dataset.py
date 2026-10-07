"""
실험 데이터셋 추출 CLI

사용 예 (DATABASE_URL·SECRET_KEY는 서버와 같은 .env 또는 환경변수):
  python scripts/export_dataset.py --label no-latitude --out data/no-latitude
  python scripts/export_dataset.py --ids disc_a disc_b --out data/pair --format jsonl
  python scripts/export_dataset.py --label pilot --out data/pilot --coding-sample 100 --seed 7

출력: 표마다 파일 1개 (discussions, utterances, stances, moves, concessions, attacks, surveys).
--coding-sample N이면 사람 코딩용 coding_blind.csv(코더용)와 coding_key.csv(LLM 판정, 코더에게 주지 않음)도 만든다.
"""
import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from api.runtime import persistence  # noqa: E402
from src.services.experiment_export import coding_sample, merge_tables  # noqa: E402


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
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--label", help="실험 조건 label이 같은 토론 전부")
    target.add_argument("--ids", nargs="+", help="토론 id 목록")
    parser.add_argument("--out", required=True, help="출력 폴더")
    parser.add_argument("--format", choices=("csv", "jsonl"), default="csv")
    parser.add_argument("--coding-sample", type=int, default=0, help="사람 코딩용 표본 발언 수")
    parser.add_argument("--seed", type=int, default=0, help="표본 추출 시드")
    args = parser.parse_args(argv)

    ids = persistence.discussion_ids_by_label(args.label) if args.label else args.ids
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
