"""
설정 로더 모듈
YAML 파일에서 설정과 프롬프트를 로드하고 관리
"""
import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    """LLM 설정"""
    temperature: float = 0.7
    max_tokens: int = 500
    timeout_seconds: float = 60
    max_retries: int = 2
    default_models: Dict[str, str] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LLMConfig':
        return cls(
            temperature=data.get('temperature', 0.7),
            max_tokens=data.get('max_tokens', 500),
            timeout_seconds=data.get('timeout_seconds', 60),
            max_retries=data.get('max_retries', 2),
            default_models=data.get('default_models', {})
        )


@dataclass
class DiscussionConfig:
    """토론 설정"""
    min_sentences: int = 3
    max_sentences: int = 8
    display_limit: int = 400
    default_rounds: int = 2
    max_context_messages: int = 5
    default_persona_count: int = 3
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DiscussionConfig':
        response_length = data.get('response_length', {})
        return cls(
            min_sentences=response_length.get('min_sentences', 3),
            max_sentences=response_length.get('max_sentences', 8),
            display_limit=response_length.get('display_limit', 400),
            default_rounds=data.get('default_rounds', 2),
            max_context_messages=data.get('max_context_messages', 5),
            default_persona_count=data.get('persona', {}).get('default_count', 3)
        )


@dataclass
class UIConfig:
    """UI 설정"""
    use_emoji: bool = True
    panel_width: int = 80
    colors: Dict[str, str] = field(default_factory=dict)
    show_thinking: bool = True
    show_round_info: bool = True
    show_statistics: bool = True
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UIConfig':
        console_config = data.get('console', {})
        output_config = data.get('output', {})
        return cls(
            use_emoji=console_config.get('use_emoji', True),
            panel_width=console_config.get('panel_width', 80),
            colors=data.get('colors', {}),
            show_thinking=output_config.get('show_thinking', True),
            show_round_info=output_config.get('show_round_info', True),
            show_statistics=output_config.get('show_statistics', True)
        )


@dataclass 
class AppConfig:
    """전체 애플리케이션 설정"""
    llm: LLMConfig
    discussion: DiscussionConfig
    ui: UIConfig
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        return cls(
            llm=LLMConfig.from_dict(data.get('llm', {})),
            discussion=DiscussionConfig.from_dict(data.get('discussion', {})),
            ui=UIConfig.from_dict(data.get('ui', {}))
        )


class PromptManager:
    """프롬프트 관리자"""
    
    def __init__(self, prompts_data: Dict[str, Any]):
        self.prompts = prompts_data
    
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
    
    def get_discussion_prompt(self, phase: str, prompt_type: str, **kwargs) -> str:
        """토론 단계별 프롬프트"""
        phase_prompts = self.prompts.get('discussion', {}).get(phase, {})
        template = phase_prompts.get(prompt_type, '')
        return template.format(**kwargs) if template else ''
    
    def get_moderator_prompt(self, prompt_type: str, **kwargs) -> str:
        """모더레이터 프롬프트"""
        template = self.prompts.get('moderator', {}).get(prompt_type, '')
        return template.format(**kwargs) if template else ''


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
        
        # 프롬프트 파일 로드
        with open(prompts_path, 'r', encoding='utf-8') as f:
            prompts_data = yaml.safe_load(f)
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
    
    def get_discussion_config(self) -> DiscussionConfig:
        """토론 설정 반환"""
        return self.config.discussion
    
    def get_ui_config(self) -> UIConfig:
        """UI 설정 반환"""
        return self.config.ui


# 싱글톤 인스턴스
config_loader = ConfigLoader()