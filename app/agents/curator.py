"""Curator and scout agent."""

from .ports import EngineeringAnalyst, GitHubClient, LLMClient
from .schemas import CodeContext, CommitData, RepositoryInput


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

        repository_name = self._repository_name(str(repository.github_url))
        commits = self.github.list_commits(repository_name, limit=50)
        candidates = [commit for commit in commits if self._is_meaningful(commit)]
        if not candidates:
            raise ValueError("No candidate commits remained after heuristic filtering.")

        for commit in candidates:
            assessment = self.llm.assess_commit(commit)
            if assessment.suitable:
                return commit

        raise ValueError("The LLM found no commit suitable for turning into a problem.")

    @staticmethod
    def _repository_name(url: str) -> str:
        return url.rstrip("/").removesuffix(".git").split("github.com/", 1)[-1]

    @staticmethod
    def _is_meaningful(commit: CommitData) -> bool:
        message = commit.message.lower()
        trivial_terms = ("readme", "typo", "format", "chore", "bump version")
        return not any(term in message for term in trivial_terms)
