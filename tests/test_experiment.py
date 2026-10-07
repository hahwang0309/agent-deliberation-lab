"""
실험 조건 테스트 - 토론별 설정 사본, 진행 장치 on/off, 참가자별 고집도·temperature, 분석 모델 분리, API 저장·실행
(가짜 LLM)
"""
import asyncio
from dataclasses import fields

import pytest
from pydantic import ValidationError

from api.runtime import persistence, registry
from api.runtime import runtime as runtime_module
from config.discussion_config import get_config
from src.core.agent import DiscussionAgent
from src.core.debate_state import DynamicsParams
from src.core.experiment import FULL_LATITUDE, ExperimentConfig, engine_settings
from src.core.moderator import DiscussionModerator
from src.core.natural_discussion import NaturalDiscussion, plan_debate
from src.discussion import ParticipantSpec, create_discussion
from src.models.personas import LLMProvider, Persona
from tests.conftest import LoggedInClient, create_user
from tests.test_discussion_quality import BASE, analyzed, latest_by, run, utterances
from tests.test_events_api import PERSONA
from tests.test_runtime import FakeAnalyzer, FakeBundle


def make_engine(names, max_statements, experiment=None, analyzer_fn=None):
    settings = engine_settings(ExperimentConfig(**experiment) if experiment else None)
    bundle = FakeBundle(analyzer=FakeAnalyzer(analyzer_fn) if analyzer_fn else None)
    agents = [DiscussionAgent(Persona(name=n, **BASE), llm=bundle.agent, config=settings) for n in names]
    return NaturalDiscussion(agents, moderator=DiscussionModerator(llm=bundle.moderator),
                             max_statements=max_statements, analyzer=bundle.analyzer, config=settings)


def ai_actions(events):
    return [u.action for u in utterances(events) if u.speaker_type == "ai"]


# ---------- 설정 사본 ----------

def test_engine_settings_copies_and_overrides_without_touching_global():
    before = vars(get_config()).copy()
    exp = ExperimentConfig(dynamics={"accept_wide": 1.0, "concession_cap": 0.1}, context_messages=3,
                           agent_temperature=0.2, mechanisms={"devils_advocate": False, "closing_round": False})
    a, b = engine_settings(exp), engine_settings(None)
    assert (a.accept_wide, a.concession_cap, a.context_messages, a.agent_temperature) == (1.0, 0.1, 3, 0.2)
    assert not a.use_devils_advocate and not a.use_closing_round and a.use_reply_obligation
    assert b.accept_wide == before["accept_wide"] and b is not get_config()
    assert vars(get_config()) == before  # 전역 설정은 그대로

    off = engine_settings(ExperimentConfig(mechanisms={"latitude": False, "concession_shift": False}))
    assert off.accept_wide == off.accept_narrow == FULL_LATITUDE and off.concession_step == 0.0


def test_dynamics_fields_cover_every_debate_parameter():
    """DynamicsParams에 새 파라미터가 생기면 실험 조건에서도 지정할 수 있어야 한다"""
    from src.core.experiment import Dynamics
    names = {f.name for f in fields(DynamicsParams)} - {"step", "anchor"} | {"dynamics_step", "dynamics_anchor"}
    assert names == set(Dynamics.model_fields)


@pytest.mark.parametrize("bad", [
    {"mechanisms": {"analysys": False}},          # 오타
    {"dynamics": {"accept_wide": 3.0}},           # 범위 밖
    {"participants": {"A": {"stubbornness": 1.5}}},
    {"unknown_key": 1},
])
def test_experiment_rejects_typos_and_out_of_range(bad):
    with pytest.raises(ValidationError):
        ExperimentConfig(**bad)


# ---------- 진행 장치 on/off ----------

def challenge_fn(messages):
    """A와 B가 서로 반박 (교착·응답 의무를 만들기 위한 분석기)"""
    seq, speaker, context = analyzed(messages)
    opponent = {"A": "B", "B": "A"}.get(speaker)
    target = latest_by(context, opponent) if opponent else None
    return {"stance": {"A": 0.8, "B": -0.8, "C": 0.0}[speaker],
            "targets": [{"seq": target, "speaker": opponent, "relation": "attack"}] if target else []}


@pytest.mark.asyncio
async def test_reply_obligation_and_stalemate_mediation_can_be_switched_off():
    on = ai_actions(await run(make_engine(["A", "B", "C"], 14, analyzer_fn=challenge_fn)))
    assert "respond_challenge" in on and {"mediate", "third_option"} & set(on)

    off = ai_actions(await run(make_engine(
        ["A", "B", "C"], 14, analyzer_fn=challenge_fn,
        experiment={"mechanisms": {"reply_obligation": False, "stalemate_mediation": False}})))
    assert "respond_challenge" not in off and not {"mediate", "third_option"} & set(off)


@pytest.mark.asyncio
async def test_two_person_moderator_mediation_follows_stalemate_switch():
    events = await run(make_engine(["A", "B"], 10, analyzer_fn=challenge_fn,
                                   experiment={"mechanisms": {"stalemate_mediation": False}}))
    assert not any(u.action == "mediation" for u in utterances(events))


@pytest.mark.asyncio
async def test_devils_advocate_and_closing_round_can_be_switched_off():
    same = lambda m: {"stance": 0.7}  # noqa: E731 — 모두 같은 입장 → 성급한 합의
    on = ai_actions(await run(make_engine(["A", "B", "C"], 12, analyzer_fn=same)))
    assert "devils_advocate" in on and on[-3:] == ["closing"] * 3

    engine = make_engine(["A", "B", "C"], 12, analyzer_fn=same,
                         experiment={"mechanisms": {"devils_advocate": False, "closing_round": False}})
    off = ai_actions(await run(engine))
    assert "devils_advocate" not in off and "closing" not in off and len(off) == 12
    assert engine.plan == plan_debate(3, 12, 5, closing_round=False) and engine.plan.closing == 0


@pytest.mark.asyncio
async def test_conditions_do_not_leak_between_concurrent_discussions():
    same = lambda m: {"stance": 0.7}  # noqa: E731
    plain = make_engine(["A", "B", "C"], 12, analyzer_fn=same)
    stripped = make_engine(["A", "B", "C"], 12, analyzer_fn=same,
                           experiment={"mechanisms": {"devils_advocate": False, "closing_round": False}})
    on, off = await asyncio.gather(run(plain), run(stripped))
    assert "devils_advocate" in ai_actions(on) and "closing" in ai_actions(on)
    assert "devils_advocate" not in ai_actions(off) and "closing" not in ai_actions(off)


# ---------- 참가자별 조건·분석 모델 (조립 헬퍼) ----------

class RecordingBundle(FakeBundle):
    """어떤 (provider, model, temperature)로 LLM을 요청했는지 기록"""

    def __init__(self):
        super().__init__()
        self.requests = []

    def get(self, provider, model=None, temperature=None):
        self.requests.append((provider, model, temperature))
        return super().get(provider, model, temperature)


def specs():
    return [ParticipantSpec(Persona(name=n, **BASE), LLMProvider.CLAUDE, "m-agent") for n in ("A", "B")]


def test_participant_conditions_and_separate_analyzer_model():
    bundle = RecordingBundle()
    exp = ExperimentConfig(agent_temperature=0.4, moderator_temperature=0.2,
                           participants={"B": {"stubbornness": 0.9, "temperature": 1.0}},
                           analyzer={"provider": "claude", "model": "m-judge"})
    engine = create_discussion(specs(), bundle=bundle, experiment=exp)
    assert (LLMProvider.CLAUDE, "m-agent", 0.4) in bundle.requests      # A: 실험 기본 temperature
    assert (LLMProvider.CLAUDE, "m-agent", 1.0) in bundle.requests      # B: 참가자별 temperature
    assert (LLMProvider.CLAUDE, "m-agent", 0.2) in bundle.requests      # 모더레이터
    assert (LLMProvider.CLAUDE, "m-judge", 0.0) in bundle.requests      # 분석 모델 분리
    assert engine.debate.participants["B"].stubbornness == 0.9
    assert engine.debate.participants["A"].stubbornness == engine.agents[0].stubbornness  # 지정 안 하면 성격으로
    assert engine.agents[1].config is engine.config  # 에이전트도 같은 토론별 설정을 씀


def test_analysis_off_removes_analyzer_and_default_keeps_lead_model():
    engine = create_discussion(specs(), bundle=RecordingBundle(),
                               experiment=ExperimentConfig(mechanisms={"analysis": False}))
    assert engine.analyzer is None
    bundle = RecordingBundle()
    create_discussion(specs(), bundle=bundle)
    assert (LLMProvider.CLAUDE, "m-agent", 0.0) in bundle.requests and (LLMProvider.CLAUDE, "m-agent", 0.7) in bundle.requests


# ---------- API ----------

BODY = {"topic": "Remote work mandates?", "max_statements": 6,
        "personas": [dict(name="Alice", **PERSONA), dict(name="Bob", **PERSONA)]}


@pytest.mark.asyncio
async def test_api_stores_experiment_and_runtime_applies_it(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", FakeBundle)
    admin = create_user(role="admin")
    experiment = {"label": "no-closing", "mechanisms": {"closing_round": False},
                  "participants": {"Bob": {"stubbornness": 0.8}}}
    async with LoggedInClient(admin) as client:
        r = await client.post("/api/v1/discussions", json={**BODY, "experiment": experiment})
        assert r.status_code == 201, r.text
        stored = r.json()["config"]["experiment"]
        assert stored["label"] == "no-closing" and stored["mechanisms"]["closing_round"] is False
        assert stored["participants"] == {"Bob": {"stubbornness": 0.8}}

        discussion_id = r.json()["id"]
        assert (await client.post(f"/api/v1/discussions/{discussion_id}/start")).status_code == 202
        await asyncio.wait_for(registry.get(discussion_id).task, timeout=10)
    actions = [m["action"] for m in persistence.list_messages_after(discussion_id, 0) if m["speaker_type"] == "ai"]
    assert len(actions) == 6 and "closing" not in actions


@pytest.mark.asyncio
async def test_api_validates_experiment():
    admin, user = create_user(role="admin"), create_user()
    async with LoggedInClient(user) as c_user, LoggedInClient(admin) as c_admin:
        r = await c_user.post("/api/v1/discussions", json={**BODY, "experiment": {"label": "x"}})
        assert r.status_code == 403 and r.json()["detail"]["error"]["code"] == "FEATURE_RESTRICTED"
        r = await c_admin.post("/api/v1/discussions",
                               json={**BODY, "experiment": {"participants": {"Carol": {"stubbornness": 0.5}}}})
        assert r.status_code == 400 and r.json()["detail"]["error"]["code"] == "UNKNOWN_PARTICIPANT"
        r = await c_admin.post("/api/v1/discussions", json={**BODY, "experiment": {"mechanisms": {"analysys": False}}})
        assert r.status_code == 422
        r = await c_admin.post("/api/v1/discussions", json=BODY)  # 조건 없이도 그대로 동작
        assert r.status_code == 201 and "experiment" not in r.json()["config"]
