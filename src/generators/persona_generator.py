from typing import List, Optional, Dict
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from src.models.personas import Persona, LLMProvider
from src.utils.llm_provider import LLMFactory
from config.config_loader import config_loader
from src.utils.language_detector import LanguageDetector
import json


class PersonaGenerator:
    """주제에 맞는 페르소나를 생성하는 클래스"""
    
    def __init__(self, llm: Optional[BaseChatModel] = None, provider: Optional[LLMProvider] = None):
        if llm:
            self.llm = llm
        elif provider:
            self.llm = LLMFactory.create_llm(provider, temperature=0.8)
        else:
            self.llm = LLMFactory.create_llm(LLMProvider.OPENAI, temperature=0.8)
        
        self.parser = JsonOutputParser(pydantic_object=Persona)
    
    async def generate_persona(self, topic: str, perspective: Optional[str] = None, agent_id: Optional[str] = None, language: Optional[str] = None) -> Persona:
        """단일 페르소나 생성"""
        
        # 언어 감지
        if not language:
            language = LanguageDetector.detect_language(topic)
        
        perspective_text = f"with a {perspective} perspective" if perspective else ""
        
        # 프롬프트를 설정 파일에서 가져오기
        prompts = config_loader.prompts
        system_prompt = prompts.get_persona_system_prompt()
        user_prompt = prompts.get_persona_user_prompt(topic, perspective_text)
        
        # 언어 지시 추가
        language_instruction = LanguageDetector.get_language_instruction(language)
        system_prompt += language_instruction
        
        if language == "ko":
            system_prompt += "\n- role은 한국어로 작성 (예: 'AI 연구원', '윤리학 교수')\n- background, personality, expertise, beliefs 모두 한국어로 작성\n- 각 필드를 간결하게 작성 (background는 100자 이내)"
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        try:
            # 응답 내용 정리 (마크다운 코드 블록 제거)
            content = response.content
            if isinstance(content, str):
                # 마크다운 코드 블록 제거
                if content.startswith("```json"):
                    content = content[7:]
                elif content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                # 잘린 JSON 복구 시도
                if not content.endswith("}"):
                    # 마지막 완전한 속성까지만 사용
                    last_complete = content.rfind('",')
                    if last_complete > 0:
                        content = content[:last_complete + 1] + ']}'
                    else:
                        # 복구 불가능한 경우
                        raise json.JSONDecodeError("Incomplete JSON", content, len(content))
                
                # JSON 파싱
                persona_dict = json.loads(content)
            else:
                # AIMessage 객체에서 content 추출
                persona_dict = json.loads(str(content))
            
            # 이름을 Agent ID로 대체
            if agent_id:
                persona_dict['name'] = agent_id
            
            return Persona(**persona_dict)
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            print(f"Response content preview: {response.content[:200]}...")
            
            # 언어에 따른 기본 페르소나
            if language == "ko":
                default_role = "전문가"
                default_background = f"{topic}에 대한 깊은 지식과 경험을 가진 전문가입니다."
                default_personality = ["분석적", "신중함", "전문적"]
                default_expertise = [topic, "분석", "전략"]
                default_style = "전문적이고 명확한 의사소통"
                default_beliefs = ["증거 기반 추론이 중요하다", "다양한 관점을 고려해야 한다"]
            else:
                default_role = "Domain Specialist"
                default_background = f"An experienced professional with deep knowledge in {topic}."
                default_personality = ["analytical", "thoughtful", "professional"]
                default_expertise = [topic, "analysis", "strategy"]
                default_style = "Professional and clear"
                default_beliefs = ["Evidence-based reasoning is important", "Multiple perspectives should be considered"]
            
            # 기본 페르소나 반환
            return Persona(
                name=agent_id or f"Expert {perspective or 'General'}",
                role=default_role,
                background=default_background,
                personality=default_personality,
                expertise=default_expertise,
                communication_style=default_style,
                beliefs=default_beliefs
            )
        except Exception as e:
            print(f"Error creating persona: {e}")
            return Persona(
                name="Expert",
                role="Specialist",
                background="An experienced professional in the field.",
                personality=["analytical", "thoughtful", "professional"],
                expertise=["general knowledge"],
                communication_style="Professional and clear",
                beliefs=["Evidence-based reasoning is important"]
            )
    
    async def refine_user_persona(self, topic: str, user_input: Dict[str, str], language: Optional[str] = None) -> Persona:
        """사용자가 입력한 페르소나 정보를 다듬어서 완성"""
        
        # 언어 감지
        if not language:
            language = LanguageDetector.detect_language(topic)
        
        # 사용자 입력을 바탕으로 프롬프트 생성
        system_prompt = f"""You are refining a user-defined persona for a discussion about: {topic}
        
Take the user's input and enhance it to create a complete, consistent persona.
Keep the core identity the user specified, but add depth and detail.

Return a valid JSON object with this structure:
{{
    "name": "name",
    "role": "professional role",
    "background": "2-3 sentences about experience",
    "personality": ["trait1", "trait2", "trait3"],
    "expertise": ["area1", "area2", "area3"],
    "communication_style": "detailed description",
    "beliefs": ["belief1", "belief2", "belief3"]
}}"""
        
        # 언어 지시 추가
        language_instruction = LanguageDetector.get_language_instruction(language)
        system_prompt += language_instruction
        
        if language == "ko":
            system_prompt += "\n- 모든 필드를 한국어로 작성하세요"
        
        # 사용자가 입력한 필드만 포함
        provided_info = []
        if user_input.get('name'):
            provided_info.append(f"- Name/Identity: {user_input['name']}")
        if user_input.get('role'):
            provided_info.append(f"- Role/Position: {user_input['role']}")
        if user_input.get('perspective'):
            provided_info.append(f"- Perspective: {user_input['perspective']}")
        if user_input.get('traits'):
            provided_info.append(f"- Key traits: {user_input['traits']}")
        if user_input.get('background'):
            provided_info.append(f"- Background: {user_input['background']}")
        
        if provided_info:
            user_prompt = f"""Refine this partially defined persona:
{chr(10).join(provided_info)}

Create a complete persona that maintains any specified identity but adds all missing details appropriate for the topic."""
        else:
            # 아무것도 입력하지 않은 경우
            user_prompt = f"""Create a persona for the topic with no specific constraints.
Generate a complete persona with unique perspective suitable for a discussion about the topic."""
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        try:
            content = response.content
            if isinstance(content, str):
                if content.startswith("```json"):
                    content = content[7:]
                elif content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
            persona_dict = json.loads(content)
            
            # 사용자가 지정한 이름이 있으면 유지
            if user_input.get('name'):
                persona_dict['name'] = user_input['name']
                
            return Persona(**persona_dict)
            
        except Exception as e:
            print(f"Error refining persona: {e}")
            # 기본값으로 반환
            return Persona(
                name=user_input.get('name', 'Custom Agent'),
                role=user_input.get('role', 'Specialist'),
                background=user_input.get('background', f"Expert in {topic}"),
                personality=["thoughtful", "analytical"],
                expertise=[topic],
                communication_style="Clear and professional",
                beliefs=["Evidence-based reasoning is important"]
            )
    
    async def generate_multiple_personas(
        self, 
        topic: str, 
        count: int = 3,
        perspectives: Optional[List[str]] = None,
        use_simple_names: bool = True,
        language: Optional[str] = None
    ) -> List[Persona]:
        """여러 페르소나 생성"""
        
        if not perspectives:
            # 더 대립적인 기본 관점들 (동적 생성)
            base_perspectives = ['strongly supportive', 'highly skeptical', 'contrarian', 'pragmatic critic', 'radical']
            # count만큼 반복해서 생성
            perspectives = base_perspectives * ((count // len(base_perspectives)) + 1)
            perspectives = perspectives[:count]
        
        personas = []
        
        # Agent ID 동적 생성 (A, B, C, ... Z, AA, AB, ...)
        agent_ids = [f"Agent {chr(65 + i)}" for i in range(count)]
        
        # 더 논쟁적인 커뮤니케이션 스타일 힌트 (동적 생성)
        base_style_hints = [
            "Make this persona confrontational and data-driven, often challenging others with hard facts and statistics",
            "Make this persona skeptical and questioning, constantly probing for weaknesses in arguments", 
            "Make this persona contrarian and provocative, taking devil's advocate positions",
            "Make this persona critical but constructive, identifying flaws while proposing alternatives",
            "Make this persona radical and disruptive, challenging fundamental assumptions"
        ]
        # count만큼 반복해서 생성
        style_hints = base_style_hints * ((count // len(base_style_hints)) + 1)
        style_hints = style_hints[:count]
        
        for i in range(count):
            perspective = perspectives[i % len(perspectives)]
            # 스타일 힌트를 perspective에 추가
            enhanced_perspective = f"{perspective} perspective. {style_hints[i % len(style_hints)]}"
            agent_id = agent_ids[i] if use_simple_names and i < len(agent_ids) else None
            persona = await self.generate_persona(topic, enhanced_perspective, agent_id, language)
            personas.append(persona)
        
        return personas