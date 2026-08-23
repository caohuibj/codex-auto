"""Provider and repository boundaries used by the orchestration core."""

from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from codex_auto.config import ModelRoute
from codex_auto.models import (
    ImplementationProposal,
    PullRequestEvidence,
    RepositorySnapshot,
    TaskContract,
    UsageRecord,
    VerificationResult,
)

OutputT = TypeVar("OutputT", bound=BaseModel)


class ModelCompletion(BaseModel):
    output: BaseModel
    usage: UsageRecord


class ResponsesClient(Protocol):
    def complete(
        self,
        *,
        phase: str,
        route: ModelRoute,
        instructions: str,
        input_data: dict[str, Any],
        output_type: type[OutputT],
        metadata: dict[str, str],
    ) -> tuple[OutputT, UsageRecord]: ...


class GitHubAdapter(Protocol):
    def snapshot(self, context_paths: list[str]) -> RepositorySnapshot: ...

    def create_feature_branch(self, branch: str, base_sha: str) -> None: ...

    def apply_proposal(self, branch: str, proposal: ImplementationProposal) -> list[str]: ...

    def run_verification(self, names: list[str]) -> list[VerificationResult]: ...

    def commit_and_push(self, branch: str, message: str, paths: list[str]) -> str: ...

    def open_or_update_pull_request(
        self, branch: str, contract: TaskContract, verification: list[VerificationResult]
    ) -> tuple[int, str]: ...

    def collect_pull_request_evidence(
        self, number: int, verification: list[VerificationResult]
    ) -> PullRequestEvidence: ...
