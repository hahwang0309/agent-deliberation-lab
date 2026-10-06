import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from enum import Enum


class LLMProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"
    CLAUDE = "claude"
    MISTRAL = "mistral"


class Persona(BaseModel):
    """페르소나 정보를 담는 모델"""
    name: str = Field(description="페르소나의 이름")
    role: str = Field(description="페르소나의 역할/직업")
    background: str = Field(description="페르소나의 배경 및 경험")
    personality: List[str] = Field(description="성격 특성 리스트")
    expertise: List[str] = Field(description="전문 분야 리스트")
    communication_style: str = Field(description="의사소통 스타일")
    beliefs: List[str] = Field(description="핵심 신념 리스트")

    @field_validator("personality", "expertise", "beliefs", mode="before")
    @classmethod
    def _coerce_list(cls, value: Any) -> Any:
        """LLM이 목록을 문자열(JSON 배열 문자열 또는 쉼표 구분)로 반환한 경우 목록으로 변환"""
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in text.split(",") if item.strip()]
    
    def to_prompt(self) -> str:
        """페르소나를 프롬프트로 변환"""
        return f"""You are {self.name}, a {self.role}.

Background: {self.background}

Your personality traits: {', '.join(self.personality)}

Your areas of expertise: {', '.join(self.expertise)}

Your communication style: {self.communication_style}

Your core beliefs: {'. '.join(self.beliefs)}

Stay in character and respond based on your persona. Express your unique perspective on topics based on your background and beliefs."""


class Message(BaseModel):
    """대화 메시지 모델"""
    role: str = Field(description="메시지 역할 (user/assistant/system)")
    content: str = Field(description="메시지 내용")
    timestamp: datetime = Field(default_factory=datetime.now)
    agent_name: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentState(BaseModel):
    """에이전트 상태를 관리하는 모델"""
    persona: Persona
    messages: List[Message] = Field(default_factory=list)
    current_topic: Optional[str] = None
    thinking: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True