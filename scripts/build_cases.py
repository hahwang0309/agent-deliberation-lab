"""
연구용 사례 생성 CLI - 공개 데이터에서 실험 계획 YAML을 만든다 (실행: scripts/run_experiment.py)

원자료는 data/raw/ 아래에 둔다 (저장소에 포함하지 않음, docs/experiments.md "사례 생성").
  data/raw/delidata/*.tsv                 DeliData (CC-BY 4.0)
  data/raw/a1r/{dataset,codebook}.tab     America in One Room (CC0)
  data/raw/a1r/briefing.pdf               A1R 브리핑 자료집 (pdftotext 필요)
  data/raw/argq/{train,dev,test}.csv      IBM ArgQ 30k (CC-BY 3.0)

사용 예:
  python scripts/build_cases.py wason --out data/cases/wason.yaml
  python scripts/build_cases.py wason-variants --n 60 --seed 1 --out data/cases/wason_variants.yaml
  python scripts/build_cases.py a1r-briefing --out data/cases/a1r_briefing.yaml   # 초안 → 연구자가 원문과 대조해 확정
  python scripts/build_cases.py a1r --set development --groups-per-item 8 --seed 1 --briefing data/cases/a1r_briefing.yaml --out data/cases/a1r_dev.yaml
  python scripts/build_cases.py a1r --debranded --seed 1 --briefing data/cases/a1r_briefing.yaml --out data/cases/a1r_debranded.yaml
  python scripts/build_cases.py a1r --small-groups Q5A Q3A --seed 1 --briefing data/cases/a1r_briefing.yaml --out data/cases/a1r_groups.yaml
  python scripts/build_cases.py argq --seed 1 --out data/cases/argq.yaml

만든 계획은 실행 전에 모든 (주제, 조건) 요청을 검증한다. 실패하면 이유를 출력하고 파일을 쓰지 않는다
(--allow-invalid로 그래도 쓸 수 있음. 예: 참가자 상한보다 큰 소집단).
"""
import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RAW = ROOT / "data" / "raw"


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def plan_dict(name: str, topics: List[Dict[str, Any]], conditions: List[Dict[str, Any]],
              repetitions: int = 1) -> Dict[str, Any]:
    return {"name": name, "repetitions": repetitions, "concurrency": 4, "retries": 1, "report": False,
            "limits": {"max_total_tokens": 5_000_000}, "topics": topics, "conditions": conditions}


def validate(plan: Dict[str, Any]) -> List[str]:
    """계획 형식과 모든 (주제, 조건)의 토론 생성 요청을 검사 (LLM·DB 없이)"""
    from fastapi import HTTPException
    from pydantic import ValidationError

    from api.services.discussion_service import DiscussionService
    from api.services.experiment_runner import ExperimentPlan, Run, build_request
    try:
        parsed = ExperimentPlan(**plan)
    except ValidationError as e:
        return [f"plan: {e}"]
    errors = []
    for t in parsed.topics:
        for c in parsed.conditions:
            try:
                DiscussionService.validate_request(build_request(parsed, Run(t, c, 0)), is_admin=True)
            except HTTPException as e:
                errors.append(f"{t.key} / {c.label}: {e.detail['error']['code']}: {e.detail['error']['message']}")
            except (ValidationError, ValueError) as e:
                errors.append(f"{t.key} / {c.label}: {str(e).splitlines()[0]} ...")
    return errors


def write_plan(plan: Dict[str, Any], out: str, allow_invalid: bool) -> int:
    errors = validate(plan)
    for e in errors[:20]:
        print("invalid:", e, file=sys.stderr)
    if len(errors) > 20:
        print(f"... {len(errors) - 20} more", file=sys.stderr)
    if errors and not allow_invalid:
        print("plan not written (use --allow-invalid to write anyway)", file=sys.stderr)
        return 1
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(plan, Dumper=_NoAliasDumper, allow_unicode=True, sort_keys=False, width=120),
                    encoding="utf-8")
    runs = sum((c.get("repetitions") or plan["repetitions"]) for c in plan["conditions"]) * len(plan["topics"])
    print(f"wrote {path}: {len(plan['topics'])} topics x {len(plan['conditions'])} conditions = {runs} runs")
    return 0


def cmd_wason(args) -> int:
    from src.cases import wason
    groups = wason.load_delidata(args.data)
    topics, excluded = wason.replica_topics(groups, size=args.size, max_statements=args.max_statements)
    print(f"DeliData groups with {args.size} members: {len(topics) + sum(excluded.values())}; "
          f"replicated {len(topics)}; excluded {excluded or 0}")
    return write_plan(plan_dict(args.name, topics, wason.CONDITIONS), args.out, args.allow_invalid)


def cmd_wason_variants(args) -> int:
    from src.cases import wason
    dist = wason.solo_role_distribution(wason.load_delidata(args.data))
    topics = wason.variant_topics(args.n, dist, args.seed, size=args.size, max_statements=args.max_statements)
    conditions = [c for c in wason.CONDITIONS if c["label"] != "B-resolve"]  # 설계: A 두 모드 + C
    print("solo answer role distribution:", {"+".join(k): v for k, v in dist.most_common()})
    return write_plan(plan_dict(args.name, topics, conditions), args.out, args.allow_invalid)


def cmd_a1r_briefing(args) -> int:
    from src.cases import a1r, briefing
    text_path = Path(args.pdf).with_suffix(".txt")
    subprocess.run(["pdftotext", "-layout", args.pdf, str(text_path)], check=True, capture_output=True)
    text = text_path.read_text(encoding="utf-8")
    t = a1r.texts()["a1r"]
    items = a1r.load_items(args.codebook)
    wanted = {q: items[q] for q in t["development"] + t["locked"]}
    rows = briefing.parse_tables(text)
    matched = briefing.match_items(rows, wanted)
    issues = briefing.parse_issues(text, list(t["domains"].values()))
    draft = {"_note": "DRAFT parsed from briefing.pdf. Check every item against the PDF (match_score, column bleed) "
                      "before use; set reviewed: true when done.",
             "reviewed": False, "issues": issues,
             "items": {q: {"label": wanted[q], **matched[q]} for q in wanted if q in matched}}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(yaml.dump(draft, Dumper=_NoAliasDumper, allow_unicode=True, sort_keys=False, width=120),
                              encoding="utf-8")
    low = sorted((v["match_score"], q) for q, v in draft["items"].items() if v["match_score"] < args.min_score)
    print(f"parsed {len(rows)} table rows, matched {len(draft['items'])}/{len(wanted)} items, issues for {sorted(issues)}")
    print(f"low match (< {args.min_score}), check first: {low}")
    print(f"wrote draft {args.out}")
    return 0


def _briefing(path: str, require_reviewed: bool) -> Dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if require_reviewed and not data.get("reviewed"):
        raise SystemExit(f"{path} is an unreviewed draft (reviewed: false). Check it and set reviewed: true, "
                         "or pass --allow-draft for a pilot")
    return data


def cmd_a1r(args) -> int:
    from src.cases import a1r
    t = a1r.texts()["a1r"]
    items = a1r.load_items(args.codebook)
    brief = _briefing(args.briefing, not args.allow_draft) if args.briefing else None
    if args.small_groups:
        ids = args.small_groups
    elif args.debranded:
        ids = list(t["debranded"])
    else:
        ids = {"development": t["development"], "locked": t["locked"],
               "all": t["development"] + t["locked"]}[args.set]
    delegates = a1r.load_delegates(args.dataset, list(items))
    print(f"delegates with post-survey: {len(delegates)}; party mix {dict(Counter(a1r.PARTIES[d.party] for d in delegates))}")
    if args.small_groups:
        topics = a1r.small_group_topics(delegates, items, ids, args.seed, brief, max_statements=args.max_statements)
        sizes = Counter(len(tp["personas"]) for tp in topics)
        print(f"small groups: {len(topics)} topics, sizes {dict(sorted(sizes.items()))}")
    else:
        topics = a1r.sampled_topics(delegates, items, ids, args.groups_per_item, args.seed, brief,
                                    max_statements=args.max_statements or 15, debranded=args.debranded)
    conditions = a1r.CONDITIONS if brief else [c for c in a1r.CONDITIONS if c.get("use_materials") is False]
    if not brief:
        print("no --briefing: only conditions without materials (C, D) are included")
    return write_plan(plan_dict(args.name, topics, conditions), args.out, args.allow_invalid)


def cmd_argq(args) -> int:
    from src.cases import argq
    topics, conditions = argq.topics_and_conditions(argq.load_arguments(args.data), args.seed)
    return write_plan(plan_dict(args.name, topics, conditions, repetitions=args.repetitions), args.out,
                      args.allow_invalid)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="연구용 사례 생성")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, name):
        p.add_argument("--out", required=True)
        p.add_argument("--name", default=name, help="배치 이름 (plan name)")
        p.add_argument("--allow-invalid", action="store_true")

    p = sub.add_parser("wason", help="DeliData 집단 복제")
    common(p, "wason-replica")
    p.add_argument("--data", default=str(RAW / "delidata"))
    p.add_argument("--size", type=int, default=3)
    p.add_argument("--max-statements", type=int, default=9)
    p.set_defaults(func=cmd_wason)

    p = sub.add_parser("wason-variants", help="같은 구조의 새 변형 문항")
    common(p, "wason-variants")
    p.add_argument("--data", default=str(RAW / "delidata"))
    p.add_argument("--n", type=int, default=60)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--size", type=int, default=3)
    p.add_argument("--max-statements", type=int, default=9)
    p.set_defaults(func=cmd_wason_variants)

    p = sub.add_parser("a1r-briefing", help="자료집에서 자료 상자 초안 추출")
    p.add_argument("--pdf", default=str(RAW / "a1r" / "briefing.pdf"))
    p.add_argument("--codebook", default=str(RAW / "a1r" / "codebook.tab"))
    p.add_argument("--min-score", type=float, default=0.75)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_a1r_briefing)

    p = sub.add_parser("a1r", help="A1R 반복 집단·이름 제거·실제 소집단")
    common(p, "a1r")
    p.add_argument("--dataset", default=str(RAW / "a1r" / "dataset.tab"))
    p.add_argument("--codebook", default=str(RAW / "a1r" / "codebook.tab"))
    p.add_argument("--briefing", help="확정한 자료 상자 YAML (없으면 자료 없는 조건만)")
    p.add_argument("--allow-draft", action="store_true", help="검토 전 초안 자료로 만들기 (파일럿용)")
    p.add_argument("--set", choices=("development", "locked", "all"), default="development")
    p.add_argument("--groups-per-item", type=int, default=8)
    p.add_argument("--debranded", action="store_true", help="이름 제거 문항(cases.yaml a1r.debranded)만")
    p.add_argument("--small-groups", nargs="+", metavar="ITEM", help="이 문항들로 실제 소집단 복제")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--max-statements", type=int)
    p.set_defaults(func=cmd_a1r)

    p = sub.add_parser("argq", help="ArgQ 강·약 논거 × 지지자 수")
    common(p, "argq")
    p.add_argument("--data", default=str(RAW / "argq"))
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--repetitions", type=int, default=8)
    p.set_defaults(func=cmd_argq)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
