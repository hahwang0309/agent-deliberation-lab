"""
종합보고서 자동 생성·재생성·내보내기 API 테스트 (가짜 LLM)
"""
import asyncio

import pytest

from api.runtime import registry, reports
from api.runtime import runtime as runtime_module
from tests.report_stubs import NARRATIVE, StubLLM
from tests.conftest import LoggedInClient, create_user
from tests.test_events_api import PERSONA, parse_sse
from tests.test_runtime import FakeBundle


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", FakeBundle)
    return LoggedInClient(create_user(daily_limit=100))


async def _create(client, max_statements):
    r = await client.post("/api/v1/discussions", json={
        "topic": "Universal basic income?", "max_statements": max_statements,
        "personas": [dict(name="Alice", **PERSONA), dict(name="Bob", **PERSONA)]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_completed_discussion_gets_report_before_completed_status(client):
    async with client:
        discussion_id = await _create(client, max_statements=4)
        assert (await client.post(f"/api/v1/discussions/{discussion_id}/start")).status_code == 202
        events = parse_sse((await client.get(f"/api/v1/discussions/{discussion_id}/events")).text)
        names = [e for e, _, _ in events]
        # 클라이언트가 보는 상태 = 접속 시 snapshot + 이후 status 이벤트 (running 이벤트는 접속 전에 지나갈 수 있음)
        observed = [d["status"] for e, _, d in events if e in ("snapshot", "status")]
        distinct = [st for i, st in enumerate(observed) if i == 0 or st != observed[i - 1]]
        assert distinct[-2:] == ["reporting", "completed"]
        order = ["draft", "running", "reporting", "completed"]
        assert [order.index(st) for st in distinct] == sorted(order.index(st) for st in distinct)
        assert names.index("report_ready") < len(names) - 1

        report = (await client.get(f"/api/v1/discussions/{discussion_id}/report")).json()
        assert report["status"] == "ready" and report["model"] == "stub-model"
        # 가짜 LLM 쟁점: [찬성, 반대] → 쌍 일치도 0
        assert report["consensus_score"] == 0.0 and report["consensus_label"] == "disagreed"
        assert report["ai_score"] == 0.0 and report["human_score"] is None and report["ai_human_score"] is None
        assert report["content"]["disagreed"] == ["Proposition"]
        assert (await client.get(f"/api/v1/discussions/{discussion_id}")).json()["consensus_score"] == 0.0

        md = await client.get(f"/api/v1/discussions/{discussion_id}/report/export?format=md")
        assert md.status_code == 200 and md.text.startswith("# 종합보고서: Universal basic income?")
        assert "attachment" in md.headers["content-disposition"]
        js = await client.get(f"/api/v1/discussions/{discussion_id}/report/export?format=json")
        assert js.json()["scores"]["overall"] == 0.0


@pytest.mark.asyncio
async def test_too_short_discussion_has_no_report_and_cannot_regenerate(client):
    async with client:
        discussion_id = await _create(client, max_statements=3)
        await client.post(f"/api/v1/discussions/{discussion_id}/start")
        await asyncio.wait_for(registry.get(discussion_id).task, timeout=10)
        assert (await client.get(f"/api/v1/discussions/{discussion_id}/report")).status_code == 404
        r = await client.post(f"/api/v1/discussions/{discussion_id}/report")
        assert r.status_code == 409 and r.json()["detail"]["error"]["code"] == "INSUFFICIENT_MESSAGES"


@pytest.mark.asyncio
async def test_stopped_discussion_with_enough_messages_gets_report(client, monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", lambda callbacks=None: FakeBundle(slow=True))
    async with client:
        discussion_id = await _create(client, max_statements=20)
        await client.post(f"/api/v1/discussions/{discussion_id}/start")
        runtime = registry.get(discussion_id)
        for _ in range(200):
            if runtime.ai_messages >= 4:
                break
            await asyncio.sleep(0.05)
        assert (await client.post(f"/api/v1/discussions/{discussion_id}/stop")).status_code == 200
        task = registry.report_task(discussion_id)
        assert task is not None
        await asyncio.wait_for(task, timeout=10)
        report = (await client.get(f"/api/v1/discussions/{discussion_id}/report")).json()
        assert report["status"] == "ready"
        assert (await client.get(f"/api/v1/discussions/{discussion_id}")).json()["status"] == "stopped"


@pytest.mark.asyncio
async def test_report_failure_keeps_discussion_completed_and_regenerate_recovers(client, monkeypatch):
    broken = StubLLM({"IssueMap": [{"issues": [{"title": "missing fields"}]}] * 3, "Narrative": NARRATIVE})
    monkeypatch.setattr(reports, "create_report_llm", lambda callbacks: broken)
    async with client:
        discussion_id = await _create(client, max_statements=4)
        await client.post(f"/api/v1/discussions/{discussion_id}/start")
        await asyncio.wait_for(registry.get(discussion_id).task, timeout=10)
        assert (await client.get(f"/api/v1/discussions/{discussion_id}")).json()["status"] == "completed"
        failed = (await client.get(f"/api/v1/discussions/{discussion_id}/report")).json()
        assert failed["status"] == "failed" and "ReportGenerationError" in failed["error"]
        assert (await client.get(f"/api/v1/discussions/{discussion_id}/report/export")).status_code == 409

        from tests.report_stubs import default_stub
        monkeypatch.setattr(reports, "create_report_llm", lambda callbacks: default_stub())
        assert (await client.post(f"/api/v1/discussions/{discussion_id}/report")).status_code == 202
        await asyncio.wait_for(registry.report_task(discussion_id), timeout=10)
        assert (await client.get(f"/api/v1/discussions/{discussion_id}/report")).json()["status"] == "ready"
        assert (await client.delete(f"/api/v1/discussions/{discussion_id}")).status_code == 204
