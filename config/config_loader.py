"""
설정 로더 모듈
YAML 파일에서 설정과 프롬프트를 로드하고 관리
"""
import yaml
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, fields

from config.discussion_config import DiscussionConfig


def _strict(cls, data: Dict[str, Any], section: str):
    """YAML 섹션을 dataclass로. 빠진 항목·모르는 항목은 오류 (코드에 기본값을 두지 않음)"""
    names = {f.name for f in fields(cls)}
    data = data or {}
    missing, unknown = names - set(data), set(data) - names
    if missing or unknown:
        raise ValueError(f"config.yaml [{section}]: missing {sorted(missing)}, unknown {sorted(unknown)}")
    return cls(**data)


@dataclass
class LLMConfig:
    """LLM 설정 (모델명은 default_models에만 둔다)"""
    default_provider: str
    default_models: Dict[str, str]
    fixed_sampling_prefixes: List[str]
    json_schema_prefixes: List[str]
    temperature: float
    task_temperatures: Dict[str, float]
    max_tokens: int
    structured_max_tokens: int
    timeout_seconds: float
    max_retries: int


@dataclass
class PersonaGenerationConfig:
    max_attempts: int


@dataclass
class SurveySettings:
    """사전·사후 설문 실행 설정 (문항 형식은 src/services/survey.py의 SurveyConfig)"""
    transcript_chars: int
    max_attempts: int


@dataclass
class AnalysisConfig:
    repeat_threshold: float
    min_shift: float


@dataclass
class RunnerConfig:
    rough_input_per_statement: int
    rough_output_per_statement: int


@dataclass
class LimitsConfig:
    """API 토론 실행 제한"""
    max_global_running: int
    default_statements: int
    max_statements: int
    min_personas: int
    max_personas: int
    user_max_concurrent: int
    user_daily_starts: int
    user_expensive_features: bool
    max_human_turns_per_user: int
    max_human_chars: int


@dataclass
class ReportConfig:
    """종합보고서 설정"""
    model: Optional[str]
    temperature: float
    max_tokens: int
    max_attempts: int
    min_ai_messages: int
    partial_weight: float
    agreed_threshold: float
    partial_threshold: float


@dataclass
class AppConfig:
    """전체 애플리케이션 설정 (config/config.yaml)"""
    llm: LLMConfig
    persona_generation: PersonaGenerationConfig
    engine: DiscussionConfig
    survey: SurveySettings
    analysis: AnalysisConfig
    experiment_runner: RunnerConfig
    limits: LimitsConfig
    report: ReportConfig

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        sections = {f.name: f.type for f in fields(cls)}
        unknown = set(data) - set(sections)
        if unknown:
            raise ValueError(f"config.yaml: unknown sections {sorted(unknown)}")
        report = dict(data.get("report") or {})
        thresholds = report.pop("thresholds", {}) or {}
        report.update(agreed_threshold=thresholds.get("agreed"), partial_threshold=thresholds.get("partial"))
        if None in (report["agreed_threshold"], report["partial_threshold"]):
            raise ValueError("config.yaml [report.thresholds]: agreed and partial are required")
        return cls(
            llm=_strict(LLMConfig, data.get("llm"), "llm"),
            persona_generation=_strict(PersonaGenerationConfig, data.get("persona_generation"), "persona_generation"),
            engine=_strict(DiscussionConfig, data.get("engine"), "engine"),
            survey=_strict(SurveySettings, data.get("survey"), "survey"),
            analysis=_strict(AnalysisConfig, data.get("analysis"), "analysis"),
            experiment_runner=_strict(RunnerConfig, data.get("experiment_runner"), "experiment_runner"),
            limits=_strict(LimitsConfig, data.get("limits"), "limits"),
            report=_strict(ReportConfig, report, "report"),
        )


class PromptManager:
    """프롬프트 관리자"""
    
    def __init__(self, prompts_data: Dict[str, Any]):
        self.prompts = prompts_data
    
    def get(self, path: str, default: Any = None) -> Any:
        """점(.) 경로로 프롬프트 조회 (예: 'turn_actions.position')"""
        node: Any = self.prompts
        for key in path.split('.'):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def render(self, path: str, **kwargs) -> str:
        """점(.) 경로의 템플릿을 kwargs로 채워 반환 (없으면 KeyError)"""
        template = self.get(path)
        if not isinstance(template, str):
            raise KeyError(f"Prompt template not found: {path}")
        return template.format(**kwargs)

    def get_persona_system_prompt(self) -> str:
        """페르소나 생성 시스템 프롬프트"""
        return self.prompts.get('persona_generation', {}).get('system', '')
    
    def get_persona_user_prompt(self, topic: str, perspective_text: str = '') -> str:
        """페르소나 생성 사용자 프롬프트"""
        template = self.prompts.get('persona_generation', {}).get('user_template', '')
        return template.format(topic=topic, perspective_text=perspective_text)
    
    def get_agent_base_prompt(self, persona_dict: Dict[str, Any]) -> str:
        """에이전트 기본 프롬프트"""
        template = self.prompts.get('agent', {}).get('base_persona', '')
        return template.format(**persona_dict)
    
    def get_agent_length_instruction(self, min_sentences: int, max_sentences: int) -> str:
        """에이전트 길이 제한 지시사항"""
        template = self.prompts.get('agent', {}).get('length_instruction', '')
        return template.format(min_sentences=min_sentences, max_sentences=max_sentences)
    
    


class ConfigLoader:
    """설정 로더"""
    
    _instance: Optional['ConfigLoader'] = None
    _config: Optional[AppConfig] = None
    _prompts: Optional[PromptManager] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            self.load()
    
    def load(self, config_path: str = None, prompts_path: str = None):
        """설정 파일 로드"""
        # 기본 경로 설정
        base_dir = Path(__file__).parent.parent
        config_path = config_path or base_dir / 'config' / 'config.yaml'
        prompts_path = prompts_path or base_dir / 'config' / 'prompts.yaml'
        
        # 설정 파일 로드
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
            self._config = AppConfig.from_dict(config_data)
        
        # 프롬프트 파일 로드 (보고서 프롬프트는 'report' 네임스페이스로 병합)
        with open(prompts_path, 'r', encoding='utf-8') as f:
            prompts_data = yaml.safe_load(f)
        report_prompts_path = base_dir / 'config' / 'report_prompts.yaml'
        if report_prompts_path.exists():
            with open(report_prompts_path, 'r', encoding='utf-8') as f:
                prompts_data['report'] = yaml.safe_load(f)
        self._prompts = PromptManager(prompts_data)
    
    @property
    def config(self) -> AppConfig:
        """설정 객체 반환"""
        if self._config is None:
            self.load()
        return self._config
    
    @property
    def prompts(self) -> PromptManager:
        """프롬프트 매니저 반환"""
        if self._prompts is None:
            self.load()
        return self._prompts
    
    def get_llm_config(self) -> LLMConfig:
        """LLM 설정 반환"""
        return self.config.llm
    

# 싱글톤 인스턴스
config_loader = ConfigLoader()