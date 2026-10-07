"""
토론 1건의 실행 런타임

uvicorn 메인 루프의 asyncio.Task로 엔진(src.core.natural_discussion)을 구동하고,
완성된 발언은 저장 후 발행(persist-then-publish), 스트리밍 조각은 발행만 한다.
"""
import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from api.models.discussion import DiscussionStatus
from api.models.message import SpeakerType
from api.runtime import persistence
from api.runtime.broker import EventBroker
from api.runtime.intervention import HumanDesk
from api.runtime.reports import run_report_job
from api.runtime.usage import UsageCounter
from config.config_loader import config_loader
from src.core.experiment import ExperimentConfig
from src.core.natural_discussion import EngineEvent
from src.services.survey import SurveyConfig
from src.discussion import ParticipantSpec, create_discussion
from src.models.personas import LLMProvider, Message, Persona
from src.utils.llm_provider import LLMBundle

logger = logging.getLogger(__name__)


class DiscussionRuntime:
    def __init__(self, discussion_id: str, broker: EventBroker,
                 schedule_report: Optional[Callable[[str], Any]] = None, resume: bool = False):
        self.discussion_id = discussion_id
        self.resume = resume  # interrupted 토론을 저장된 발언에서 이어서 진행
        self.broker = broker
        self.schedule_report = schedule_report  # 중지 후 보고서 생성을 별도 태스크로 예약
        self.ai_messages = 0
        self.status = DiscussionStatus.RUNNING
        self.last_seq = 0
        self.current_utterance: Optional[Dict[str, Any]] = None
        self.task: Optional[asyncio.Task] = None
        self.stop_request: Optional[Dict[str, Optional[str]]] = None
        self._participant_ids: Dict[str, str] = {}
        self.desk = HumanDesk(self)  # 사람 발언 대기열·발언권

    @property
    def persona_names(self):
        return self._participant_ids.keys()

    # ---------- 외부 조회 ----------

    def snapshot(self) -> Dict[str, Any]:
        """새 구독자에게 보내는 현재 상태"""
        return {
            "status": self.status,
            "last_seq": self.last_seq,
            "current_utterance": dict(self.current_utterance) if self.current_utterance else None,
            "hands": self.desk.state(),
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
                experiment=ExperimentConfig(**config["experiment"]) if config.get("experiment") else None,
                propositions=config.get("propositions"),
                materials=config.get("materials"),
                survey=SurveyConfig(**config["survey"]) if config.get("survey") else None,
            )

            if self.resume:
                await self._restore(engine, data)
                await self.set_status(DiscussionStatus.RUNNING, error=None)
            else:
                await self.set_status(DiscussionStatus.RUNNING, started_at=persistence.utcnow(), error=None)
            topic = data["topic"] if not data["description"] else f"{data['topic']}\n\n{data['description']}"
            async for event in engine.stream(topic, language=data["language"], gate=self.desk,
                                             start_seq=self.last_seq + 1):
                await self._handle(event)

            if self._report_eligible():
                await self.set_status(DiscussionStatus.REPORTING)
                await run_report_job(self.discussion_id, self.broker)
            await self.set_status(DiscussionStatus.COMPLETED, completed_at=persistence.utcnow())

        except asyncio.CancelledError:
            await self._on_cancelled()
            raise
        except Exception as e:
            logger.exception("Discussion %s failed", self.discussion_id)
            self._abort_utterance()
            await self.set_status(DiscussionStatus.FAILED, error=f"{type(e).__name__}: {e}")
        finally:
            totals = usage.totals()
            await asyncio.shield(asyncio.to_thread(persistence.add_usage, self.discussion_id, **totals))

    async def _restore(self, engine, data: Dict[str, Any]) -> None:
        rows = await asyncio.to_thread(persistence.list_messages_after, self.discussion_id, 0, 100000)
        role = {SpeakerType.AI: "assistant", SpeakerType.MODERATOR: "moderator", SpeakerType.HUMAN: "user"}
        engine.restore(
            [Message(role=role.get(r["speaker_type"], "system"), content=r["content"], agent_name=r["speaker"],
                     metadata={**r["meta"], "speaker_type": r["speaker_type"], "seq": r["seq"]})
             for r in rows if r["speaker_type"] in role],
            subtopics=data["subtopics"], current_subtopic=data["current_subtopic"],
            snapshot=next((r["meta"]["debate"] for r in reversed(rows) if r["meta"].get("debate")), None),
        )
        self.ai_messages = sum(r["speaker_type"] == SpeakerType.AI for r in rows)
        for r in rows:
            if r["speaker_type"] == SpeakerType.HUMAN and r["user_id"]:
                self.desk.turns[r["user_id"]] = self.desk.turns.get(r["user_id"], 0) + 1
                self.desk.display_names.setdefault(r["user_id"], r["speaker"])

    async def _on_cancelled(self) -> None:
        self._abort_utterance()
        self.desk.abort()
        was_reporting = self.status == DiscussionStatus.REPORTING
        req = self.stop_request or {}
        await asyncio.shield(self.set_status(
            DiscussionStatus.STOPPED, stopped_at=persistence.utcnow(),
            stopped_by=req.get("by"), stop_reason=req.get("reason"),
        ))
        # 사용자가 중지한 토론도 발언이 충분하면 보고서를 만든다 (서버 종료·보고서 생성 중 중지는 제외)
        if (self.schedule_report and not was_reporting and req.get("by") != "system"
                and self._report_eligible()):
            self.schedule_report(self.discussion_id)

    def _report_eligible(self) -> bool:
        return self.ai_messages >= config_loader.config.report.min_ai_messages

    def _abort_utterance(self) -> None:
        if self.current_utterance:
            self.broker.publish(self.discussion_id, "utterance_aborted",
                                {"speaker": self.current_utterance["speaker"]})
            self.current_utterance = None

    async def set_status(self, status: str, **fields: Any) -> None:
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

        elif event.kind == "analysis":
            # 발언 분석·토론 상태를 해당 메시지에 기록 (보고서의 입장 궤적, 재개 시 상태 복원에 사용)
            seq = event.meta["seq"]
            await asyncio.to_thread(persistence.update_message_meta, self.discussion_id, seq, {
                "analysis": event.meta["analysis"], "moves": event.meta["moves"],
                "stances": event.meta["stances"], "debate": event.meta["debate"],
            })
            state = event.meta["debate"]["state"]
            self.broker.publish(self.discussion_id, "analysis", {
                "seq": seq, "speaker": event.speaker, "subtopic_idx": event.meta["subtopic_idx"],
                "move": event.meta["analysis"].get("move"), "stances": event.meta["stances"],
                "moves": event.meta["moves"],
                "open_challenges": [{"challenger": c["challenger"], "target": c["target"]} for c in state["challenges"]],
            })

        elif event.kind == "survey":
            await asyncio.to_thread(persistence.save_survey, self.discussion_id, event.meta["phase"],
                                    event.speaker, event.speaker_type or "ai", event.meta["answers"])
            self.broker.publish(self.discussion_id, "survey", {"phase": event.meta["phase"], "participant": event.speaker})

        elif event.kind == "utterance":
            speaker_type = SpeakerType.MODERATOR if event.speaker_type == "moderator" else SpeakerType.AI
            if event.meta.get("seq") not in (None, self.last_seq + 1):
                logger.warning("Engine seq %s != runtime seq %s", event.meta.get("seq"), self.last_seq + 1)
            await self.save_and_publish(
                speaker_type, event.speaker, event.content, event.action, event.meta,
                participant_id=self._participant_ids.get(event.speaker) if speaker_type == SpeakerType.AI else None,
            )
            self.current_utterance = None
            if speaker_type == SpeakerType.AI:
                self.ai_messages += 1
            if event.action == "transition" and event.meta.get("subtopic"):
                await asyncio.to_thread(persistence.update_discussion, self.discussion_id,
                                        current_subtopic=event.meta["subtopic"][:200])

    async def save_and_publish(self, speaker_type: str, speaker: str, content: str, action: Optional[str] = None,
                               meta: Optional[Dict[str, Any]] = None, participant_id: Optional[str] = None,
                               user_id: Optional[str] = None) -> Dict[str, Any]:
        """완성된 발언에 다음 seq를 붙여 저장한 뒤 발행 (persist-then-publish)"""
        seq = self.last_seq + 1
        message = await asyncio.to_thread(
            persistence.save_message, self.discussion_id, seq, speaker_type, speaker, content, action, meta,
            participant_id=participant_id, user_id=user_id,
        )
        self.last_seq = seq
        self.broker.publish(self.discussion_id, "message", message, id=seq)
        return message
