"""
토론 상태 - 공약 저장소, 열린 도전(답하지 않은 반박·질문), 입장 동역학

이론적 배경
- 공약 저장소(Hamblin, Walton & Krabbe): 참가자별로 자신이 한 주장을 기억해 일관성과 입장 변화를 표현
- 논증 공격 관계(Pollock, Dung): 반박·근거 공격·질문은 상대에게 응답 의무를 만든다 (답하지 않으면 열린 쟁점)
- 의견 동역학(Friedkin-Johnsen):
    x_i ← x_i + step·(1 − s_i)·q·(x_j − x_i) + s_i·anchor·(x_i0 − x_i)
  s_i = 고집도(초기 신념으로 돌아가려는 힘)
- 설득력 q의 요인(LLM이 청자별로 판정, 코드가 결합):
    q = quality × novelty × (0.5 + 0.5·value_match) × (0.5 + 0.5·credibility) × (0.7 + 0.3·receptive)
  논증의 질(ELM 중심 경로), 반복 효과 감소(Cacioppo & Petty), 청자 가치로의 재구성(Feinberg & Willer),
  출처 신뢰도(Hovland & Weiss), 상대 논거 인정(Minson et al. 대화 수용성)
- 수용·거부 범위(Sherif & Hovland 사회 판단 이론): 고집도(자아 관여)가 높을수록 수용 범위가 좁다.
  비관여 범위·거부 범위에서는 q를 줄이고, 거부 범위에서 정체성 위협(threat)이 클 때만 반대로 멀어진다
  (역효과는 드물다는 재현 연구, Wood & Porter 2019)
- 양보(Rokeach 신념 중심성, Cialdini 상호 양보): 중심 입장과 별도로 상대 주장의 일부를 인정한 기록을 남기고,
  양보한 AI 참가자는 일관성 압력으로 상대 쪽으로 조금 이동한다(명제당 상한)
- 모래성 문턱(Redlawsk et al. 2010 감정적 티핑 포인트, van der Maas et al. 2003 파국 모델, Friedkin et al. 2016,
  Chinn & Brewer 1993, Lakatos 보호대): 참가자·명제별 지지 근거의 강도를 기록하고, 근거가 약화된 비율
  D(방어 압력)가 문턱 θ = θ_min + (θ_max − θ_min)·s를 넘으면 핵심 입장이 상대 쪽으로 급변한다(되돌아가지 않음).
  문턱 전 고관여 참가자는 오히려 약간 보강하고, 저관여(s < low_involvement)는 문턱 없이 D에 비례해 움직인다

입장 x ∈ [−1, 1]은 현재 소주제 명제에 대한 입장이다 (−1 강한 반대, +1 강한 찬성). 소주제가 바뀌면 새로 시작한다.
"""
from collections import Counter
from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional, Tuple

from config.discussion_config import get_config

ATTACK_RELATIONS = ("attack", "question")


ZONE_ACCEPT, ZONE_NONCOMMIT, ZONE_REJECT = "accept", "noncommit", "reject"


@dataclass
class DynamicsParams:
    """입장 동역학 파라미터. 값은 config.yaml engine 섹션 (의미도 그쪽 주석)"""
    step: float                 # 설득 1회의 최대 이동 비율 (engine.dynamics_step)
    anchor: float               # 초기 입장으로 돌아가려는 힘 (engine.dynamics_anchor)
    accept_wide: float
    accept_narrow: float
    noncommit_width: float
    noncommit_factor: float
    reject_factor: float
    threat_dampen: float
    boomerang_threshold: float
    boomerang_step: float
    concession_step: float
    concession_cap: float
    value_match_weight: float
    credibility_weight: float
    receptive_weight: float
    undermine_self: float
    undermine_other: float
    undermine_unanswered: float
    switch_theta_min: float
    switch_theta_max: float
    low_involvement: float
    continuous_gain: float
    bolster_step: float
    switch_base: float
    switch_gain: float

    @classmethod
    def from_settings(cls, settings, **overrides) -> "DynamicsParams":
        """토론 설정(DiscussionConfig)에서 만든다. overrides로 일부만 바꿀 수 있다"""
        values = {f.name: getattr(settings, f.name) for f in fields(cls) if f.name not in ("step", "anchor")}
        values.update(step=settings.dynamics_step, anchor=settings.dynamics_anchor)
        values.update(overrides)
        return cls(**values)


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
    conceded_shift: float = 0.0  # 현재 명제에서 양보로 이동한 양 (상한 적용)
    grounds: List[Dict[str, Any]] = field(default_factory=list)  # 현재 명제의 지지 근거 {id, claim, w, why}
    pressure_applied: float = 0.0  # 입장에 이미 반영한 방어 압력 D
    switched: bool = False       # 현재 명제에서 문턱을 넘어 전환했는가

    def pressure(self) -> float:
        """방어 압력 D = 1 − 남은 강도 / 초기 강도 (근거가 없으면 0)"""
        return 1 - sum(g["w"] for g in self.grounds) / len(self.grounds) if self.grounds else 0.0


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class DebateState:
    def __init__(self, params: Optional[DynamicsParams] = None, commitments_kept: Optional[int] = None,
                 grounds_max: Optional[int] = None, threshold_switch: Optional[bool] = None):
        settings = get_config()
        self.params = params or DynamicsParams.from_settings(settings)
        self.commitments_kept = commitments_kept or settings.commitments_kept  # 참가자별로 기억하는 최근 주장 수
        self.grounds_max = grounds_max or settings.grounds_max
        self.threshold_switch = settings.use_threshold_switch if threshold_switch is None else threshold_switch
        self.participants: Dict[str, ParticipantState] = {}
        self.challenges: List[Challenge] = []
        self.concessions: List[Dict[str, Any]] = []  # 현재 명제의 양보 {by, to, claim, seq}
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
            p.conceded_shift = 0.0
            p.grounds, p.pressure_applied, p.switched = [], 0.0, False
        self.challenges.clear()
        self.concessions.clear()
        self.pair_attacks.clear()
        self.attacks_in_subtopic = 0

    # ---------- 분석 반영 ----------

    def apply(self, seq: Optional[int], speaker: str, kind: str, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """발언 분석을 상태에 반영하고, 청자 입장 이동 목록을 돌려준다.

        analysis: {claims: [str], targets: [{seq, speaker, relation}], addressed: [str],
                   concessions: [{to, claim}], stance: float,
                   influence: [{listener, quality, novelty, value_match, credibility, receptive, threat}]}
        (이전 형식 influence: [{listener, persuasiveness}]도 받는다)
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
        sp.commitments = (sp.commitments + [c for c in analysis.get("claims", []) if c])[-self.commitments_kept:]
        # 지지 근거: 이 명제에서 화자가 처음 내놓은 주장들 (최대 grounds_max개, 강도 1.0)
        for claim in analysis.get("claims", []):
            if claim and len(sp.grounds) < self.grounds_max and all(g["claim"] != claim for g in sp.grounds):
                sp.grounds.append({"id": f"{speaker}#{len(sp.grounds) + 1}", "claim": claim, "w": 1.0, "why": []})

        # 화자 입장 = 이번 발언에서 관찰된 입장
        if analysis.get("stance") is not None:
            sp.x = clamp(float(analysis["stance"]))
            if sp.x0 is None:
                sp.x0 = sp.x

        moves = []
        # 양보: 기록하고, AI 화자는 양보한 상대 쪽으로 조금 이동 (사람 입장은 시뮬레이션하지 않음)
        for c in analysis.get("concessions", []):
            to = self.participants.get(c.get("to"))
            if to is None or to.name == speaker or not c.get("claim"):
                continue
            self.concessions.append({"by": speaker, "to": to.name, "claim": c["claim"], "seq": seq})
            delta = self.concede(sp, to)
            if abs(delta) >= 0.01:
                moves.append({"listener": speaker, "by": to.name, "delta": round(delta, 3), "x": round(sp.x, 3),
                              "kind": "concession"})

        # 근거 약화 (분석이 지목한 근거와 심각도): 스스로 인정하면 크게, 다른 참가자의 반박이면 작게
        touched = []
        for u in analysis.get("undermined", []):
            owner, ground = self._ground(u.get("ground"))
            if ground is None:
                continue
            factor = self.params.undermine_self if owner.name == speaker else self.params.undermine_other
            weaken = factor * clamp(float(u.get("severity") or 0.0), 0.0, 1.0)
            if weaken > 0:
                ground["w"] = max(0.0, ground["w"] - weaken)
                ground["why"].append(seq)
                if owner not in touched:
                    touched.append(owner)
        for owner in touched:
            move = self.respond_to_pressure(owner)
            if move:
                moves.append(move)

        # 청자 입장 이동 (Friedkin-Johnsen + 수용·거부 범위)
        if sp.x is None:
            return moves
        for inf in analysis.get("influence", []):
            listener = self.participants.get(inf.get("listener"))
            if listener is None or listener.name == speaker or listener.x is None:
                continue
            zone = self.zone(listener, sp.x)
            threat = clamp(float(inf.get("threat") or 0.0), 0.0, 1.0)
            delta = self.update_listener(listener, sp.x, persuasion(inf, self.params), threat)
            if abs(delta) >= 0.01:
                moves.append({"listener": listener.name, "by": speaker, "delta": round(delta, 3),
                              "x": round(listener.x, 3), "zone": zone,
                              "boomerang": zone == ZONE_REJECT and threat >= self.params.boomerang_threshold})
        return moves

    def _ground(self, ground_id: Optional[str]):
        for p in self.participants.values():
            for g in p.grounds:
                if g["id"] == ground_id:
                    return p, g
        return None, None

    def theta(self, p: ParticipantState) -> float:
        prm = self.params
        return prm.switch_theta_min + (prm.switch_theta_max - prm.switch_theta_min) * p.stubbornness

    def respond_to_pressure(self, p: ParticipantState) -> Optional[Dict[str, Any]]:
        """방어 압력 D의 증가에 따른 핵심 입장 반응 (AI만). 저관여: 연속 이동, 고관여: 문턱 전 보강 / 문턱에서 전환"""
        d = p.pressure()
        increase = d - p.pressure_applied
        if p.kind != "ai" or p.x is None or increase <= 0 or not self.threshold_switch:
            p.pressure_applied = max(p.pressure_applied, d)
            return None
        p.pressure_applied = d
        others = [o.x for o in self.participants.values() if o is not p and o.x is not None]
        opposing = [x for x in others if x * p.x < 0] if p.x != 0 else []
        target = (sum(opposing) / len(opposing)) if opposing else (sum(others) / len(others) if others else None)
        if target is None or target == p.x:
            return None
        prm, before = self.params, p.x
        kind = "pressure"
        if p.stubbornness < prm.low_involvement:
            p.x = clamp(p.x + prm.continuous_gain * increase * (target - p.x))
        elif not p.switched and d >= self.theta(p):
            p.x = clamp(p.x + (target - p.x) * min(1.0, prm.switch_base + prm.switch_gain * p.stubbornness))
            p.x0 = p.x  # 히스테리시스: 새 입장이 기준점이 되어 되돌아가지 않음
            p.switched = True
            kind = "switch"
        elif not p.switched:
            away = 1.0 if target < p.x else -1.0  # 문턱 전 보강: 상대와 반대 방향으로 조금
            p.x = clamp(p.x + away * prm.bolster_step * increase)
        else:
            return None
        delta = p.x - before
        return {"listener": p.name, "by": "pressure", "delta": round(delta, 3), "x": round(p.x, 3),
                "kind": kind, "pressure": round(d, 3), "theta": round(self.theta(p), 3)}

    def close_proposition(self) -> List[Dict[str, Any]]:
        """명제가 끝날 때: 답하지 않은 반박을 받은 AI 참가자의 가장 강한 근거를 약화하고 압력에 반응"""
        moves = []
        for c in self.challenges:
            if c.kind != "attack":
                continue
            p = self.participants.get(c.target)
            if p is None or p.kind != "ai" or not p.grounds:
                continue
            g = max(p.grounds, key=lambda g: g["w"])
            g["w"] = max(0.0, g["w"] - self.params.undermine_unanswered)
            g["why"].append("unanswered")
            move = self.respond_to_pressure(p)
            if move:
                moves.append(move)
        self.challenges = [c for c in self.challenges if c.kind != "attack"]
        return moves

    def grounds_text(self) -> str:
        """분석 프롬프트용 근거 목록 (id: 주장 [강도])"""
        lines = [f"{g['id']}: {g['claim']} [strength {g['w']:.2f}]"
                 for p in self.participants.values() for g in p.grounds]
        return "\n".join(lines) or "(none yet)"

    def zone(self, listener: ParticipantState, speaker_x: float) -> str:
        """화자 입장이 청자의 수용 / 비관여 / 거부 범위 중 어디에 있는가 (고집도가 높을수록 수용 범위가 좁다)"""
        p = self.params
        accept = p.accept_wide - (p.accept_wide - p.accept_narrow) * listener.stubbornness
        distance = abs(listener.x - speaker_x)
        if distance <= accept:
            return ZONE_ACCEPT
        return ZONE_NONCOMMIT if distance <= accept + p.noncommit_width else ZONE_REJECT

    def update_listener(self, listener: ParticipantState, speaker_x: float, q: float, threat: float = 0.0) -> float:
        p = self.params
        zone = self.zone(listener, speaker_x)
        q = clamp(q, 0.0, 1.0) * (1 - p.threat_dampen * threat)
        q *= {ZONE_ACCEPT: 1.0, ZONE_NONCOMMIT: p.noncommit_factor, ZONE_REJECT: p.reject_factor}[zone]
        s = listener.stubbornness
        anchor_pull = s * p.anchor * ((listener.x0 if listener.x0 is not None else listener.x) - listener.x)
        delta = p.step * (1 - s) * q * (speaker_x - listener.x) + anchor_pull
        if zone == ZONE_REJECT and threat >= p.boomerang_threshold and speaker_x != listener.x:
            away = -1.0 if speaker_x > listener.x else 1.0
            delta += away * p.boomerang_step * threat * (1 - s)
        listener.x = clamp(listener.x + delta)
        return delta

    def concede(self, conceder: ParticipantState, to: ParticipantState) -> float:
        """양보에 따른 일관성 이동: 상대 쪽으로 concession_step·(1 − s), 명제당 concession_cap까지"""
        p = self.params
        if conceder.kind != "ai" or conceder.x is None or to.x is None or conceder.x == to.x:
            return 0.0
        room = p.concession_cap - conceder.conceded_shift
        size = min(p.concession_step * (1 - conceder.stubbornness), max(0.0, room), abs(to.x - conceder.x))
        delta = size if to.x > conceder.x else -size
        conceder.x = clamp(conceder.x + delta)
        conceder.conceded_shift += abs(delta)
        return delta

    def concessions_to(self, name: str, after_seq: int = 0) -> List[Dict[str, Any]]:
        """after_seq 이후 다른 참가자가 name에게 한 양보 (상호성 안내용)"""
        return [c for c in self.concessions if c["to"] == name and (c["seq"] or 0) > after_seq]

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
                                 "commitments": p.commitments, "conceded_shift": p.conceded_shift,
                                 "grounds": p.grounds, "pressure_applied": p.pressure_applied, "switched": p.switched}
                             for n, p in self.participants.items()},
            "challenges": [vars(c) for c in self.challenges],
            "concessions": self.concessions,
            "pair_attacks": [[a, b, n] for (a, b), n in self.pair_attacks.items() if n],
            "attacks_in_subtopic": self.attacks_in_subtopic,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any], params: Optional[DynamicsParams] = None,
                      commitments_kept: Optional[int] = None, grounds_max: Optional[int] = None,
                      threshold_switch: Optional[bool] = None) -> "DebateState":
        state = cls(params, commitments_kept, grounds_max, threshold_switch)
        for name, p in data.get("participants", {}).items():
            state.participants[name] = ParticipantState(name=name, **p)
        state.challenges = [Challenge(**c) for c in data.get("challenges", [])]
        state.concessions = list(data.get("concessions", []))
        state.pair_attacks = Counter({(a, b): n for a, b, n in data.get("pair_attacks", [])})
        state.attacks_in_subtopic = data.get("attacks_in_subtopic", 0)
        return state


def persuasion(influence: Dict[str, Any], params: Optional[DynamicsParams] = None) -> float:
    """청자별 설득력 q. 요인이 있으면 요인을 결합하고, 이전 형식(persuasiveness)이면 그 값을 쓴다"""
    params = params or DynamicsParams.from_settings(get_config())
    if influence.get("quality") is None:
        return clamp(float(influence.get("persuasiveness") or 0.0), 0.0, 1.0)

    def f(key: str, default: float) -> float:
        value = influence.get(key)
        return clamp(float(default if value is None else value), 0.0, 1.0)

    def weighted(key: str, default: float, w: float) -> float:
        return (1 - w) + w * f(key, default)

    return (f("quality", 0.0) * f("novelty", 1.0) * weighted("value_match", 0.0, params.value_match_weight)
            * weighted("credibility", 0.5, params.credibility_weight)
            * weighted("receptive", 0.0, params.receptive_weight))
