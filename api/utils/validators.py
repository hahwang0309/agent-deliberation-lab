"""
유효성 검사 유틸리티
"""
import re
from api.config import settings


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    비밀번호 강도 검사
    
    Args:
        password: 검사할 비밀번호
        
    Returns:
        (유효 여부, 에러 메시지)
    """
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return False, f"비밀번호는 최소 {settings.PASSWORD_MIN_LENGTH}자 이상이어야 합니다."
    
    if not re.search(r'[A-Za-z]', password):
        return False, "비밀번호는 영문자를 포함해야 합니다."
    
    if not re.search(r'\d', password):
        return False, "비밀번호는 숫자를 포함해야 합니다."
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "비밀번호는 특수문자를 포함해야 합니다."
    
    return True, ""


def validate_email_format(email: str) -> bool:
    """
    이메일 형식 검사
    
    Args:
        email: 검사할 이메일
        
    Returns:
        유효 여부
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

