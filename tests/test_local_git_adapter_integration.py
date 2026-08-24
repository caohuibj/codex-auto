from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from codex_auto.config import RepositoryConfig
from codex_auto.models import TaskContract, VerificationStatus
from codex_auto.repository import LocalGitAdapter, RepositoryAdapterError

from .helpers import make_contract


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=True
    ).stdout.strip()


def make_local_repo(tmp_path: Path) -> Path:
    root = tmp_path / "local-only"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "codex-auto test")
    git(root, "config", "user.email", "codex-auto@example.invalid")
    (root / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    git(root, "add", "feature.py")
    git(root, "commit", "-m", "initial")
    return root


def local_config() -> RepositoryConfig:
    return RepositoryConfig(
        identifier="local-only",
        base_branch="main",
        verification_commands={
            "unit": ["python", "-c", "assert open('feature.py').read() == 'VALUE = 2\\n'"]
        },
    )


def contract_for(snapshot_sha: str) -> TaskContract:
    return make_contract().model_copy(
        update={
            "target_repository": "local-only",
            "base_sha": snapshot_sha,
            "protocol_version": "v2",
        }
    )


def test_local_git_flow_needs_no_remote_and_binds_evidence_to_commit(tmp_path):
    root = make_local_repo(tmp_path)
    adapter = LocalGitAdapter(root, local_config())
    snapshot = adapter.snapshot(["feature.py"])
    contract = contract_for(snapshot.base_sha)

    adapter.create_feature_branch("codex-auto/task-001", snapshot.base_sha)
    (root / "feature.py").write_text("VALUE = 2\n", encoding="utf-8")
    head_sha = adapter.commit_change(
        "codex-auto/task-001", "feat: update value", ["feature.py"]
    )
    verification = adapter.run_verification(["unit"])
    adapter.publish_change("codex-auto/task-001", contract, verification)
    evidence = adapter.collect_change_evidence(
        "codex-auto/task-001", contract, verification
    )

    assert git(root, "remote") == ""
    assert evidence.remote is None
    assert evidence.base_sha == snapshot.base_sha
    assert evidence.head_sha == head_sha
    assert "+VALUE = 2" in evidence.diff
    assert verification[0].status == VerificationStatus.PASS


def test_local_evidence_rejects_uncommitted_or_generated_drift(tmp_path):
    root = make_local_repo(tmp_path)
    adapter = LocalGitAdapter(root, local_config())
    snapshot = adapter.snapshot([])
    contract = contract_for(snapshot.base_sha)
    adapter.create_feature_branch("codex-auto/task-001", snapshot.base_sha)
    (root / "feature.py").write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(RepositoryAdapterError, match="worktree must be clean"):
        adapter.collect_change_evidence("codex-auto/task-001", contract, [])
