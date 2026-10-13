"""Smoke-test the curator, engineering analyst, and problem creator workflow.

Usage:
    python test.py https://github.com/pallets/flask

Set GITHUB_TOKEN and either GEMINI_API_KEY or OPENROUTER_API_KEY before running.
"""

import argparse
import logging
import sys

from app.agents.curator import CuratorScoutAgent
from app.cache import load_analyst_context, save_analyst_context
from app.agents.engineering_analyst import EngineeringAnalystAgent
from app.agents.llm import CuratorLLMClient
from app.agents.problem_creator import ProblemCreatorAgent
from app.agents.schemas import RepositoryInput
from app.integrations.github import GitHubClientAdapter, GitHubApiError


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Run the Accelerate generation pipeline for a GitHub repository."
    )
    parser.add_argument(
        "repository",
        nargs="?",
        default="https://github.com/pallets/flask",
        help="GitHub repository URL or owner/name (default: pallets/flask)",
    )
    parser.add_argument(
        "--show-starter-code",
        action="store_true",
        help="Print the exact before-state code given to the generated problem.",
    )
    parser.add_argument(
        "--cached-sha",
        help=(
            "Skip Curator and Engineering Analyst, then run Problem Creator "
            "from the cached analyst result for this commit SHA."
        ),
    )
    args = parser.parse_args()

    try:
        repository = RepositoryInput(github_url=args.repository)
        llm = CuratorLLMClient()
        if args.cached_sha:
            repository_name = repository.github_url.path.strip("/")
            context = load_analyst_context(repository_name, args.cached_sha)
            if context is None:
                raise ValueError(
                    "No cached analyst result found for "
                    f"{repository_name}@{args.cached_sha}. "
                    "Run the normal pipeline or tests\\analyst_test.py first."
                )
            selected = context.commit
            print("Using cached Engineering Analyst output.", flush=True)
            print("Skipping Curator and Engineering Analyst.")
        else:
            github = GitHubClientAdapter()
            analyst = EngineeringAnalystAgent(github=github, llm=llm)
            curator = CuratorScoutAgent(github=github, llm=llm, analyst=analyst)

            print("Running Curator (GitHub + LLM assessment)...", flush=True)
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

            cached_context = load_analyst_context(
                selected.repository, selected.commit_sha
            )
            if cached_context is not None:
                print("\nUsing cached Engineering Analyst output.", flush=True)
                context = cached_context
            else:
                print("\nRunning Engineering Analyst...", flush=True)
                context = analyst.run(selected)
                save_analyst_context(context)
                print("Engineering Analyst output cached.", flush=True)

        print("\nSelected commit:")
        print(f"  Repository: {selected.repository}")
        print(f"  SHA:        {selected.commit_sha}")
        print(f"  Message:    {selected.message.splitlines()[0]}")
        print("\nEngineering analysis completed:")
        print(f"  Before files: {len(context.before_code)}")
        print(f"  After files:  {len(context.after_code)}")
        print(f"  Requirements: {len(context.requirements)}")
        print(f"  Relevant files: {len(context.relevant_files)}")
        print(f"  Missing context: {len(context.missing_context)}")
        print("\nIssue explanation:")
        print(context.issue_explanation)
        if context.requirements:
            print("\nRequirements:")
            for requirement in context.requirements:
                print(f"  - {requirement}")

        print("\nRunning Problem Creator...", flush=True)
        problem = ProblemCreatorAgent(llm=llm).run(context)
        print("\nGenerated problem:")
        print(f"  Title: {problem.title}")
        print("\nProblem statement:")
        print(problem.description)
        if problem.constraints:
            print("\nConstraints:")
            for constraint in problem.constraints:
                print(f"  - {constraint}")
        if problem.examples:
            print("\nExamples:")
            for index, example in enumerate(problem.examples, start=1):
                print(f"  Example {index}:")
                print(f"    Input:  {example.get('input', '')}")
                print(f"    Output: {example.get('output', '')}")

        print("\nLearner starter workspace:")
        for path, contents in problem.starter_files.items():
            print(f"  - {path} ({len(contents)} characters, before-commit state)")
            if args.show_starter_code:
                print("    " + "\n    ".join(contents.splitlines()))

        print("\nPipeline completed successfully.")
        return 0
    except (ValueError, RuntimeError, GitHubApiError) as error:
        print(f"Accelerate pipeline test failed: {error}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
