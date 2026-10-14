"""Immutable SQLite challenges; maintainer evidence stays private until reveal."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .agents.schemas import CommitData, GeneratedProblem
from .local_challenge import validate_source, workspace, solution


class ChallengeStore:
    def __init__(self, database_path: str | Path = ".data/accelerate.sqlite3") -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            # Preserve historical prototype data for offline import.
            db.execute("""CREATE TABLE IF NOT EXISTS local_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repository TEXT NOT NULL,
                commit_sha TEXT NOT NULL,
                payload TEXT NOT NULL,
                commit_payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(repository, commit_sha)
            )""")

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.database_path)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_challenge(self, repository: str, commit_sha: str,
                       problem: GeneratedProblem, commit: CommitData) -> int:
        validate_source(commit, problem)
        if repository != commit.repository or commit_sha != commit.commit_sha:
            raise ValueError("Challenge identity does not match its source evidence.")
        with self._connection() as db:
            db.execute("""INSERT INTO local_challenges
                (repository, commit_sha, payload, commit_payload) VALUES (?, ?, ?, ?)
                ON CONFLICT(repository, commit_sha) DO NOTHING""",
                (repository, commit_sha, problem.model_dump_json(), commit.model_dump_json()))
            row = db.execute("SELECT id FROM local_challenges WHERE repository=? AND commit_sha=?",
                             (repository, commit_sha)).fetchone()
        return row["id"]

    def _row(self, challenge_id: int):
        with self._connection() as db:
            return db.execute("SELECT * FROM local_challenges WHERE id=?", (challenge_id,)).fetchone()

    def get_challenge(self, challenge_id: int) -> GeneratedProblem | None:
        row = self._row(challenge_id)
        return GeneratedProblem.model_validate_json(row["payload"]) if row else None

    def get_commit(self, challenge_id: int) -> CommitData | None:
        row = self._row(challenge_id)
        return CommitData.model_validate_json(row["commit_payload"]) if row else None

    @staticmethod
    def _export(row) -> dict:
        problem = GeneratedProblem.model_validate_json(row["payload"])
        commit = CommitData.model_validate_json(row["commit_payload"])
        # Explicit public projection excludes solution evidence and the fixed SHA.
        return {"id": row["id"], "repository": row["repository"],
                "created_at": row["created_at"],
                "problem": problem.model_dump(exclude={"source_commit_sha"}),
                "workspace": workspace(commit, problem)}

    def export_challenge(self, challenge_id: int) -> dict | None:
        row = self._row(challenge_id)
        return self._export(row) if row else None

    def find_challenge(self, repository: str) -> dict | None:
        with self._connection() as db:
            row = db.execute("SELECT * FROM local_challenges WHERE repository=? COLLATE NOCASE ORDER BY id DESC LIMIT 1",
                             (repository,)).fetchone()
        return self._export(row) if row else None

    def list_challenges(self, limit: int = 20) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        with self._connection() as db:
            rows = db.execute("SELECT * FROM local_challenges ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._export(row) for row in rows]

    def reveal_solution(self, challenge_id: int) -> dict | None:
        commit = self.get_commit(challenge_id)
        return solution(commit) if commit else None
