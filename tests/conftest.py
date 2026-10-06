"""
pytest 공통 설정 - 임시 SQLite DB와 테스트용 환경변수
api 모듈 import 전에 환경변수를 설정해야 하므로 최상단에서 처리한다.
"""
import os
import tempfile

_tmpdir = tempfile.mkdtemp(prefix="discussion-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db"
os.environ["LEGACY_EXPORT_DIR"] = f"{_tmpdir}/legacy_export"
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import pytest  # noqa: E402

from api.database import init_db  # noqa: E402


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
