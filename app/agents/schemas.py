"""Typed contracts shared by the Accelerate agents."""

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator
from urllib.parse import urlparse
import re


class RepositoryInput(BaseModel):
    """Input supplied to the repository scouting workflow."""

    github_url: HttpUrl

    @field_validator("github_url", mode="before")
    @classmethod
    def normalize_repository(cls, value):
        raw = str(value).strip()
        if "://" not in raw:
            raw = "https://github.com/" + raw
        parsed = urlparse(raw)
        path = parsed.path.strip("/").removesuffix(".git")
        if (parsed.scheme != "https" or parsed.netloc.lower() != "github.com"
                or parsed.params or parsed.query or parsed.fragment
                or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path)
                or any(part.startswith(".") for part in path.split("/"))):
            raise ValueError("Use a GitHub repository URL or owner/repository.")
        return f"https://github.com/{path}"

    @property
    def repository(self) -> str:
        return self.github_url.path.strip("/")


class ChangedFile(BaseModel):
    """A file changed by a selected commit."""

    path: str
    previous_path: str | None = None
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
    relevant_files: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(
        default_factory=list,
        description="Repository-relative file paths needed for another analysis pass.",
    )


class GeneratedProblem(BaseModel):
    """A local-repository task. Source solution evidence stays server-side."""

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    setup_notes: list[str] = Field(default_factory=list)
    verification_notes: list[str] = Field(default_factory=list)
    source_commit_sha: str
