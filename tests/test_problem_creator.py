"""Offline agent tests: no provider credentials or network are used."""

import json
import os
import unittest
from unittest.mock import Mock, patch

from app.agents.llm import CuratorLLMClient
from app.agents.problem_creator import ProblemCreatorAgent
from app.agents.schemas import CodeContext, CommitData, GeneratedProblem, RepositoryInput
from app.orchestration.langgraph_generation import LangGraphGenerationWorkflow
from app.seed_cached import DEMO_PATH


def inputs():
    item = json.loads(DEMO_PATH.read_text(encoding="utf-8"))[0]
    commit = CommitData.model_validate(item["commit"])
    problem = GeneratedProblem.model_validate(item["problem"])
    return CodeContext(commit=commit, before_code={path: "cached source" for path in problem.relevant_files},
        issue_explanation="QUERY routing is unavailable.", relevant_files=problem.relevant_files), problem


class ProblemCreatorTests(unittest.TestCase):
    def test_validation_sees_final_paths_and_revisions_are_bounded(self):
        context, problem = inputs()
        llm = Mock()
        llm.draft_problem.return_value = problem.model_copy(update={"relevant_files": []})
        llm.validate_problem.side_effect = [(False, "Clarify behavior"), (True, "grounded")]
        result = ProblemCreatorAgent(llm).run(context)
        self.assertEqual(result.relevant_files, sorted(context.relevant_files))
        self.assertEqual(llm.draft_problem.call_count, 2)
        self.assertIn("Clarify behavior", llm.draft_problem.call_args.args[0].issue_explanation)
        self.assertEqual(llm.validate_problem.call_args.args[0].relevant_files, result.relevant_files)
        self.assertNotIn("starter_files", result.model_dump())

    def test_invalid_json_and_invented_paths_can_be_revised(self):
        context, problem = inputs()
        llm = Mock()
        llm.draft_problem.side_effect = [RuntimeError("Invalid JSON"),
            problem.model_copy(update={"relevant_files": ["invented.py"]}), problem]
        llm.validate_problem.return_value = (True, "grounded")
        result = ProblemCreatorAgent(llm).run(context)
        self.assertEqual(result.title, problem.title)
        self.assertEqual(llm.draft_problem.call_count, 3)
        llm.validate_problem.assert_called_once()

    def test_rejects_after_iteration_limit(self):
        context, problem = inputs()
        llm = Mock()
        llm.draft_problem.return_value = problem
        llm.validate_problem.return_value = (False, "Leaks patch")
        with self.assertRaisesRegex(ValueError, "Leaks patch"):
            ProblemCreatorAgent(llm, max_iterations=2).run(context)
        self.assertEqual(llm.draft_problem.call_count, 2)

    def test_cached_analyst_context_skips_curator_and_github(self):
        context, problem = inputs()
        github, llm = Mock(), Mock()
        llm.draft_problem.return_value = problem
        llm.validate_problem.return_value = (True, "grounded")
        workflow = LangGraphGenerationWorkflow(github=github, llm=llm)
        with patch("app.orchestration.langgraph_generation.find_analyst_context", return_value=context):
            result = workflow.run(RepositoryInput(github_url="pallets/flask"))
        self.assertEqual(result.context, context)
        github.list_commits.assert_not_called()
        github.get_file.assert_not_called()
        llm.assess_commit.assert_not_called()
        llm.explain_change.assert_not_called()

    def test_draft_prompt_is_small_and_requests_no_generated_code_or_solution(self):
        context, problem = inputs()
        captured = {}
        def post(request):
            captured.update(json.loads(request.data))
            return json.dumps({"choices": [{"message": {"content": problem.model_dump_json()}}]}).encode()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "OPENROUTER_API_KEY": ""}):
            client = CuratorLLMClient(openrouter_api_key="fake", http_post=post)
        self.assertEqual(client.draft_problem(context), problem)
        prompt = captured["messages"][0]["content"]
        self.assertNotIn('"before_code"', prompt)
        self.assertNotIn('"after_code"', prompt)
        self.assertNotIn('"reference_solution":', prompt)
        self.assertNotIn('"hidden_test_cases":', prompt)
        self.assertEqual(captured["max_tokens"], 2048)

    def test_parser_and_truncation(self):
        self.assertEqual(CuratorLLMClient._parse_json('```json\n{"valid":true}\n```'), {"valid": True})
        with self.assertRaises(RuntimeError):
            CuratorLLMClient._parse_json('{"title":')

    def test_meaningful_message_is_not_rejected_for_information_substring(self):
        from app.agents.curator import CuratorScoutAgent
        context, _ = inputs()
        self.assertTrue(CuratorScoutAgent._is_meaningful(context.commit.model_copy(update={"message": "Fix information loss"})))
