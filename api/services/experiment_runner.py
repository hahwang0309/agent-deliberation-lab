"""
배치 실험 실행기 - 실험 계획(YAML)의 주제 × 조건 × 반복을 실험 DB에서 실행한다

- 토론은 웹과 같은 경로(DiscussionService.create → DiscussionRuntime.run)로 만들고 실행한다.
  그래서 저장 형식, 설문, 실행 기록, 보고서가 웹에서 만든 토론과 같다.
- 웹 사용자 제한(동시 실행, 일일 시작 수)과 서버 전체 동시 실행 수는 거치지 않고, 계획의 concurrency를 쓴다.
- 주제 1개가 집단 1개(블록)다. 같은 주제의 페르소나·초기 응답(seeds)·자료를 모든 조건에 그대로 복제하고,
  조건은 use_seeds·use_materials로 초기 응답과 자료를 쓸지 정한다(예: 토론 / 혼자 다시 답하기 / 사전 응답 없음).
- 실행 순서는 반복 → 주제 → 조건 순으로 섞어서, 시간에 따른 API 변화가 한 조건에 몰리지 않게 한다.
- 이미 완료된 (주제, 조건, 반복)은 건너뛴다(중단 후 이어 돌리기). 실패한 실행은 retries만큼 다시 시도한다.
- 누적 토큰(또는 가격을 주면 비용)이 상한을 넘을 것 같으면 새 실행을 시작하지 않는다.
"""
import asyncio
import logging
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.database import SessionLocal
from api.models.discussion import Discussion, DiscussionStatus
from api.models.user import User, UserRole, UserStatus
from api.runtime import broker, persistence
from api.runtime.runtime import DiscussionRuntime
from api.schemas.discussion import CreateDiscussionRequest, PersonaInput
from api.services.discussion_service import DiscussionService
from api.utils.security import hash_password
from src.services.survey import SeedValue, SurveyConfig

logger = logging.getLogger(__name__)

RUNNER_EMAIL = "experiment-runner@local.invalid"
TEMPLATES_PATH = Path(__file__).resolve().parents[2] / "config" / "persona_templates.yaml"
# 사전 추정용 대략치: 실측(Haiku 4.5, 2명·9발언·분석·설문·보고서 포함, 6회)에서
# 발언 1개당 입력 약 10,700 / 출력 약 1,530 토큰
ROUGH_INPUT_PER_STATEMENT, ROUGH_OUTPUT_PER_STATEMENT = 10700, 1530


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TopicPlan(_Strict):
    key: str = Field(..., pattern=r"^[A-Za-z0-9_\-]+$", max_length=100)
    topic: str
    description: Optional[str] = None
    language: Optional[str] = None
    max_statements: int = 9
    use_moderator: bool = True
    personas: List[Any] = Field(..., min_length=2, description="페르소나 dict 또는 persona_templates.yaml의 템플릿 id")
    propositions: Optional[List[str]] = None
    materials: Optional[str] = None
    materials_file: Optional[str] = None
    survey: Optional[SurveyConfig] = None
    seeds: Dict[str, Dict[str, SeedValue]] = Field(
        default_factory=dict, description="참가자 이름 → 심은 사전 설문 응답 (조건의 use_seeds가 켜졌을 때 씀)")


class ConditionPlan(_Strict):
    label: str = Field(..., max_length=100)
    experiment: Dict[str, Any] = Field(default_factory=dict)
    use_seeds: bool = Field(True, description="주제의 seeds를 참가자 초기 응답으로 심음")
    use_materials: bool = Field(True, description="주제의 배경 자료를 넣음")


class Limits(_Strict):
    max_total_tokens: Optional[int] = Field(None, ge=1, description="입력+출력 토큰 누적 상한")
    max_cost_usd: Optional[float] = Field(None, gt=0, description="prices가 있을 때 비용 상한")


class Prices(_Strict):
    """가격은 사용자가 확인한 값을 넣는다 (코드에 단가를 두지 않음)"""
    input_per_mtok: float = Field(..., ge=0)
    output_per_mtok: float = Field(..., ge=0)


class ExperimentPlan(_Strict):
    name: str = Field(..., pattern=r"^[A-Za-z0-9_\-]+$", max_length=100)
    repetitions: int = Field(1, ge=1, le=1000)
    concurrency: int = Field(2, ge=1, le=20)
    retries: int = Field(1, ge=0, le=5)
    topics: List[TopicPlan] = Field(..., min_length=1)
    conditions: List[ConditionPlan] = Field(..., min_length=1)
    limits: Limits = Field(default_factory=Limits)
    prices: Optional[Prices] = None

    @model_validator(mode="after")
    def check(self):
        if self.limits.max_cost_usd and not self.prices:
            raise ValueError("limits.max_cost_usd requires prices")
        for kind, keys in (("topic key", [t.key for t in self.topics]), ("condition label", [c.label for c in self.conditions])):
            if len(set(keys)) != len(keys):
                raise ValueError(f"duplicate {kind}")
        return self


def load_plan(path: str) -> ExperimentPlan:
    plan_path = Path(path)
    plan = ExperimentPlan(**yaml.safe_load(plan_path.read_text(encoding="utf-8")))
    for topic in plan.topics:  # 자료 파일은 계획 파일 기준 상대 경로
        if topic.materials_file:
            topic.materials = (plan_path.parent / topic.materials_file).read_text(encoding="utf-8")
    return plan


@dataclass
class Run:
    topic: TopicPlan
    condition: ConditionPlan
    replicate: int
    discussion_id: Optional[str] = None
    status: Optional[str] = None
    attempts: int = 0

    @property
    def key(self):
        return (self.topic.key, self.condition.label, self.replicate)


@dataclass
class BatchResult:
    completed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    skipped: int = 0
    not_started: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    stopped_by_limit: bool = False

    def cost(self, prices: Optional[Prices]) -> Optional[float]:
        if not prices:
            return None
        return (self.prompt_tokens * prices.input_per_mtok + self.completion_tokens * prices.output_per_mtok) / 1e6


def _personas(topic: TopicPlan) -> List[PersonaInput]:
    templates = yaml.safe_load(TEMPLATES_PATH.read_text(encoding="utf-8"))
    result = []
    for p in topic.personas:
        if isinstance(p, str):
            if p not in templates:
                raise ValueError(f"unknown persona template: {p}")
            result.append(PersonaInput(**{**templates[p], "template_id": p}))
        else:
            result.append(PersonaInput(**p))
    return result


def build_request(plan: ExperimentPlan, run: Run) -> CreateDiscussionRequest:
    t, c = run.topic, run.condition
    experiment = {**c.experiment, "label": c.label, "batch": plan.name,
                  "topic_key": t.key, "replicate": run.replicate}
    if c.use_seeds and t.seeds:
        participants = {name: dict(cond) for name, cond in (c.experiment.get("participants") or {}).items()}
        for name, seed in t.seeds.items():
            participants.setdefault(name, {})["seed"] = seed
        experiment["participants"] = participants
    return CreateDiscussionRequest(
        topic=t.topic, description=t.description, language=t.language, personas=_personas(t),
        max_statements=t.max_statements, use_moderator=t.use_moderator, propositions=t.propositions,
        materials=t.materials if c.use_materials else None, survey=t.survey, experiment=experiment)


def _rough_statements(run: Run) -> int:
    """대략치 계산용 발언 수. 토론 없는 조건은 설문 호출뿐이라 발언 1개 분량으로 잡는다"""
    return 1 if run.condition.experiment.get("mode") == "survey_only" else run.topic.max_statements


def plan_runs(plan: ExperimentPlan) -> List[Run]:
    """반복 → 주제 → 조건 순서 (조건이 시간대에 몰리지 않도록 교차)"""
    return [Run(t, c, r) for r in range(plan.repetitions) for t in plan.topics for c in plan.conditions]


def existing_runs(batch: str) -> Dict[tuple, Dict[str, Any]]:
    """이 배치에서 이미 만든 토론: (주제, 조건, 반복) → 가장 최근 토론의 상태·사용량"""
    found: Dict[tuple, Dict[str, Any]] = {}
    with SessionLocal() as db:
        for d in db.query(Discussion).order_by(Discussion.created_at, Discussion.id):
            exp = (d.config or {}).get("experiment") or {}
            if exp.get("batch") == batch:
                found[(exp.get("topic_key"), exp.get("label"), exp.get("replicate"))] = {
                    "id": d.id, "status": d.status, "prompt_tokens": d.prompt_tokens,
                    "completion_tokens": d.completion_tokens}
    return found


def runner_user() -> User:
    """배치 실행용 관리자 계정 (정지 상태라 로그인할 수 없음)"""
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == RUNNER_EMAIL).first()
        if user is None:
            user = User(email=RUNNER_EMAIL, name="experiment-runner", role=UserRole.ADMIN,
                        status=UserStatus.SUSPENDED, password_hash=hash_password(secrets.token_urlsafe(32)))
            db.add(user)
            db.commit()
            db.refresh(user)
        db.expunge(user)
        return user


def estimate(plan: ExperimentPlan, pending: List[Run], done: Dict[tuple, Dict[str, Any]]) -> Dict[str, Any]:
    """남은 실행의 토큰 추정. 같은 배치의 완료 실행이 있으면 그 평균, 없으면 발언 수 기반 대략치"""
    finished = [v for v in done.values() if v["status"] == DiscussionStatus.COMPLETED]
    if finished:
        per_in = sum(v["prompt_tokens"] for v in finished) / len(finished)
        per_out = sum(v["completion_tokens"] for v in finished) / len(finished)
        tokens_in, tokens_out, basis = per_in * len(pending), per_out * len(pending), f"완료 {len(finished)}건 평균"
    else:
        tokens_in = sum(ROUGH_INPUT_PER_STATEMENT * _rough_statements(r) for r in pending)
        tokens_out = sum(ROUGH_OUTPUT_PER_STATEMENT * _rough_statements(r) for r in pending)
        basis = "발언 수 기반 대략치"
    result = {"runs": len(pending), "input_tokens": int(tokens_in), "output_tokens": int(tokens_out), "basis": basis}
    if plan.prices:
        result["cost_usd"] = round((tokens_in * plan.prices.input_per_mtok + tokens_out * plan.prices.output_per_mtok) / 1e6, 2)
    return result


async def run_batch(plan: ExperimentPlan, runtime_factory: Callable[[str], DiscussionRuntime] = None,
                    on_progress: Callable[[str], None] = print) -> BatchResult:
    runtime_factory = runtime_factory or (lambda discussion_id: DiscussionRuntime(discussion_id, broker))
    done = existing_runs(plan.name)
    result = BatchResult()
    runs = []
    for run in plan_runs(plan):
        prev = done.get(run.key)
        if prev and prev["status"] == DiscussionStatus.COMPLETED:
            result.skipped += 1
        else:
            runs.append(run)
    for prev in done.values():  # 이전에 쓴 토큰도 상한에 포함
        result.prompt_tokens += prev["prompt_tokens"] or 0
        result.completion_tokens += prev["completion_tokens"] or 0

    user = runner_user()
    semaphore = asyncio.Semaphore(plan.concurrency)
    finished_usage: List[tuple] = []  # 이번 실행에서 끝난 토론의 (입력, 출력) 토큰

    def over_limit(run: Run) -> bool:
        """다음 실행 1건을 시작하면 상한을 넘을지 (끝난 실행 평균, 아직 없으면 발언 수 기반 대략치로 예측)"""
        if finished_usage:
            next_in = sum(u[0] for u in finished_usage) / len(finished_usage)
            next_out = sum(u[1] for u in finished_usage) / len(finished_usage)
        else:
            next_in = ROUGH_INPUT_PER_STATEMENT * _rough_statements(run)
            next_out = ROUGH_OUTPUT_PER_STATEMENT * _rough_statements(run)
        total_in, total_out = result.prompt_tokens + in_flight[0] + next_in, result.completion_tokens + in_flight[1] + next_out
        if plan.limits.max_total_tokens and total_in + total_out > plan.limits.max_total_tokens:
            return True
        if plan.limits.max_cost_usd and plan.prices:
            cost = (total_in * plan.prices.input_per_mtok + total_out * plan.prices.output_per_mtok) / 1e6
            return cost > plan.limits.max_cost_usd
        return False

    in_flight = [0.0, 0.0]  # 실행 중인 토론의 예측 토큰 (동시 실행이 한꺼번에 상한을 넘지 않도록)

    async def execute(run: Run) -> None:
        async with semaphore:
            while run.attempts <= plan.retries:
                if over_limit(run):
                    result.stopped_by_limit = True
                    result.not_started += 1
                    return
                reserve = (ROUGH_INPUT_PER_STATEMENT * _rough_statements(run),
                           ROUGH_OUTPUT_PER_STATEMENT * _rough_statements(run))
                in_flight[0] += reserve[0]
                in_flight[1] += reserve[1]
                run.attempts += 1
                try:
                    with SessionLocal() as db:
                        run.discussion_id = DiscussionService.create(db, build_request(plan, run), user).id
                    await runtime_factory(run.discussion_id).run()
                finally:
                    in_flight[0] -= reserve[0]
                    in_flight[1] -= reserve[1]
                usage = _usage(run.discussion_id)
                result.prompt_tokens += usage[0]
                result.completion_tokens += usage[1]
                finished_usage.append(usage)
                run.status = persistence.load_discussion(run.discussion_id)["status"]
                on_progress(f"[{run.condition.label} | {run.topic.key} | rep {run.replicate}] "
                            f"{run.discussion_id} {run.status} (attempt {run.attempts}, tokens {sum(usage)})")
                if run.status == DiscussionStatus.COMPLETED:
                    result.completed.append(run.discussion_id)
                    return
            result.failed.append(run.discussion_id)

    await asyncio.gather(*(execute(r) for r in runs))
    return result


def _usage(discussion_id: str):
    with SessionLocal() as db:
        d = db.get(Discussion, discussion_id)
        return d.prompt_tokens or 0, d.completion_tokens or 0
