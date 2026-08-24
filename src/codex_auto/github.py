"""Optional GitHub publication extension. It intentionally exposes no merge operation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codex_auto.config import GitHubConfig, RepositoryConfig
from codex_auto.models import (
    ChangeEvidence,
    CheckEvidence,
    RemoteChangeEvidence,
    TaskContract,
    VerificationResult,
)
from codex_auto.repository import LocalGitAdapter, RepositoryAdapterError


class GitHubAdapterError(RepositoryAdapterError):
    pass


class LocalGitHubAdapter(LocalGitAdapter):
    """Local Git core plus opt-in push, PR, and remote-check evidence."""

    def __init__(
        self,
        repo_path: str | Path,
        repository_config: RepositoryConfig,
        github_config: GitHubConfig,
    ) -> None:
        self.github_config = github_config
        self._remote_change: RemoteChangeEvidence | None = None
        super().__init__(repo_path, repository_config)
        remote_url = self._git("remote", "get-url", self.github_config.remote)
        normalized = remote_url.removesuffix(".git").replace(":", "/")
        expected = f"github.com/{self.github_config.repository}"
        if expected.lower() not in normalized.lower():
            raise GitHubAdapterError(
                f"remote {self.github_config.remote!r} is {remote_url!r}, "
                f"expected {self.github_config.repository!r}"
            )

    def publish_change(
        self, branch: str, contract: TaskContract, verification: list[VerificationResult]
    ) -> None:
        self._git("push", "-u", self.github_config.remote, branch)
        existing = self._run(["gh", "pr", "view", branch, "--json", "number,url"], check=False)
        if existing.returncode == 0:
            data = json.loads(existing.stdout)
        else:
            verification_lines = [
                f"- {item.name}: {item.status.value} (`{item.command}`)" for item in verification
            ]
            body = "\n".join(
                [
                    f"## Task\n\n{contract.task_id}",
                    f"## Base\n\n{contract.base_branch} @ `{contract.base_sha}`",
                    "## Contract\n\nGenerated and validated by codex-auto orchestration.",
                    "## Verification\n\n" + "\n".join(verification_lines),
                    "## Integration Gate\n\nHuman integration required; automation will not merge.",
                ]
            )
            created = self._run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    contract.base_branch,
                    "--head",
                    branch,
                    "--title",
                    contract.title,
                    "--body",
                    body,
                ]
            )
            url = created.stdout.strip().splitlines()[-1]
            viewed = self._run(["gh", "pr", "view", url, "--json", "number,url"])
            data = json.loads(viewed.stdout)
        self._remote_change = RemoteChangeEvidence(
            provider="github",
            reference=str(data["number"]),
            url=str(data["url"]),
        )

    def collect_change_evidence(
        self,
        branch: str,
        contract: TaskContract,
        verification: list[VerificationResult],
    ) -> ChangeEvidence:
        local = super().collect_change_evidence(branch, contract, verification)
        if self._remote_change is None:
            return local
        fields = "number,url,baseRefName,headRefName,headRefOid,statusCheckRollup"
        viewed = self._run(
            ["gh", "pr", "view", self._remote_change.reference, "--json", fields]
        )
        data: dict[str, Any] = json.loads(viewed.stdout)
        if str(data["baseRefName"]) != contract.base_branch:
            raise GitHubAdapterError("GitHub PR base branch does not match the contract")
        if str(data["headRefName"]) != branch or str(data["headRefOid"]) != local.head_sha:
            raise GitHubAdapterError("GitHub PR head does not match the current local commit")
        checks: list[CheckEvidence] = []
        for raw in data.get("statusCheckRollup") or []:
            checks.append(
                CheckEvidence(
                    name=raw.get("name") or raw.get("context") or "unknown",
                    status=str(raw.get("status") or raw.get("state") or "unknown"),
                    conclusion=raw.get("conclusion"),
                    url=raw.get("detailsUrl") or raw.get("targetUrl"),
                )
            )
        remote = RemoteChangeEvidence(
            provider="github",
            reference=str(data["number"]),
            url=str(data["url"]),
            checks=checks,
        )
        return local.model_copy(update={"remote": remote})
