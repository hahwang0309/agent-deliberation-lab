"""
종합보고서 생성 작업 - 토론 완료 직후(런타임 내부) 또는 중지·재생성 시(별도 태스크) 실행
"""
import asyncio
import logging
from typing import Any, List

from langchain_core.language_models import BaseChatModel

from api.runtime import persistence
from api.runtime.broker import EventBroker
from api.runtime.usage import UsageCounter
from config.config_loader import config_loader
from src.services.consensus_report import ConsensusReportGenerator, TranscriptMessage
from src.services.debate_dynamics import summarize_dynamics
from src.utils.llm_provider import LLMFactory

logger = logging.getLogger(__name__)


def create_report_llm(callbacks: List[Any]) -> BaseChatModel:
    cfg = config_loader.config.report
    return LLMFactory.create_llm(None, model=cfg.model, temperature=cfg.temperature,
                                 max_tokens=cfg.max_tokens, callbacks=callbacks)


async def run_report_job(discussion_id: str, broker: EventBroker) -> bool:
    """보고서를 생성·저장하고 이벤트를 발행한다. 성공 여부를 반환 (취소는 전파)."""
    cfg = config_loader.config.report
    usage = UsageCounter()
    await asyncio.to_thread(persistence.mark_report_pending, discussion_id)
    broker.publish(discussion_id, "report_status", {"status": "pending"})
    try:
        data = await asyncio.to_thread(persistence.load_transcript, discussion_id)
        llm = create_report_llm([usage])
        generator = ConsensusReportGenerator(llm, cfg.agreed_threshold, cfg.partial_threshold, cfg.max_attempts,
                                             partial_weight=cfg.partial_weight)
        content = await generator.generate(
            data["topic"],
            [TranscriptMessage(**m) for m in data["transcript"]],
            data["participants"],
            language=data["language"],
        )
        content["dynamics"] = summarize_dynamics(data["records"], data["subtopics"])
        model = getattr(llm, "model", None) or getattr(llm, "model_name", None)
        await asyncio.to_thread(persistence.save_report, discussion_id, content, model)
        broker.publish(discussion_id, "report_ready",
                       {"status": "ready", "scores": content["scores"], "label": content["label"]})
        return True
    except asyncio.CancelledError:
        await asyncio.shield(asyncio.to_thread(persistence.fail_report, discussion_id, "cancelled"))
        broker.publish(discussion_id, "report_status", {"status": "failed", "error": "cancelled"})
        raise
    except Exception as e:
        logger.exception("Report generation failed for %s", discussion_id)
        error = f"{type(e).__name__}: {e}"
        await asyncio.to_thread(persistence.fail_report, discussion_id, error)
        broker.publish(discussion_id, "report_status", {"status": "failed", "error": error})
        return False
    finally:
        totals = usage.totals()
        await asyncio.shield(asyncio.to_thread(persistence.add_usage, discussion_id, **totals))
