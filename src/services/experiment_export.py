"""
실험 데이터 추출 - 토론 기록을 분석용 표(행 목록)로 펼친다

입력은 persistence.export_bundle()의 결과이며 LLM을 호출하지 않는다.
여러 토론의 표를 이어 붙일 수 있도록 모든 행에 discussion_id가 있다.

표:
  discussions  토론 1행 (조건, 모드, 모델, 사용량, 보고서 점수)
  utterances   발언 1행 (화자, 행위, 명제, 대상, 텍스트, 분석 결과 요약)
  stances      발언 시점 × 참가자 1행 (분석이 추정한 입장 x)
  moves        입장 이동 1행 (설득, 양보, 반발)
  concessions  양보 1행
  attacks      반박·질문 1행 (분석이 판정한 공격 관계)
  surveys      설문 응답 1행 (참가자 × 문항 × 시점)

사람 코딩용 표본(coding_sample): 코더에게 주는 블라인드 파일과 LLM 판정이 든 정답 키를 따로 만든다.
"""
import random
from typing import Any, Dict, List, Tuple

TABLES = ("discussions", "utterances", "stances", "moves", "concessions", "attacks", "surveys")


def _experiment(discussion: Dict[str, Any]) -> Dict[str, Any]:
    return discussion["config"].get("experiment") or {}


def discussion_row(discussion: Dict[str, Any]) -> Dict[str, Any]:
    exp = _experiment(discussion)
    run = discussion["run_info"][-1] if discussion["run_info"] else {}
    llm = run.get("llm") or {}
    report = discussion["report"] or {}
    return {
        "discussion_id": discussion["id"], "topic": discussion["topic"], "language": discussion["language"],
        "status": discussion["status"], "label": exp.get("label"), "batch": exp.get("batch"),
        "topic_key": exp.get("topic_key"), "replicate": exp.get("replicate"),
        "mode": (run.get("settings") or {}).get("engine_mode") or exp.get("mode", "stateful"),
        "n_participants": len(discussion["participants"]),
        "max_statements": discussion["config"].get("max_statements"),
        "propositions": " | ".join(discussion["subtopics"]),
        "mechanisms": exp.get("mechanisms"), "experiment": exp,
        "participant_models": {p["name"]: p["model"] for p in discussion["participants"]},
        "analyzer_model": (llm.get("analyzer") or {}).get("model"),
        "git_commit": run.get("git_commit"), "git_dirty": run.get("git_dirty"),
        "prompt_hash": (run.get("prompt_hashes") or {}).get("config/prompts.yaml"),
        "prompt_tokens": discussion["prompt_tokens"], "completion_tokens": discussion["completion_tokens"],
        "llm_calls": discussion["llm_calls"],
        "consensus_overall": report.get("consensus_score"), "consensus_ai": report.get("ai_score"),
        "consensus_human": report.get("human_score"), "consensus_ai_human": report.get("ai_human_score"),
        "consensus_label": report.get("label"),
        "started_at": discussion["started_at"], "completed_at": discussion["completed_at"],
    }


def build_tables(bundle: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    discussion = bundle["discussion"]
    did = discussion["id"]
    tables: Dict[str, List[Dict[str, Any]]] = {name: [] for name in TABLES}
    tables["discussions"].append(discussion_row(discussion))

    for m in bundle["messages"]:
        meta = m.get("meta") or {}
        analysis = meta.get("analysis") or {}
        seq = m["seq"]
        tables["utterances"].append({
            "discussion_id": did, "seq": seq, "speaker": m["speaker"], "speaker_type": m["speaker_type"],
            "action": m.get("action"), "subtopic_idx": meta.get("subtopic_idx"), "target_seq": meta.get("target_seq"),
            "in_reply_to_seq": meta.get("in_reply_to_seq"), "text": m["content"], "chars": len(m["content"] or ""),
            "analyzed": bool(analysis), "move": analysis.get("move"), "stance": analysis.get("stance"),
            "claims": " | ".join(analysis.get("claims") or []),
            "n_attacks": sum(t.get("relation") == "attack" for t in analysis.get("targets") or []),
            "n_supports": sum(t.get("relation") == "support" for t in analysis.get("targets") or []),
            "n_concessions": len(analysis.get("concessions") or []),
        })
        for name, x in (meta.get("stances") or {}).items():
            if x is not None:
                tables["stances"].append({"discussion_id": did, "seq": seq, "subtopic_idx": meta.get("subtopic_idx"),
                                          "participant": name, "stance": x})
        for mv in meta.get("moves") or []:
            tables["moves"].append({"discussion_id": did, "seq": seq, "listener": mv["listener"], "by": mv["by"],
                                    "delta": mv["delta"], "x_after": mv.get("x"),
                                    "kind": mv.get("kind", "persuasion"), "zone": mv.get("zone"),
                                    "boomerang": bool(mv.get("boomerang"))})
        for c in analysis.get("concessions") or []:
            tables["concessions"].append({"discussion_id": did, "seq": seq, "by": m["speaker"], "to": c["to"],
                                          "claim": c["claim"]})
        for t in analysis.get("targets") or []:
            if t.get("relation") in ("attack", "question"):
                tables["attacks"].append({"discussion_id": did, "seq": seq, "by": m["speaker"], "target": t["speaker"],
                                          "target_seq": t["seq"], "relation": t["relation"]})

    for r in bundle["survey"]:
        tables["surveys"].append({"discussion_id": did, **r})
    return tables


def merge_tables(bundles: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    merged: Dict[str, List[Dict[str, Any]]] = {name: [] for name in TABLES}
    for bundle in bundles:
        for name, rows in build_tables(bundle).items():
            merged[name].extend(rows)
    return merged


CODING_COLUMNS = ("code_concession", "code_responds_to_previous", "code_justification_level", "code_respect_level")


def coding_sample(bundles: List[Dict[str, Any]], n: int, seed: int = 0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """사람 코딩용 표본: (블라인드 파일, 정답 키). 분석된 AI 발언 중 n개를 무작위로 뽑는다.
    블라인드 파일에는 직전 발언과 대상 발언을 문맥으로 넣고 코딩 칸은 비워 둔다. LLM 판정은 키에만 있다.
    코딩 항목: 양보 여부, 직전·대상 발언에 대한 응답 여부, 정당화 수준(DQI 0~3), 존중 수준(DQI 0~2)."""
    candidates = []
    for bundle in bundles:
        messages = bundle["messages"]
        by_seq = {m["seq"]: m for m in messages}
        for i, m in enumerate(messages):
            analysis = (m.get("meta") or {}).get("analysis")
            if m["speaker_type"] != "ai" or not analysis:
                continue
            previous = next((p for p in reversed(messages[:i]) if p["speaker_type"] != "moderator"), None)
            target = by_seq.get((m.get("meta") or {}).get("target_seq"))
            candidates.append((bundle["discussion"]["id"], m, previous, target, analysis))
    rng = random.Random(seed)
    picked = rng.sample(candidates, min(n, len(candidates)))
    blind, key = [], []
    for k, (did, m, previous, target, analysis) in enumerate(picked, start=1):
        sample_id = f"S{k:04d}"
        blind.append({
            "sample_id": sample_id, "speaker": m["speaker"],
            "previous": f"{previous['speaker']}: {previous['content']}" if previous else "",
            "target": f"{target['speaker']}: {target['content']}" if target and target is not previous else "",
            "text": m["content"], **{c: "" for c in CODING_COLUMNS},
        })
        key.append({
            "sample_id": sample_id, "discussion_id": did, "seq": m["seq"], "action": m.get("action"),
            "llm_move": analysis.get("move"), "llm_concession": bool(analysis.get("concessions")),
            "llm_concessions": " | ".join(f"{c['to']}: {c['claim']}" for c in analysis.get("concessions") or []),
            "llm_attacks": sum(t.get("relation") == "attack" for t in analysis.get("targets") or []),
        })
    return blind, key
