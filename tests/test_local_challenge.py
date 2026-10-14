"""Verify the generated commands against a real, entirely local Git history."""

import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.agents.schemas import ChangedFile, CommitData, GeneratedProblem
from app.local_challenge import workspace


class CheckoutTests(unittest.TestCase):
    def test_new_and_renamed_paths_link_to_the_correct_before_state(self):
        commit = CommitData(repository="owner/demo", parent_sha="a" * 40,
            commit_sha="b" * 40, message="fix", diff="diff", files_changed=[
                ChangedFile(path="new.py", status="added"),
                ChangedFile(path="renamed.py", previous_path="old.py", status="renamed")])
        problem = GeneratedProblem(title="Fix", description="Resolve failure",
            relevant_files=["new.py", "renamed.py"], acceptance_criteria=["Works"], source_commit_sha=commit.commit_sha)
        files = workspace(commit, problem)["files"]
        self.assertIsNone(files[0]["url"])
        self.assertTrue(files[1]["url"].endswith("/old.py"))

    def test_checkout_commands_start_at_before_revision_on_new_working_branch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source repo"
            source.mkdir()
            def git(*args, cwd=source):
                return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                    text=True, check=True).stdout.strip()
            git("init")
            (source / "main.txt").write_text("broken", encoding="utf-8")
            git("add", "main.txt")
            git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "before")
            before = git("rev-parse", "HEAD")
            (source / "main.txt").write_text("fixed", encoding="utf-8")
            git("add", "main.txt")
            git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "after")
            after = git("rev-parse", "HEAD")
            commit = CommitData(repository="owner/demo", parent_sha=before,
                commit_sha=after, message="fix", diff="diff")
            problem = GeneratedProblem(title="Fix", description="Resolve failure",
                relevant_files=["main.txt"], acceptance_criteria=["Works"], source_commit_sha=after)
            generated = workspace(commit, problem)
            cwd = root
            for command in generated["checkout_commands"]:
                arguments = shlex.split(command)
                if arguments[0] == "cd":
                    cwd = root / arguments[1]
                    continue
                if arguments[1] == "clone":
                    arguments[3] = str(source)  # Substitute local transport; never access GitHub.
                subprocess.run(arguments, cwd=cwd, capture_output=True, text=True, check=True)
            self.assertEqual(git("rev-parse", "HEAD", cwd=cwd), before)
            self.assertEqual((cwd / "main.txt").read_text(encoding="utf-8"), "broken")
            self.assertTrue(git("branch", "--show-current", cwd=cwd).startswith("accelerate/"))
            self.assertEqual(generated["relevant_directories"], ["."])
