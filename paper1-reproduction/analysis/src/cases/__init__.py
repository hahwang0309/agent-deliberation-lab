"""
연구용 사례 생성 - 공개 데이터에서 실험 계획(scripts/run_experiment.py 형식)을 만든다

- wason: DeliData 3명 집단 복제, 같은 구조의 새 변형 문항
- a1r: America in One Room 응답자 추출(정당 층화), 자료 상자, 실제 소집단 복제
- argq: IBM ArgQ 강·약 논거 선택과 공모자 대본
문구는 config/cases.yaml에 두고, 원자료는 data/raw/ 아래에 둔다(저장소에 포함하지 않음).
"""
from pathlib import Path
from typing import Any, Dict

import yaml

TEXTS_PATH = Path(__file__).resolve().parents[2] / "config" / "cases.yaml"


def texts() -> Dict[str, Any]:
    return yaml.safe_load(TEXTS_PATH.read_text(encoding="utf-8"))
