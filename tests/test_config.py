from pathlib import Path

import pytest
from pydantic import ValidationError

from codex_auto.config import AppConfig, load_config

from .helpers import make_config


def test_human_integration_gate_cannot_be_disabled():
    raw = make_config().model_dump(mode="json")
    raw["policy"]["human_integration_required"] = False

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
    assert config.policy.human_integration_required is True


def test_invalid_cost_rate_is_rejected():
    raw = make_config().model_dump(mode="json")
    raw["cost"]["models"]["sol-model"]["input_per_million"] = "not-a-number"

    with pytest.raises(ValidationError, match="decimal string"):
        AppConfig.model_validate(raw)


def test_chatgpt_app_provider_rejects_api_key_configuration():
    raw = make_config().model_dump(mode="json")
    raw["providers"] = {"app": {"type": "chatgpt_app", "api_key_env": "OPENAI_API_KEY"}}
    for route in raw["routing"].values():
        route["provider"] = "app"

    with pytest.raises(ValidationError, match="must not configure an API key"):
        AppConfig.model_validate(raw)


def test_v1_github_first_config_loads_through_explicit_compatibility_mapper():
    raw = make_config().model_dump(mode="json")
    repository = raw.pop("repository")
    raw["github"] = {
        "repository": "owner/repo",
        "base_branch": repository["base_branch"],
        "verification_commands": repository["verification_commands"],
        "required_ci_checks": ["quality"],
    }
    raw["policy"] = {
        "max_fix_cycles": 2,
        "human_merge_required": True,
        "protocol_version": "v1",
    }

    config = AppConfig.model_validate(raw)

    assert config.repository.identifier == "owner/repo"
    assert config.github is not None
    assert config.github.required_checks == ["quality"]
    assert config.policy.human_integration_required is True
