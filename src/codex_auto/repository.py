"""Deterministic local Git adapter; no network remote is required or contacted."""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path, PurePosixPath

from codex_auto.config import RepositoryConfig
from codex_auto.models import (
    ChangeEvidence,
    FileSnapshot,
    ImplementationProposal,
    RepositorySnapshot,
    TaskContract,
    VerificationResult,
    VerificationStatus,
)


class RepositoryAdapterError(RuntimeError):
    pass


_DIFF_PATH = re.compile(r"^diff --git a/(.+) b/(.+)$")


class LocalGitAdapter:
    """Own local branches, commits, diffs, verification, and change evidence."""

    def __init__(self, repo_path: str | Path, config: RepositoryConfig) -> None:
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
            raise RepositoryAdapterError(f"command failed ({' '.join(args)}): {detail}")
        return completed

    def _git(self, *args: str, input_text: str | None = None) -> str:
        return self._run(["git", *args], input_text=input_text).stdout.strip()

    def _assert_repository_identity(self) -> None:
        result = self._run(["git", "rev-parse", "--is-inside-work-tree"], check=False)
        if result.returncode != 0 or result.stdout.strip() != "true":
            raise RepositoryAdapterError(f"not a git worktree: {self.repo_path}")

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
            raise RepositoryAdapterError(f"unsafe patch path: {path!r}")
        if not self._is_allowed(path):
            raise RepositoryAdapterError(f"patch path is not allowed by policy: {path!r}")

    def snapshot(self, context_paths: list[str]) -> RepositorySnapshot:
        if self._git("status", "--porcelain"):
            raise RepositoryAdapterError("worktree must be clean before creating a task snapshot")
        base_ref = f"refs/heads/{self.config.base_branch}"
        exists = self._run(["git", "show-ref", "--verify", base_ref], check=False)
        if exists.returncode != 0:
            raise RepositoryAdapterError(
                f"local base branch {self.config.base_branch!r} does not exist; "
                "fetch/update it manually before starting"
            )
        base_sha = self._git("rev-parse", base_ref)
        tree_paths = self._git("ls-tree", "-r", "--name-only", base_sha).splitlines()
        requested = context_paths or [
            "README.md",
            "pyproject.toml",
            "package.json",
            ".codex-auto/project.yml",
            "AGENTS.md",
        ]
        selected: list[str] = []
        for pattern in requested:
            selected.extend(
                path for path in tree_paths if path == pattern or fnmatch.fnmatch(path, pattern)
            )
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
            repository=self.config.identifier,
            base_branch=self.config.base_branch,
            base_sha=base_sha,
            files=files,
            tree_paths=tree_paths,
        )

    def create_feature_branch(self, branch: str, base_sha: str) -> None:
        if self._git("status", "--porcelain"):
            raise RepositoryAdapterError(
                "worktree must be clean before creating the feature branch"
            )
        exists = self._run(["git", "show-ref", "--verify", f"refs/heads/{branch}"], check=False)
        if exists.returncode == 0:
            self._git("switch", branch)
            merge_base = self._git("merge-base", branch, base_sha)
            if merge_base != base_sha:
                raise RepositoryAdapterError(
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
            raise RepositoryAdapterError(
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
                        raise RepositoryAdapterError(f"unsafe unified diff header: {line!r}")
                    self._validate_path(raw_path[2:])
                elif line.startswith("+++ ") and not self.config.allow_deletions:
                    raise RepositoryAdapterError("file deletion is disabled by policy")
        if not paths:
            raise RepositoryAdapterError("proposal does not contain a git unified diff")
        return list(dict.fromkeys(paths))

    def apply_proposal(self, branch: str, proposal: ImplementationProposal) -> list[str]:
        current = self._git("branch", "--show-current")
        if current != branch:
            raise RepositoryAdapterError(
                f"refusing to patch branch {current!r}; expected {branch!r}"
            )
        paths = self._paths_from_patch(proposal.unified_diff)
        self._run(["git", "apply", "--check", "-"], input_text=proposal.unified_diff)
        self._run(["git", "apply", "-"], input_text=proposal.unified_diff)
        actual = self._git("diff", "--name-only").splitlines()
        undeclared = sorted(set(actual) - set(paths))
        if undeclared:
            raise RepositoryAdapterError(f"patch changed undeclared paths: {undeclared}")
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

    def commit_change(self, branch: str, message: str, paths: list[str]) -> str:
        current = self._git("branch", "--show-current")
        if current != branch:
            raise RepositoryAdapterError(
                f"refusing to commit branch {current!r}; expected {branch!r}"
            )
        self._run(["git", "add", "--", *paths])
        if not self._git("diff", "--cached", "--name-only"):
            raise RepositoryAdapterError("proposal produced no staged changes")
        self._git("commit", "-m", message)
        return self._git("rev-parse", "HEAD")

    def publish_change(
        self, branch: str, contract: TaskContract, verification: list[VerificationResult]
    ) -> None:
        """Local mode intentionally performs no push and creates no remote review object."""

    def collect_change_evidence(
        self,
        branch: str,
        contract: TaskContract,
        verification: list[VerificationResult],
    ) -> ChangeEvidence:
        current = self._git("branch", "--show-current")
        if current != branch:
            raise RepositoryAdapterError(
                f"refusing to collect branch {current!r}; expected {branch!r}"
            )
        if self._git("status", "--porcelain"):
            raise RepositoryAdapterError("worktree must be clean before collecting evidence")
        head_sha = self._git("rev-parse", "HEAD")
        merge_base = self._git("merge-base", contract.base_sha, head_sha)
        if merge_base != contract.base_sha:
            raise RepositoryAdapterError("change no longer descends from the contract base")
        diff = self._git("diff", "--no-ext-diff", f"{contract.base_sha}...{head_sha}")
        return ChangeEvidence(
            base_branch=contract.base_branch,
            base_sha=contract.base_sha,
            head_branch=branch,
            head_sha=head_sha,
            diff=diff,
            local_verification=verification,
        )
