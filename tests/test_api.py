import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.api import create_app
from app.persistence import ChallengeStore
from app.seed_cached import DEMO_PATH, seed_demos


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = ChallengeStore(Path(self.directory.name) / "test.sqlite3")
        self.ids = seed_demos(self.store)
        self.workflow = Mock()
        self.workflow.run.side_effect = AssertionError("No paid generation allowed")
        self.client = TestClient(create_app(store=self.store, workflow=self.workflow))

    def test_cached_generation_listing_and_reveal_make_no_provider_calls(self):
        with patch("socket.create_connection", side_effect=AssertionError("Network disabled")):
            response = self.client.post("/challenges/generate", json={"github_url": "pallets/flask"})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["cached"])
            public = response.json()["challenge"]
            commit = self.store.get_commit(public["id"])
            self.assertEqual(public["workspace"]["base_sha"], commit.parent_sha)
            self.assertIn(commit.parent_sha, "\n".join(public["workspace"]["checkout_commands"]))
            for url in ("/challenges", f"/challenges/{public['id']}"):
                payload = self.client.get(url)
                self.assertEqual(payload.status_code, 200)
                self.assertNotIn(commit.commit_sha, payload.text)
                self.assertNotIn("reference_solution", payload.text)
                self.assertNotIn("hidden_test_cases", payload.text)
            self.assertNotIn(commit.commit_sha, response.text)
            revealed = self.client.get(f"/challenges/{public['id']}/solution").json()
            self.assertEqual(revealed["diff"], commit.diff)
            self.assertEqual(revealed["commit_sha"], commit.commit_sha)
        self.workflow.run.assert_not_called()

    def test_makefile_challenge_is_supported_without_python_execution(self):
        response = self.client.post("/challenges/generate", json={"github_url": "Cyan4973/xxHash"})
        self.assertEqual(response.status_code, 200)
        problem = response.json()["challenge"]["problem"]
        self.assertIn("build/make/multiconf.make", problem["relevant_files"])
        self.assertEqual(self.client.post(f"/challenges/{self.ids[0]}/review", json={"code": "pass"}).status_code, 404)

    def test_cache_miss_does_not_fall_back_to_paid_generation(self):
        response = self.client.post("/challenges/generate", json={"github_url": "owner/unknown"})
        self.assertEqual(response.status_code, 409)
        self.workflow.run.assert_not_called()

    def test_live_generation_is_explicit_and_errors_are_actionable(self):
        self.workflow.run.side_effect = RuntimeError("private provider details")
        response = self.client.post("/challenges/generate", json={"github_url": "owner/new", "cache_only": False})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private provider details", response.text)

    def test_input_and_missing_resource_errors(self):
        for repository in ("https://evil.example/owner/repo", "https://github.com/a/b/tree/main", "owner/repo;echo"):
            response = self.client.post("/challenges/generate", json={"github_url": repository})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/challenges?limit=101").status_code, 422)
        self.assertEqual(self.client.get("/challenges/999").status_code, 404)
        self.assertEqual(self.client.get("/challenges/999/solution").status_code, 404)

    def test_live_pipeline_result_is_persisted_and_reused(self):
        from app.agents.schemas import CodeContext, CommitData, GeneratedProblem
        from app.orchestration.langgraph_generation import GenerationResult
        item = json.loads(DEMO_PATH.read_text(encoding="utf-8"))[0]
        commit = CommitData.model_validate(item["commit"]).model_copy(update={"repository": "owner/new"})
        problem = GeneratedProblem.model_validate(item["problem"])
        self.workflow.run.side_effect = None
        self.workflow.run.return_value = GenerationResult(context=CodeContext(commit=commit, issue_explanation="Issue"), problem=problem)
        first = self.client.post("/challenges/generate", json={"github_url": "owner/new", "cache_only": False})
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["cached"])
        second = self.client.post("/challenges/generate", json={"github_url": "owner/new"})
        self.assertTrue(second.json()["cached"])
        self.assertEqual(first.json()["challenge_id"], second.json()["challenge_id"])
        self.workflow.run.assert_called_once()
