"""
실제 토론 점검(GAI 토론)에서 드러난 문제의 회귀 테스트
- 소주제 구조화 출력, 모더레이터 개입 주기·마지막 개입 금지·질문 반복 방지
- 발언 균형, 키 없는 웹 검색 차단, 출처 없는 주장 표시
"""
import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from src.core.agent import DiscussionAgent
from src.core.moderator import DiscussionModerator
from src.core.natural_discussion import NaturalDiscussion
from src.models.personas import Persona
from src.services.consensus_report import ConsensusReportGenerator, TranscriptMessage, to_markdown
from tests.conftest import LoggedInClient, create_user
from tests.report_stubs import NARRATIVE, StubLLM
from tests.test_events_api import PERSONA
from tests.test_runtime import FakeBundle

BASE = {k: v for k, v in PERSONA.items() if k != "model"}


class CapturingLLM:
    """프롬프트를 기록하는 가짜 모더레이터 LLM"""

    def __init__(self, subtopics=None):
        self.prompts = []
        self.subtopics = subtopics or ["A", "B", "C"]

    async def ainvoke(self, messages):
        self.prompts.append(messages[-1].content)
        return AIMessage(content=f"Question {len(self.prompts)}?")

    def with_structured_output(self, schema, **kwargs):
        return RunnableLambda(lambda _m: schema(subtopics=self.subtopics))


def make_engine(names, max_statements, moderator_llm=None):
    bundle = FakeBundle()
    agents = [DiscussionAgent(Persona(name=n, **BASE), llm=bundle.agent) for n in names]
    moderator = DiscussionModerator(llm=moderator_llm or bundle.moderator)
    return NaturalDiscussion(agents, moderator=moderator, max_statements=max_statements)


@pytest.mark.asyncio
async def test_subtopics_from_structured_output_are_cleaned():
    moderator = DiscussionModerator(llm=CapturingLLM(["## **기술 안전성**", "- 경제 효과", "  ", "**의료 혜택**"]))
    assert await moderator.generate_subtopics("topic") == ["기술 안전성", "경제 효과", "의료 혜택"]


@pytest.mark.asyncio
async def test_moderator_cadence_covers_subtopics_and_never_ends_discussion():
    engine = make_engine(["Alice", "Bob"], max_statements=6)
    events = [e async for e in engine.stream("topic", language="en") if e.kind == "utterance"]
    kinds = [(e.speaker_type, e.action) for e in events]

    assert sum(t == "ai" for t, _ in kinds) == 6
    assert kinds[-1][0] == "ai"  # 답 없는 모더레이터 질문으로 끝나지 않음
    # 6발언 / 소주제 3개 → 2발언마다 전환, 그 사이 3번째 발언 뒤 질문 1회
    assert [a for t, a in kinds if t == "moderator"] == ["transition", "question", "transition"]
    assert engine.moderator.current_subtopic_idx == 2  # 모든 소주제를 다룸


@pytest.mark.asyncio
async def test_moderator_does_not_repeat_previous_questions():
    llm = CapturingLLM(subtopics=["only one"])  # 소주제 1개 → 전환 없이 질문만
    engine = make_engine(["Alice", "Bob"], max_statements=10, moderator_llm=llm)
    [e async for e in engine.stream("topic", language="en")]

    question_prompts = llm.prompts  # 소주제 생성은 구조화 출력이라 기록되지 않음
    assert len(question_prompts) == 3  # 3, 6, 9번째 발언 뒤
    assert "(none)" in question_prompts[0]
    assert "Question 1?" in question_prompts[1] and "Question 2?" in question_prompts[2]
    assert "Do NOT demand statistics" in question_prompts[0]


@pytest.mark.asyncio
async def test_speakers_are_balanced():
    engine = make_engine(["A", "B", "C"], max_statements=9)
    [e async for e in engine.stream("topic", language="en")]
    counts = engine.agent_turn_count.values()
    assert max(counts) - min(counts) <= 1


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
