"""
토론 API + SSE 재생 테스트 (가짜 LLM, ASGI 직접 호출)
"""
import asyncio
import json

import pytest

from api.runtime import registry
from api.runtime import runtime as runtime_module
from tests.conftest import LoggedInClient, create_user
from tests.test_runtime import FakeBundle

PERSONA = dict(role="Analyst", background="bg", personality=["calm"], expertise=["x"],
               communication_style="plain", beliefs=["evidence"], model="fake-model")


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        fields = {}
        for line in block.splitlines():
            if line.startswith(":"):
                continue
            key, _, value = line.partition(": ")
            fields[key] = value
        if "event" in fields:
            events.append((fields["event"], fields.get("id"), json.loads(fields["data"])))
    return events


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", FakeBundle)
    return LoggedInClient(create_user())


async def _create_and_run(client, max_statements=3):
    r = await client.post("/api/v1/discussions", json={
        "topic": "Four-day work week?", "max_statements": max_statements,
        "personas": [dict(name="Alice", **PERSONA), dict(name="Bob", **PERSONA)],
    })
    assert r.status_code == 201, r.text
    discussion_id = r.json()["id"]
    assert r.json()["status"] == "draft"
    r = await client.post(f"/api/v1/discussions/{discussion_id}/start")
    assert r.status_code == 202, r.text
    return discussion_id


@pytest.mark.asyncio
async def test_live_subscriber_receives_all_messages_once(client):
    async with client:
        discussion_id = await _create_and_run(client)
        r = await client.get(f"/api/v1/discussions/{discussion_id}/events")  # 완료 status까지 수신 후 종료
        events = parse_sse(r.text)
        seqs = [int(i) for e, i, _ in events if e == "message"]
        assert seqs == list(range(1, len(seqs) + 1)) and len(seqs) >= 3
        assert events[-1][0] == "status" and events[-1][2]["status"] == "completed"

        listed = (await client.get(f"/api/v1/discussions/{discussion_id}/messages")).json()
        assert [m["seq"] for m in listed["items"]] == seqs


@pytest.mark.asyncio
async def test_late_subscriber_replays_backlog_and_resumes_from_last_event_id(client):
    async with client:
        discussion_id = await _create_and_run(client)
        await asyncio.wait_for(registry.get(discussion_id).task, timeout=10)

        full = parse_sse((await client.get(f"/api/v1/discussions/{discussion_id}/events")).text)
        all_seqs = [int(i) for e, i, _ in full if e == "message"]
        assert full[-1][0] == "snapshot" and full[-1][2]["status"] == "completed"

        resumed = parse_sse((await client.get(f"/api/v1/discussions/{discussion_id}/events",
                                              headers={"Last-Event-ID": "2"})).text)
        assert [int(i) for e, i, _ in resumed if e == "message"] == [s for s in all_seqs if s > 2]


@pytest.mark.asyncio
async def test_state_rules(client):
    async with client:
        discussion_id = await _create_and_run(client)
        assert (await client.post(f"/api/v1/discussions/{discussion_id}/start")).status_code == 409
        assert (await client.delete(f"/api/v1/discussions/{discussion_id}")).status_code == 409
        await asyncio.wait_for(registry.get(discussion_id).task, timeout=10)
        assert (await client.post(f"/api/v1/discussions/{discussion_id}/stop")).status_code == 409
        assert (await client.delete(f"/api/v1/discussions/{discussion_id}")).status_code == 204
        assert (await client.get(f"/api/v1/discussions/{discussion_id}")).status_code == 404

        bad = await client.post("/api/v1/discussions", json={
            "topic": "x topic", "personas": [dict(name="Same", **PERSONA), dict(name="Same", **PERSONA)]})
        assert bad.status_code == 400
