"""
FastAPI 의존성
"""
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from api.database import get_db
from api.models.user import User
from api.utils.security import decode_token

# HTTP Bearer 토큰 스키마
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    현재 인증된 사용자 조회
    
    Args:
        credentials: Bearer 토큰
        db: 데이터베이스 세션
        
    Returns:
        현재 사용자
        
    Raises:
        HTTPException: 인증 실패
    """
    token = credentials.credentials
    
    # 토큰 디코딩
    payload = decode_token(token)
    
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_TOKEN",
                    "message": "유효하지 않은 토큰입니다."
                }
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_TOKEN",
                    "message": "유효하지 않은 토큰입니다."
                }
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # 사용자 조회
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "사용자를 찾을 수 없습니다."
                }
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    선택적으로 인증된 사용자 조회 (비로그인도 허용)

    Args:
        credentials: Bearer 토큰 (선택)
        db: 데이터베이스 세션

    Returns:
        현재 사용자 또는 None
    """
    if not credentials:
        return None

    token = credentials.credentials
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    return user

