"""
중단된(interrupted) 토론 재개 테스트 (가짜 LLM)
"""
import asyncio

import pytest

from api.models.discussion import DiscussionStatus
from api.runtime import broker, persistence, registry
from api.runtime import runtime as runtime_module
from src.core.agent import DiscussionAgent
from src.core.natural_discussion import ActionType, NaturalDiscussion
from src.models.personas import Message, Persona
from tests.conftest import LoggedInClient, create_user, update_user
from tests.test_events_api import PERSONA
from tests.test_intervention import wait_until
from tests.test_runtime import FakeBundle

BODY = {"topic": "Remote work mandates?", "max_statements": 6,
        "personas": [dict(name="Alice", **PERSONA), dict(name="Bob", **PERSONA)]}


@pytest.fixture(autouse=True)
def slow_engine(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", lambda callbacks=None: FakeBundle(slow=True))


async def interrupt_after(client, ai_messages: int) -> str:
    """토론을 시작해 AI 발언이 n개 쌓이면 서버 재시작처럼 중단시킨다"""
    discussion_id = (await client.post("/api/v1/discussions", json=BODY)).json()["id"]
    assert (await client.post(f"/api/v1/discussions/{discussion_id}/start")).status_code == 202
    runtime = registry.get(discussion_id)
    await wait_until(lambda: runtime.ai_messages >= ai_messages)
    await registry.stop(discussion_id, by="system", reason="simulated crash")  # 보고서 예약 없음
    persistence.update_discussion(discussion_id, status=DiscussionStatus.INTERRUPTED, error="server restarted")
    return discussion_id


@pytest.mark.asyncio
async def test_resume_continues_seq_without_regenerating_subtopics():
    owner = create_user()
    async with LoggedInClient(owner) as client:
        discussion_id = await interrupt_after(client, ai_messages=2)
        before = persistence.list_messages_after(discussion_id, 0)
        subtopics_before = (await client.get(f"/api/v1/discussions/{discussion_id}")).json()["subtopics"]

        update_user(owner.id, daily_limit=1)  # 오늘 이미 1개 시작 → 재개는 일일 시작 수에 포함되지 않아야 함
        sub = broker.subscribe(discussion_id)
        assert (await client.post(f"/api/v1/discussions/{discussion_id}/resume")).status_code == 202
        await asyncio.wait_for(registry.get(discussion_id).task, timeout=30)
        events = []
        while not sub.queue.empty():
            events.append(sub.queue.get_nowait())
        broker.unsubscribe(discussion_id, sub)

        after = persistence.list_messages_after(discussion_id, 0)
        assert [m["seq"] for m in after] == list(range(1, len(after) + 1))       # seq 연속, 중복 없음
        assert after[:len(before)] == before                                      # 기존 발언 보존
        assert sum(m["speaker_type"] == "ai" for m in after) == BODY["max_statements"]  # 예산 이어서 사용
        assert not any(e.event == "subtopics" for e in events)                    # 소주제 재생성 없음
        detail = (await client.get(f"/api/v1/discussions/{discussion_id}")).json()
        assert detail["subtopics"] == subtopics_before
        assert [r["resumed"] for r in detail["run_info"]] == [False, True]  # 시작·재개마다 실행 기록
        assert detail["status"] == "completed" and detail["error"] is None


@pytest.mark.asyncio
async def test_resume_permissions_status_and_concurrency():
    owner, other = create_user(), create_user()
    async with LoggedInClient(owner) as c_owner, LoggedInClient(other) as c_other:
        discussion_id = await interrupt_after(c_owner, ai_messages=1)
        r = await c_other.post(f"/api/v1/discussions/{discussion_id}/resume")
        assert r.status_code == 403

        draft_id = (await c_owner.post("/api/v1/discussions", json=BODY)).json()["id"]
        r = await c_owner.post(f"/api/v1/discussions/{draft_id}/resume")
        assert r.status_code == 409 and r.json()["detail"]["error"]["code"] == "INVALID_STATUS"

        assert (await c_owner.post(f"/api/v1/discussions/{draft_id}/start")).status_code == 202  # 동시 실행 1개 사용
        r = await c_owner.post(f"/api/v1/discussions/{discussion_id}/resume")
        assert r.status_code == 403 and r.json()["detail"]["error"]["code"] == "CONCURRENT_LIMIT_EXCEEDED"
        await registry.stop(draft_id, by="test")


@pytest.mark.asyncio
async def test_restore_responds_to_unanswered_human_and_keeps_counts():
    bundle = FakeBundle()
    base = {k: v for k, v in PERSONA.items() if k != "model"}
    agents = [DiscussionAgent(Persona(name=n, **base), llm=bundle.agent) for n in ("Alice", "Bob")]
    engine = NaturalDiscussion(agents, moderator=None, max_statements=3)
    engine.restore([
        Message(role="assistant", content="a1", agent_name="Alice", metadata={"seq": 1}),
        Message(role="assistant", content="b1", agent_name="Bob", metadata={"seq": 2}),
        Message(role="user", content="human view", agent_name="Visitor", metadata={"speaker_type": "human", "seq": 3}),
    ])
    assert engine.turn_count == 2 and engine.agent_turn_count == {"Alice": 1, "Bob": 1}

    utterances = [e async for e in engine.stream("topic", language="en") if e.kind == "utterance"]
    assert utterances[0].action == ActionType.RESPOND_TO_HUMAN.value
    assert utterances[0].meta["in_reply_to_seq"] == 3
    assert utterances[0].speaker == "Alice"  # 직전 AI 발언자(Bob) 제외
    assert len(utterances) == 1  # 남은 예산 1 = 응답 1개


@pytest.mark.parametrize("spoken,idx,on_subtopic,closing_done", [
    (4, 0, 4, []),            # 계획(3, 12) = 명제 [5, 4] + 종결 3
    (5, 1, 0, []),
    (9, 1, 4, []),
    (11, 1, 4, ["C2", "C3"]),  # 종결 라운드 2명 완료
])
def test_restore_without_snapshot_places_progress_by_plan(spoken, idx, on_subtopic, closing_done):
    bundle = FakeBundle()
    base = {k: v for k, v in PERSONA.items() if k != "model"}
    agents = [DiscussionAgent(Persona(name=n, **base), llm=bundle.agent) for n in ("A", "B", "C")]
    engine = NaturalDiscussion(agents, moderator=None, max_statements=12)
    names = ["A", "B", "C"] * 3 + ["C2", "C3"]
    engine.restore([Message(role="assistant", content="x", agent_name=names[i], metadata={"seq": i + 1})
                    for i in range(spoken)])
    assert (engine.subtopic_idx, engine.statements_on_subtopic) == (idx, on_subtopic)
    assert engine.closing_started == bool(closing_done) and engine.closing_done == closing_done


def test_restore_replays_statements_saved_after_last_snapshot():
    """발언은 저장됐지만 분석(스냅숏) 전에 중단되면, 스냅숏 이후 발언을 진행 상태에 다시 반영해 예산을 초과하지 않는다"""
    bundle = FakeBundle()
    base = {k: v for k, v in PERSONA.items() if k != "model"}
    agents = [DiscussionAgent(Persona(name=n, **base), llm=bundle.agent) for n in ("Alice", "Bob")]
    engine = NaturalDiscussion(agents, moderator=None, max_statements=6)
    snapshot = {"subtopic_idx": 0, "statements_on_subtopic": 2, "spoken_in_subtopic": {"Alice": 1, "Bob": 1},
                "closing_started": False, "closing_done": [], "devils_advocate_used": False}
    msgs = [Message(role="assistant", content=c, agent_name=n, metadata={"seq": s, "action": "position"})
            for s, n, c in ((1, "Alice", "a1"), (2, "Bob", "b1"), (3, "Alice", "a2"))]
    engine.restore(msgs, snapshot=snapshot, snapshot_seq=2)  # #3은 분석 전에 중단됨
    assert engine.statements_on_subtopic == 3 and engine.spoken_in_subtopic["Alice"] == 2
