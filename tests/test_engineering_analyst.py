"""Deterministic tests for the Engineering Analyst workflow."""

import pathlib
import sys
import unittest

# Allow this file to be run directly as well as through unittest discovery.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.agents.engineering_analyst import EngineeringAnalystAgent
from app.agents.schemas import CodeContext, CommitData, ChangedFile


class FakeGitHub:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []

    def get_file(self, repository: str, path: str, ref: str) -> str:
        self.requests.append((path, ref))
        return f"{path}@{ref}"


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    def explain_change(
        self,
        commit: CommitData,
        before_code: dict[str, str],
        after_code: dict[str, str],
    ) -> CodeContext:
        self.calls += 1
        missing = ["src/dependency.py"] if self.calls == 1 else []
        return CodeContext(
            commit=commit,
            before_code=before_code,
            after_code=after_code,
            issue_explanation="The old implementation mishandled the request.",
            requirements=["Preserve the expected request behavior."],
            missing_context=missing,
        )


def make_commit() -> CommitData:
    return CommitData(
        repository="owner/repository",
        commit_sha="after",
        parent_sha="before",
        message="Fix request handling",
        diff="diff",
        files_changed=[
            ChangedFile(path="src/changed.py", status="modified"),
            ChangedFile(path="src/added.py", status="added"),
            ChangedFile(path="src/removed.py", status="removed"),
        ],
    )


class EngineeringAnalystTests(unittest.TestCase):
    def test_fetches_changed_files_and_missing_dependency_then_reanalyzes(self) -> None:
        github = FakeGitHub()
        llm = FakeLLM()

        context = EngineeringAnalystAgent(
            github=github, llm=llm, max_iterations=2
        ).run(make_commit())

        self.assertEqual(llm.calls, 2)
        self.assertEqual(context.missing_context, [])
        self.assertIn(("src/changed.py", "before"), github.requests)
        self.assertIn(("src/changed.py", "after"), github.requests)
        self.assertNotIn(("src/added.py", "before"), github.requests)
        self.assertNotIn(("src/removed.py", "after"), github.requests)
        self.assertIn(("src/dependency.py", "before"), github.requests)
        self.assertIn(("src/dependency.py", "after"), github.requests)

    def test_raises_when_context_remains_missing_at_iteration_limit(self) -> None:
        github = FakeGitHub()

        class AlwaysMissing(FakeLLM):
            def explain_change(self, commit, before_code, after_code):
                self.calls += 1
                return CodeContext(
                    commit=commit,
                    before_code=before_code,
                    after_code=after_code,
                    issue_explanation="Insufficient evidence.",
                    missing_context=["missing.py"],
                )

        llm = AlwaysMissing()
        with self.assertRaisesRegex(ValueError, "missing.py"):
            EngineeringAnalystAgent(
                github=github, llm=llm, max_iterations=2
            ).run(make_commit())
        self.assertEqual(llm.calls, 2)


if __name__ == "__main__":
    unittest.main()
