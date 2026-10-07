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
    assert answers == [{"item_id": "q1", "score": 6, "reason": "data shows gains", "scale": 7},
                       {"item_id": "q2", "score": 2, "reason": "", "scale": 7}]
    assert "outside 1..7" in agent.prompts[-1] and "unknown item id qX" in agent.prompts[-1]

    stubborn = ScriptedSurveyAgent([[{"item_id": "q1", "score": 5}], [{"item_id": "q1", "score": 5}]])
    answers = await run_survey(stubborn, survey, "post", transcript="A: hello")
    assert answers[1] == {"item_id": "q2", "score": None, "reason": "", "scale": 7}  # 끝까지 답 안 함 → None
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
