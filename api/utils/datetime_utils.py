"""
Datetime 유틸리티
"""
from datetime import datetime, timezone


def utc_now() -> datetime:
    """
    현재 UTC 시간을 timezone-aware datetime으로 반환
    
    DB에서 DateTime(timezone=True)를 사용하므로
    모든 datetime 생성 시 이 함수를 사용해야 함
    
    Returns:
        timezone-aware UTC datetime
    """
    return datetime.now(timezone.utc)


def make_aware(dt: datetime) -> datetime:
    """
    naive datetime을 UTC timezone-aware datetime으로 변환
    
    Args:
        dt: datetime 객체
        
    Returns:
        timezone-aware datetime
    """
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def make_naive(dt: datetime) -> datetime:
    """
    timezone-aware datetime을 naive datetime으로 변환
    
    Args:
        dt: datetime 객체
        
    Returns:
        naive datetime (timezone 정보 제거)
    """
    if dt.tzinfo is None:
        return dt
    return dt.replace(tzinfo=None)


def safe_subtract(end: datetime, start: datetime) -> float:
    """
    timezone 불일치를 처리하며 두 datetime 차이를 초 단위로 반환
    
    Args:
        end: 종료 시간
        start: 시작 시간
        
    Returns:
        시간 차이 (초)
    """
    try:
        return (end - start).total_seconds()
    except TypeError:
        # timezone aware/naive 불일치 시 둘 다 naive로 변환
        end_naive = make_naive(end)
        start_naive = make_naive(start)
        return (end_naive - start_naive).total_seconds()

