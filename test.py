"""Smoke-test the curator and engineering analyst workflow.

Usage:
    python test.py https://github.com/pallets/flask

Set GITHUB_TOKEN and either GEMINI_API_KEY or OPENROUTER_API_KEY before running.
"""

import argparse
import sys

from app.agents.curator import CuratorScoutAgent
from app.agents.engineering_analyst import EngineeringAnalystAgent
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
        analyst = EngineeringAnalystAgent(github=github, llm=llm)
        curator = CuratorScoutAgent(github=github, llm=llm, analyst=analyst)

        selected_result = curator.select_commit_with_assessment(repository)
        selected = selected_result.commit
        print("Fetched and assessed up to 50 commits.")
        print("\nSelected commit:")
        print(f"  Repository: {selected.repository}")
        print(f"  SHA:        {selected.commit_sha}")
        print(f"  Message:    {selected.message.splitlines()[0]}")
        print(f"  Files:      {len(selected.files_changed)}")
        print(f"  Diff size:  {len(selected.diff)} characters")
        print(f"  Rationale:  {selected_result.assessment.rationale}")
        print("\nRunning Engineering Analyst...")

        context = analyst.run(selected)
        print("\nEngineering analysis completed:")
        print(f"  Before files: {len(context.before_code)}")
        print(f"  After files:  {len(context.after_code)}")
        print(f"  Requirements: {len(context.requirements)}")
        print(f"  Missing context: {len(context.missing_context)}")
        print("\nIssue explanation:")
        print(context.issue_explanation)
        if context.requirements:
            print("\nRequirements:")
            for requirement in context.requirements:
                print(f"  - {requirement}")
        return 0
    except (ValueError, RuntimeError, GitHubApiError) as error:
        print(f"Curator smoke test failed: {error}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
