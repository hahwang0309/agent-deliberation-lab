"""
실행 중인 토론 런타임 레지스트리 (프로세스 메모리, 단일 워커 전제)
"""
import asyncio
import logging
from typing import Dict, Optional

from api.runtime.broker import EventBroker
from api.runtime.reports import run_report_job
from api.runtime.runtime import DiscussionRuntime

logger = logging.getLogger(__name__)


class AlreadyRunningError(Exception):
    pass


class CapacityError(Exception):
    pass


class DiscussionRegistry:
    def __init__(self, broker: EventBroker, max_running: int):
        self.broker = broker
        self.max_running = max_running
        self._runtimes: Dict[str, DiscussionRuntime] = {}
        self._report_tasks: Dict[str, asyncio.Task] = {}

    def get(self, discussion_id: str) -> Optional[DiscussionRuntime]:
        return self._runtimes.get(discussion_id)

    def running_count(self) -> int:
        return len(self._runtimes)

    def start(self, discussion_id: str) -> DiscussionRuntime:
        if discussion_id in self._runtimes:
            raise AlreadyRunningError(discussion_id)
        if len(self._runtimes) >= self.max_running:
            raise CapacityError(self.max_running)

        runtime = DiscussionRuntime(discussion_id, self.broker, schedule_report=self.start_report)
        runtime.task = asyncio.create_task(runtime.run(), name=f"discussion:{discussion_id}")
        runtime.task.add_done_callback(lambda _t: self._runtimes.pop(discussion_id, None))
        self._runtimes[discussion_id] = runtime
        return runtime

    def report_running(self, discussion_id: str) -> bool:
        runtime = self._runtimes.get(discussion_id)
        return discussion_id in self._report_tasks or (runtime is not None and runtime.status == "reporting")

    def start_report(self, discussion_id: str) -> asyncio.Task:
        """종료된 토론의 보고서 생성을 별도 태스크로 실행"""
        if self.report_running(discussion_id):
            raise AlreadyRunningError(discussion_id)
        task = asyncio.create_task(run_report_job(discussion_id, self.broker), name=f"report:{discussion_id}")
        task.add_done_callback(lambda _t: self._report_tasks.pop(discussion_id, None))
        self._report_tasks[discussion_id] = task
        return task

    def report_task(self, discussion_id: str) -> Optional[asyncio.Task]:
        return self._report_tasks.get(discussion_id)

    async def stop(self, discussion_id: str, by: Optional[str] = None, reason: Optional[str] = None) -> bool:
        """실행 중이면 취소하고 종료될 때까지 기다린다. 실행 중이 아니면 False."""
        runtime = self._runtimes.get(discussion_id)
        if runtime is None or runtime.task is None:
            return False
        runtime.stop_request = {"by": by, "reason": reason}
        runtime.task.cancel()
        try:
            await runtime.task
        except asyncio.CancelledError:
            pass
        return True

    async def shutdown(self) -> None:
        """서버 종료 시 모든 토론 중지 (다음 시작 때 interrupted로 표시되지 않도록 stopped 처리)"""
        for discussion_id in list(self._runtimes):
            await self.stop(discussion_id, by="system", reason="server shutdown")
        for task in list(self._report_tasks.values()):
            task.cancel()
        await asyncio.gather(*self._report_tasks.values(), return_exceptions=True)
