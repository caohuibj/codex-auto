from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from codex_auto.config import load_config, validate_chatgpt_app_routes
from codex_auto.project_init import (
    ProjectInitError,
    initialize_project,
    parse_verification_specs,
)


def init(root: Path, *, force: bool = False) -> list[Path]:
    return initialize_project(
        repo_path=root,
        repository="owner/example",
        base_branch="dev",
        production_branch="main",
        sol_model="sol-model",
        luna_model="luna-model",
        verification_specs=[
            "lint=uv run ruff check .",
            "unit=uv run pytest -q",
        ],
        required_ci_checks=[],
        max_fix_cycles=2,
        force=force,
    )


def make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "consumer"
    root.mkdir()
    (root / ".git").mkdir()
    return root


def test_parse_verification_specs_preserves_argument_boundaries():
    commands = parse_verification_specs(["unit=python -m pytest -k 'not slow'"])

    assert commands == {"unit": ["python", "-m", "pytest", "-k", "not slow"]}


def test_initialize_project_creates_repo_scoped_runtime_and_skill(tmp_path):
    root = make_repo(tmp_path)

    created = init(root)
    config = load_config(root / ".codex-auto/orchestrator.yml")

    assert len(created) == 10
    assert config.repository.identifier == "owner/example"
    assert config.repository.base_branch == "dev"
    assert config.repository.verification_commands["unit"] == ["uv", "run", "pytest", "-q"]
    assert config.github is None
    assert ".agents/skills/**" in config.repository.forbidden_paths
    assert ".codex/**" in config.repository.forbidden_paths
    assert "AGENTS.md" in config.repository.forbidden_paths
    assert config.policy.human_integration_required is True
    assert config.routing.planning.model == "sol-model"
    assert config.routing.implementation.model == "luna-model"
    assert config.providers["chatgpt_app"].type == "chatgpt_app"
    assert config.providers["chatgpt_app"].api_key_env is None

    skill = (root / ".agents/skills/codex-auto/SKILL.md").read_text(encoding="utf-8")
    assert "name: codex-auto" in skill
    assert "owner/example" in skill
    assert ".codex-auto/bin/codex-auto app-start" in skill
    assert "Do not invoke Codex CLI" in skill
    assert (root / ".agents/skills/codex-auto/references/app-workflow.md").exists()
    assert (root / ".codex-auto/bin/codex-auto").stat().st_mode & 0o111

    project_config = (root / ".codex/config.toml").read_text(encoding="utf-8")
    luna_agent = (root / ".codex/agents/luna-implementer.toml").read_text(encoding="utf-8")
    assert 'model = "sol-model"' in project_config
    assert 'default_subagent_model = "luna-model"' in project_config
    assert 'name = "luna_implementer"' in luna_agent
    assert 'model = "luna-model"' in luna_agent
    validate_chatgpt_app_routes(config, root)

    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert ".codex-auto/runtime/" in gitignore
    assert ".codex-auto/.env" in gitignore
    assert "$HOME" not in "\n".join(str(path) for path in created)
    assert "No OpenAI API key" in (root / ".codex-auto/.env.example").read_text(encoding="utf-8")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "GitHub is optional" in agents
    assert "human integration gate" in agents


def test_initialize_project_can_opt_in_to_github_publication(tmp_path):
    root = make_repo(tmp_path)

    initialize_project(
        repo_path=root,
        repository="example-local",
        github_repository="owner/example",
        remote="upstream",
        base_branch="main",
        production_branch="main",
        sol_model="sol-model",
        luna_model="luna-model",
        verification_specs=["unit=python -m pytest -q"],
        required_ci_checks=["quality"],
        max_fix_cycles=1,
    )

    config = load_config(root / ".codex-auto/orchestrator.yml")
    assert config.github is not None
    assert config.github.repository == "owner/example"
    assert config.github.remote == "upstream"
    assert config.github.required_checks == ["quality"]


def test_initialize_project_can_explicitly_select_responses_api(tmp_path):
    root = make_repo(tmp_path)

    initialize_project(
        repo_path=root,
        repository="owner/example",
        base_branch="main",
        production_branch="main",
        sol_model="sol-model",
        luna_model="luna-model",
        verification_specs=["unit=python -m pytest -q"],
        required_ci_checks=[],
        max_fix_cycles=1,
        execution_mode="responses-api",
    )

    config = load_config(root / ".codex-auto/orchestrator.yml")
    assert config.providers["openai"].api_key_env == "OPENAI_API_KEY"
    assert (root / ".codex-auto/.env.example").read_text(encoding="utf-8") == (
        "OPENAI_API_KEY=replace_me\n"
    )
    assert not (root / ".codex/config.toml").exists()


def test_chatgpt_app_route_validation_fails_closed_on_model_drift(tmp_path):
    root = make_repo(tmp_path)
    init(root)
    agent_path = root / ".codex/agents/luna-implementer.toml"
    agent_path.write_text(
        agent_path.read_text(encoding="utf-8").replace('model = "luna-model"', 'model = "other"'),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="luna_implementer route mismatch"):
        validate_chatgpt_app_routes(load_config(root / ".codex-auto/orchestrator.yml"), root)


def test_chatgpt_app_route_validation_requires_project_agent_files(tmp_path):
    root = make_repo(tmp_path)
    init(root)
    (root / ".codex/agents/luna-implementer.toml").unlink()

    with pytest.raises(ValueError, match="missing or invalid"):
        validate_chatgpt_app_routes(load_config(root / ".codex-auto/orchestrator.yml"), root)


def test_initialize_project_is_idempotent_and_does_not_duplicate_gitignore(tmp_path):
    root = make_repo(tmp_path)

    init(root)
    init(root)

    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert gitignore.count("# codex-auto project-local runtime") == 1
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.count("<!-- codex-auto:start -->") == 1


def test_initialize_project_preserves_existing_agents_rules(tmp_path):
    root = make_repo(tmp_path)
    (root / "AGENTS.md").write_text(
        "# Existing rules\n\nDo not change billing.\n", encoding="utf-8"
    )

    init(root)

    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# Existing rules\n")
    assert "Do not change billing." in agents
    assert "<!-- codex-auto:start -->" in agents


def test_required_remote_checks_require_explicit_github_mode(tmp_path):
    root = make_repo(tmp_path)

    with pytest.raises(ProjectInitError, match="explicit --github-repository"):
        initialize_project(
            repo_path=root,
            repository="local-only",
            base_branch="main",
            production_branch="main",
            sol_model="sol-model",
            luna_model="luna-model",
            verification_specs=["unit=python -m pytest -q"],
            required_ci_checks=["quality"],
            max_fix_cycles=1,
        )


def test_initialize_project_requires_force_for_managed_changes(tmp_path):
    root = make_repo(tmp_path)
    init(root)
    config_path = root / ".codex-auto/orchestrator.yml"
    config_path.write_text("custom: true\n", encoding="utf-8")

    with pytest.raises(ProjectInitError, match="refusing to overwrite"):
        init(root)

    init(root, force=True)
    assert "custom: true" not in config_path.read_text(encoding="utf-8")


@pytest.mark.skipif(os.name == "nt", reason="the project launcher is POSIX-only")
def test_project_launcher_loads_only_project_env_and_calls_local_runtime(tmp_path):
    root = make_repo(tmp_path)
    init(root)
    runtime = root / ".codex-auto/runtime/bin/codex-auto"
    runtime.parent.mkdir(parents=True)
    runtime.write_text(
        '#!/bin/sh\nprintf \'%s|%s\' "$OPENAI_API_KEY" "$*"\n',
        encoding="utf-8",
    )
    runtime.chmod(0o755)
    (root / ".codex-auto/.env").write_text("OPENAI_API_KEY=project-only-key\n", encoding="utf-8")

    completed = subprocess.run(
        [str(root / ".codex-auto/bin/codex-auto"), "validate", "--task", "task.yml"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
        env={key: value for key, value in os.environ.items() if key != "OPENAI_API_KEY"},
    )

    assert completed.stdout == "project-only-key|validate --task task.yml"
