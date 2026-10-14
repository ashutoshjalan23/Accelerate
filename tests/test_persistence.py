import json
import tempfile
import unittest
from pathlib import Path

from app.agents.schemas import GeneratedProblem, CommitData
from app.persistence import ChallengeStore
from app.seed_cached import DEMO_PATH, seed_demos


class PersistenceTests(unittest.TestCase):
    def test_cached_import_is_idempotent_and_challenges_are_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChallengeStore(Path(directory) / "test.sqlite3")
            ids = seed_demos(store)
            self.assertEqual(seed_demos(store), ids)
            problem = store.get_challenge(ids[0])
            commit = store.get_commit(ids[0])
            same_id = store.save_challenge(commit.repository, commit.commit_sha,
                problem.model_copy(update={"description": "Changed task"}), commit)
            self.assertEqual(same_id, ids[0])
            self.assertEqual(store.get_challenge(same_id), problem)

    def test_rejects_mismatched_sha_and_unsafe_command_inputs(self):
        item = json.loads(DEMO_PATH.read_text(encoding="utf-8"))[0]
        problem = GeneratedProblem.model_validate(item["problem"])
        commit = CommitData.model_validate(item["commit"])
        with tempfile.TemporaryDirectory() as directory:
            store = ChallengeStore(Path(directory) / "test.sqlite3")
            for altered in (commit.model_copy(update={"parent_sha": "abc; bad"}),
                            commit.model_copy(update={"repository": "owner/repo;bad"})):
                with self.assertRaises(ValueError):
                    store.save_challenge(altered.repository, altered.commit_sha, problem, altered)
            with self.assertRaises(ValueError):
                store.save_challenge(commit.repository, commit.commit_sha,
                    problem.model_copy(update={"source_commit_sha": "0" * 40}), commit)
            with self.assertRaises(ValueError):
                store.save_challenge(commit.repository, commit.commit_sha,
                    problem.model_copy(update={"relevant_files": ["../escape"]}), commit)
