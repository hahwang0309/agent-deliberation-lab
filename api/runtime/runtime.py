"""
토론 1건의 실행 런타임

uvicorn 메인 루프의 asyncio.Task로 엔진(src.core.natural_discussion)을 구동하고,
완성된 발언은 저장 후 발행(persist-then-publish), 스트리밍 조각은 발행만 한다.
"""
import asyncio
import logging
from typing import Any, Dict, Optional

from langchain_core.callbacks import UsageMetadataCallbackHandler

from api.models.discussion import DiscussionStatus
from api.models.message import SpeakerType
from api.runtime import persistence
from api.runtime.broker import EventBroker
from src.core.natural_discussion import EngineEvent
from src.discussion import ParticipantSpec, create_discussion
from src.models.personas import LLMProvider, Persona
from src.utils.llm_provider import LLMBundle

logger = logging.getLogger(__name__)


class UsageCounter(UsageMetadataCallbackHandler):
    """토큰 사용량 + LLM 호출 횟수 집계"""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def on_llm_end(self, response, **kwargs) -> None:
        self.calls += 1
        super().on_llm_end(response, **kwargs)

    def totals(self) -> Dict[str, int]:
        prompt = sum(u.get("input_tokens", 0) for u in self.usage_metadata.values())
        completion = sum(u.get("output_tokens", 0) for u in self.usage_metadata.values())
        return {"prompt_tokens": prompt, "completion_tokens": completion, "llm_calls": self.calls}


class DiscussionRuntime:
    def __init__(self, discussion_id: str, broker: EventBroker):
        self.discussion_id = discussion_id
        self.broker = broker
        self.status = DiscussionStatus.RUNNING
        self.last_seq = 0
        self.current_utterance: Optional[Dict[str, Any]] = None
        self.task: Optional[asyncio.Task] = None
        self.stop_request: Optional[Dict[str, Optional[str]]] = None
        self._participant_ids: Dict[str, str] = {}

    # ---------- 외부 조회 ----------

    def snapshot(self) -> Dict[str, Any]:
        """새 구독자에게 보내는 현재 상태"""
        return {
            "status": self.status,
            "last_seq": self.last_seq,
            "current_utterance": dict(self.current_utterance) if self.current_utterance else None,
        }

    # ---------- 실행 ----------

    async def run(self) -> None:
        usage = UsageCounter()
        try:
            data = await asyncio.to_thread(persistence.load_discussion, self.discussion_id)
            self.last_seq = data["last_seq"]
            self._participant_ids = {p["name"]: p["id"] for p in data["participants"]}
            config = data["config"]

            engine = create_discussion(
                [ParticipantSpec(persona=Persona(**p["persona"]), provider=LLMProvider(p["provider"]),
                                 model=p["model"] or None)
                 for p in data["participants"]],
                bundle=LLMBundle(callbacks=[usage]),
                use_moderator=config.get("use_moderator", True),
                enable_web_search=config.get("enable_web_search", False),
                enable_belief_reasoning=config.get("enable_belief_reasoning", False),
                max_statements=config["max_statements"],
            )

            await self._set_status(DiscussionStatus.RUNNING, started_at=persistence.utcnow(), error=None)
            topic = data["topic"] if not data["description"] else f"{data['topic']}\n\n{data['description']}"
            async for event in engine.stream(topic, language=data["language"]):
                await self._handle(event)

            await self._set_status(DiscussionStatus.COMPLETED, completed_at=persistence.utcnow())

        except asyncio.CancelledError:
            await self._on_cancelled()
            raise
        except Exception as e:
            logger.exception("Discussion %s failed", self.discussion_id)
            self._abort_utterance()
            await self._set_status(DiscussionStatus.FAILED, error=f"{type(e).__name__}: {e}")
        finally:
            totals = usage.totals()
            await asyncio.shield(asyncio.to_thread(persistence.add_usage, self.discussion_id, **totals))

    async def _on_cancelled(self) -> None:
        self._abort_utterance()
        req = self.stop_request or {}
        await asyncio.shield(self._set_status(
            DiscussionStatus.STOPPED, stopped_at=persistence.utcnow(),
            stopped_by=req.get("by"), stop_reason=req.get("reason"),
        ))

    def _abort_utterance(self) -> None:
        if self.current_utterance:
            self.broker.publish(self.discussion_id, "utterance_aborted",
                                {"speaker": self.current_utterance["speaker"]})
            self.current_utterance = None

    async def _set_status(self, status: str, **fields: Any) -> None:
        self.status = status
        await asyncio.to_thread(persistence.update_discussion, self.discussion_id, status=status, **fields)
        payload = {"status": status}
        if fields.get("error"):
            payload["error"] = fields["error"]
        self.broker.publish(self.discussion_id, "status", payload)

    async def _handle(self, event: EngineEvent) -> None:
        if event.kind == "subtopics":
            subtopics = event.meta["subtopics"]
            await asyncio.to_thread(persistence.update_discussion, self.discussion_id,
                                    subtopics=subtopics, current_subtopic=subtopics[0][:200])
            self.broker.publish(self.discussion_id, "subtopics", {"subtopics": subtopics})

        elif event.kind == "utterance_start":
            self.current_utterance = {"speaker": event.speaker, "speaker_type": event.speaker_type,
                                      "action": event.action, "text": ""}
            self.broker.publish(self.discussion_id, "utterance_start",
                                {k: v for k, v in self.current_utterance.items() if k != "text"})

        elif event.kind == "chunk":
            if self.current_utterance is not None:
                self.current_utterance["text"] += event.content
            self.broker.publish(self.discussion_id, "chunk", {"speaker": event.speaker, "delta": event.content})

        elif event.kind == "utterance":
            seq = self.last_seq + 1
            speaker_type = SpeakerType.MODERATOR if event.speaker_type == "moderator" else SpeakerType.AI
            message = await asyncio.to_thread(
                persistence.save_message, self.discussion_id, seq, speaker_type, event.speaker,
                event.content, event.action, event.meta,
                participant_id=self._participant_ids.get(event.speaker) if speaker_type == SpeakerType.AI else None,
            )
            self.last_seq = seq
            self.current_utterance = None
            if event.action == "transition" and event.meta.get("subtopic"):
                await asyncio.to_thread(persistence.update_discussion, self.discussion_id,
                                        current_subtopic=event.meta["subtopic"][:200])
            self.broker.publish(self.discussion_id, "message", message, id=seq)
