"""
인증 서비스
"""
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from api.models.user import User
from api.schemas.auth import RegisterRequest, LoginRequest
from api.utils.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from api.config import settings


class AuthService:
    """인증 관련 비즈니스 로직"""
    
    @staticmethod
    def register_user(db: Session, request: RegisterRequest) -> User:
        """
        사용자 등록
        
        Args:
            db: 데이터베이스 세션
            request: 회원가입 요청 데이터
            
        Returns:
            생성된 사용자
            
        Raises:
            HTTPException: 이메일 중복 등의 오류
        """
        # 이메일 중복 체크
        existing_user = db.query(User).filter(User.email == request.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "EMAIL_ALREADY_EXISTS",
                        "message": "이미 사용 중인 이메일입니다.",
                        "field": "email"
                    }
                }
            )
        
        # 사용자 생성
        user = User(
            email=request.email,
            password_hash=hash_password(request.password),
            name=request.name,
            organization=request.organization
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        return user
    
    @staticmethod
    def authenticate_user(db: Session, request: LoginRequest) -> tuple[User, str, str]:
        """
        사용자 인증 및 토큰 발급
        
        Args:
            db: 데이터베이스 세션
            request: 로그인 요청 데이터
            
        Returns:
            (사용자, access_token, refresh_token)
            
        Raises:
            HTTPException: 인증 실패 등의 오류
        """
        # 사용자 조회
        user = db.query(User).filter(User.email == request.email).first()
        
        # 로그인 시도 제한 체크
        if user and user.login_locked_until:
            if user.login_locked_until > datetime.utcnow():
                retry_after = int((user.login_locked_until - datetime.utcnow()).total_seconds())
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": {
                            "code": "TOO_MANY_ATTEMPTS",
                            "message": f"로그인 시도 횟수를 초과했습니다. {retry_after}초 후 다시 시도해주세요.",
                            "retry_after": retry_after
                        }
                    }
                )
            else:
                # 잠금 해제
                user.login_attempts = 0
                user.login_locked_until = None
        
        # 인증 실패
        if not user or not verify_password(request.password, user.password_hash):
            if user:
                user.login_attempts += 1
                
                # 최대 시도 횟수 초과 시 잠금
                if user.login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                    user.login_locked_until = datetime.utcnow() + timedelta(seconds=settings.LOGIN_ATTEMPT_TIMEOUT)
                
                db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {
                        "code": "INVALID_CREDENTIALS",
                        "message": "이메일 또는 비밀번호가 올바르지 않습니다."
                    }
                }
            )
        
        # 계정 비활성화 체크
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {
                        "code": "ACCOUNT_DISABLED",
                        "message": "비활성화된 계정입니다."
                    }
                }
            )
        
        # 로그인 성공 - 시도 횟수 리셋
        user.login_attempts = 0
        user.login_locked_until = None
        user.last_login_at = datetime.utcnow()
        db.commit()
        
        # 토큰 생성
        access_token = create_access_token(data={"sub": user.id})
        refresh_token = create_refresh_token(data={"sub": user.id})
        
        return user, access_token, refresh_token
    
    @staticmethod
    def refresh_access_token(db: Session, refresh_token: str) -> str:
        """
        Access Token 갱신
        
        Args:
            db: 데이터베이스 세션
            refresh_token: Refresh Token
            
        Returns:
            새로운 Access Token
            
        Raises:
            HTTPException: 토큰 무효 등의 오류
        """
        # 토큰 디코딩
        payload = decode_token(refresh_token)
        
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {
                        "code": "INVALID_REFRESH_TOKEN",
                        "message": "리프레시 토큰이 유효하지 않거나 만료되었습니다."
                    }
                }
            )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {
                        "code": "INVALID_REFRESH_TOKEN",
                        "message": "리프레시 토큰이 유효하지 않거나 만료되었습니다."
                    }
                }
            )
        
        # 사용자 존재 여부 확인
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {
                        "code": "INVALID_REFRESH_TOKEN",
                        "message": "리프레시 토큰이 유효하지 않거나 만료되었습니다."
                    }
                }
            )
        
        # 새 Access Token 생성
        new_access_token = create_access_token(data={"sub": user.id})
        
        return new_access_token

