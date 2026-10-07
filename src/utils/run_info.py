"""
실행 기록 - 토론 1회 실행을 다시 만들거나 조건을 검증하는 데 필요한 정보

코드 커밋, 프롬프트 파일 해시, 실제 적용된 설정 전체, 참가자·모더레이터·분석 모델과 temperature,
주요 패키지 버전을 모은다. git이 없는 환경(Docker 등)에서는 커밋 정보가 null이다.
"""
import hashlib
import platform
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILES = ("config/prompts.yaml", "config/report_prompts.yaml", "config/rag_prompts.yaml",
                "config/persona_templates.yaml", "config/config.yaml")
PACKAGES = ("langchain-core", "langchain-anthropic", "anthropic", "langchain-openai", "langchain-google-genai")


def _git(*args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _sha256(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return None


def _version(package: str) -> Optional[str]:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def collect_run_info(settings: Any, llm_spec: Dict[str, Any], resumed: bool = False) -> Dict[str, Any]:
    status = _git("status", "--porcelain")
    return {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "resumed": resumed,
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(status) if status is not None else None,  # 커밋되지 않은 변경이 있었는가
        "prompt_hashes": {f: _sha256(ROOT / f) for f in PROMPT_FILES},
        "settings": asdict(settings),
        "llm": llm_spec,
        "python": platform.python_version(),
        "packages": {p: _version(p) for p in PACKAGES if _version(p)},
    }
