"""
토론 상태 - 공약 저장소, 열린 도전(답하지 않은 반박·질문), 입장 동역학

이론적 배경
- 공약 저장소(Hamblin, Walton & Krabbe): 참가자별로 자신이 한 주장을 기억해 일관성과 입장 변화를 표현
- 논증 공격 관계(Pollock, Dung): 반박·근거 공격·질문은 상대에게 응답 의무를 만든다 (답하지 않으면 열린 쟁점)
- 의견 동역학(Friedkin-Johnsen + 제한 신뢰 Hegselmann-Krause):
    x_i ← x_i + step·(1 − s_i)·q·(x_j − x_i) + s_i·anchor·(x_i0 − x_i)
  q = 화자 j의 논증이 청자 i에게 갖는 설득력(LLM 판정), |x_i − x_j| > ε 이면 q에 패널티,
  s_i = 고집도(초기 신념으로 돌아가려는 힘)

입장 x ∈ [−1, 1]은 현재 소주제 명제에 대한 입장이다 (−1 강한 반대, +1 강한 찬성). 소주제가 바뀌면 새로 시작한다.
"""
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

ATTACK_RELATIONS = ("attack", "question")


@dataclass
class DynamicsParams:
    step: float = 0.5               # 설득 1회의 최대 이동 비율
    anchor: float = 0.1             # 초기 입장으로 돌아가려는 힘 (고집도와 곱해짐)
    confidence_bound: float = 1.0   # 이보다 먼 의견은 잘 받아들이지 않음
    confidence_penalty: float = 0.3  # 신뢰 범위 밖 설득력에 곱하는 값


@dataclass
class Challenge:
    """응답 의무: challenger가 target에게 한 반박·질문 (target이 다음에 말하면 해소)"""
    challenger: str
    target: str
    seq: Optional[int]
    kind: str  # attack | question
    claim: str = ""


@dataclass
class ParticipantState:
    name: str
    kind: str = "ai"            # ai | human
    stubbornness: float = 0.5
    x0: Optional[float] = None  # 현재 소주제 첫 입장
    x: Optional[float] = None   # 현재 입장
    commitments: List[str] = field(default_factory=list)  # 최근 주장 (최대 6개)


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class DebateState:
    def __init__(self, params: Optional[DynamicsParams] = None):
        self.params = params or DynamicsParams()
        self.participants: Dict[str, ParticipantState] = {}
        self.challenges: List[Challenge] = []
        self.pair_attacks: Counter = Counter()  # (공격자, 대상) → 현재 소주제 공격 횟수
        self.attacks_in_subtopic = 0

    # ---------- 참가자 ----------

    def ensure(self, name: str, kind: str = "ai", stubbornness: Optional[float] = None) -> ParticipantState:
        if name not in self.participants:
            self.participants[name] = ParticipantState(
                name=name, kind=kind, stubbornness=0.5 if stubbornness is None else stubbornness)
        return self.participants[name]

    def stance(self, name: str) -> Optional[float]:
        p = self.participants.get(name)
        return p.x if p else None

    def stances(self) -> Dict[str, Optional[float]]:
        return {name: (round(p.x, 3) if p.x is not None else None) for name, p in self.participants.items()}

    # ---------- 소주제 ----------

    def reset_subtopic(self) -> None:
        """새 명제로 넘어가면 입장·도전·교착 카운터를 초기화 (공약 저장소는 유지)"""
        for p in self.participants.values():
            p.x0 = p.x = None
        self.challenges.clear()
        self.pair_attacks.clear()
        self.attacks_in_subtopic = 0

    # ---------- 분석 반영 ----------

    def apply(self, seq: Optional[int], speaker: str, kind: str, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """발언 분석을 상태에 반영하고, 청자 입장 이동 목록을 돌려준다.

        analysis: {claims: [str], targets: [{seq, speaker, relation}], addressed: [str],
                   stance: float, influence: [{listener, persuasiveness}]}
        """
        sp = self.ensure(speaker, kind)

        # 화자가 말했으므로 화자를 향한 도전은 해소
        self.challenges = [c for c in self.challenges if c.target != speaker]

        # 새 도전: 다른 참가자의 발언을 반박·질문했거나 지목 질문을 함
        for t in analysis.get("targets", []):
            target = t.get("speaker")
            if t.get("relation") in ATTACK_RELATIONS and target and target != speaker and target in self.participants:
                # 응답할 대상은 반박·질문한 '이 발언'(seq) — 공격받은 원래 발언이 아님
                self._add_challenge(Challenge(speaker, target, seq, t["relation"],
                                              (analysis.get("claims") or [""])[0]))
                if t["relation"] == "attack":
                    self.pair_attacks[(speaker, target)] += 1
                    self.attacks_in_subtopic += 1
        for name in analysis.get("addressed", []):
            if name != speaker and name in self.participants:
                self._add_challenge(Challenge(speaker, name, seq, "question", ""))

        # 공약 저장소
        sp.commitments = (sp.commitments + [c for c in analysis.get("claims", []) if c])[-6:]

        # 화자 입장 = 이번 발언에서 관찰된 입장
        if analysis.get("stance") is not None:
            sp.x = clamp(float(analysis["stance"]))
            if sp.x0 is None:
                sp.x0 = sp.x

        # 청자 입장 이동 (Friedkin-Johnsen + 제한 신뢰)
        moves = []
        if sp.x is None:
            return moves
        for inf in analysis.get("influence", []):
            listener = self.participants.get(inf.get("listener"))
            if listener is None or listener.name == speaker or listener.x is None:
                continue
            delta = self.update_listener(listener, sp.x, float(inf.get("persuasiveness", 0.0)))
            if abs(delta) >= 0.01:
                moves.append({"listener": listener.name, "by": speaker, "delta": round(delta, 3),
                              "x": round(listener.x, 3)})
        return moves

    def update_listener(self, listener: ParticipantState, speaker_x: float, persuasiveness: float) -> float:
        p = self.params
        q = clamp(persuasiveness, 0.0, 1.0)
        if abs(listener.x - speaker_x) > p.confidence_bound:
            q *= p.confidence_penalty
        s = listener.stubbornness
        anchor_pull = s * p.anchor * ((listener.x0 if listener.x0 is not None else listener.x) - listener.x)
        delta = p.step * (1 - s) * q * (speaker_x - listener.x) + anchor_pull
        listener.x = clamp(listener.x + delta)
        return delta

    def _add_challenge(self, challenge: Challenge) -> None:
        if not any(c.challenger == challenge.challenger and c.target == challenge.target for c in self.challenges):
            self.challenges.append(challenge)

    # ---------- 진행 판단 ----------

    def open_challenge_for(self, candidates: List[str]) -> Optional[Challenge]:
        """가장 오래된 열린 도전 중 대상이 후보에 있는 것"""
        return next((c for c in self.challenges if c.target in candidates), None)

    def stalemate_pair(self, min_exchanges: int) -> Optional[Tuple[str, str]]:
        """서로 min_exchanges회 이상 공격을 주고받은 쌍 (교착)"""
        for (a, b), n in self.pair_attacks.items():
            if a < b and n >= min_exchanges and self.pair_attacks[(b, a)] >= min_exchanges:
                return a, b
        return None

    def clear_pair(self, pair: Tuple[str, str]) -> None:
        a, b = pair
        self.pair_attacks[(a, b)] = self.pair_attacks[(b, a)] = 0

    def spread(self, names: List[str]) -> Optional[float]:
        values = [self.participants[n].x for n in names if n in self.participants and self.participants[n].x is not None]
        return (max(values) - min(values)) if len(values) == len(names) and values else None

    # ---------- 저장·복원 ----------

    def snapshot(self) -> Dict[str, Any]:
        return {
            "participants": {n: {"kind": p.kind, "stubbornness": p.stubbornness, "x0": p.x0, "x": p.x,
                                 "commitments": p.commitments} for n, p in self.participants.items()},
            "challenges": [vars(c) for c in self.challenges],
            "pair_attacks": [[a, b, n] for (a, b), n in self.pair_attacks.items() if n],
            "attacks_in_subtopic": self.attacks_in_subtopic,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any], params: Optional[DynamicsParams] = None) -> "DebateState":
        state = cls(params)
        for name, p in data.get("participants", {}).items():
            state.participants[name] = ParticipantState(name=name, **p)
        state.challenges = [Challenge(**c) for c in data.get("challenges", [])]
        state.pair_attacks = Counter({(a, b): n for a, b, n in data.get("pair_attacks", [])})
        state.attacks_in_subtopic = data.get("attacks_in_subtopic", 0)
        return state
