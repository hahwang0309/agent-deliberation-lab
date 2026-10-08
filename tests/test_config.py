"""설정 중앙 관리: 모델명·파라미터는 config/config.yaml에만 둔다"""
import re
from pathlib import Path

import pytest
import yaml

from config.config_loader import AppConfig
from config.discussion_config import get_config
from src.core.debate_state import DynamicsParams, persuasion

ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = re.compile(r"[\"'](gpt-\d|claude-[a-z0-9]|gemini-\d|gemini-pro|mistral-(large|small|medium)|open-mistral)")


def _config():
    return yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))


def test_no_model_names_hardcoded_in_application_code():
    offenders = [f"{p.relative_to(ROOT)}:{i}" for d in ("src", "api", "scripts") for p in (ROOT / d).rglob("*.py")
                 for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if MODEL_NAME.search(line)]
    assert offenders == [], f"model names belong in config/config.yaml: {offenders}"


@pytest.mark.parametrize("section,key", [("engine", "dynamics_step"), ("llm", "default_models"), ("limits", "max_personas")])
def test_missing_config_key_is_an_error_not_a_silent_default(section, key):
    data = _config()
    del data[section][key]
    with pytest.raises(ValueError, match=key):
        AppConfig.from_dict(data)


def test_unknown_config_key_or_section_is_an_error():
    data = _config()
    data["engine"]["typo_param"] = 1
    with pytest.raises(ValueError, match="typo_param"):
        AppConfig.from_dict(data)
    with pytest.raises(ValueError, match="ui"):
        AppConfig.from_dict({**_config(), "ui": {}})


def test_persuasion_weights_come_from_config():
    full = {"quality": 1.0, "novelty": 1.0, "value_match": 0.0, "credibility": 0.0, "receptive": 0.0}
    base = DynamicsParams.from_settings(get_config())
    assert persuasion(full, base) == pytest.approx((1 - base.value_match_weight) * (1 - base.credibility_weight)
                                                   * (1 - base.receptive_weight))
    assert persuasion(full, DynamicsParams.from_settings(get_config(), value_match_weight=0.0, credibility_weight=0.0,
                                                         receptive_weight=0.0)) == pytest.approx(1.0)
