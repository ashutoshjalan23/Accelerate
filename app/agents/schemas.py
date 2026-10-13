"""Typed contracts shared by the AceProgramming agents."""

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class RepositoryInput(BaseModel):
    """Input supplied to the repository scouting workflow."""

    github_url: HttpUrl


class ChangedFile(BaseModel):
    """A file changed by a selected commit."""

    path: str
    status: Literal["added", "modified", "removed", "renamed", "copied", "unknown"] = (
        "unknown"
    )
    additions: int = 0
    deletions: int = 0
    patch: str | None = None


class CommitData(BaseModel):
    """Evidence extracted from a meaningful repository commit."""

    repository: str
    commit_sha: str
    parent_sha: str
    message: str
    diff: str
    files_changed: list[ChangedFile] = Field(default_factory=list)
    pull_request_description: str | None = None


class CommitAssessment(BaseModel):
    """LLM assessment of whether a commit can become a self-contained problem."""

    suitable: bool
    rationale: str


class SelectedCommit(BaseModel):
    """A commit accepted by the curator and the evidence for that decision."""

    commit: CommitData
    assessment: CommitAssessment


class CodeContext(BaseModel):
    """Before and after code plus the reconstructed engineering context."""

    commit: CommitData
    before_code: dict[str, str] = Field(default_factory=dict)
    after_code: dict[str, str] = Field(default_factory=dict)
    issue_explanation: str
    requirements: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)


class GeneratedProblem(BaseModel):
    """A self-contained challenge generated from repository evidence."""

    title: str
    description: str
    constraints: list[str] = Field(default_factory=list)
    starting_code: str = ""
    examples: list[dict[str, str]] = Field(default_factory=list)
    hidden_test_cases: list[dict[str, str]] = Field(default_factory=list)
    reference_solution: str | None = None
    source_commit_sha: str


class UserSubmission(BaseModel):
    """A learner's submitted solution."""

    problem_id: str
    code: str
    language: str = "python"


class ReviewReport(BaseModel):
    """Structured feedback for a learner submission."""

    feedback: str
    score: float = Field(ge=0, le=100)
    complexity_analysis: str
    style_analysis: str
    solution_comparison: str
    passed_tests: bool | None = None
