"""
API 라우터
"""
from api.routers.auth import router as auth_router
from api.routers.users import router as users_router
from api.routers.discussions import router as discussions_router
from api.routers.messages import router as messages_router
from api.routers.personas import router as personas_router
from api.routers.config import router as config_router

__all__ = ["auth_router", "users_router", "discussions_router", "messages_router", "personas_router", "config_router"]
