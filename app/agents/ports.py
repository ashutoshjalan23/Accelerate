"""Small dependency-injection ports used by the agents."""

from collections.abc import Sequence
from typing import Protocol

from .schemas import (
    CodeContext,
    CommitAssessment,
    CommitData,
    GeneratedProblem,
    ReviewReport,
)


class GitHubClient(Protocol):
    """Repository operations required by the agent workflows."""

    def list_commits(self, repository: str, limit: int = 50) -> Sequence[CommitData]:
        ...

    def get_commit(self, repository: str, sha: str) -> CommitData:
        ...

    def get_file(self, repository: str, path: str, ref: str) -> str:
        ...


class LLMClient(Protocol):
    """Structured generation interface implemented by Gemini/OpenRouter adapters."""

    def assess_commit(self, commit: CommitData) -> CommitAssessment:
        ...

    def explain_change(
        self, commit: CommitData, before_code: dict[str, str], after_code: dict[str, str]
    ) -> CodeContext:
        ...

    def draft_problem(self, context: CodeContext) -> GeneratedProblem:
        ...

    def validate_problem(
        self, problem: GeneratedProblem, context: CodeContext
    ) -> tuple[bool, str]:
        ...

    def review_submission(
        self,
        submission: object,
        problem: GeneratedProblem,
        commit: CommitData,
    ) -> ReviewReport:
        ...


class EngineeringAnalyst(Protocol):
    """The analyst operation required by the curator."""

    def run(self, commit: CommitData) -> CodeContext:
        ...
