"""
언어 감지 유틸리티
입력 텍스트의 언어를 감지하고 적절한 언어로 응답하도록 지원
"""
from typing import Literal
import re
from config.config_loader import config_loader


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
        return config_loader.prompts.get(f"language.instruction.{language}", "")
