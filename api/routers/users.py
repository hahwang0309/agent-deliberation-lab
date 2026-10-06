"""
사용자 엔드포인트
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import Optional
from api.database import get_db
from api.dependencies import get_current_user, get_optional_user
from api.models.user import User
from api.schemas.user import (
    UserResponse,
    UserUpdateRequest,
    PasswordChangeRequest,
    MessageResponse,
    UserStatistics,
    SubscriptionInfo,
    SubscriptionFeatures
)
from api.services.user_service import UserService

router = APIRouter(prefix="/api/v1/users", tags=["사용자"])


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="내 정보 조회 (게스트 지원)",
    description="현재 로그인한 사용자의 정보를 조회합니다. 로그인 선택사항."
)
def get_my_info(
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    내 정보 조회
    
    인증된 사용자의 프로필, 통계, 구독 정보를 반환합니다.
    게스트의 경우 기본 정보를 반환합니다.
    
    **Authorization 헤더 선택사항 (게스트 허용):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    # 게스트 사용자 처리
    if not current_user:
        from datetime import datetime
        statistics = UserStatistics(
            total_discussions=0,
            completed_discussions=0,
            active_discussions=0
        )
        features = UserService.get_subscription_plan_features("free")
        subscription = SubscriptionInfo(
            plan="free",
            expires_at=None,
            features=SubscriptionFeatures(**features)
        )
        return UserResponse(
            id="guest",
            email="guest@temp.com",
            name="Guest",
            organization=None,
            created_at=datetime.utcnow(),
            statistics=statistics,
            subscription=subscription
        )
    # 통계 정보 (실제로는 DB에서 조회해야 함)
    statistics = UserStatistics(
        total_discussions=15,
        completed_discussions=12,
        active_discussions=3
    )
    
    # 구독 정보
    features = UserService.get_subscription_plan_features(current_user.subscription_plan)
    subscription = SubscriptionInfo(
        plan=current_user.subscription_plan,
        expires_at=current_user.subscription_expires_at,
        features=SubscriptionFeatures(**features)
    )
    
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        organization=current_user.organization,
        created_at=current_user.created_at,
        statistics=statistics,
        subscription=subscription
    )


@router.put(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="내 정보 수정 (게스트 지원)",
    description="현재 로그인한 사용자의 정보를 수정합니다. 로그인 선택사항."
)
def update_my_info(
    request: UserUpdateRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    내 정보 수정
    
    - **name**: 변경할 이름 (선택)
    - **organization**: 변경할 조직/회사명 (선택)
    
    **Authorization 헤더 선택사항 (게스트는 수정 불가):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    # 게스트 사용자는 수정 불가
    if not current_user:
        from fastapi import HTTPException
        from datetime import datetime
        statistics = UserStatistics(
            total_discussions=0,
            completed_discussions=0,
            active_discussions=0
        )
        features = UserService.get_subscription_plan_features("free")
        subscription = SubscriptionInfo(
            plan="free",
            expires_at=None,
            features=SubscriptionFeatures(**features)
        )
        return UserResponse(
            id="guest",
            email="guest@temp.com",
            name="Guest",
            organization=None,
            created_at=datetime.utcnow(),
            statistics=statistics,
            subscription=subscription
        )
    # 사용자 정보 수정
    updated_user = UserService.update_user(db, current_user.id, request)
    
    # 통계 및 구독 정보
    statistics = UserStatistics(
        total_discussions=15,
        completed_discussions=12,
        active_discussions=3
    )
    
    features = UserService.get_subscription_plan_features(updated_user.subscription_plan)
    subscription = SubscriptionInfo(
        plan=updated_user.subscription_plan,
        expires_at=updated_user.subscription_expires_at,
        features=SubscriptionFeatures(**features)
    )
    
    return UserResponse(
        id=updated_user.id,
        email=updated_user.email,
        name=updated_user.name,
        organization=updated_user.organization,
        created_at=updated_user.created_at,
        statistics=statistics,
        subscription=subscription
    )


@router.put(
    "/me/password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="비밀번호 변경 (게스트 지원)",
    description="현재 로그인한 사용자의 비밀번호를 변경합니다. 로그인 선택사항."
)
def change_password(
    request: PasswordChangeRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    비밀번호 변경
    
    - **current_password**: 현재 비밀번호
    - **new_password**: 새 비밀번호 (최소 8자, 영문+숫자+특수문자)
    
    **Authorization 헤더 선택사항 (게스트는 변경 불가):**
    ```
    Authorization: Bearer {access_token}
    ```
    """
    # 게스트 사용자는 비밀번호 변경 불가
    if not current_user:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "GUEST_NOT_ALLOWED",
                    "message": "게스트는 비밀번호를 변경할 수 없습니다."
                }
            }
        )
    
    user = UserService.change_password(db, current_user.id, request)
    
    return MessageResponse(
        message="비밀번호가 성공적으로 변경되었습니다.",
        updated_at=user.updated_at
    )

