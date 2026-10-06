"""
사용자 서비스
"""
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from datetime import datetime
from api.models.user import User
from api.schemas.user import UserUpdateRequest, PasswordChangeRequest
from api.utils.security import hash_password, verify_password


class UserService:
    """사용자 관련 비즈니스 로직"""
    
    @staticmethod
    def get_user_by_id(db: Session, user_id: str) -> User:
        """
        사용자 ID로 조회
        
        Args:
            db: 데이터베이스 세션
            user_id: 사용자 ID
            
        Returns:
            사용자
            
        Raises:
            HTTPException: 사용자 없음
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "USER_NOT_FOUND",
                        "message": "사용자를 찾을 수 없습니다."
                    }
                }
            )
        return user
    
    @staticmethod
    def update_user(db: Session, user_id: str, request: UserUpdateRequest) -> User:
        """
        사용자 정보 수정
        
        Args:
            db: 데이터베이스 세션
            user_id: 사용자 ID
            request: 수정 요청 데이터
            
        Returns:
            수정된 사용자
        """
        user = UserService.get_user_by_id(db, user_id)
        
        # 수정할 필드 업데이트
        if request.name is not None:
            user.name = request.name
        if request.organization is not None:
            user.organization = request.organization
        
        user.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(user)
        
        return user
    
    @staticmethod
    def change_password(db: Session, user_id: str, request: PasswordChangeRequest) -> User:
        """
        비밀번호 변경
        
        Args:
            db: 데이터베이스 세션
            user_id: 사용자 ID
            request: 비밀번호 변경 요청
            
        Returns:
            사용자
            
        Raises:
            HTTPException: 현재 비밀번호 불일치 등
        """
        user = UserService.get_user_by_id(db, user_id)
        
        # 현재 비밀번호 확인
        if not verify_password(request.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {
                        "code": "CURRENT_PASSWORD_INCORRECT",
                        "message": "현재 비밀번호가 올바르지 않습니다."
                    }
                }
            )
        
        # 새 비밀번호 해싱 및 저장
        user.password_hash = hash_password(request.new_password)
        user.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(user)
        
        return user
    
    @staticmethod
    def get_subscription_plan_features(plan: str) -> dict:
        """
        구독 플랜별 기능 반환
        
        Args:
            plan: 구독 플랜 (free, pro, enterprise)
            
        Returns:
            기능 딕셔너리
        """
        plans = {
            "free": {
                "max_concurrent_discussions": 1,
                "max_participants": 3,
                "enable_rag": False
            },
            "pro": {
                "max_concurrent_discussions": 5,
                "max_participants": 5,
                "enable_rag": True
            },
            "enterprise": {
                "max_concurrent_discussions": 999,
                "max_participants": 10,
                "enable_rag": True
            }
        }
        
        return plans.get(plan, plans["free"])

