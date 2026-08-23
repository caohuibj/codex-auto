"""Scaffold a repository-local codex-auto installation without global state."""

from __future__ import annotations

import shlex
from importlib.resources import files
from pathlib import Path

import yaml

from codex_auto.config import AppConfig


class ProjectInitError(ValueError):
    pass


_GITIGNORE_BLOCK = """# codex-auto project-local runtime
.codex-auto/runtime/
.codex-auto/.env
.codex-auto/audit/
.codex-auto/tasks/
.codex-auto/results/
"""

_LAUNCHER = """#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
env_file="$project_root/.codex-auto/.env"
runtime="$project_root/.codex-auto/runtime/bin/codex-auto"

if [ -f "$env_file" ]; then
  set -a
  . "$env_file"
  set +a
fi

if [ ! -x "$runtime" ]; then
  echo "codex-auto project runtime is missing: $runtime" >&2
  echo "Install it with the command in docs/PROJECT_LOCAL_INSTALLATION.md." >&2
  exit 2
fi

exec "$runtime" "$@"
"""


def parse_verification_specs(specs: list[str]) -> dict[str, list[str]]:
    commands: dict[str, list[str]] = {}
    for spec in specs:
        name, separator, command = spec.partition("=")
        name = name.strip()
        if not separator or not name or not command.strip():
            raise ProjectInitError(
                "verification must use NAME=COMMAND, for example unit=uv run pytest -q"
            )
        if name in commands:
            raise ProjectInitError(f"duplicate verification name: {name}")
        argv = shlex.split(command)
        if not argv:
            raise ProjectInitError(f"verification command is empty: {name}")
        commands[name] = argv
    if not commands:
        raise ProjectInitError("at least one --verification NAME=COMMAND is required")
    return commands


def _render_template(relative_path: str, repository: str) -> str:
    template = files("codex_auto").joinpath("templates", relative_path).read_text(encoding="utf-8")
    return template.replace("__REPOSITORY__", repository)


def _write_managed(path: Path, content: str, *, force: bool, executable: bool = False) -> None:
    if path.exists() and path.read_text(encoding="utf-8") != content and not force:
        raise ProjectInitError(f"refusing to overwrite existing project file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def _append_gitignore(root: Path) -> None:
    path = root / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if "# codex-auto project-local runtime" in existing:
        return
    separator = "" if not existing or existing.endswith("\n") else "\n"
    prefix = "" if not existing else "\n"
    path.write_text(existing + separator + prefix + _GITIGNORE_BLOCK, encoding="utf-8")


def initialize_project(
    *,
    repo_path: str | Path,
    repository: str,
    base_branch: str,
    production_branch: str,
    sol_model: str,
    luna_model: str,
    verification_specs: list[str],
    required_ci_checks: list[str],
    max_fix_cycles: int,
    execution_mode: str = "chatgpt-app",
    force: bool = False,
) -> list[Path]:
    root = Path(repo_path).resolve()
    if not (root / ".git").exists():
        raise ProjectInitError(f"target must be a git repository or worktree: {root}")
    commands = parse_verification_specs(verification_specs)

    if execution_mode not in {"chatgpt-app", "responses-api"}:
        raise ProjectInitError("execution_mode must be chatgpt-app or responses-api")
    app_native = execution_mode == "chatgpt-app"
    provider_name = "chatgpt_app" if app_native else "openai"
    config = AppConfig.model_validate(
        {
            "providers": {
                provider_name: {
                    "type": provider_name,
                    "api_key_env": None if app_native else "OPENAI_API_KEY",
                    "timeout_seconds": 180,
                    "store": False,
                }
            },
            "routing": {
                "planning": {
                    "provider": provider_name,
                    "model": sol_model,
                    "reasoning_effort": "high",
                    "max_output_tokens": 8000,
                },
                "implementation": {
                    "provider": provider_name,
                    "model": luna_model,
                    "reasoning_effort": "max",
                    "max_output_tokens": 20000,
                },
                "review": {
                    "provider": provider_name,
                    "model": sol_model,
                    "reasoning_effort": "high",
                    "max_output_tokens": 10000,
                },
                "fix": {
                    "provider": provider_name,
                    "model": luna_model,
                    "reasoning_effort": "max",
                    "max_output_tokens": 12000,
                },
            },
            "github": {
                "repository": repository,
                "base_branch": base_branch,
                "verification_commands": commands,
                "required_ci_checks": required_ci_checks,
            },
            "policy": {
                "max_fix_cycles": max_fix_cycles,
                "human_merge_required": True,
                "protocol_version": "v1",
            },
            "audit": {"path": ".codex-auto/audit/{task_id}.jsonl"},
        }
    )
    project_profile = {
        "protocol": {"repository": "caohuibj/codex-auto", "version": "v1"},
        "project": {
            "repository": repository,
            "integration_branch": base_branch,
            "production_branch": production_branch,
        },
        "workflow": {
            "execution_mode": execution_mode,
            "human_merge_required": True,
            "feature_branch_pattern": "codex-auto/*",
            "task_contract_required": True,
            "independent_review_required": True,
        },
        "architecture": {"protected_boundaries": [], "prohibited_changes": []},
        "verification": {"required": list(commands), "conditional": []},
        "quality": {"avoid": ["unrelated refactor", "unnecessary abstraction"]},
        "escalation": {
            "always_escalate": [
                "auth/security boundary changes",
                "destructive data migration",
                "public API break",
            ]
        },
    }

    managed: dict[Path, tuple[str, bool]] = {
        root / ".codex-auto/project.yml": (
            yaml.safe_dump(project_profile, sort_keys=False, allow_unicode=True),
            False,
        ),
        root / ".codex-auto/orchestrator.yml": (
            yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
            False,
        ),
        root / ".codex-auto/.env.example": (
            (
                "# ChatGPT App mode uses the signed-in ChatGPT subscription.\n"
                "# No OpenAI API key or copied ChatGPT token is required.\n"
            )
            if app_native
            else "OPENAI_API_KEY=replace_me\n",
            False,
        ),
        root / ".codex-auto/bin/codex-auto": (_LAUNCHER, True),
        root / ".agents/skills/codex-auto/SKILL.md": (
            _render_template("codex-auto/SKILL.md", repository),
            False,
        ),
        root / ".agents/skills/codex-auto/agents/openai.yaml": (
            _render_template("codex-auto/agents/openai.yaml", repository),
            False,
        ),
        root / ".agents/skills/codex-auto/references/app-workflow.md": (
            _render_template("codex-auto/references/app-workflow.md", repository),
            False,
        ),
    }
    conflicts = [
        path
        for path, (content, _) in managed.items()
        if path.exists() and path.read_text(encoding="utf-8") != content
    ]
    if conflicts and not force:
        joined = ", ".join(str(path) for path in conflicts)
        raise ProjectInitError(f"refusing to overwrite existing project files: {joined}")
    for path, (content, executable) in managed.items():
        _write_managed(path, content, force=force, executable=executable)
    _append_gitignore(root)
    return list(managed)
