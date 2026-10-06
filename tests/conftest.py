"""
pytest 공통 설정 - 임시 SQLite DB, 테스트 환경변수, 로그인 클라이언트
api 모듈 import 전에 환경변수를 설정해야 하므로 최상단에서 처리한다.
"""
import os
import tempfile
import uuid

_tmpdir = tempfile.mkdtemp(prefix="discussion-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db"
os.environ["LEGACY_EXPORT_DIR"] = f"{_tmpdir}/legacy_export"
os.environ["SECRET_KEY"] = "test-secret-" + "x" * 40
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import httpx  # noqa: E402
import pytest  # noqa: E402

from api.database import SessionLocal, init_db  # noqa: E402
from api.models.user import User, UserRole, UserStatus  # noqa: E402
from api.utils.security import hash_password  # noqa: E402

PASSWORD = "Corr3ct-horse-battery"


@pytest.fixture(scope="session", autouse=True)
def database():
    init_db()
    yield


@pytest.fixture(autouse=True)
def stub_report_llm(monkeypatch):
    """보고서 LLM은 기본적으로 가짜 구현 (실제 API 호출 방지)"""
    from api.runtime import reports
    from tests.report_stubs import default_stub
    monkeypatch.setattr(reports, "create_report_llm", lambda callbacks: default_stub())


def create_user(role=UserRole.USER, status=UserStatus.ACTIVE, must_change_password=False, **fields) -> User:
    db = SessionLocal()
    try:
        user = User(email=f"{uuid.uuid4().hex[:10]}@example.com", name=fields.pop("name", "Tester"),
                    password_hash=hash_password(PASSWORD), role=role, status=status,
                    must_change_password=must_change_password, **fields)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def update_user(user_id: str, **fields) -> None:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        for k, v in fields.items():
            setattr(user, k, v)
        db.commit()
    finally:
        db.close()


def new_client() -> httpx.AsyncClient:
    from api.main import app
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> httpx.Response:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    if r.status_code == 200:
        client.headers["X-CSRF-Token"] = client.cookies["csrf_token"]
    return r


class LoggedInClient(httpx.AsyncClient):
    """async with 진입 시 주어진 사용자로 로그인하는 테스트 클라이언트"""

    def __init__(self, user: User):
        from api.main import app
        super().__init__(transport=httpx.ASGITransport(app=app), base_url="http://test")
        self.user = user

    async def __aenter__(self):
        await super().__aenter__()
        r = await login(self, self.user.email)
        assert r.status_code == 200, r.text
        return self
