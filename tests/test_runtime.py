"""
토론 런타임 테스트 (가짜 LLM 사용, 실제 API 호출 없음)
"""
import asyncio
import itertools

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from api.database import SessionLocal
from api.models.discussion import Discussion, DiscussionStatus
from api.runtime import broker, registry
from api.runtime import persistence
from api.runtime import runtime as runtime_module
from api.schemas.discussion import CreateDiscussionRequest
from api.services.discussion_service import DiscussionService
from tests.conftest import create_user

SUBTOPICS = ["Economic impact on households", "Ethical considerations for society", "Technical feasibility today"]


class SlowFakeChatModel(GenericFakeChatModel):
    """스트리밍 조각 사이에 지연을 넣어 중지 테스트에 사용"""

    async def _astream(self, *args, **kwargs):
        async for chunk in super()._astream(*args, **kwargs):
            await asyncio.sleep(0.05)
            yield chunk


def _with_structured_subtopics(base):
    """모더레이터용: 소주제는 구조화 출력으로, 질문은 일반 응답으로 돌려주는 가짜 모델"""

    class FakeModerator(base):
        def with_structured_output(self, schema, **kwargs):
            return RunnableLambda(lambda _messages: schema(subtopics=list(SUBTOPICS)))

    return FakeModerator


class FakeBundle:
    """LLMBundle 대체: temperature 0.5 = 모더레이터, 그 외 = 에이전트"""

    def __init__(self, callbacks=None, slow=False):
        cls = SlowFakeChatModel if slow else GenericFakeChatModel
        self.moderator = _with_structured_subtopics(cls)(
            messages=itertools.cycle([AIMessage(content="What is the strongest counterargument here?")]))
        self.agent = cls(messages=itertools.cycle(
            [AIMessage(content=f"Point number {i} with concrete evidence and data.") for i in range(1, 50)]
        ))

    def get(self, provider, model=None, temperature=None):
        return self.moderator if temperature == 0.5 else self.agent


def _create(max_statements=4):
    db = SessionLocal()
    try:
        persona = dict(role="Analyst", background="bg", personality=["calm"], expertise=["x"],
                       communication_style="plain", beliefs=["evidence matters"], model="fake-model")
        request = CreateDiscussionRequest(
            topic="Should cities ban cars downtown?",
            personas=[dict(name="Alice", **persona), dict(name="Bob", **persona)],
            max_statements=max_statements,
        )
        return DiscussionService.create(db, request, user=create_user()).id
    finally:
        db.close()


def _discussion(discussion_id):
    db = SessionLocal()
    try:
        return db.get(Discussion, discussion_id)
    finally:
        db.close()


@pytest.mark.asyncio
async def test_runtime_persists_messages_in_seq_order_and_publishes(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", FakeBundle)
    discussion_id = _create(max_statements=4)

    sub = broker.subscribe(discussion_id)
    runtime = registry.start(discussion_id)
    await asyncio.wait_for(runtime.task, timeout=10)
    broker.unsubscribe(discussion_id, sub)

    messages = persistence.list_messages_after(discussion_id, 0)
    ai_messages = [m for m in messages if m["speaker_type"] == "ai"]
    assert [m["seq"] for m in messages] == list(range(1, len(messages) + 1))
    assert len(ai_messages) == 4
    assert {m["speaker"] for m in ai_messages} == {"Alice", "Bob"}
    assert all(m["participant_id"] for m in ai_messages)

    d = _discussion(discussion_id)
    assert d.status == DiscussionStatus.COMPLETED
    assert d.last_seq == len(messages)
    assert d.subtopics and len(d.subtopics) == 3

    events = []
    while not sub.queue.empty():
        events.append(sub.queue.get_nowait())
    published = [e.id for e in events if e.event == "message"]
    assert published == [m["seq"] for m in messages]
    assert any(e.event == "chunk" for e in events)
    assert events[-1].event == "status" and events[-1].data["status"] == "completed"
    assert registry.get(discussion_id) is None


@pytest.mark.asyncio
async def test_stop_cancels_running_discussion(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", lambda callbacks=None: FakeBundle(slow=True))
    discussion_id = _create(max_statements=20)

    registry.start(discussion_id)
    await asyncio.sleep(0.5)
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    assert await registry.stop(discussion_id, by="tester", reason="enough")
    assert loop.time() - t0 < 1.0

    d = _discussion(discussion_id)
    assert d.status == DiscussionStatus.STOPPED
    assert d.stopped_by == "tester" and d.stop_reason == "enough"
    messages = persistence.list_messages_after(discussion_id, 0)
    assert [m["seq"] for m in messages] == list(range(1, len(messages) + 1))


def test_mark_active_as_interrupted():
    discussion_id = _create()
    persistence.update_discussion(discussion_id, status=DiscussionStatus.RUNNING)
    assert persistence.mark_active_as_interrupted() >= 1
    assert _discussion(discussion_id).status == DiscussionStatus.INTERRUPTED
