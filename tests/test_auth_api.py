"""
계정·권한·실행 제한·CSRF 테스트
"""
import asyncio
import uuid

import pytest

from api.config import settings
from api.database import SessionLocal
from api.models.user import User, UserRole, UserStatus
from api.runtime import registry
from api.runtime import runtime as runtime_module
from api.services.auth_service import AuthService
from tests.conftest import PASSWORD, LoggedInClient, create_user, login, new_client, update_user
from tests.test_events_api import PERSONA
from tests.test_runtime import FakeBundle

BODY = {"topic": "Ban cars downtown?", "max_statements": 20,
        "personas": [dict(name="Alice", **PERSONA), dict(name="Bob", **PERSONA)]}


@pytest.fixture(autouse=True)
def slow_engine(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", lambda callbacks=None: FakeBundle(slow=True))


async def _create(client, **overrides):
    r = await client.post("/api/v1/discussions", json={**BODY, **overrides})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _stop_all():
    for discussion_id in registry.running_ids():
        await registry.stop(discussion_id, by="test")
    for discussion_id in registry.report_ids():
        task = registry.report_task(discussion_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_signup_requires_admin_approval():
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    async with new_client() as anon, LoggedInClient(create_user(role=UserRole.ADMIN)) as admin:
        r = await anon.post("/api/v1/auth/signup-request",
                            json={"email": email, "password": PASSWORD, "name": "New", "note": "연구용"})
        assert r.status_code == 201 and r.json()["status"] == "pending"
        assert (await anon.post("/api/v1/auth/signup-request",
                                json={"email": email, "password": PASSWORD, "name": "Dup"})).status_code == 409

        r = await login(anon, email)
        assert r.status_code == 403 and r.json()["detail"]["error"]["code"] == "ACCOUNT_PENDING"

        pending = (await admin.get("/api/v1/admin/users?status=pending")).json()
        user_id = next(u["id"] for u in pending if u["email"] == email)
        assert (await admin.post(f"/api/v1/admin/users/{user_id}/approve")).json()["status"] == "active"

        assert (await login(anon, email)).status_code == 200
        me = (await anon.get("/api/v1/auth/me")).json()
        assert me["email"] == email and me["role"] == "user"


@pytest.mark.asyncio
async def test_weak_password_rejected():
    async with new_client() as anon:
        r = await anon.post("/api/v1/auth/signup-request",
                            json={"email": "weakling@example.com", "password": "short", "name": "W"})
        assert r.status_code == 422 and r.json()["detail"]["error"]["code"] == "INVALID_PASSWORD"


@pytest.mark.asyncio
async def test_unauthenticated_requests_are_rejected_but_pages_are_public():
    async with new_client() as anon:
        assert (await anon.get("/api/v1/discussions")).status_code == 401
        assert (await anon.get("/api/v1/admin/users")).status_code == 401
        assert (await anon.get("/")).status_code == 200
        assert (await anon.get("/health")).status_code == 200


@pytest.mark.asyncio
async def test_owner_or_admin_controls_but_everyone_can_read():
    owner, other, admin = create_user(), create_user(), create_user(role=UserRole.ADMIN)
    async with LoggedInClient(owner) as c_owner, LoggedInClient(other) as c_other, LoggedInClient(admin) as c_admin:
        discussion_id = await _create(c_owner)
        assert (await c_other.post(f"/api/v1/discussions/{discussion_id}/start")).status_code == 403
        assert (await c_owner.post(f"/api/v1/discussions/{discussion_id}/start")).status_code == 202

        assert (await c_other.get(f"/api/v1/discussions/{discussion_id}")).status_code == 200  # 공동 참여: 조회 가능
        r = await c_other.post(f"/api/v1/discussions/{discussion_id}/stop")
        assert r.status_code == 403 and r.json()["detail"]["error"]["code"] == "FORBIDDEN"
        assert (await c_admin.post(f"/api/v1/discussions/{discussion_id}/stop", json={"reason": "admin"})).status_code == 200

        detail = (await c_other.get(f"/api/v1/discussions/{discussion_id}")).json()
        assert detail["status"] == "stopped" and detail["stopped_by"] == admin.id
        assert detail["created_by_name"] == owner.name
        assert (await c_other.delete(f"/api/v1/discussions/{discussion_id}")).status_code == 403
    await _stop_all()


@pytest.mark.asyncio
async def test_concurrent_and_daily_limits():
    user = create_user()
    async with LoggedInClient(user) as client:
        first, second = await _create(client), await _create(client)
        assert (await client.post(f"/api/v1/discussions/{first}/start")).status_code == 202
        r = await client.post(f"/api/v1/discussions/{second}/start")
        assert r.status_code == 403 and r.json()["detail"]["error"]["code"] == "CONCURRENT_LIMIT_EXCEEDED"
        assert (await client.post(f"/api/v1/discussions/{first}/stop")).status_code == 200
        await _stop_all()

        update_user(user.id, daily_limit=1)  # 오늘 이미 1개 시작함
        r = await client.post(f"/api/v1/discussions/{second}/start")
        assert r.status_code == 429 and r.json()["detail"]["error"]["code"] == "DAILY_LIMIT_EXCEEDED"
        assert (await client.get(f"/api/v1/discussions/{second}")).json()["status"] == "draft"


@pytest.mark.asyncio
async def test_admin_is_not_limited_and_expensive_features_are_admin_only():
    async with LoggedInClient(create_user()) as user, LoggedInClient(create_user(role=UserRole.ADMIN)) as admin:
        r = await user.post("/api/v1/discussions", json={**BODY, "enable_web_search": True})
        assert r.status_code == 403 and r.json()["detail"]["error"]["code"] == "FEATURE_RESTRICTED"
        assert (await admin.post("/api/v1/discussions", json={**BODY, "enable_web_search": True})).status_code == 201

        ids = [await _create(admin) for _ in range(2)]
        for discussion_id in ids:
            assert (await admin.post(f"/api/v1/discussions/{discussion_id}/start")).status_code == 202
    await _stop_all()


@pytest.mark.asyncio
async def test_csrf_required_for_cookie_authenticated_writes():
    async with LoggedInClient(create_user()) as client:
        token = client.headers.pop("X-CSRF-Token")
        r = await client.post("/api/v1/discussions", json=BODY)
        assert r.status_code == 403 and r.json()["detail"]["error"]["code"] == "CSRF_FAILED"
        client.headers["X-CSRF-Token"] = "wrong"
        assert (await client.post("/api/v1/discussions", json=BODY)).status_code == 403
        client.headers["X-CSRF-Token"] = token
        r = await client.post("/api/v1/discussions", json=BODY, headers={"Origin": "http://evil.example"})
        assert r.status_code == 403
        assert (await client.post("/api/v1/discussions", json=BODY)).status_code == 201


@pytest.mark.asyncio
async def test_sse_works_with_cookie_only():
    async with LoggedInClient(create_user()) as client:
        discussion_id = await _create(client, max_statements=2)
        await client.post(f"/api/v1/discussions/{discussion_id}/start")
        r = await client.get(f"/api/v1/discussions/{discussion_id}/events")
        assert r.status_code == 200 and "event: status" in r.text and '"completed"' in r.text


@pytest.mark.asyncio
async def test_suspension_and_password_reset_revoke_sessions_immediately():
    user, admin = create_user(), create_user(role=UserRole.ADMIN)
    async with LoggedInClient(user) as c_user, LoggedInClient(admin) as c_admin:
        assert (await c_user.get("/api/v1/discussions")).status_code == 200
        assert (await c_admin.post(f"/api/v1/admin/users/{user.id}/suspend")).status_code == 200
        assert (await c_user.get("/api/v1/discussions")).status_code == 401
        assert (await c_user.post("/api/v1/auth/refresh")).status_code == 401
        assert (await login(c_user, user.email)).json()["detail"]["error"]["code"] == "ACCOUNT_SUSPENDED"

        assert (await c_admin.post(f"/api/v1/admin/users/{user.id}/reactivate")).status_code == 200
        temp = (await c_admin.post(f"/api/v1/admin/users/{user.id}/reset-password")).json()["temp_password"]
        assert (await login(c_user, user.email)).status_code == 401  # 기존 비밀번호 무효
        assert (await login(c_user, user.email, temp)).status_code == 200
        assert (await c_user.get("/api/v1/discussions")).json()["detail"]["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"


@pytest.mark.asyncio
async def test_issued_account_must_change_password_first():
    async with LoggedInClient(create_user(role=UserRole.ADMIN)) as admin, new_client() as fresh:
        email = f"{uuid.uuid4().hex[:8]}@example.com"
        issued = (await admin.post("/api/v1/admin/users", json={"email": email, "name": "Issued"})).json()
        assert issued["user"]["must_change_password"] is True

        assert (await login(fresh, email, issued["temp_password"])).status_code == 200
        r = await fresh.get("/api/v1/discussions")
        assert r.status_code == 403 and r.json()["detail"]["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
        assert (await fresh.get("/api/v1/auth/me")).status_code == 200

        r = await fresh.put("/api/v1/users/me/password",
                            json={"current_password": issued["temp_password"], "new_password": PASSWORD})
        assert r.status_code == 200 and r.json()["must_change_password"] is False
        fresh.headers["X-CSRF-Token"] = fresh.cookies["csrf_token"]
        assert (await fresh.get("/api/v1/discussions")).status_code == 200  # 재발급된 쿠키로 계속 사용


@pytest.mark.asyncio
async def test_refresh_and_logout():
    async with LoggedInClient(create_user()) as client:
        assert (await client.post("/api/v1/auth/refresh")).status_code == 200
        assert (await client.get("/api/v1/discussions")).status_code == 200
        assert (await client.post("/api/v1/auth/logout")).status_code == 204
        assert (await client.get("/api/v1/discussions")).status_code == 401


@pytest.mark.asyncio
async def test_login_lockout_after_repeated_failures():
    user = create_user()
    async with new_client() as client:
        for _ in range(settings.MAX_LOGIN_ATTEMPTS):
            assert (await login(client, user.email, "wrong-password-1")).status_code == 401
        r = await login(client, user.email)
        assert r.status_code == 429 and r.json()["detail"]["error"]["code"] == "TOO_MANY_ATTEMPTS"


def test_initial_admin_bootstrap(monkeypatch):
    db = SessionLocal()
    try:
        admins = db.query(User).filter(User.role == UserRole.ADMIN).all()
        for a in admins:  # 관리자가 없는 상태를 만들기 위해 임시로 강등
            a.role = UserRole.USER
        db.commit()
        monkeypatch.setattr(settings, "ADMIN_EMAIL", "Boss@Example.com")
        monkeypatch.setattr(settings, "ADMIN_INITIAL_PASSWORD", "Initial-pass-123")
        AuthService.ensure_initial_admin(db)
        boss = db.query(User).filter(User.email == "boss@example.com").one()
        assert boss.role == UserRole.ADMIN and boss.status == UserStatus.ACTIVE and boss.must_change_password
        AuthService.ensure_initial_admin(db)  # 관리자가 있으면 아무것도 하지 않음
        assert db.query(User).filter(User.email == "boss@example.com").count() == 1
    finally:
        for a in admins:
            a.role = UserRole.ADMIN
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_login_accepts_reserved_domain_email_of_bootstrapped_admin():
    # 회귀: ADMIN_EMAIL=admin@test.local로 만든 관리자가 EmailStr 검사 때문에 로그인하지 못하던 문제
    user = create_user()
    update_user(user.id, email="admin@corp.local")
    async with new_client() as client:
        assert (await login(client, "Admin@Corp.local")).status_code == 200
