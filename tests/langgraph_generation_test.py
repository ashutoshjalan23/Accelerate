"""Run live LangGraph generation; provider calls may incur costs."""

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.agents.schemas import RepositoryInput
from app.cache import load_analyst_context
from app.orchestration.langgraph_generation import LangGraphGenerationWorkflow


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Accelerate's top-level LangGraph generation workflow."
    )
    parser.add_argument("repository", help="GitHub URL or owner/name.")
    parser.add_argument(
        "--cached-sha",
        help="Skip Curator and Analyst and use a cached analyst context.",
    )
    args = parser.parse_args()

    try:
        repository = RepositoryInput(github_url=args.repository)
        workflow = LangGraphGenerationWorkflow()
        if args.cached_sha:
            repository_name = repository.github_url.path.strip("/")
            context = load_analyst_context(repository_name, args.cached_sha)
            if context is None:
                raise ValueError(
                    f"No cached analyst result found for "
                    f"{repository_name}@{args.cached_sha}."
                )
            problem = workflow.run_from_cached_context(context)
            print("LangGraph Problem Creator completed from cached context.")
            print(f"Repository: {context.commit.repository}")
            print(f"Commit:     {context.commit.commit_sha}")
        else:
            result = workflow.run(repository)
            context = result.context
            problem = result.problem
            print("LangGraph generation workflow completed.")
            print(f"Repository: {context.commit.repository}")
            print(f"Commit:     {context.commit.commit_sha}")
        print(f"Title:      {problem.title}")
        print("\nProblem statement:")
        print(problem.description)
        from app.local_challenge import workspace
        print("\n".join(workspace(context.commit, problem)["checkout_commands"]))
        return 0
    except (RuntimeError, ValueError) as error:
        print(f"LangGraph generation test failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
