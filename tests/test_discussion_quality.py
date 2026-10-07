"""
토론 메커니즘 테스트 - 진행 계획, 상태 기반 발언 선택(응답 의무·교착 중재·반대 검토·종결), 입장 동역학
(가짜 LLM: 에이전트·모더레이터·발언 분석기)
"""
import re

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from src.core.agent import DiscussionAgent
from src.core.debate_state import DebateState, DynamicsParams
from src.core.moderator import DiscussionModerator
from src.core.natural_discussion import ActionType, NaturalDiscussion, plan_debate
from src.models.personas import Persona
from src.services.consensus_report import ConsensusReportGenerator, TranscriptMessage, to_markdown
from src.services.debate_dynamics import dynamics_markdown, summarize_dynamics
from tests.conftest import LoggedInClient, create_user
from tests.report_stubs import NARRATIVE, StubLLM
from tests.test_events_api import PERSONA
from tests.test_runtime import FakeAnalyzer, FakeBundle

BASE = {k: v for k, v in PERSONA.items() if k != "model"}


def analyzed(messages):
    """분석 프롬프트에서 (발언 seq, 화자, 문맥의 [(seq, 화자)])를 읽는다"""
    text = messages[-1].content
    seq, speaker = re.search(r"Utterance to analyze \(#(\d+)\) by (.+?):", text).groups()
    context = [(int(s), n) for s, n in re.findall(r"\[#(\d+)\] (.+?):", text)]
    return int(seq), speaker, context


def latest_by(context, name):
    return next((s for s, n in reversed(context) if n == name), None)


def make_engine(names, max_statements, analyzer_fn=None, moderator_llm=None, personality=None):
    bundle = FakeBundle(analyzer=FakeAnalyzer(analyzer_fn) if analyzer_fn else None)
    agents = [DiscussionAgent(Persona(name=n, **{**BASE, "personality": personality or BASE["personality"]}),
                              llm=bundle.agent) for n in names]
    moderator = DiscussionModerator(llm=moderator_llm or bundle.moderator)
    engine = NaturalDiscussion(agents, moderator=moderator, max_statements=max_statements, analyzer=bundle.analyzer)
    return engine, bundle


async def run(engine):
    return [e async for e in engine.stream("topic", language="en")]


def utterances(events):
    return [e for e in events if e.kind == "utterance"]


# ---------- 진행 계획 ----------

@pytest.mark.parametrize("n,s,budgets,closing", [
    (3, 9, [6], 3),          # 본론 6 → 명제 1개(전원 입장 3 + 상호 논증 3) + 종결 3
    (3, 12, [5, 4], 3),
    (2, 6, [4], 2),
    (4, 20, [6, 5, 5], 4),
    (5, 30, [7, 6, 6, 6], 5),
    (2, 2, [2], 0),          # 너무 짧으면 종결 라운드 없음
])
def test_plan_scales_with_participants_and_statements(n, s, budgets, closing):
    plan = plan_debate(n, s, max_subtopics=5)
    assert plan.budgets == budgets and plan.closing == closing
    assert sum(plan.budgets) + plan.closing == s
    assert all(b >= n for b in plan.budgets)  # 명제마다 전원이 최소 1번 발언


@pytest.mark.asyncio
async def test_everyone_speaks_on_each_proposition_then_closing_round():
    engine, _ = make_engine(["A", "B", "C"], max_statements=12)
    events = await run(engine)
    subtopics = next(e for e in events if e.kind == "subtopics").meta["subtopics"]
    assert len(subtopics) == 2  # plan_debate(3, 12) → 명제 2개

    said = utterances(events)
    ai = [u for u in said if u.speaker_type == "ai"]
    assert len(ai) == 12 and said[-1].speaker_type == "ai"
    for idx, budget in enumerate([5, 4]):
        body = [u for u in ai if u.meta["subtopic_idx"] == idx and u.action != "closing"]
        assert len(body) == budget and {u.speaker for u in body} == {"A", "B", "C"}
        assert [u.action for u in body[:3]] == ["position"] * 3  # 전원 입장 표명 먼저
    closing = [u for u in ai if u.action == "closing"]
    assert [u.speaker for u in closing] == ["A", "B", "C"] and ai[-3:] == closing
    assert [u.action for u in said if u.speaker_type == "moderator"] == ["opening", "transition", "closing_announce"]


# ---------- 상태 기반 발언 선택 ----------

@pytest.mark.asyncio
async def test_challenged_participant_must_respond_next():
    attack = {}

    def fn(messages):
        seq, speaker, context = analyzed(messages)
        stance = {"A": 0.6, "B": -0.6, "C": 0.0}[speaker]
        if speaker == "C" and not attack:  # 첫 명제 입장 표명 마지막(C)이 B를 반박 → 명제 예산이 남아 있을 때
            target = latest_by(context, "B")
            if target:
                attack.update(seq=seq, target=target)
                return {"stance": stance, "targets": [{"seq": target, "speaker": "B", "relation": "attack"}]}
        return {"stance": stance}

    engine, _ = make_engine(["A", "B", "C"], max_statements=12, analyzer_fn=fn)
    said = [u for u in utterances(await run(engine)) if u.speaker_type == "ai"]
    assert attack, "C did not attack in this run"
    i = next(i for i, u in enumerate(said) if u.meta["seq"] == attack["seq"])
    # 입장 표명 라운드가 끝나면 다음 발언은 반박받은 B의 응답 (발언 순서·발언 횟수보다 우선)
    reply = next(u for u in said[i + 1:] if u.action != "position")
    assert reply.speaker == "B" and reply.action == "respond_challenge" and reply.meta["target_seq"] == attack["seq"]


@pytest.mark.asyncio
async def test_stalemate_brings_in_third_party_mediation():
    def fn(messages):
        seq, speaker, context = analyzed(messages)
        opponent = {"A": "B", "B": "A"}.get(speaker)
        target = latest_by(context, opponent) if opponent else None
        targets = [{"seq": target, "speaker": opponent, "relation": "attack"}] if target else []
        return {"stance": {"A": 0.8, "B": -0.8, "C": 0.0}[speaker], "targets": targets}

    engine, _ = make_engine(["A", "B", "C"], max_statements=14, analyzer_fn=fn)
    said = [u for u in utterances(await run(engine)) if u.speaker_type == "ai"]
    mediation = [u for u in said if u.action in ("mediate", "third_option")]
    assert mediation and all(u.speaker == "C" for u in mediation)


@pytest.mark.asyncio
async def test_quick_consensus_triggers_devils_advocate_once_per_proposition():
    engine, _ = make_engine(["A", "B", "C"], max_statements=12, analyzer_fn=lambda m: {"stance": 0.7})
    said = [u for u in utterances(await run(engine)) if u.speaker_type == "ai"]
    devils = [(u.meta["subtopic_idx"], u.speaker) for u in said if u.action == "devils_advocate"]
    assert [idx for idx, _ in devils] == [0, 1]


@pytest.mark.asyncio
async def test_two_participants_stalemate_gets_moderator_question_and_obligation():
    def fn(messages):
        seq, speaker, context = analyzed(messages)
        opponent = {"A": "B", "B": "A"}[speaker]
        target = latest_by(context, opponent)
        return {"stance": 0.8 if speaker == "A" else -0.8,
                "targets": [{"seq": target, "speaker": opponent, "relation": "attack"}] if target else []}

    engine, _ = make_engine(["A", "B"], max_statements=10, analyzer_fn=fn)
    said = utterances(await run(engine))
    i = next(i for i, u in enumerate(said) if u.action == "mediation")
    assert said[i].speaker_type == "moderator"
    assert said[i + 1].speaker in ("A", "B") and said[i + 1].action == "respond_challenge"


# ---------- 입장 동역학 ----------

def test_friedkin_johnsen_update_with_bounded_confidence():
    state = DebateState(DynamicsParams(step=0.5, anchor=0.1, confidence_bound=1.0, confidence_penalty=0.3))
    listener = state.ensure("L", stubbornness=0.5)
    listener.x0 = listener.x = -0.5
    delta = state.update_listener(listener, speaker_x=0.5, persuasiveness=0.8)
    assert delta == pytest.approx(0.5 * 0.5 * 0.8 * 1.0) and listener.x == pytest.approx(-0.3)
    # 고집도: 처음 입장으로 당기는 힘
    delta = state.update_listener(listener, speaker_x=-0.3, persuasiveness=0.0)
    assert delta == pytest.approx(0.5 * 0.1 * (-0.5 - -0.3))

    far = state.ensure("F", stubbornness=0.0)
    far.x0 = far.x = -0.6
    delta = state.update_listener(far, speaker_x=0.6, persuasiveness=1.0)  # 거리 1.2 > 1.0 → 설득력 ×0.3
    assert delta == pytest.approx(0.5 * 1.0 * 0.3 * 1.2)


@pytest.mark.asyncio
async def test_persuasion_moves_listener_and_shows_in_their_next_prompt():
    def fn(messages):
        seq, speaker, context = analyzed(messages)
        if speaker == "A":
            return {"stance": 0.8, "influence": [{"listener": "B", "persuasiveness": 0.9}]}
        return {"stance": -0.8 if seq < 5 else -0.2}

    engine, _ = make_engine(["A", "B"], max_statements=4, analyzer_fn=fn, personality=["open-minded"])
    events = await run(engine)
    moves = [m for e in events if e.kind == "analysis" for m in e.meta["moves"]]
    assert moves and moves[0]["listener"] == "B" and moves[0]["by"] == "A" and moves[0]["delta"] > 0
    assert engine.agents[1].stubbornness == 0.3  # 개방적 성격 → 낮은 고집도

    # 이동은 다음 발언 프롬프트의 입장 설명에 들어간다
    engine2, _ = make_engine(["A", "B"], max_statements=4, analyzer_fn=fn)
    engine2.debate.participants["B"].x = -0.5
    engine2.recent_moves["B"] = [{"listener": "B", "by": "A", "delta": 0.3}]
    note = engine2._stance_note("B")
    assert "leaning disagree (-0.50" in note and "moved +0.30 after hearing A" in note


@pytest.mark.asyncio
async def test_dynamics_summary_reports_trajectory_influence_and_unresolved():
    def fn(messages):
        seq, speaker, context = analyzed(messages)
        if speaker == "A":
            target = latest_by(context, "B")
            return {"stance": 0.8, "influence": [{"listener": "B", "persuasiveness": 0.9}],
                    "targets": [{"seq": target, "speaker": "B", "relation": "attack"}] if target else []}
        return {"stance": -0.8 if seq < 5 else -0.2}

    engine, _ = make_engine(["A", "B"], max_statements=2, analyzer_fn=fn)
    events = await run(engine)
    actions = {e.meta["seq"]: e.action for e in utterances(events)}
    records = [{"seq": e.meta["seq"], "speaker": e.speaker, "speaker_type": "ai", "action": actions.get(e.meta["seq"]),
                "meta": {"debate": e.meta["debate"], "moves": e.meta["moves"]}} for e in events if e.kind == "analysis"]
    dynamics = summarize_dynamics(records, ["P1"])
    prop = dynamics["propositions"][0]
    assert prop["title"] == "P1" and dynamics["actions"] == {"position": 2}
    a = next(t for t in prop["trajectories"] if t["name"] == "A")
    assert (a["start"], a["end"], a["shift"]) == (0.8, 0.8, 0.0)
    assert prop["spread_end"] is not None
    if prop["unresolved"]:  # 예산이 끝나 B가 답하지 못한 반박은 미해결로 남는다
        assert prop["unresolved"][0]["challenger"] == "A" and prop["unresolved"][0]["target"] == "B"
    md = "\n".join(dynamics_markdown(dynamics))
    assert "명제 1: P1" in md and "**A**: 강한 찬성 +0.80 → 강한 찬성 +0.80 (변화 없음)" in md


@pytest.mark.asyncio
async def test_human_stance_is_observed_but_not_simulated():
    state = DebateState()
    state.ensure("A")
    human = state.ensure("Hana", kind="human")
    state.apply(1, "Hana", "human", {"stance": -0.4})
    assert human.x == -0.4
    engine, _ = make_engine(["A", "B"], max_statements=2,
                            analyzer_fn=lambda m: {"stance": 0.5, "influence": [{"listener": "Hana", "persuasiveness": 1.0}]})
    engine.debate.ensure("Hana", "human").x = -0.4
    events = await run(engine)
    assert all(m["listener"] != "Hana" for e in events if e.kind == "analysis" for m in e.meta["moves"])
    assert engine.debate.stance("Hana") == -0.4


# ---------- 프롬프트 ----------

@pytest.mark.asyncio
async def test_prompt_carries_proposition_stance_commitments_and_full_target():
    engine, _ = make_engine(["A", "B"], max_statements=4)
    engine.propositions = ["GAI raises productivity more than it destroys jobs"]
    long_text = "x" * 900
    from src.models.personas import Message
    target = Message(role="assistant", content=long_text, agent_name="A", metadata={"seq": 7})
    engine.debate.participants["B"].commitments = ["jobs vanish first"]
    from src.core.natural_discussion import Turn
    prompt = engine._build_prompt("topic", Turn(engine.agents[1], ActionType.REBUT, target))
    assert "Proposition under discussion: GAI raises productivity" in prompt
    assert "Your earlier claims in this discussion: jobs vanish first" in prompt
    assert "A said (#7)" in prompt and long_text in prompt  # 대상 발언 전문 (900자)
    assert "Reply rules" in prompt


# ---------- 기존 품질 규칙 ----------

class CapturingLLM:
    def __init__(self, subtopics):
        self.subtopics = subtopics

    async def ainvoke(self, messages):
        return AIMessage(content="?")

    def with_structured_output(self, schema, **kwargs):
        return RunnableLambda(lambda _m: schema(subtopics=self.subtopics))


@pytest.mark.asyncio
async def test_subtopics_are_cleaned_and_limited_to_requested_count():
    moderator = DiscussionModerator(llm=CapturingLLM(["## **1. 기술 안전성**", "- 경제 효과", "  ", "**의료 혜택**"]))
    assert await moderator.generate_subtopics("topic", count=2) == ["기술 안전성", "경제 효과"]


@pytest.mark.asyncio
async def test_web_search_requires_tavily_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    body = {"topic": "t topic", "enable_web_search": True,
            "personas": [dict(name="A", **PERSONA), dict(name="B", **PERSONA)]}
    async with LoggedInClient(create_user(role="admin")) as admin:
        r = await admin.post("/api/v1/discussions", json=body)
        assert r.status_code == 422 and r.json()["detail"]["error"]["code"] == "WEB_SEARCH_UNAVAILABLE"
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        assert (await admin.post("/api/v1/discussions", json=body)).status_code == 201


@pytest.mark.asyncio
async def test_unsourced_claims_are_flagged_in_narrative_input_and_markdown():
    issue_map = {"issues": [{"title": "T", "summary": "s", "positions": [
        {"participant": "Alice", "stance": "agree", "claim": "85 of 280 quit", "evidence_seqs": [1],
         "unsourced_specifics": True},
        {"participant": "Bob", "stance": "agree", "claim": "reasoned view", "evidence_seqs": [2]}]}]}
    llm = StubLLM({"IssueMap": [issue_map], "Narrative": NARRATIVE})
    transcript = [TranscriptMessage(1, "Alice", "ai", "x"), TranscriptMessage(2, "Bob", "ai", "y")]
    report = await ConsensusReportGenerator(llm).generate("t", transcript, {"Alice": "ai", "Bob": "ai"}, "en")

    narrative_prompt = next(m for name, m in llm.calls if name == "Narrative")[-1].content
    assert "Alice: agree [unsourced]" in narrative_prompt and "Bob: agree —" in narrative_prompt
    md = to_markdown(report)
    assert "85 of 280 quit ⚠ 출처 없는 수치·사례" in md and "reasoned view ⚠" not in md


def test_analysis_normalizes_relation_synonyms_and_drops_unknown():
    from src.core.natural_discussion import UtteranceAnalysis
    a = UtteranceAnalysis(stance=0.2, targets=[{"seq": 1, "speaker": "A", "relation": "extend"},
                                               {"seq": 2, "speaker": "B", "relation": "weird"},
                                               {"seq": 3, "speaker": "C", "relation": "Rebut"}])
    assert [(t.seq, t.relation) for t in a.targets] == [(1, "support"), (3, "attack")] and a.stance == 0.2
