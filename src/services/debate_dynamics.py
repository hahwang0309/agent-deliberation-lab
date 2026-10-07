"""
토론 동역학 요약 - 발언마다 저장된 토론 상태(meta.debate)에서 명제별 입장 궤적·영향·미해결 쟁점을 정리

입력은 저장된 발언 기록 [{seq, speaker, speaker_type, action, meta}]이며 LLM을 호출하지 않는다.
"""
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

MIN_SHIFT = 0.05  # 이보다 작은 이동은 '변화 없음'으로 본다


def summarize_dynamics(records: List[Dict[str, Any]], subtopics: Optional[List[str]] = None) -> Dict[str, Any]:
    subtopics = subtopics or []
    groups: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    actions: Counter = Counter()
    for r in records:
        meta = r.get("meta") or {}
        if r.get("speaker_type") == "ai" and r.get("action"):
            actions[r["action"]] += 1
        if meta.get("debate"):
            groups[meta["debate"].get("subtopic_idx", meta.get("subtopic_idx", 0))].append(r)

    propositions = []
    for idx in sorted(groups):
        rows = groups[idx]
        state = rows[-1]["meta"]["debate"].get("state", {})
        trajectories = []
        for name, p in state.get("participants", {}).items():
            if p.get("x") is None:
                continue
            start = p["x0"] if p.get("x0") is not None else p["x"]
            trajectories.append({"name": name, "kind": p.get("kind", "ai"), "start": round(start, 2),
                                 "end": round(p["x"], 2), "shift": round(p["x"] - start, 2)})
        influence: Counter = Counter()
        for r in rows:
            for m in r["meta"].get("moves") or []:
                influence[(m["by"], m["listener"])] += m["delta"]
        ends = [t["end"] for t in trajectories]
        starts = [t["start"] for t in trajectories]
        propositions.append({
            "index": idx,
            "title": subtopics[idx] if idx < len(subtopics) else None,
            "trajectories": trajectories,
            "spread_start": round(max(starts) - min(starts), 2) if len(starts) > 1 else None,
            "spread_end": round(max(ends) - min(ends), 2) if len(ends) > 1 else None,
            "influences": [{"by": by, "listener": listener, "shift": round(total, 2)}
                           for (by, listener), total in influence.most_common() if abs(total) >= MIN_SHIFT],
            "unresolved": [{"challenger": c["challenger"], "target": c["target"], "kind": c.get("kind"),
                            "claim": c.get("claim", "")} for c in state.get("challenges", [])],
        })
    return {"propositions": propositions, "actions": dict(actions)}


def stance_text(x: float) -> str:
    return ("강한 찬성" if x >= 0.6 else "찬성" if x >= 0.2 else "유보" if x > -0.2 else
            "반대" if x > -0.6 else "강한 반대")


def dynamics_markdown(dynamics: Dict[str, Any]) -> List[str]:
    """보고서 마크다운의 '입장 변화' 절"""
    props = dynamics.get("propositions") or []
    if not props:
        return []
    lines = ["## 토론 과정의 입장 변화", ""]
    for p in props:
        lines += [f"### 명제 {p['index'] + 1}: {p['title'] or '-'}", ""]
        if p["spread_start"] is not None:
            lines += [f"- 입장 간격: {p['spread_start']:.2f} → {p['spread_end']:.2f} (−1 반대 ~ +1 찬성 척도의 최대−최소)"]
        for t in p["trajectories"]:
            moved = f" ({t['shift']:+.2f})" if abs(t["shift"]) >= MIN_SHIFT else " (변화 없음)"
            human = " (사람, 관찰값)" if t["kind"] == "human" else ""
            lines.append(f"- **{t['name']}**{human}: {stance_text(t['start'])} {t['start']:+.2f} → "
                         f"{stance_text(t['end'])} {t['end']:+.2f}{moved}")
        if p["influences"]:
            lines.append("- 영향: " + ", ".join(f"{i['by']} → {i['listener']} {i['shift']:+.2f}" for i in p["influences"]))
        if p["unresolved"]:
            lines.append("- 답하지 않은 반박·질문: " + "; ".join(
                f"{u['challenger']} → {u['target']}" + (f" ({u['claim']})" if u["claim"] else "") for u in p["unresolved"]))
        lines.append("")
    lines.append("> 입장 값은 발언마다 LLM이 판정한 입장과, 설득력 판정을 Friedkin–Johnsen 식으로 반영한 AI 청자의 이동입니다. "
                 "사람 참가자의 입장은 발언에서 관찰한 값만 쓰며 시뮬레이션하지 않습니다.")
    lines.append("")
    return lines
