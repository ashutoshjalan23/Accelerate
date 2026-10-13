"""Smoke-test the GitHub commit curator.

Usage:
    python test.py https://github.com/pallets/flask

Set GEMINI_API_KEY or OPENROUTER_API_KEY before running the LLM assessment.
"""

import argparse
import sys

from app.agents.curator import CuratorScoutAgent
from app.agents.llm import CuratorLLMClient
from app.agents.schemas import RepositoryInput
from app.integrations.github import GitHubClientAdapter, GitHubApiError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether the curator identifies a useful GitHub commit."
    )
    parser.add_argument(
        "repository",
        nargs="?",
        default="https://github.com/pallets/flask",
        help="GitHub repository URL or owner/name (default: pallets/flask)",
    )
    args = parser.parse_args()

    try:
        repository = RepositoryInput(github_url=args.repository)
        github = GitHubClientAdapter()
        llm = CuratorLLMClient()
        curator = CuratorScoutAgent(github=github, llm=llm, analyst=_UnusedAnalyst())

        selected_result = curator.select_commit_with_assessment(repository)
        selected = selected_result.commit
        print(f"Fetched and assessed up to 50 commits.")
        print("\nSelected commit:")
        print(f"  Repository: {selected.repository}")
        print(f"  SHA:        {selected.commit_sha}")
        print(f"  Message:    {selected.message.splitlines()[0]}")
        print(f"  Files:      {len(selected.files_changed)}")
        print(f"  Diff size:  {len(selected.diff)} characters")
        print(f"  Rationale:  {selected_result.assessment.rationale}")
        return 0
    except (ValueError, RuntimeError, GitHubApiError) as error:
        print(f"Curator smoke test failed: {error}", file=sys.stderr)
        return 1


class _UnusedAnalyst:
    """Placeholder because this smoke test exercises commit selection only."""

    def run(self, commit: object) -> object:
        raise RuntimeError("The smoke test does not run the engineering analyst.")


if __name__ == "__main__":
    raise SystemExit(main())
