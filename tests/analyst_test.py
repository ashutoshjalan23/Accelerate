r"""Run the Engineering Analyst directly for one commit.

Usage:
    .\.venv\Scripts\python.exe tests\analyst_test.py pallets/flask SHA
    .\.venv\Scripts\python.exe tests\analyst_test.py https://github.com/pallets/flask SHA

Set GITHUB_TOKEN and either GEMINI_API_KEY or OPENROUTER_API_KEY first.
"""

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.agents.engineering_analyst import EngineeringAnalystAgent
from app.cache import load_analyst_context, save_analyst_context
from app.agents.llm import CuratorLLMClient
from app.integrations.github import GitHubApiError, GitHubClientAdapter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Engineering Analyst for a specific commit SHA."
    )
    parser.add_argument(
        "repository",
        help="GitHub repository URL or owner/name, for example pallets/flask",
    )
    parser.add_argument("sha", help="Commit SHA to analyze")
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum analyst context-retrieval iterations (default: 3)",
    )
    args = parser.parse_args()

    try:
        github = GitHubClientAdapter()
        llm = CuratorLLMClient()
        commit = github.get_commit(args.repository, args.sha)
        context = load_analyst_context(commit.repository, commit.commit_sha)
        if context is None:
            context = EngineeringAnalystAgent(
                github=github,
                llm=llm,
                max_iterations=args.max_iterations,
            ).run(commit)
            save_analyst_context(context)
            print("Engineering Analyst output cached.")
        else:
            print("Using cached Engineering Analyst output.")
    except (ValueError, RuntimeError, GitHubApiError) as error:
        print(f"Engineering Analyst test failed: {error}", file=sys.stderr)
        return 1

    print("Engineering analysis completed.")
    print(f"Repository: {commit.repository}")
    print(f"Commit:     {commit.commit_sha}")
    print(f"Message:    {commit.message.splitlines()[0]}")
    print(f"Before files: {len(context.before_code)}")
    print(f"After files:  {len(context.after_code)}")
    print(f"Requirements: {len(context.requirements)}")
    print(f"Missing context: {len(context.missing_context)}")
    print("\nIssue explanation:")
    print(context.issue_explanation)
    if context.requirements:
        print("\nRequirements:")
        for requirement in context.requirements:
            print(f"- {requirement}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
