"""
페르소나 서비스
"""
import secrets
from datetime import datetime
from typing import List
from sqlalchemy.orm import Session

from api.models.persona import CustomPersona
from api.schemas.persona import (
    PersonaTemplateResponse,
    PersonaTemplateListResponse,
    CustomPersonaCreateRequest,
    CustomPersonaResponse
)


# ========================================
# 사전 정의된 페르소나 템플릿
# ========================================

PERSONA_TEMPLATES = [
    {
        "id": "safety_researcher",
        "name": "Dr. Safety",
        "role": "AI Safety Researcher",
        "background": "AI 안전성 연구 전문가로 10년 이상 경력",
        "expertise": ["AI Safety", "Ethics", "Risk Assessment"],
        "personality": ["신중한", "분석적", "객관적"],
        "communication_style": "학술적이고 데이터 기반",
        "beliefs": ["안전이 최우선", "데이터 기반 의사결정"],
        "default_llm": "openai",
        "default_model": "gpt-4",
        "initial_openness": 0.45,
        "tags": ["안전", "규제", "리스크"]
    },
    {
        "id": "tech_innovator",
        "name": "Mr. Innovation",
        "role": "Tech CEO",
        "background": "기술 스타트업 CEO, 3번의 성공적인 엑싯 경험",
        "expertise": ["Business Strategy", "Innovation", "Market Analysis"],
        "personality": ["낙관적", "도전적", "실용적"],
        "communication_style": "직관적이고 비즈니스 중심",
        "beliefs": ["혁신이 진보를 이끈다", "시장이 답을 안다"],
        "default_llm": "claude",
        "default_model": "claude-3-opus-20240229",
        "initial_openness": 0.70,
        "tags": ["혁신", "비즈니스", "성장"]
    },
    {
        "id": "ethics_professor",
        "name": "Prof. Ethics",
        "role": "Philosophy Professor",
        "background": "윤리학 전문가, 철학 박사",
        "expertise": ["Ethics", "Philosophy", "Social Impact"],
        "personality": ["신중한", "비판적", "공정한"],
        "communication_style": "철학적이고 원칙 중심",
        "beliefs": ["공정성", "투명성", "사회적 책임"],
        "default_llm": "openai",
        "default_model": "gpt-4",
        "initial_openness": 0.60,
        "tags": ["윤리", "철학", "사회"]
    },
    {
        "id": "policy_maker",
        "name": "Ms. Policy",
        "role": "Policy Maker",
        "background": "정부 정책 입안자, 공공정책 전문",
        "expertise": ["Public Policy", "Regulation", "Governance"],
        "personality": ["신중한", "균형잡힌", "현실적"],
        "communication_style": "정책 중심적이고 구조화된",
        "beliefs": ["공공의 이익", "균형잡힌 접근", "증거 기반 정책"],
        "default_llm": "openai",
        "default_model": "gpt-4",
        "initial_openness": 0.55,
        "tags": ["정책", "규제", "거버넌스"]
    },
    {
        "id": "citizen_advocate",
        "name": "Alex Citizen",
        "role": "Citizen Advocate",
        "background": "시민 권익 옹호자, NGO 활동가",
        "expertise": ["Human Rights", "Social Justice", "Community"],
        "personality": ["열정적", "공감적", "실천적"],
        "communication_style": "감정적이고 설득력 있는",
        "beliefs": ["시민의 권리", "참여 민주주의", "평등"],
        "default_llm": "claude",
        "default_model": "claude-3-sonnet-20240229",
        "initial_openness": 0.65,
        "tags": ["시민", "권리", "사회정의"]
    }
]


class PersonaService:
    """페르소나 서비스"""
    
    @staticmethod
    def get_templates() -> PersonaTemplateListResponse:
        """
        페르소나 템플릿 목록 조회
        
        Returns:
            PersonaTemplateListResponse: 템플릿 목록
        """
        templates = [PersonaTemplateResponse(**template) for template in PERSONA_TEMPLATES]
        return PersonaTemplateListResponse(
            templates=templates,
            total_count=len(templates)
        )
    
    @staticmethod
    def create_custom_persona(
        db: Session,
        user_id: str,
        persona_data: CustomPersonaCreateRequest
    ) -> CustomPersonaResponse:
        """
        커스텀 페르소나 생성
        
        Args:
            db: 데이터베이스 세션
            user_id: 사용자 ID
            persona_data: 페르소나 데이터
            
        Returns:
            CustomPersonaResponse: 생성된 페르소나
        """
        # 고유 ID 생성 (custom_ 접두사 + 랜덤 문자열)
        persona_id = f"custom_{secrets.token_hex(6)}"
        
        # 커스텀 페르소나 생성
        custom_persona = CustomPersona(
            id=persona_id,
            user_id=user_id,
            name=persona_data.name,
            role=persona_data.role,
            background=persona_data.background,
            expertise=persona_data.expertise,
            personality=persona_data.personality,
            communication_style=persona_data.communication_style,
            beliefs=persona_data.beliefs,
            initial_openness=persona_data.initial_openness,
            llm_provider=persona_data.llm_provider,
            model=persona_data.model,
            is_custom=True,
            created_at=datetime.utcnow()
        )
        
        db.add(custom_persona)
        db.commit()
        db.refresh(custom_persona)
        
        # 응답 생성
        return CustomPersonaResponse(
            id=custom_persona.id,
            name=custom_persona.name,
            role=custom_persona.role,
            background=custom_persona.background,
            expertise=custom_persona.expertise,
            personality=custom_persona.personality,
            communication_style=custom_persona.communication_style,
            beliefs=custom_persona.beliefs,
            initial_openness=custom_persona.initial_openness,
            llm_provider=custom_persona.llm_provider,
            model=custom_persona.model,
            is_custom=custom_persona.is_custom,
            created_by=custom_persona.user_id,
            created_at=custom_persona.created_at
        )
    
    @staticmethod
    def get_user_custom_personas(db: Session, user_id: str) -> List[CustomPersonaResponse]:
        """
        사용자의 커스텀 페르소나 목록 조회
        
        Args:
            db: 데이터베이스 세션
            user_id: 사용자 ID
            
        Returns:
            List[CustomPersonaResponse]: 커스텀 페르소나 목록
        """
        personas = db.query(CustomPersona).filter(CustomPersona.user_id == user_id).all()
        
        return [
            CustomPersonaResponse(
                id=p.id,
                name=p.name,
                role=p.role,
                background=p.background,
                expertise=p.expertise,
                personality=p.personality,
                communication_style=p.communication_style,
                beliefs=p.beliefs,
                initial_openness=p.initial_openness,
                llm_provider=p.llm_provider,
                model=p.model,
                is_custom=p.is_custom,
                created_by=p.user_id,
                created_at=p.created_at
            )
            for p in personas
        ]

