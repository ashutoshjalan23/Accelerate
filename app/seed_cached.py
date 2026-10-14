"""Import existing generated challenges or checked-in demos without API calls."""

import argparse
import json
from pathlib import Path

from .agents.schemas import CommitData, GeneratedProblem
from .persistence import ChallengeStore

DEMO_PATH = Path(__file__).resolve().parents[1] / "tests/fixtures/cached_challenges.json"


def seed_demos(store: ChallengeStore, path: Path = DEMO_PATH) -> list[int]:
    ids = []
    for item in json.loads(path.read_text(encoding="utf-8")):
        problem = GeneratedProblem.model_validate(item["problem"])
        commit = CommitData.model_validate(item["commit"])
        ids.append(store.save_challenge(commit.repository, commit.commit_sha, problem, commit))
    return ids


def import_legacy(store: ChallengeStore) -> list[int]:
    # Read only the old table; its historical payloads/reviews are not rewritten.
    with store._connection() as db:
        exists = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='challenges'").fetchone()
        if not exists:
            return []
        rows = db.execute("SELECT payload, commit_payload FROM challenges").fetchall()
    ids = []
    for row in rows:
        old = json.loads(row["payload"])
        commit = CommitData.model_validate_json(row["commit_payload"])
        paths = list(old.get("starter_files", {})) or [file.previous_path or file.path for file in commit.files_changed]
        problem = GeneratedProblem(title=old["title"], description=old["description"],
            constraints=old.get("constraints", []), relevant_files=paths,
            acceptance_criteria=old.get("constraints") or ["Resolve the behavior described in the challenge and add regression coverage."],
            setup_notes=["Follow the checked-out README and contribution guide. Setup has not been verified."],
            verification_notes=["Imported prototype challenge: inspect the acceptance criteria before using it for learning. Run checks locally."],
            source_commit_sha=commit.commit_sha)
        ids.append(store.save_challenge(commit.repository, commit.commit_sha, problem, commit))
    return ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=".data/accelerate.sqlite3")
    parser.add_argument("--demo", action="store_true", help="Load curated cached Flask and xxHash demos.")
    args = parser.parse_args()
    store = ChallengeStore(args.database)
    ids = seed_demos(store) if args.demo else import_legacy(store)
    print(f"Loaded {len(ids)} cached challenges. No GitHub or LLM requests made.")


if __name__ == "__main__":
    main()
