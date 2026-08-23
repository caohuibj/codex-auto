"""Minimal command-line entry point for one orchestration run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from codex_auto.audit import JsonlAuditLog
from codex_auto.config import load_config
from codex_auto.github import LocalGitHubAdapter
from codex_auto.models import TaskRequest, TaskState
from codex_auto.orchestrator import Orchestrator
from codex_auto.responses import OpenAIResponsesClient


def _load_mapping(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a mapping")
    return raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-auto")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate config and task files")
    validate.add_argument("--config", required=True, type=Path)
    validate.add_argument("--task", required=True, type=Path)

    run = subparsers.add_parser("run", help="run one bounded orchestration task")
    run.add_argument("--config", required=True, type=Path)
    run.add_argument("--task", required=True, type=Path)
    run.add_argument("--repo-path", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    task = TaskRequest.model_validate(_load_mapping(args.task))
    if args.command == "validate":
        print(json.dumps({"valid": True, "task_id": task.task_id}, indent=2))
        return 0

    clients = {
        name: OpenAIResponsesClient(name, provider) for name, provider in config.providers.items()
    }
    audit_path = Path(config.audit.path.format(task_id=task.task_id))
    if not audit_path.is_absolute():
        audit_path = args.repo_path.resolve() / audit_path
    audit = JsonlAuditLog(audit_path, task.task_id, config.audit.max_payload_chars)
    github = LocalGitHubAdapter(args.repo_path, config.github)
    result = Orchestrator(config, clients, github, audit).run(task)
    print(result.model_dump_json(indent=2))
    return 0 if result.state == TaskState.MERGE_READY else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
