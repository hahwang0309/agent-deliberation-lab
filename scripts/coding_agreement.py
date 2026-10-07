"""
코딩 일치도 계산 CLI

  python scripts/coding_agreement.py --coded coder1.csv --key coding_key.csv      # 사람 vs LLM (양보)
  python scripts/coding_agreement.py --coded coder1.csv --second coder2.csv       # 코더 간 (모든 코딩 항목)
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.coding_agreement import coder_vs_coder, human_vs_llm  # noqa: E402


def read(path: str):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="코딩 일치도")
    parser.add_argument("--coded", required=True, help="코더가 채운 coding_blind.csv")
    parser.add_argument("--key", help="coding_key.csv (LLM 판정과 비교)")
    parser.add_argument("--second", help="두 번째 코더의 파일 (코더 간 비교)")
    args = parser.parse_args(argv)
    if not (args.key or args.second):
        parser.error("--key 또는 --second가 필요합니다")
    result = {}
    if args.key:
        result["human_vs_llm"] = human_vs_llm(read(args.coded), read(args.key))
    if args.second:
        result["coder_vs_coder"] = coder_vs_coder(read(args.coded), read(args.second))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
