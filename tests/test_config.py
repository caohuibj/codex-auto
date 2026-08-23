from pathlib import Path

import pytest
from pydantic import ValidationError

from codex_auto.config import AppConfig, load_config

from .helpers import make_config


def test_human_merge_gate_cannot_be_disabled():
    raw = make_config().model_dump(mode="json")
    raw["policy"]["human_merge_required"] = False

    with pytest.raises(ValidationError):
        AppConfig.model_validate(raw)


def test_unknown_route_provider_is_rejected():
    raw = make_config().model_dump(mode="json")
    raw["routing"]["review"]["provider"] = "missing"

    with pytest.raises(ValidationError, match="unknown provider"):
        AppConfig.model_validate(raw)


def test_repository_example_config_loads():
    root = Path(__file__).parents[1]
    config = load_config(root / "config/orchestrator.example.yml")

    assert config.routing.planning.model == "gpt-5.6-sol"
    assert config.routing.implementation.model == "gpt-5.6-luna"
    assert config.policy.human_merge_required is True


def test_invalid_cost_rate_is_rejected():
    raw = make_config().model_dump(mode="json")
    raw["cost"]["models"]["sol-model"]["input_per_million"] = "not-a-number"

    with pytest.raises(ValidationError, match="decimal string"):
        AppConfig.model_validate(raw)
