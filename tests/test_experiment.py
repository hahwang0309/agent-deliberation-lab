"""
실험 조건 테스트 - 토론별 설정 사본, 진행 장치 on/off, 참가자별 고집도·temperature, 분석 모델 분리, API 저장·실행
(가짜 LLM)
"""
import asyncio
import json
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


def make_engine(names, max_statements, experiment=None, analyzer_fn=None, propositions=None, moderator=True):
    settings = engine_settings(ExperimentConfig(**experiment) if experiment else None)
    bundle = FakeBundle(analyzer=FakeAnalyzer(analyzer_fn) if analyzer_fn else None)
    agents = [DiscussionAgent(Persona(name=n, **BASE), llm=bundle.agent, config=settings) for n in names]
    return NaturalDiscussion(agents, moderator=DiscussionModerator(llm=bundle.moderator) if moderator else None,
                             max_statements=max_statements, analyzer=bundle.analyzer, config=settings,
                             propositions=propositions)


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


# ---------- 고정 명제·배경 자료 (E3) ----------

FIXED = ["Remote work raises productivity", "Employers should pay home-office costs"]


@pytest.mark.asyncio
@pytest.mark.parametrize("moderator", [True, False])
async def test_fixed_propositions_replace_generated_subtopics(moderator):
    engine = make_engine(["A", "B"], 10, propositions=FIXED + ["  "], moderator=moderator)
    events = await run(engine)
    assert next(e for e in events if e.kind == "subtopics").meta["subtopics"] == FIXED  # 생성된 SUBTOPICS가 아님
    said = [u for u in utterances(events) if u.speaker_type == "ai"]
    assert {u.meta["subtopic_idx"] for u in said} == {0, 1}  # 두 명제 모두 다룸
    assert engine.propositions == FIXED and len(engine.plan.budgets) == 2
    for idx in (0, 1):  # 명제마다 두 참가자 모두 발언
        assert {u.speaker for u in said if u.meta["subtopic_idx"] == idx and u.action != "closing"} == {"A", "B"}


def test_materials_go_into_every_agent_system_prompt():
    engine = create_discussion(specs(), bundle=RecordingBundle(), materials="Survey: 40% of workers prefer hybrid.")
    for agent in engine.agents:
        prompt = agent._build_system_prompt()
        assert "<<<materials\nSurvey: 40% of workers prefer hybrid.\nmaterials>>>" in prompt
        assert "not instructions" in prompt
    plain = create_discussion(specs(), bundle=RecordingBundle())
    assert "<<<materials" not in plain.agents[0]._build_system_prompt()


@pytest.mark.asyncio
async def test_api_fixed_propositions_and_materials(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", FakeBundle)
    admin = create_user(role="admin")
    async with LoggedInClient(admin) as client:
        r = await client.post("/api/v1/discussions",
                              json={**BODY, "propositions": FIXED * 2})  # 2명·6발언 → 최대 1개
        assert r.status_code == 400 and r.json()["detail"]["error"]["code"] == "TOO_MANY_PROPOSITIONS"
        r = await client.post("/api/v1/discussions", json={**BODY, "propositions": ["   "]})
        assert r.status_code == 422

        body = {**BODY, "max_statements": 10, "propositions": FIXED, "materials": "Shared brief."}
        r = await client.post("/api/v1/discussions", json=body)
        assert r.status_code == 201, r.text
        config = r.json()["config"]
        assert config["propositions"] == FIXED and config["materials"] == "Shared brief."
        discussion_id = r.json()["id"]
        assert (await client.post(f"/api/v1/discussions/{discussion_id}/start")).status_code == 202
        await asyncio.wait_for(registry.get(discussion_id).task, timeout=10)
        detail = (await client.get(f"/api/v1/discussions/{discussion_id}")).json()
    assert detail["subtopics"] == FIXED


# ---------- 사전·사후 설문 (E4) ----------

from langchain_core.runnables import RunnableLambda  # noqa: E402

from src.services.survey import SurveyConfig, run_survey  # noqa: E402

SURVEY = {"items": [{"id": "q1", "text": "Remote work raises productivity"},
                    {"id": "q2", "text": "Employers should pay home-office costs"}], "scale": 7}


class ScriptedSurveyAgent:
    """설문 응답을 차례로 돌려주는 최소 에이전트 (run_survey 단위 테스트용)"""

    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []
        self.persona = Persona(name="A", **BASE)
        outer = self

        class LLM:
            def with_structured_output(self, schema, **kwargs):
                def run(messages):
                    outer.prompts.append(messages[-1].content)
                    return schema(answers=outer.replies.pop(0))
                return RunnableLambda(run)
        self.llm = LLM()

    def _build_system_prompt(self):
        return "persona"


@pytest.mark.asyncio
async def test_run_survey_retries_invalid_answers_and_never_fills_missing():
    survey = SurveyConfig(**SURVEY)
    agent = ScriptedSurveyAgent([
        [{"item_id": "q1", "score": 9, "reason": "too high"}, {"item_id": "qX", "score": 3}],  # 범위 밖·없는 id
        [{"item_id": "q1", "score": 6, "reason": "  data shows gains "}, {"item_id": "q2", "score": 2}],
    ])
    answers = await run_survey(agent, survey, "pre")
    common = {"choices": None, "correct": None, "scale": 7, "scale_min": 1}
    assert answers == [{"item_id": "q1", "score": 6, "reason": "data shows gains", "source": "answered", **common},
                       {"item_id": "q2", "score": 2, "reason": "", "source": "answered", **common}]
    assert "integer in 1..7" in agent.prompts[-1] and "unknown item id 'qX' (valid ids: q1, q2)" in agent.prompts[-1]

    stubborn = ScriptedSurveyAgent([[{"item_id": "q1", "score": 5}], [{"item_id": "q1", "score": 5}]])
    answers = await run_survey(stubborn, survey, "post", transcript="A: hello")
    assert answers[1] == {"item_id": "q2", "score": None, "choices": None, "correct": None, "reason": "",
                          "scale": 7, "scale_min": 1, "source": "missing"}  # 끝까지 답 안 함 → 값 없음
    assert "A: hello" in stubborn.prompts[0]


@pytest.mark.asyncio
async def test_engine_runs_pre_survey_first_and_post_survey_last():
    bundle = FakeBundle()
    agents = [DiscussionAgent(Persona(name=n, **BASE), llm=bundle.agent) for n in ("A", "B")]
    engine = NaturalDiscussion(agents, moderator=DiscussionModerator(llm=bundle.moderator), max_statements=4,
                               analyzer=bundle.analyzer, survey=SurveyConfig(**SURVEY))
    events = await run(engine)
    kinds = [e.kind for e in events]
    surveys = [e for e in events if e.kind == "survey"]
    assert [(e.meta["phase"], e.speaker) for e in surveys] == [("pre", "A"), ("pre", "B"), ("post", "A"), ("post", "B")]
    assert kinds[:2] == ["survey", "survey"] and kinds[-2:] == ["survey", "survey"]
    assert all(a["score"] == 4 for e in surveys for a in e.meta["answers"])

    engine.restored = True  # 재개한 토론은 사전 설문을 다시 받지 않음
    engine.messages, engine.closing_started, engine.closing_done = [], True, ["A", "B"]
    again = [e for e in await run(engine) if e.kind == "survey"]
    assert {e.meta["phase"] for e in again} == {"post"}


@pytest.mark.asyncio
async def test_api_survey_is_stored_listed_and_deleted_with_discussion(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", FakeBundle)
    owner = create_user()
    async with LoggedInClient(owner) as client:
        r = await client.post("/api/v1/discussions", json={**BODY, "max_statements": 4, "survey": SURVEY})
        assert r.status_code == 201, r.text
        discussion_id = r.json()["id"]
        assert (await client.post(f"/api/v1/discussions/{discussion_id}/start")).status_code == 202
        await asyncio.wait_for(registry.get(discussion_id).task, timeout=10)

        data = (await client.get(f"/api/v1/discussions/{discussion_id}/survey")).json()
        assert data["survey"]["items"][0]["id"] == "q1"
        rows = data["responses"]
        assert len(rows) == 2 * 2 * 2  # 시점 × 참가자 × 문항
        assert {(r["phase"], r["participant"], r["item_id"]) for r in rows} == {
            (p, n, i) for p in ("pre", "post") for n in ("Alice", "Bob") for i in ("q1", "q2")}
        assert all(r["score"] == 4 and r["participant_type"] == "ai" for r in rows)

        r = await client.post("/api/v1/discussions", json={**BODY, "survey": {"items": [{"id": "q1", "text": "a"},
                                                                                       {"id": "q1", "text": "b"}]}})
        assert r.status_code == 422  # 중복 문항 id

        assert (await client.delete(f"/api/v1/discussions/{discussion_id}")).status_code == 204
    assert persistence.list_survey(discussion_id) == []


# ---------- 기준선 모드 (E2) ----------

@pytest.mark.asyncio
async def test_baseline_is_round_robin_reply_without_state_driven_moves():
    engine = make_engine(["A", "B", "C"], 12, analyzer_fn=challenge_fn, experiment={"mode": "baseline"})
    events = await run(engine)
    said = [u for u in utterances(events) if u.speaker_type == "ai"]
    assert [u.action for u in said] == ["reply"] * 9 + ["closing"] * 3  # 응답 의무·중재·반대 검토 없음
    assert [u.speaker for u in said[:9]] == ["A", "B", "C"] * 3          # 순서대로
    assert any(e.kind == "analysis" for e in events)                       # 분석은 측정용으로 계속 기록

    prompt = engine._build_prompt("topic", engine._baseline_turn("A"))
    assert "Continue the discussion" in prompt and "Arguments you have already made" not in prompt
    assert "Your current position" not in prompt and "acknowledged these points" not in prompt


@pytest.mark.asyncio
async def test_baseline_two_people_get_no_moderator_mediation_and_same_structure():
    events = await run(make_engine(["A", "B"], 10, analyzer_fn=challenge_fn, experiment={"mode": "baseline"}))
    assert not any(u.action == "mediation" for u in utterances(events))
    stateful = await run(make_engine(["A", "B"], 10, analyzer_fn=challenge_fn))
    # 비교 공정성: 명제·발언 수·종결 라운드는 같다
    count = lambda evs: sum(u.speaker_type == "ai" for u in utterances(evs))  # noqa: E731
    subtopics = lambda evs: next(e for e in evs if e.kind == "subtopics").meta["subtopics"]  # noqa: E731
    assert count(events) == count(stateful) == 10 and subtopics(events) == subtopics(stateful)
    assert ai_actions(events)[-2:] == ai_actions(stateful)[-2:] == ["closing", "closing"]


# ---------- 재현성 기록 (E6) ----------

from src.utils.run_info import PROMPT_FILES, collect_run_info  # noqa: E402


def test_collect_run_info_has_code_prompt_settings_and_models():
    engine = create_discussion(specs(), bundle=RecordingBundle(),
                               experiment=ExperimentConfig(agent_temperature=0.3, analyzer={"model": "m-judge"}))
    info = collect_run_info(engine.config, engine.llm_spec)
    assert info["git_commit"] and len(info["git_commit"]) == 40 and isinstance(info["git_dirty"], bool)
    assert set(info["prompt_hashes"]) == set(PROMPT_FILES) and all(info["prompt_hashes"].values())
    assert info["settings"]["agent_temperature"] == 0.3 and info["settings"]["engine_mode"] == "stateful"
    assert info["llm"]["participants"]["A"] == {"provider": "claude", "model": "m-agent", "temperature": 0.3}
    assert info["llm"]["analyzer"] == {"provider": "claude", "model": "m-judge", "temperature": 0.0}
    assert "langchain-core" in info["packages"]


@pytest.mark.asyncio
async def test_runtime_records_run_info_and_prompts_only_for_experiments(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", FakeBundle)
    admin = create_user(role="admin")
    async with LoggedInClient(admin) as client:
        ids = []
        for extra in ({"experiment": {"label": "exp", "mode": "baseline"}}, {}):
            r = await client.post("/api/v1/discussions", json={**BODY, "max_statements": 4, **extra})
            ids.append(r.json()["id"])
            assert (await client.post(f"/api/v1/discussions/{ids[-1]}/start")).status_code == 202
            await asyncio.wait_for(registry.get(ids[-1]).task, timeout=10)
        exp, plain = [(await client.get(f"/api/v1/discussions/{i}")).json() for i in ids]

    assert len(exp["run_info"]) == 1 and exp["run_info"][0]["resumed"] is False
    assert exp["run_info"][0]["settings"]["engine_mode"] == "baseline"
    assert plain["run_info"][0]["settings"]["engine_mode"] == "stateful"
    exp_ai = [m for m in persistence.list_messages_after(ids[0], 0) if m["speaker_type"] == "ai"]
    plain_ai = [m for m in persistence.list_messages_after(ids[1], 0) if m["speaker_type"] == "ai"]
    assert all("Continue the discussion" in m["meta"]["prompt"] for m in exp_ai if m["action"] == "reply")
    assert all("prompt" not in m["meta"] for m in plain_ai)


# ---------- 데이터 추출 (E7) ----------

import csv  # noqa: E402

from scripts.export_dataset import main as export_main  # noqa: E402
from src.services.experiment_export import TABLES, build_tables, coding_sample  # noqa: E402


def export_analyzer(messages):
    seq, speaker, context = analyzed(messages)
    other = {"Alice": "Bob", "Bob": "Alice"}[speaker]
    target = latest_by(context, other)
    if not target:
        return {"stance": 0.6 if speaker == "Alice" else -0.6, "claims": [f"{speaker} claim"]}
    return {"stance": 0.5 if speaker == "Alice" else -0.5, "claims": [f"{speaker} claim"],
            "targets": [{"seq": target, "speaker": other, "relation": "attack"}],
            "concessions": [{"to": other, "claim": "a fair point"}],
            "influence": [{"listener": other, "quality": 0.9, "novelty": 1, "value_match": 1, "credibility": 1, "receptive": 1}]}


async def run_labelled(client, label, n=1):
    ids = []
    for _ in range(n):
        r = await client.post("/api/v1/discussions", json={**BODY, "max_statements": 4, "survey": SURVEY,
                                                             "experiment": {"label": label}})
        ids.append(r.json()["id"])
        assert (await client.post(f"/api/v1/discussions/{ids[-1]}/start")).status_code == 202
        await asyncio.wait_for(registry.get(ids[-1]).task, timeout=10)
    return ids


@pytest.mark.asyncio
async def test_dataset_tables_api_and_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_module, "LLMBundle",
                        lambda callbacks=None: FakeBundle(analyzer=FakeAnalyzer(export_analyzer)))
    admin = create_user(role="admin")
    async with LoggedInClient(admin) as client:
        ids = await run_labelled(client, "export-test", n=2)
        api_tables = (await client.get(f"/api/v1/discussions/{ids[0]}/dataset")).json()

    tables = build_tables(persistence.export_bundle(ids[0]))
    assert api_tables == json.loads(json.dumps(tables))
    assert set(tables) == set(TABLES)
    d = tables["discussions"][0]
    assert d["label"] == "export-test" and d["mode"] == "stateful" and d["n_participants"] == 2 and d["git_commit"]
    ai = [u for u in tables["utterances"] if u["speaker_type"] == "ai"]
    assert len(ai) == 4 and all(u["analyzed"] for u in ai)
    assert tables["concessions"] and tables["attacks"] and tables["stances"]
    assert {m["kind"] for m in tables["moves"]} >= {"concession"}
    assert len(tables["surveys"]) == 2 * 2 * 2

    out = tmp_path / "ds"
    assert export_main(["--label", "export-test", "--out", str(out), "--coding-sample", "3", "--seed", "1"]) == 0
    with (out / "discussions.csv").open(encoding="utf-8-sig") as f:
        assert [r["discussion_id"] for r in csv.DictReader(f)] == ids  # label로 모은 두 토론
    with (out / "coding_blind.csv").open(encoding="utf-8-sig") as f:
        blind = list(csv.DictReader(f))
    with (out / "coding_key.csv").open(encoding="utf-8-sig") as f:
        key = list(csv.DictReader(f))
    assert len(blind) == len(key) == 3 and [b["sample_id"] for b in blind] == [k["sample_id"] for k in key]
    assert not any(c.startswith("llm_") for c in blind[0]) and all(b["code_concession"] == "" for b in blind)
    assert export_main(["--label", "no-such-label", "--out", str(tmp_path / "none")]) == 1


def test_coding_sample_is_reproducible_with_seed():
    bundle = {"discussion": {"id": "d1"}, "messages": [
        {"seq": i, "speaker": "A" if i % 2 else "B", "speaker_type": "ai", "content": f"m{i}", "action": "rebut",
         "meta": {"analysis": {"move": "rebut", "concessions": [], "targets": []}}} for i in range(1, 11)]}
    a, _ = coding_sample([bundle], 4, seed=3)
    b, _ = coding_sample([bundle], 4, seed=3)
    assert a == b and len(a) == 4 and all(row["previous"] for row in a if row["text"] != "m1")


# ---------- 배치 실행기 (E5) ----------

import subprocess  # noqa: E402
import sys  # noqa: E402

import yaml  # noqa: E402

from api.services.experiment_runner import (  # noqa: E402
    ExperimentPlan, build_request, existing_runs, plan_runs, run_batch)

PLAN = {
    "name": "batch-test", "repetitions": 2, "concurrency": 2,
    "topics": [{"key": "remote", "topic": "Remote work mandates?", "max_statements": 4,
                "personas": [dict(name="Alice", **PERSONA), "safety_researcher"], "survey": SURVEY}],
    "conditions": [{"label": "full", "experiment": {}}, {"label": "base", "experiment": {"mode": "baseline"}}],
}


def test_plan_validation_order_and_request():
    plan = ExperimentPlan(**PLAN)
    assert [(r.replicate, r.condition.label) for r in plan_runs(plan)] == [(0, "full"), (0, "base"), (1, "full"), (1, "base")]
    request = build_request(plan, plan_runs(plan)[1])
    assert request.personas[1].template_id == "safety_researcher" and request.personas[1].name == "Dr. Safety"
    exp = request.experiment
    assert (exp.label, exp.batch, exp.topic_key, exp.replicate, exp.mode) == ("base", "batch-test", "remote", 0, "baseline")
    with pytest.raises(ValidationError):  # 비용 상한에는 단가 필요
        ExperimentPlan(**{**PLAN, "limits": {"max_cost_usd": 1}})
    with pytest.raises(ValidationError):  # 조건 label 중복
        ExperimentPlan(**{**PLAN, "conditions": [{"label": "x"}, {"label": "x"}]})
    with pytest.raises(ValidationError):  # 알 수 없는 키
        ExperimentPlan(**{**PLAN, "repetition": 3})


@pytest.mark.asyncio
async def test_run_batch_runs_skips_completed_and_respects_token_limit(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", FakeBundle)
    plan = ExperimentPlan(**PLAN)
    lines = []
    result = await run_batch(plan, on_progress=lines.append)
    assert len(result.completed) == 4 and not result.failed and result.skipped == 0 and len(lines) == 4
    done = existing_runs("batch-test")
    assert set(done) == {("remote", c, r) for c in ("full", "base") for r in (0, 1)}
    assert all(v["status"] == "completed" for v in done.values())
    assert set(persistence.experiment_discussion_ids(batch="batch-test", label="base")) == {
        done[("remote", "base", 0)]["id"], done[("remote", "base", 1)]["id"]}

    again = await run_batch(plan, on_progress=lines.append)  # 이어 돌리기: 완료분은 건너뜀
    assert again.skipped == 4 and not again.completed and len(lines) == 4

    tight = ExperimentPlan(**{**PLAN, "name": "batch-limit", "limits": {"max_total_tokens": 1000}})
    limited = await run_batch(tight, on_progress=lines.append)  # 1회 예상치(발언 수 기반)가 이미 상한 초과
    assert limited.stopped_by_limit and limited.not_started == 4 and not limited.completed
    assert existing_runs("batch-limit") == {}


def test_run_experiment_cli_dry_run_uses_separate_db(tmp_path):
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text(yaml.safe_dump(PLAN, allow_unicode=True), encoding="utf-8")
    db = tmp_path / "exp" / "experiments.db"
    out = subprocess.run([sys.executable, "scripts/run_experiment.py", str(plan_file), "--db", str(db), "--dry-run"],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "= 4 runs, already completed 0" in out.stdout and '"basis": "발언 수 기반 대략치"' in out.stdout
    assert db.exists()  # 실험 DB가 따로 만들어지고 마이그레이션 적용됨
    missing = subprocess.run([sys.executable, "scripts/run_experiment.py", str(plan_file)], capture_output=True, text=True)
    assert missing.returncode != 0 and "--db" in missing.stderr  # 웹 DB에 섞이지 않도록 --db 필수


# ---------- 측정 신뢰도 (E8) ----------

from scripts.coding_agreement import main as agreement_main  # noqa: E402
from src.services.coding_agreement import coder_vs_coder, cohen_kappa, human_vs_llm  # noqa: E402
from src.services.experiment_export import repeat_scores, similarity  # noqa: E402


def test_repeat_scores_compare_only_with_same_speakers_earlier_claims():
    claims = lambda *cs: {"analysis": {"claims": list(cs)}}  # noqa: E731
    messages = [
        {"seq": 1, "speaker": "A", "speaker_type": "ai", "meta": claims("오판으로 집행된 사형은 되돌릴 수 없다")},
        {"seq": 2, "speaker": "B", "speaker_type": "ai", "meta": claims("오판으로 집행된 사형은 되돌릴 수 없다")},
        {"seq": 3, "speaker": "A", "speaker_type": "ai", "meta": claims("오판으로 집행된 사형은 결코 되돌릴 수 없다")},
        {"seq": 4, "speaker": "A", "speaker_type": "ai", "meta": claims("피해자 지원 예산을 늘려야 한다")},
    ]
    scores = repeat_scores(messages)
    assert 1 not in scores and 2 not in scores  # 화자의 첫 발언은 비교 대상 없음 (B는 A와 비교하지 않음)
    assert scores[3] >= 0.7 and scores[4] < 0.2
    assert similarity("abc", "abc") == 1.0 and similarity("", "abc") == 0.0


def test_cohen_kappa_and_agreement_reports():
    assert cohen_kappa([1, 1, 0, 0], [1, 0, 0, 0]) == 0.5
    assert cohen_kappa([1, 1], [1, 1]) is None  # 한 범주만 나오면 정의되지 않음
    coded = [{"sample_id": "S1", "code_concession": "예", "code_responds_to_previous": "1", "code_justification_level": "2",
              "code_respect_level": "1"},
             {"sample_id": "S2", "code_concession": "no", "code_responds_to_previous": "0", "code_justification_level": "",
              "code_respect_level": "2"},
             {"sample_id": "S3", "code_concession": "", "code_responds_to_previous": "1", "code_justification_level": "1",
              "code_respect_level": "1"}]
    key = [{"sample_id": "S1", "llm_concession": "True"}, {"sample_id": "S2", "llm_concession": "True"},
           {"sample_id": "S3", "llm_concession": "False"}]
    result = human_vs_llm(coded, key)["concession"]
    assert result["n"] == 2 and result["agreement"] == 0.5  # 빈칸(S3) 제외
    second = [dict(r, code_justification_level="2") for r in coded]
    inter = coder_vs_coder(coded, second)
    assert inter["code_concession"]["agreement"] == 1.0 and inter["code_justification_level"]["n"] == 2


def test_coding_agreement_cli(tmp_path, capsys):
    rows = [{"sample_id": "S1", "code_concession": "1"}, {"sample_id": "S2", "code_concession": "0"}]
    key = [{"sample_id": "S1", "llm_concession": "True"}, {"sample_id": "S2", "llm_concession": "False"}]
    for name, data in (("coded.csv", rows), ("key.csv", key)):
        with (tmp_path / name).open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
    assert agreement_main(["--coded", str(tmp_path / "coded.csv"), "--key", str(tmp_path / "key.csv")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["human_vs_llm"]["concession"]["agreement"] == 1.0


def test_repetition_is_coded_and_compared_with_lexical_proxy():
    claims = lambda c: {"analysis": {"claims": [c], "concessions": [], "targets": []}}  # noqa: E731
    bundle = {"discussion": {"id": "d1"}, "messages": [
        {"seq": 1, "speaker": "A", "speaker_type": "ai", "content": "first", "action": "position",
         "meta": claims("오판으로 집행된 사형은 되돌릴 수 없다")},
        {"seq": 2, "speaker": "A", "speaker_type": "ai", "content": "second", "action": "rebut",
         "meta": claims("오판으로 집행된 사형은 결코 되돌릴 수 없다")}]}
    blind, key = coding_sample([bundle], 2, seed=0)
    second = next(b for b in blind if b["text"] == "second")
    assert second["own_earlier"] == "first" and second["code_repeats_own_argument"] == ""
    k = next(k for k in key if k["sample_id"] == second["sample_id"])
    assert k["repeat_score"] >= 0.7
    coded = [dict(second, code_repeats_own_argument="예")]
    assert human_vs_llm(coded, key)["repeats_own_argument"] == {"n": 1, "agreement": 1.0, "kappa": None,
                                                               "confusion": {"True/True": 1}}


# ---------- 최신 모델 호환 (E9) ----------

from langchain_core.messages import AIMessage  # noqa: E402

from src.utils.llm_provider import LLMFactory, structured_output  # noqa: E402


def test_fixed_sampling_models_get_no_temperature_and_json_schema(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert not LLMFactory.supports_temperature(LLMProvider.CLAUDE, "claude-sonnet-5-5")
    assert not LLMFactory.supports_temperature(LLMProvider.CLAUDE, "claude-fable-5-1")
    assert LLMFactory.supports_temperature(LLMProvider.CLAUDE, "claude-haiku-4-5-20251001")
    assert LLMFactory.effective_temperature(LLMProvider.CLAUDE, "claude-sonnet-5-5", 0.0) is None
    assert LLMFactory.create_llm(LLMProvider.CLAUDE, model="claude-sonnet-5-5", temperature=0.3).temperature is None
    assert LLMFactory.create_llm(LLMProvider.CLAUDE, model="claude-haiku-4-5-20251001", temperature=0.3).temperature == 0.3

    class Recorder:
        def __init__(self, model):
            self.model, self.kwargs = model, None

        def with_structured_output(self, schema, **kwargs):
            self.kwargs = kwargs
            return self
    sonnet, haiku = Recorder("claude-sonnet-5-5"), Recorder("claude-haiku-4-5-20251001")
    structured_output(sonnet, dict), structured_output(haiku, dict)
    assert sonnet.kwargs == {"method": "json_schema"} and haiku.kwargs == {}


def test_run_record_shows_model_default_temperature():
    specs_ = [ParticipantSpec(Persona(name="A", **BASE), LLMProvider.CLAUDE, "claude-sonnet-5-5"),
              ParticipantSpec(Persona(name="B", **BASE), LLMProvider.CLAUDE, "claude-haiku-4-5-20251001")]
    engine = create_discussion(specs_, bundle=RecordingBundle())
    assert engine.llm_spec["participants"]["A"]["temperature"] is None  # 모델 기본값
    assert engine.llm_spec["participants"]["B"]["temperature"] == 0.7
    assert engine.llm_spec["analyzer"]["temperature"] is None  # 분석 모델 = 첫 참가자(Sonnet 5.5)


@pytest.mark.asyncio
async def test_agent_reads_only_text_blocks_from_thinking_responses():
    class Thinking:
        async def ainvoke(self, messages):
            return AIMessage(content=[{"type": "thinking", "thinking": "secret plan", "signature": "s"},
                                      {"type": "text", "text": "Visible answer."}])
    agent = DiscussionAgent(Persona(name="A", **BASE), llm=Thinking())
    assert await agent.respond("hi") == "Visible answer."


# ---------- 설문 확장: 선택형·0~10 척도·초기값 심기 ----------

from src.services.survey import initial_position_text, validate_seed  # noqa: E402

WASON = {"items": [{"id": "cards", "type": "choice", "multi": True, "options": ["E", "K", "4", "7"],
                    "correct": ["E", "7"],
                    "text": 'Which cards should you turn to test the rule: "All cards with vowels on one side '
                            'have an even number on the other"?'}]}
POLICY = {"items": [{"id": "Q5A", "text": "The Affordable Care Act should be repealed."}], "scale": 10, "scale_min": 0}


@pytest.mark.parametrize("bad", [
    {"items": [{"id": "c", "type": "choice", "options": ["A"]}]},                              # 보기 1개
    {"items": [{"id": "c", "type": "choice", "options": ["A", "B"], "correct": ["C"]}]},       # 보기에 없는 정답
    {"items": [{"id": "c", "type": "choice", "options": ["A", "B"], "correct": ["A", "B"]}]},  # 단일 선택인데 정답 2개
    {"items": [{"id": "q", "text": "x", "options": ["A", "B"]}]},                               # likert에 보기
    {"items": [{"id": "q", "text": "x"}], "scale": 2, "scale_min": 1},                          # 2점 척도
])
def test_survey_rejects_malformed_items(bad):
    bad = {"items": [{"text": "t", **i} if "text" not in i else i for i in bad["items"]],
           **{k: v for k, v in bad.items() if k != "items"}}
    with pytest.raises(ValidationError):
        SurveyConfig(**bad)


@pytest.mark.asyncio
async def test_choice_answers_are_matched_scored_and_retried():
    survey = SurveyConfig(**WASON)
    agent = ScriptedSurveyAgent([
        [{"item_id": "cards", "choices": ["e", "Q"]}],            # 없는 보기 → 다시 묻기
        [{"item_id": "cards", "choices": ["7", "e"], "reason": "falsify"}],  # 대소문자·순서 무관
    ])
    [row] = await run_survey(agent, survey, "post")
    assert row["choices"] == ["E", "7"] and row["correct"] is True and row["score"] is None
    assert "unknown options ['Q']" in agent.prompts[-1] and "Choose all that apply from: E, K, 4, 7" in agent.prompts[0]

    wrong = ScriptedSurveyAgent([[{"item_id": "cards", "choices": ["E", "4"]}]])
    [row] = await run_survey(wrong, survey, "post")
    assert row["correct"] is False  # 확증 편향의 전형적 오답


@pytest.mark.asyncio
async def test_zero_to_ten_scale_accepts_zero_and_rejects_eleven():
    survey = SurveyConfig(**POLICY)
    agent = ScriptedSurveyAgent([[{"item_id": "Q5A", "score": 11}], [{"item_id": "Q5A", "score": 0}]])
    [row] = await run_survey(agent, survey, "pre")
    assert row["score"] == 0 and row["scale_min"] == 0 and row["scale"] == 10
    assert "integer in 0..10" in agent.prompts[-1] and "from 0 (strongly disagree" in agent.prompts[0]


@pytest.mark.asyncio
async def test_seeded_items_are_recorded_without_asking():
    survey = SurveyConfig(**WASON)
    agent = ScriptedSurveyAgent([])  # 호출되면 pop에서 실패
    [row] = await run_survey(agent, survey, "pre", seeded={"cards": ["E", "4"]})
    assert row["source"] == "seeded" and row["choices"] == ["E", "4"] and row["correct"] is False
    assert agent.prompts == []

    assert validate_seed(survey, {"cards": ["E", "X"]}) and validate_seed(survey, {"other": 3})
    assert validate_seed(SurveyConfig(**POLICY), {"Q5A": 11}) and not validate_seed(SurveyConfig(**POLICY), {"Q5A": 10})
    text = initial_position_text(SurveyConfig(**POLICY), {"Q5A": 8})
    assert "Your answer: 8 (on a scale from 0 to 10)" in text and "The Affordable Care Act" in text


@pytest.mark.asyncio
async def test_engine_uses_seed_for_pre_survey_and_system_prompt(monkeypatch):
    bundle = FakeBundle()
    exp = ExperimentConfig(participants={"A": {"seed": {"cards": ["E", "4"]}}})
    engine = create_discussion(specs(), bundle=bundle, experiment=exp, survey=SurveyConfig(**WASON), max_statements=4)
    a, b = engine.agents
    assert "Your answer: E, 4." in a._build_system_prompt() and "Your answer" not in b._build_system_prompt()
    events = [e async for e in engine.stream("Wason task", language="en") if e.kind == "survey"]
    pre = {e.speaker: e.meta["answers"][0] for e in events if e.meta["phase"] == "pre"}
    assert pre["A"]["source"] == "seeded" and pre["B"]["source"] in ("answered", "missing")
    assert all(e.meta["answers"][0]["source"] != "seeded" for e in events if e.meta["phase"] == "post")


@pytest.mark.asyncio
async def test_api_validates_and_stores_seeded_choice_answers(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", FakeBundle)
    admin = create_user(role="admin")
    seed_exp = {"participants": {"Alice": {"seed": {"cards": ["E", "4"]}}}}
    async with LoggedInClient(admin) as client:
        r = await client.post("/api/v1/discussions", json={**BODY, "experiment": seed_exp})
        assert r.status_code == 400 and r.json()["detail"]["error"]["code"] == "SEED_WITHOUT_SURVEY"
        bad = {"participants": {"Alice": {"seed": {"cards": ["Z"]}}}}
        r = await client.post("/api/v1/discussions", json={**BODY, "survey": WASON, "experiment": bad})
        assert r.status_code == 422 and r.json()["detail"]["error"]["code"] == "INVALID_SEED"

        r = await client.post("/api/v1/discussions", json={**BODY, "max_statements": 4, "survey": WASON,
                                                         "experiment": seed_exp})
        assert r.status_code == 201, r.text
        discussion_id = r.json()["id"]
        assert (await client.post(f"/api/v1/discussions/{discussion_id}/start")).status_code == 202
        await asyncio.wait_for(registry.get(discussion_id).task, timeout=10)
    rows = {(r["phase"], r["participant"]): r for r in persistence.list_survey(discussion_id)}
    assert rows[("pre", "Alice")]["source"] == "seeded" and rows[("pre", "Alice")]["choices"] == ["E", "4"]
    assert rows[("pre", "Alice")]["correct"] is False


# ---------- 토론 없는 조건과 집단 복제 ----------

import src.core.natural_discussion as engine_module  # noqa: E402
from config.config_loader import config_loader  # noqa: E402


@pytest.mark.asyncio
async def test_survey_only_mode_asks_pre_then_alone_without_discussion(monkeypatch):
    calls = []
    original = engine_module.run_survey

    async def spy(agent, survey, phase, transcript="", seeded=None, prompt_key=None, **kw):
        calls.append((agent.persona.name, phase, prompt_key, transcript))
        return await original(agent, survey, phase, transcript, seeded=seeded, prompt_key=prompt_key, **kw)
    monkeypatch.setattr(engine_module, "run_survey", spy)

    bundle = FakeBundle()
    exp = ExperimentConfig(mode="survey_only", participants={"A": {"seed": {"q1": 6}}})
    engine = create_discussion(specs(), bundle=bundle, experiment=exp, survey=SurveyConfig(**SURVEY), max_statements=4)
    events = await run(engine)
    assert [e.kind for e in events] == ["survey"] * 4 and not engine.messages
    assert sorted((n, p, k) for n, p, k, _ in calls) == [
        ("A", "post", "post_alone"), ("A", "pre", None), ("B", "post", "post_alone"), ("B", "pre", None)]
    assert all(t == "" for *_, t in calls)
    pre_a = next(e for e in events if e.speaker == "A" and e.meta["phase"] == "pre").meta["answers"]
    assert [(a["item_id"], a["source"], a["score"]) for a in pre_a] == [("q1", "seeded", 6), ("q2", "answered", 4)]
    assert "There is no discussion" in config_loader.prompts.render("survey.post_alone", items="x")


@pytest.mark.asyncio
async def test_api_survey_only_requires_survey_and_completes_without_report(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", FakeBundle)
    admin = create_user(role="admin")
    async with LoggedInClient(admin) as client:
        r = await client.post("/api/v1/discussions", json={**BODY, "experiment": {"mode": "survey_only"}})
        assert r.status_code == 400 and r.json()["detail"]["error"]["code"] == "SURVEY_REQUIRED"
        r = await client.post("/api/v1/discussions", json={**BODY, "survey": SURVEY,
                                                         "experiment": {"mode": "survey_only"}})
        discussion_id = r.json()["id"]
        assert (await client.post(f"/api/v1/discussions/{discussion_id}/start")).status_code == 202
        await asyncio.wait_for(registry.get(discussion_id).task, timeout=10)
        assert (await client.get(f"/api/v1/discussions/{discussion_id}")).json()["status"] == "completed"
        assert (await client.get(f"/api/v1/discussions/{discussion_id}/report")).status_code == 404
    rows = persistence.list_survey(discussion_id)
    assert len(rows) == 2 * 2 * 2 and not persistence.list_messages_after(discussion_id)


CLONE_PLAN = {
    "name": "clone-test", "repetitions": 1,
    "topics": [{"key": "g1", "topic": "Remote work mandates?", "max_statements": 4, "materials": "Brief.",
                "personas": [dict(name="Alice", **PERSONA), dict(name="Bob", **PERSONA)], "survey": SURVEY,
                "seeds": {"Alice": {"q1": 2}, "Bob": {"q1": 6}}}],
    "conditions": [
        {"label": "discuss", "experiment": {"mode": "baseline", "participants": {"Bob": {"temperature": 0.3}}}},
        {"label": "alone", "experiment": {"mode": "survey_only"}, "use_materials": False},
        {"label": "prior", "experiment": {"mode": "survey_only"}, "use_seeds": False, "use_materials": False},
    ],
}


def test_same_group_is_cloned_across_conditions_with_seed_and_materials_switches():
    plan = ExperimentPlan(**CLONE_PLAN)
    discuss, alone, prior = (build_request(plan, r) for r in plan_runs(plan))
    assert [p.name for p in discuss.personas] == [p.name for p in alone.personas] == [p.name for p in prior.personas]
    assert discuss.materials == "Brief." and alone.materials is None and prior.materials is None
    assert discuss.experiment.participants["Bob"].seed == {"q1": 6}
    assert discuss.experiment.participants["Bob"].temperature == 0.3       # 조건의 참가자 설정과 합침
    assert alone.experiment.participants["Alice"].seed == {"q1": 2}
    assert prior.experiment.participants == {}
    assert CLONE_PLAN["conditions"][0]["experiment"]["participants"] == {"Bob": {"temperature": 0.3}}  # 원본 불변


@pytest.mark.asyncio
async def test_run_batch_with_survey_only_conditions(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", FakeBundle)
    result = await run_batch(ExperimentPlan(**CLONE_PLAN), on_progress=lambda _: None)
    assert len(result.completed) == 3 and not result.failed
    done = existing_runs("clone-test")
    seeded = {r["participant"]: r["source"] for r in persistence.list_survey(done[("g1", "alone", 0)]["id"])
              if r["phase"] == "pre" and r["item_id"] == "q1"}
    assert seeded == {"Alice": "seeded", "Bob": "seeded"}
    unseeded = {r["source"] for r in persistence.list_survey(done[("g1", "prior", 0)]["id"]) if r["phase"] == "pre"}
    assert unseeded == {"answered"}


# ---------- 정해진 발언(공모자)과 고정 발언 순서 ----------

def three_specs():
    return [ParticipantSpec(Persona(name=n, **BASE), LLMProvider.CLAUDE, "m-agent") for n in ("T", "C1", "C2")]


SCRIPTED = {"mode": "baseline", "mechanisms": {"closing_round": False},
            "turn_order": ["C1", "C2", "T"],
            "participants": {"C1": {"script": ["Strong argument one."]},
                             "C2": {"script": ["Same argument again.", "Second line."]}}}


@pytest.mark.parametrize("bad", [
    {"turn_order": ["A"]},                                                      # stateful에는 고정 순서 없음
    {"participants": {"A": {"script": ["x"]}}},                                 # stateful에는 정해진 발언 없음
    {"mode": "baseline", "participants": {"A": {"script": [""]}}},              # 빈 줄
    {"mode": "baseline", "participants": {"A": {"script": ["x"], "seed": {"q1": 3}}}},  # 공모자에게 초기 응답
])
def test_script_and_turn_order_validation(bad):
    with pytest.raises(ValidationError):
        ExperimentConfig(**bad)


@pytest.mark.asyncio
async def test_scripted_confederates_follow_fixed_order_and_skip_surveys():
    bundle = FakeBundle()
    engine = create_discussion(three_specs(), bundle=bundle, experiment=ExperimentConfig(**SCRIPTED),
                               survey=SurveyConfig(**SURVEY), max_statements=6)
    events = await run(engine)
    said = [(e.speaker, e.content, e.meta.get("scripted", False)) for e in events
            if e.kind == "utterance" and e.speaker_type == "ai"]
    assert [s for s, *_ in said] == ["C1", "C2", "T", "C2", "T", "T"]  # 대본을 다 쓴 C1은 건너뜀
    assert said[0][1:] == ("Strong argument one.", True) and said[3][1:] == ("Second line.", True)
    assert not said[2][2] and "prompt" not in next(e for e in events if e.speaker == "C1" and e.kind == "utterance").meta
    assert {e.speaker for e in events if e.kind == "survey"} == {"T"}


@pytest.mark.asyncio
async def test_closing_round_skips_confederates_whose_script_ran_out():
    exp = {**SCRIPTED, "mechanisms": {}}
    engine = create_discussion(three_specs(), bundle=FakeBundle(), experiment=ExperimentConfig(**exp), max_statements=9)
    said = [(e.speaker, e.action) for e in await run(engine) if e.kind == "utterance" and e.speaker_type == "ai"]
    assert [s for s, a in said if a == "closing"] == ["T"]  # 대본을 다 쓴 C1·C2는 마무리 없이 끝
    assert [s for s, a in said if a != "closing"] == ["C1", "C2", "T", "C2", "T", "T"]


def test_restore_resumes_script_and_turn_order_position():
    from src.models.personas import Message
    engine = create_discussion(three_specs(), bundle=FakeBundle(), experiment=ExperimentConfig(**SCRIPTED),
                               max_statements=6)
    prior = [Message(role="assistant", content=c, agent_name=n,
                     metadata={"seq": i + 1, "action": "reply", "speaker_type": "ai"})
             for i, (n, c) in enumerate([("C1", "Strong argument one."), ("C2", "Same argument again."), ("T", "ok")])]
    engine.restore(prior)
    assert engine._agent("C2").script_pos == 1 and not engine._agent("C1").can_speak()
    assert engine.order_pos == 3 and engine._baseline_turn("T").speaker.persona.name == "C2"


@pytest.mark.asyncio
async def test_api_rejects_turn_order_with_unknown_names():
    admin = create_user(role="admin")
    async with LoggedInClient(admin) as client:
        r = await client.post("/api/v1/discussions", json={**BODY, "experiment": {"mode": "baseline",
                                                                               "turn_order": ["Alice", "Zed"]}})
        assert r.status_code == 400 and r.json()["detail"]["error"]["code"] == "UNKNOWN_PARTICIPANT"


# ---------- 보고서 끄기, 실행 기록 보강, OpenAI 호환 서버 ----------

@pytest.mark.asyncio
async def test_report_off_skips_report_and_run_info_has_params_and_prompt_hashes(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", FakeBundle)
    admin = create_user(role="admin")
    async with LoggedInClient(admin) as client:
        ids = {}
        for report in (False, True):
            r = await client.post("/api/v1/discussions", json={**BODY, "materials": "Brief.",
                                                             "experiment": {"report": report}})
            ids[report] = r.json()["id"]
            assert (await client.post(f"/api/v1/discussions/{ids[report]}/start")).status_code == 202
            await asyncio.wait_for(registry.get(ids[report]).task, timeout=10)
        assert (await client.get(f"/api/v1/discussions/{ids[False]}/report")).status_code == 404
        assert (await client.get(f"/api/v1/discussions/{ids[True]}/report")).status_code == 200
        detail = (await client.get(f"/api/v1/discussions/{ids[False]}")).json()
    assert detail["status"] == "completed"
    info = detail["run_info"][0]
    assert info["llm_params"]["max_tokens"] == 1500 and info["llm_params"]["top_p"] is None
    hashes = info["llm"]["system_prompts"]
    assert set(hashes) == {"Alice", "Bob"} and all(len(h) == 16 for h in hashes.values())


def test_plan_level_report_off_and_condition_override():
    plan = ExperimentPlan(**{**PLAN, "report": False,
                             "conditions": [{"label": "a"}, {"label": "b", "experiment": {"report": True}}]})
    a, b = (build_request(plan, r).experiment for r in plan_runs(plan)[:2])
    assert a.report is False and b.report is True


def test_openai_base_url_allows_local_server_without_key(monkeypatch):
    from src.utils.llm_provider import LLMFactory
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:8080/v1")
    llm = LLMFactory.create_llm(LLMProvider.OPENAI, model="mistral-7b-instruct-v0.3", temperature=0.7)
    assert str(llm.openai_api_base).startswith("http://127.0.0.1:8080") and llm.model_name == "mistral-7b-instruct-v0.3"
    assert LLMFactory.get_available_providers()[LLMProvider.OPENAI]
    monkeypatch.delenv("OPENAI_BASE_URL")
    with pytest.raises(ValueError):
        LLMFactory.create_llm(LLMProvider.OPENAI, model="x")


@pytest.mark.asyncio
async def test_empty_structured_output_is_retried_not_crashing():
    """모델이 구조화 출력 없이(None) 답해도 설문은 다시 묻고, 끝까지 없으면 missing으로 남긴다"""
    agent = ScriptedSurveyAgent([])
    calls = []

    class NoneLLM:
        def with_structured_output(self, schema, **kwargs):
            return RunnableLambda(lambda messages: calls.append(1))  # 항상 None
    agent.llm = NoneLLM()
    rows = await run_survey(agent, SurveyConfig(**SURVEY), "pre")
    assert len(calls) == 2 and {r["source"] for r in rows} == {"missing"}


@pytest.mark.asyncio
async def test_survey_with_no_answers_at_all_fails_the_run(monkeypatch):
    """모델 호출이 전부 실패해 응답이 하나도 없으면 완료가 아니라 실패로 남는다 (배치 실행기가 다시 시도)"""
    async def nothing(agent, survey, phase, transcript="", seeded=None, prompt_key=None, **kw):
        return [{"item_id": i.id, "source": "seeded" if seeded and i.id in seeded else "missing"} for i in survey.items]
    monkeypatch.setattr(engine_module, "run_survey", nothing)
    engine = create_discussion(specs(), bundle=FakeBundle(), experiment=ExperimentConfig(mode="survey_only"),
                               survey=SurveyConfig(**SURVEY), max_statements=4)
    with pytest.raises(engine_module.SurveyFailed):
        await run(engine)


def test_seed_wording_neutral_has_no_hold_instruction():
    hold = create_discussion(specs(), bundle=FakeBundle(), survey=SurveyConfig(**SURVEY),
                             experiment=ExperimentConfig(participants={"A": {"seed": {"q1": 6}}}))
    neutral = create_discussion(specs(), bundle=FakeBundle(), survey=SurveyConfig(**SURVEY),
                                experiment=ExperimentConfig(seed_wording="neutral", participants={"A": {"seed": {"q1": 6}}}))
    assert "hold it as your view" in hold.agents[0].initial_position
    assert "hold it as your view" not in neutral.agents[0].initial_position
    assert "Your answer: 6" in neutral.agents[0].initial_position


@pytest.mark.asyncio
async def test_survey_accepts_bracketed_item_id_and_lists_valid_ids_on_retry():
    survey = SurveyConfig(**SURVEY)
    agent = ScriptedSurveyAgent([
        [{"item_id": "[q1] Remote work raises productivity", "score": 5}, {"item_id": "q2_costs", "score": 3}],
        [{"item_id": "q2", "score": 3}],
    ])
    rows = {r["item_id"]: r for r in await run_survey(agent, survey, "pre")}
    assert rows["q1"]["score"] == 5 and rows["q2"]["score"] == 3
    assert "unknown item id 'q2_costs' (valid ids: q1, q2)" in agent.prompts[-1]
