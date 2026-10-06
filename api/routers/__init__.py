"""
API 라우터
"""
from api.routers.auth import router as auth_router
from api.routers.users import router as users_router
from api.routers.discussions import router as discussions_router
from api.routers.messages import router as messages_router
from api.routers.personas import router as personas_router
from api.routers.config import router as config_router
from api.routers.reports import router as reports_router
from api.routers.admin import router as admin_router
from api.routers.interventions import router as interventions_router

__all__ = ["auth_router", "users_router", "discussions_router", "messages_router", "personas_router", "config_router", "reports_router", "admin_router", "interventions_router"]
