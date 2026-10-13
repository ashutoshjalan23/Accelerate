"""Deterministic tests for the Problem Creator workflow."""

import pathlib
import json
import sys
import unittest
from urllib.request import Request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.agents.problem_creator import ProblemCreatorAgent
from app.agents.llm import CuratorLLMClient
from app.agents.schemas import CodeContext, CommitData, GeneratedProblem


def make_context() -> CodeContext:
    commit = CommitData(
        repository="owner/repository",
        commit_sha="after",
        parent_sha="before",
        message="Fix behavior",
        diff="diff",
    )
    return CodeContext(
        commit=commit,
        before_code={"src/main.py": "def solve(value):\n    return value\n"},
        after_code={"src/main.py": "def solve(value):\n    return value + 1\n"},
        issue_explanation="The old implementation returned the wrong result.",
        requirements=["Return the corrected result."],
        relevant_files=["src/main.py"],
    )


class FakeProblemLLM:
    def __init__(self) -> None:
        self.draft_calls = 0
        self.validation_calls = 0

    def draft_problem(self, context: CodeContext) -> GeneratedProblem:
        self.draft_calls += 1
        return GeneratedProblem(
            title="Correct the result",
            description="Implement solve so it returns the corrected result.",
            constraints=["The input is an integer."],
            starter_files={"src/main.py": "model-invented content"},
            examples=[{"input": "1", "output": "2"}],
            hidden_test_cases=[{"input": "2", "output": "3"}],
            reference_solution="return value + 1",
            source_commit_sha=context.commit.commit_sha,
        )

    def validate_problem(
        self, problem: GeneratedProblem, context: CodeContext
    ) -> tuple[bool, str]:
        self.validation_calls += 1
        if self.validation_calls == 1:
            return False, "Clarify the expected result."
        return True, "The task is self-contained."


class ProblemCreatorTests(unittest.TestCase):
    def test_llm_parser_accepts_fenced_json_and_trailing_text(self) -> None:
        parsed = CuratorLLMClient._parse_json(
            'Here is the result:\n```json\n{"title": "Challenge"}\n```\nDone.'
        )
        self.assertEqual(parsed, {"title": "Challenge"})

    def test_llm_parser_reports_truncated_json(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
            CuratorLLMClient._parse_json('{"title": "truncated"')

    def test_problem_draft_request_avoids_source_duplication(self) -> None:
        captured: dict[str, object] = {}

        def post(request: Request) -> bytes:
            captured.update(json.loads(request.data))
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "title": "Challenge",
                                        "description": "Solve it.",
                                        "source_commit_sha": "after",
                                    }
                                )
                            }
                        }
                    ]
                }
            ).encode()

        client = CuratorLLMClient(
            openrouter_api_key="test-key",
            http_post=post,
        )
        client.draft_problem(make_context())

        self.assertEqual(captured["max_tokens"], 2048)
        self.assertEqual(captured["reasoning"], {"enabled": False})
        prompt = captured["messages"][0]["content"]
        self.assertIn('"starter_files": {}', prompt)
        self.assertNotIn('"before_code"', prompt)
        self.assertNotIn('"after_code"', prompt)

    def test_openrouter_truncation_is_reported_before_json_parsing(self) -> None:
        def post(request: Request) -> bytes:
            return json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": '{"title": "partial"'},
                        }
                    ]
                }
            ).encode()

        client = CuratorLLMClient(openrouter_api_key="test-key", http_post=post)
        with self.assertRaisesRegex(RuntimeError, "truncated"):
            client._generate_with_openrouter("test")

    def test_retries_and_materializes_exact_before_state(self) -> None:
        llm = FakeProblemLLM()
        problem = ProblemCreatorAgent(llm, max_iterations=2).run(make_context())

        self.assertEqual(llm.draft_calls, 2)
        self.assertEqual(llm.validation_calls, 2)
        self.assertEqual(
            problem.starter_files,
            {"src/main.py": "def solve(value):\n    return value\n"},
        )
        self.assertIn("def solve(value):", problem.starting_code)

    def test_rejects_problem_after_iteration_limit(self) -> None:
        class AlwaysInvalid(FakeProblemLLM):
            def validate_problem(
                self, problem: GeneratedProblem, context: CodeContext
            ) -> tuple[bool, str]:
                self.validation_calls += 1
                return False, "Not self-contained."

        llm = AlwaysInvalid()
        with self.assertRaisesRegex(ValueError, "Not self-contained"):
            ProblemCreatorAgent(llm, max_iterations=2).run(make_context())
        self.assertEqual(llm.draft_calls, 2)
        self.assertEqual(llm.validation_calls, 2)


if __name__ == "__main__":
    unittest.main()
