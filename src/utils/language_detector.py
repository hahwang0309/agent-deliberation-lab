"""
언어 감지 유틸리티
입력 텍스트의 언어를 감지하고 적절한 언어로 응답하도록 지원
"""
from typing import Literal, Optional
import re


class LanguageDetector:
    """간단한 언어 감지기"""
    
    @staticmethod
    def detect_language(text: str) -> Literal["ko", "en", "auto"]:
        """텍스트의 언어 감지
        
        Args:
            text: 감지할 텍스트
            
        Returns:
            "ko" (한국어), "en" (영어), "auto" (자동)
        """
        if not text:
            return "auto"
        
        # 한글 패턴
        korean_pattern = re.compile('[가-힣ㄱ-ㅎㅏ-ㅣ]')
        # 영문 패턴  
        english_pattern = re.compile('[a-zA-Z]')
        
        # 각 언어 문자 수 계산
        korean_chars = len(korean_pattern.findall(text))
        english_chars = len(english_pattern.findall(text))
        
        # 전체 문자 수 (공백 제외)
        total_chars = len(text.replace(' ', ''))
        
        if total_chars == 0:
            return "auto"
        
        # 비율 계산
        korean_ratio = korean_chars / total_chars
        english_ratio = english_chars / total_chars
        
        # 주요 언어 결정 (60% 이상)
        if korean_ratio > 0.6:
            return "ko"
        elif english_ratio > 0.6:
            return "en"
        else:
            # 더 많은 쪽 선택
            return "ko" if korean_ratio > english_ratio else "en"
    
    @staticmethod
    def get_language_instruction(language: str) -> str:
        """언어별 지시사항 생성
        
        Args:
            language: 언어 코드
            
        Returns:
            언어 지시사항
        """
        if language == "ko":
            return "\n\nIMPORTANT: Respond in Korean (한국어로 응답하세요)."
        elif language == "en":
            return "\n\nIMPORTANT: Respond in English."
        else:
            return ""
    
    @staticmethod
    def get_discussion_language_context(language: str) -> str:
        """토론용 언어 컨텍스트
        
        Args:
            language: 언어 코드
            
        Returns:
            토론 언어 컨텍스트
        """
        if language == "ko":
            return """
이 토론은 한국어로 진행됩니다.
- 모든 응답을 한국어로 작성하세요
- 한국어 존댓말을 사용하되, 토론 상황에 맞게 적절히 조절하세요
- 전문 용어는 필요시 영어 병기 가능 (예: 인공지능(AI))
"""
        elif language == "en":
            return """
This discussion will be conducted in English.
- All responses should be in English
- Use professional and respectful language
- Technical terms should be clearly explained when necessary
"""
        else:
            return ""
    
    @staticmethod
    def translate_role(role: str, language: str) -> str:
        """역할명 번역
        
        Args:
            role: 영문 역할명
            language: 대상 언어
            
        Returns:
            번역된 역할명
        """
        if language != "ko":
            return role
        
        # 간단한 역할 번역 매핑
        role_translations = {
            "AI Researcher": "AI 연구원",
            "Ethics Professor": "윤리학 교수",
            "Software Engineer": "소프트웨어 엔지니어",
            "Data Scientist": "데이터 과학자",
            "Policy Maker": "정책 입안자",
            "Economist": "경제학자",
            "Philosopher": "철학자",
            "Social Scientist": "사회과학자",
            "Technology Expert": "기술 전문가",
            "Business Analyst": "비즈니스 분석가",
            "Professor": "교수",
            "Researcher": "연구원",
            "Expert": "전문가",
            "Analyst": "분석가",
            "Consultant": "컨설턴트"
        }
        
        # 정확한 매칭 시도
        if role in role_translations:
            return role_translations[role]
        
        # 부분 매칭 시도
        for eng, kor in role_translations.items():
            if eng.lower() in role.lower():
                return role.replace(eng, kor)
        
        # 번역 못하면 원본 반환
        return role