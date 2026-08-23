"""Minimal command-line entry point for one orchestration run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from codex_auto.audit import JsonlAuditLog
from codex_auto.config import load_config
from codex_auto.github import LocalGitHubAdapter
from codex_auto.models import TaskRequest, TaskState
from codex_auto.orchestrator import Orchestrator
from codex_auto.project_init import ProjectInitError, initialize_project
from codex_auto.responses import OpenAIResponsesClient


def _load_mapping(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a mapping")
    return raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-auto")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser(
        "init-project", help="create a repository-local installation and Codex skill"
    )
    init.add_argument("--repo-path", required=True, type=Path)
    init.add_argument("--repository", required=True)
    init.add_argument("--base-branch", default="main")
    init.add_argument("--production-branch", default="main")
    init.add_argument("--sol-model", default="gpt-5.6-sol")
    init.add_argument("--luna-model", default="gpt-5.6-luna")
    init.add_argument(
        "--verification",
        action="append",
        default=[],
        metavar="NAME=COMMAND",
        help="trusted verification command; repeat for each check",
    )
    init.add_argument("--required-ci-check", action="append", default=[])
    init.add_argument("--max-fix-cycles", type=int, default=2)
    init.add_argument("--force", action="store_true")

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
    if args.command == "init-project":
        try:
            created = initialize_project(
                repo_path=args.repo_path,
                repository=args.repository,
                base_branch=args.base_branch,
                production_branch=args.production_branch,
                sol_model=args.sol_model,
                luna_model=args.luna_model,
                verification_specs=args.verification,
                required_ci_checks=args.required_ci_check,
                max_fix_cycles=args.max_fix_cycles,
                force=args.force,
            )
        except (ProjectInitError, ValueError) as exc:
            print(json.dumps({"initialized": False, "error": str(exc)}), file=sys.stderr)
            return 2
        print(json.dumps({"initialized": True, "files": [str(path) for path in created]}, indent=2))
        return 0

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
