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

from config.config_loader import config_loader

# 이 이상이면 같은 화자가 앞서 한 주장을 되풀이한 것으로 본다. 문자 2-gram 유사도라 표현을 바꾼 반복은
# 잘 잡지 못하는 대리 지표다(실측: 같은 논거의 바꿔 말하기가 0.37~0.55). 사람 코딩(code_repeats_own_argument)으로 보정할 것.


def _bigrams(text: str) -> set:
    """문자 2-gram (공백·문장부호 제거, 한국어에도 형태소 분석 없이 쓸 수 있음)"""
    chars = "".join(ch for ch in text.lower() if ch.isalnum())
    return {chars[i:i + 2] for i in range(len(chars) - 1)}


def similarity(a: str, b: str) -> float:
    """문자 2-gram Jaccard 유사도 (0~1)"""
    x, y = _bigrams(a), _bigrams(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def repeat_scores(messages: List[Dict[str, Any]]) -> Dict[int, float]:
    """발언 seq → 이 발언의 주장들이 같은 화자의 이전 주장과 가장 비슷한 정도(0~1).
    발언 분석의 claims를 쓰며, 주장이 없거나 화자의 첫 발언이면 기록하지 않는다."""
    earlier: Dict[str, List[str]] = {}
    scores: Dict[int, float] = {}
    for m in messages:
        claims = ((m.get("meta") or {}).get("analysis") or {}).get("claims") or []
        if m["speaker_type"] == "moderator" or not claims:
            continue
        previous = earlier.get(m["speaker"], [])
        if previous:
            scores[m["seq"]] = round(max(similarity(c, p) for c in claims for p in previous), 3)
        earlier[m["speaker"]] = previous + claims
    return scores


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
    repeats = repeat_scores(bundle["messages"])
    row = discussion_row(discussion)
    ai_repeats = [s for m in bundle["messages"] if m["speaker_type"] == "ai" and (s := repeats.get(m["seq"])) is not None]
    row["repeat_rate"] = (round(sum(s >= config_loader.config.analysis.repeat_threshold for s in ai_repeats) / len(ai_repeats), 3)
                          if ai_repeats else None)  # AI 발언 중 이전 주장을 되풀이한 비율
    tables["discussions"].append(row)

    for m in bundle["messages"]:
        meta = m.get("meta") or {}
        analysis = meta.get("analysis") or {}
        seq = m["seq"]
        tables["utterances"].append({
            "discussion_id": did, "seq": seq, "speaker": m["speaker"], "speaker_type": m["speaker_type"],
            "action": m.get("action"), "subtopic_idx": meta.get("subtopic_idx"), "target_seq": meta.get("target_seq"),
            "in_reply_to_seq": meta.get("in_reply_to_seq"), "scripted": bool(meta.get("scripted")), "text": m["content"], "chars": len(m["content"] or ""),
            "analyzed": bool(analysis), "move": analysis.get("move"), "stance": analysis.get("stance"),
            "claims": " | ".join(analysis.get("claims") or []),
            "n_attacks": sum(t.get("relation") == "attack" for t in analysis.get("targets") or []),
            "n_supports": sum(t.get("relation") == "support" for t in analysis.get("targets") or []),
            "n_concessions": len(analysis.get("concessions") or []),
            "repeat_score": repeats.get(seq),
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


CODING_COLUMNS = ("code_concession", "code_responds_to_previous", "code_repeats_own_argument",
                  "code_justification_level", "code_respect_level")


def coding_sample(bundles: List[Dict[str, Any]], n: int, seed: int = 0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """사람 코딩용 표본: (블라인드 파일, 정답 키). 분석된 AI 발언 중 n개를 무작위로 뽑는다.
    블라인드 파일에는 직전 발언과 대상 발언을 문맥으로 넣고 코딩 칸은 비워 둔다. LLM 판정은 키에만 있다.
    코딩 항목: 양보 여부, 직전·대상 발언에 대한 응답 여부, 자기 논거 반복 여부, 정당화 수준(DQI 0~3), 존중 수준(DQI 0~2).
    반복 여부를 판단할 수 있도록 같은 화자의 이전 발언을 문맥에 넣는다."""
    candidates = []
    for bundle in bundles:
        messages = bundle["messages"]
        repeats = repeat_scores(messages)
        by_seq = {m["seq"]: m for m in messages}
        for i, m in enumerate(messages):
            analysis = (m.get("meta") or {}).get("analysis")
            if m["speaker_type"] != "ai" or not analysis:
                continue
            previous = next((p for p in reversed(messages[:i]) if p["speaker_type"] != "moderator"), None)
            own = [p["content"] for p in messages[:i] if p["speaker"] == m["speaker"]]
            target = by_seq.get((m.get("meta") or {}).get("target_seq"))
            candidates.append((bundle["discussion"]["id"], m, previous, target, analysis, repeats.get(m["seq"]), own))
    rng = random.Random(seed)
    picked = rng.sample(candidates, min(n, len(candidates)))
    blind, key = [], []
    for k, (did, m, previous, target, analysis, repeat, own) in enumerate(picked, start=1):
        sample_id = f"S{k:04d}"
        blind.append({
            "sample_id": sample_id, "speaker": m["speaker"],
            "previous": f"{previous['speaker']}: {previous['content']}" if previous else "",
            "target": f"{target['speaker']}: {target['content']}" if target and target is not previous else "",
            "own_earlier": "\n---\n".join(own),
            "text": m["content"], **{c: "" for c in CODING_COLUMNS},
        })
        key.append({
            "sample_id": sample_id, "discussion_id": did, "seq": m["seq"], "action": m.get("action"),
            "llm_move": analysis.get("move"), "llm_concession": bool(analysis.get("concessions")),
            "llm_concessions": " | ".join(f"{c['to']}: {c['claim']}" for c in analysis.get("concessions") or []),
            "llm_attacks": sum(t.get("relation") == "attack" for t in analysis.get("targets") or []),
            "repeat_score": repeat,
        })
    return blind, key
