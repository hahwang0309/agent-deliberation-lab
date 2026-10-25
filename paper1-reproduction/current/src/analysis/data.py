"""
실험 DB와 계획 파일을 합쳐 설문 응답 표를 만든다 (분석 계획 2절, 6절)

행 = 실행(토론) × 참가자 × 문항 × 시점. 계획 파일의 주제 메타(심은 값, 응답자 행, DeliData 집단)를 붙인다.
"""
import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd
import yaml


def study_of(topic_key: str) -> str:
    """주제 키로 연구를 가른다: deli-/variant- → wason, argq → argq, 나머지(문항 id) → a1r"""
    if topic_key.startswith(("deli-", "variant-")):
        return "wason"
    if topic_key.startswith("argq"):
        return "argq"
    return "a1r"


def a1r_set(topic_key: str) -> str:
    """1-B 주제의 종류: groups(5명 반복 집단), debranded(이름 제거), small(실제 소집단 복제)"""
    if "-debranded-" in topic_key:
        return "debranded"
    if "-group" in topic_key:
        return "small"
    return "groups"


def load_plans(paths: Iterable[str]) -> Dict[str, Dict[str, dict]]:
    """계획 이름 → 주제 키 → 주제 (계획 파일의 name이 실행의 batch)"""
    plans = {}
    for path in paths:
        with open(path, encoding="utf-8") as f:
            plan = yaml.safe_load(f)
        plans[plan["name"]] = {t["key"]: t for t in plan["topics"]}
    return plans


def _participant_model(run_info: list, default_models: Dict[str, str]) -> Tuple[str, str]:
    """실행 기록에서 참가자 모델 (모두 같은 모델이라고 가정하고 첫 참가자). 모델이 비어 있으면 프로바이더 기본 모델"""
    llm = (run_info[-1] if run_info else {}).get("llm") or {}
    first = next(iter((llm.get("participants") or {}).values()), {})
    provider = first.get("provider")
    return provider, first.get("model") or default_models.get(provider)


def load_runs(dbs: Iterable[str], plans: Dict[str, Dict[str, dict]], default_models: Dict[str, str]
              ) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """(실행 표, 설문 표). 실행 표는 완료 여부와 관계없이 모든 실행, 설문 표는 완료한 실행의 응답만"""
    runs, surveys = [], []
    for db in dbs:
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        for d in con.execute("select id, status, config, run_info from discussions"):
            cfg = json.loads(d["config"])
            e = cfg.get("experiment") or {}
            key = e.get("topic_key")
            if not key or e.get("batch") not in plans:
                continue
            provider, model = _participant_model(json.loads(d["run_info"] or "[]"), default_models)
            run = {"db": Path(db).name, "discussion_id": d["id"], "status": d["status"], "batch": e["batch"],
                   "study": study_of(key), "topic_key": key, "label": e.get("label"),
                   "mode": e.get("mode", "stateful"), "replicate": e.get("replicate", 0),
                   "provider": provider, "model": model}
            run["block"] = block_of(run)
            runs.append(run)
            if d["status"] != "completed":
                continue
            for r in con.execute("select phase, participant, item_id, score, correct, source, scale, scale_min, "
                                 "choices from survey_responses where discussion_id=?", (d["id"],)):
                surveys.append({**run, **dict(r)})
    return pd.DataFrame(runs), pd.DataFrame(surveys)


def block_of(row) -> str:
    """같은 처치를 받는 복제 단위: 1-A·1-B는 주제(집단) × 반복, 1-C는 세트(주제 × 표적 입장) × 반복"""
    return f"{row['topic_key']}#r{row['replicate']}"


def exclusions(runs: pd.DataFrame, required: Dict[str, List[str]]) -> Tuple[pd.DataFrame, List[dict]]:
    """분석 계획 6절: 재시도 후에도 실패한 조건이 있는 블록은 그 연구에서 통째로 제외.
    required: 연구 → 블록마다 있어야 하는 조건 label. 반환: (남길 실행, 제외 기록)"""
    keep, log = [], []
    for (model, study, topic), g in runs.groupby(["model", "study", "topic_key"]):
        ok = g[g["status"] == "completed"]
        need = required.get(study, [])
        # 같은 주제의 반복(replicate) 수가 조건마다 다를 수 있어 조건 label 단위로만 확인
        missing = [lab for lab in need if lab in set(g["label"]) and lab not in set(ok["label"])]
        if missing:
            log.append({"model": model, "study": study, "topic_key": topic, "missing": missing,
                        "failed_runs": int((g["status"] != "completed").sum())})
            continue
        keep.append(ok)
    kept = pd.concat(keep) if keep else runs.iloc[0:0]
    return kept, log


MISSING_GAP = 0.05  # 6절: 조건 간 무응답률 차이가 이보다 크면 민감도 분석


def sensitivity_studies(rates: pd.DataFrame) -> Dict[str, float]:
    """조건 간 무응답률 차이(최대 − 최소)가 5%p를 넘는 연구 → 그 차이"""
    gaps = rates.groupby("study")["missing_rate"].agg(lambda r: r.max() - r.min()) if len(rates) else pd.Series(dtype=float)
    return {s: float(g) for s, g in gaps.items() if g > MISSING_GAP}


def complete_blocks(surveys: pd.DataFrame, studies: Iterable[str]) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """민감도 분석의 완전 블록: 지정한 연구에서 사후 무응답이 하나라도 있는 주제(모든 조건·반복)를 뺀다.
    제외 단위는 실패 블록 제외(exclusions)와 같은 주제. 반환: (남은 설문 표, 연구 → 뺀 주제 수)"""
    post = surveys[surveys["phase"] == "post"]
    bad = post[post["score"].isna() & post["correct"].isna() & post["study"].isin(list(studies))]
    drop = set(zip(bad["study"], bad["topic_key"]))
    keep = [(s, k) not in drop for s, k in zip(surveys["study"], surveys["topic_key"])]
    dropped = pd.Series([s for s, _ in drop]).value_counts().to_dict() if drop else {}
    return surveys[keep], {s: int(n) for s, n in dropped.items()}


def missing_rates(surveys: pd.DataFrame) -> pd.DataFrame:
    """사후 설문 무응답률 (모델 × 연구 × 조건). 6절: 조건 간 차이가 5%p를 넘으면 민감도 분석"""
    post = surveys[surveys["phase"] == "post"]
    out = (post.assign(missing=post["score"].isna() & post["correct"].isna())
           .groupby(["model", "study", "label"])["missing"].agg(["mean", "size"]).reset_index())
    return out.rename(columns={"mean": "missing_rate", "size": "n"})
