"""Engineering analyst agent with a bounded evidence-gathering loop."""

from .ports import GitHubClient, LLMClient
from .schemas import CodeContext, CommitData


class EngineeringAnalystAgent:
    """Reconstruct the bug or bottleneck addressed by a selected commit."""

    def __init__(
        self, github: GitHubClient, llm: LLMClient, max_iterations: int = 3
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1.")
        self.github = github
        self.llm = llm
        self.max_iterations = max_iterations

    def run(self, commit: CommitData) -> CodeContext:
        before_code: dict[str, str] = {}
        after_code: dict[str, str] = {}
        context = CodeContext(commit=commit, issue_explanation="")

        for _ in range(self.max_iterations):
            for file in commit.files_changed:
                if file.status != "added":
                    before_code.setdefault(
                        file.path,
                        self.github.get_file(
                            commit.repository, file.path, commit.parent_sha
                        ),
                    )
                if file.status != "removed":
                    after_code.setdefault(
                        file.path,
                        self.github.get_file(
                            commit.repository, file.path, commit.commit_sha
                        ),
                    )

            context = self.llm.explain_change(commit, before_code, after_code)
            if not context.missing_context:
                return context

        raise ValueError(
            "Unable to reconstruct the commit with available repository context: "
            + ", ".join(context.missing_context)
        )
