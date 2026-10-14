"""Curator and scout agent."""

import re
from .ports import EngineeringAnalyst, GitHubClient, LLMClient
from .schemas import CodeContext, CommitData, RepositoryInput, SelectedCommit


class CuratorScoutAgent:
    """Find a problem-worthy commit and pass it to the engineering analyst."""

    def __init__(
        self, github: GitHubClient, llm: LLMClient, analyst: EngineeringAnalyst
    ) -> None:
        self.github = github
        self.llm = llm
        self.analyst = analyst

    def run(self, repository: RepositoryInput) -> CodeContext:
        """Scout, assess, and analyze the first suitable commit."""

        commit = self.select_commit(repository)
        return self.analyst.run(commit)

    def select_commit(self, repository: RepositoryInput) -> CommitData:
        """Return a commit accepted by the LLM as suitable for a problem."""

        return self.select_commit_with_assessment(repository).commit

    def select_commit_with_assessment(
        self, repository: RepositoryInput
    ) -> SelectedCommit:
        """Return an accepted commit together with the LLM's assessment."""

        repository_name = repository.repository
        commits = self.github.list_commits(repository_name, limit=50)
        candidates = [commit for commit in commits if self._is_meaningful(commit)]
        if not candidates:
            raise ValueError("No candidate commits remained after heuristic filtering.")

        for commit in candidates:
            assessment = self.llm.assess_commit(commit)
            if assessment.suitable:
                return SelectedCommit(commit=commit, assessment=assessment)

        raise ValueError("The LLM found no commit suitable for turning into a problem.")

    @staticmethod
    def _repository_name(url: str) -> str:
        return RepositoryInput(github_url=url).repository

    @staticmethod
    def _is_meaningful(commit: CommitData) -> bool:
        message = commit.message.lower()
        trivial_terms = ("readme", "typo", "format", "chore", "bump version")
        return not any(re.search(r"\b" + re.escape(term) + r"\b", message) for term in trivial_terms)
