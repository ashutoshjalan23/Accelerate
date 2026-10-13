"""Small persistent caches for expensive agent outputs."""

import hashlib
import json
from pathlib import Path

from .agents.schemas import CodeContext


def _cache_path(repository: str, commit_sha: str) -> Path:
    cache_key = hashlib.sha256(
        f"{repository}@{commit_sha}".encode("utf-8")
    ).hexdigest()
    return Path(".cache") / "analyst" / f"{cache_key}.json"


def load_analyst_context(repository: str, commit_sha: str) -> CodeContext | None:
    """Load a cached analyst result when it belongs to the requested commit."""

    path = _cache_path(repository, commit_sha)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        context = CodeContext.model_validate(data)
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError):
        return None
    if (
        context.commit.repository != repository
        or context.commit.commit_sha != commit_sha
    ):
        return None
    return context


def save_analyst_context(context: CodeContext) -> None:
    """Persist a completed analyst result for future runs."""

    path = _cache_path(context.commit.repository, context.commit.commit_sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        context.model_dump_json(indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)
