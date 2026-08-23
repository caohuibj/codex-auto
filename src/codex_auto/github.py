"""Local git + GitHub CLI adapter. It intentionally exposes no merge operation."""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from codex_auto.config import GitHubConfig
from codex_auto.models import (
    CheckEvidence,
    FileSnapshot,
    ImplementationProposal,
    PullRequestEvidence,
    RepositorySnapshot,
    TaskContract,
    VerificationResult,
    VerificationStatus,
)


class GitHubAdapterError(RuntimeError):
    pass


_DIFF_PATH = re.compile(r"^diff --git a/(.+) b/(.+)$")


class LocalGitHubAdapter:
    def __init__(self, repo_path: str | Path, config: GitHubConfig) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.config = config
        self._assert_repository_identity()

    def _run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            args,
            cwd=self.repo_path,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
        if check and completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise GitHubAdapterError(f"command failed ({' '.join(args)}): {detail}")
        return completed

    def _git(self, *args: str, input_text: str | None = None) -> str:
        return self._run(["git", *args], input_text=input_text).stdout.strip()

    def _assert_repository_identity(self) -> None:
        if not (self.repo_path / ".git").exists():
            raise GitHubAdapterError(f"not a git worktree: {self.repo_path}")
        remote_url = self._git("remote", "get-url", self.config.remote)
        normalized = remote_url.removesuffix(".git").replace(":", "/")
        expected = f"github.com/{self.config.repository}"
        if expected.lower() not in normalized.lower():
            raise GitHubAdapterError(
                f"remote {self.config.remote!r} is {remote_url!r}, "
                f"expected {self.config.repository!r}"
            )

    def _is_allowed(self, path: str) -> bool:
        def matches(pattern: str) -> bool:
            return fnmatch.fnmatch(path, pattern) or (
                pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:])
            )

        allowed = any(matches(pattern) for pattern in self.config.allowed_paths)
        forbidden = any(matches(pattern) for pattern in self.config.forbidden_paths)
        return allowed and not forbidden

    def _validate_path(self, path: str) -> None:
        candidate = PurePosixPath(path)
        if candidate.is_absolute() or ".." in candidate.parts or not path or path == "/dev/null":
            raise GitHubAdapterError(f"unsafe patch path: {path!r}")
        if not self._is_allowed(path):
            raise GitHubAdapterError(f"patch path is not allowed by policy: {path!r}")

    def snapshot(self, context_paths: list[str]) -> RepositorySnapshot:
        self._git("fetch", self.config.remote, self.config.base_branch)
        base_ref = f"{self.config.remote}/{self.config.base_branch}"
        base_sha = self._git("rev-parse", base_ref)
        tree_paths = self._git("ls-tree", "-r", "--name-only", base_sha).splitlines()
        requested = context_paths or [
            "README.md",
            "pyproject.toml",
            "package.json",
            ".codex-auto/project.yml",
        ]
        selected: list[str] = []
        for pattern in requested:
            matches = [
                path for path in tree_paths if path == pattern or fnmatch.fnmatch(path, pattern)
            ]
            selected.extend(matches)
        selected = list(dict.fromkeys(selected))

        files: list[FileSnapshot] = []
        remaining = self.config.context_max_bytes
        for path in selected:
            if remaining <= 0 or not self._is_allowed(path):
                continue
            raw = self._run(["git", "show", f"{base_sha}:{path}"], check=False)
            if raw.returncode != 0:
                continue
            encoded = raw.stdout.encode("utf-8", errors="replace")
            truncated = len(encoded) > remaining
            content = encoded[:remaining].decode("utf-8", errors="replace")
            files.append(FileSnapshot(path=path, content=content, truncated=truncated))
            remaining -= min(len(encoded), remaining)
        return RepositorySnapshot(
            repository=self.config.repository,
            base_branch=self.config.base_branch,
            base_sha=base_sha,
            files=files,
            tree_paths=tree_paths,
        )

    def create_feature_branch(self, branch: str, base_sha: str) -> None:
        if self._git("status", "--porcelain"):
            raise GitHubAdapterError("worktree must be clean before creating the feature branch")
        exists = self._run(["git", "show-ref", "--verify", f"refs/heads/{branch}"], check=False)
        if exists.returncode == 0:
            self._git("switch", branch)
            merge_base = self._git("merge-base", branch, base_sha)
            if merge_base != base_sha:
                raise GitHubAdapterError(
                    "existing feature branch does not descend from contract base"
                )
        else:
            self._git("switch", "-c", branch, base_sha)

    def _paths_from_patch(self, patch: str) -> list[str]:
        if any(
            marker in patch
            for marker in (
                "GIT binary patch",
                "new file mode 120000",
                "new file mode 160000",
                "Subproject commit ",
            )
        ):
            raise GitHubAdapterError(
                "binary, symbolic-link, and submodule patches are not supported"
            )
        paths: list[str] = []
        for line in patch.splitlines():
            match = _DIFF_PATH.match(line)
            if match:
                for path in match.groups():
                    self._validate_path(path)
                    paths.append(path)
            if line.startswith(("--- ", "+++ ")):
                raw_path = line[4:].split("\t", 1)[0]
                if raw_path != "/dev/null":
                    if not raw_path.startswith(("a/", "b/")):
                        raise GitHubAdapterError(f"unsafe unified diff header: {line!r}")
                    self._validate_path(raw_path[2:])
            if line == "+++ /dev/null" and not self.config.allow_deletions:
                raise GitHubAdapterError("file deletion is disabled by policy")
        if not paths:
            raise GitHubAdapterError("proposal does not contain a git unified diff")
        return list(dict.fromkeys(paths))

    def apply_proposal(self, branch: str, proposal: ImplementationProposal) -> list[str]:
        current = self._git("branch", "--show-current")
        if current != branch:
            raise GitHubAdapterError(f"refusing to patch branch {current!r}; expected {branch!r}")
        paths = self._paths_from_patch(proposal.unified_diff)
        self._run(["git", "apply", "--check", "-"], input_text=proposal.unified_diff)
        self._run(["git", "apply", "-"], input_text=proposal.unified_diff)
        actual = self._git("diff", "--name-only").splitlines()
        undeclared = sorted(set(actual) - set(paths))
        if undeclared:
            raise GitHubAdapterError(f"patch changed undeclared paths: {undeclared}")
        return paths

    def run_verification(self, names: list[str]) -> list[VerificationResult]:
        results: list[VerificationResult] = []
        for name in names:
            command = self.config.verification_commands.get(name)
            if command is None:
                results.append(
                    VerificationResult(
                        name=name,
                        command="",
                        status=VerificationStatus.NOT_RUN,
                        output="verification command is not configured",
                    )
                )
                continue
            completed = self._run(command, check=False)
            output = (completed.stdout + completed.stderr)[-20_000:]
            results.append(
                VerificationResult(
                    name=name,
                    command=" ".join(command),
                    status=(
                        VerificationStatus.PASS
                        if completed.returncode == 0
                        else VerificationStatus.FAIL
                    ),
                    exit_code=completed.returncode,
                    output=output,
                )
            )
        return results

    def commit_and_push(self, branch: str, message: str, paths: list[str]) -> str:
        current = self._git("branch", "--show-current")
        if current != branch:
            raise GitHubAdapterError(f"refusing to commit branch {current!r}; expected {branch!r}")
        self._run(["git", "add", "--", *paths])
        if not self._git("diff", "--cached", "--name-only"):
            raise GitHubAdapterError("proposal produced no staged changes")
        self._git("commit", "-m", message)
        head_sha = self._git("rev-parse", "HEAD")
        self._git("push", "-u", self.config.remote, branch)
        return head_sha

    def open_or_update_pull_request(
        self, branch: str, contract: TaskContract, verification: list[VerificationResult]
    ) -> tuple[int, str]:
        existing = self._run(["gh", "pr", "view", branch, "--json", "number,url"], check=False)
        if existing.returncode == 0:
            data = json.loads(existing.stdout)
            return int(data["number"]), str(data["url"])

        verification_lines = [
            f"- {item.name}: {item.status.value} (`{item.command}`)" for item in verification
        ]
        body = "\n".join(
            [
                f"## Task\n\n{contract.task_id}",
                f"## Base\n\n{contract.base_branch} @ `{contract.base_sha}`",
                "## Contract\n\nGenerated and validated by codex-auto orchestration.",
                "## Verification\n\n" + "\n".join(verification_lines),
                "## Merge Gate\n\nHuman merge required. The orchestrator will not merge this PR.",
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
        return int(data["number"]), str(data["url"])

    def collect_pull_request_evidence(
        self, number: int, verification: list[VerificationResult]
    ) -> PullRequestEvidence:
        fields = "number,url,baseRefName,headRefName,headRefOid,statusCheckRollup"
        viewed = self._run(["gh", "pr", "view", str(number), "--json", fields])
        data: dict[str, Any] = json.loads(viewed.stdout)
        diff = self._run(["gh", "pr", "diff", str(number)]).stdout
        head_sha = str(data["headRefOid"])
        base_sha = self._git("merge-base", f"{self.config.remote}/{data['baseRefName']}", head_sha)
        checks: list[CheckEvidence] = []
        for raw in data.get("statusCheckRollup") or []:
            name = raw.get("name") or raw.get("context") or "unknown"
            checks.append(
                CheckEvidence(
                    name=name,
                    status=str(raw.get("status") or raw.get("state") or "unknown"),
                    conclusion=raw.get("conclusion"),
                    url=raw.get("detailsUrl") or raw.get("targetUrl"),
                )
            )
        return PullRequestEvidence(
            number=int(data["number"]),
            url=str(data["url"]),
            base_branch=str(data["baseRefName"]),
            base_sha=base_sha,
            head_branch=str(data["headRefName"]),
            head_sha=head_sha,
            diff=diff,
            checks=checks,
            local_verification=verification,
        )
