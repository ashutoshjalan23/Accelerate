"""Deterministic checkout and comparison instructions from GitHub evidence."""

import re
from pathlib import PurePosixPath
from urllib.parse import quote

from .agents.schemas import CommitData, GeneratedProblem, RepositoryInput


def validate_source(commit: CommitData, problem: GeneratedProblem) -> None:
    repository = RepositoryInput(github_url=commit.repository).repository
    if repository != commit.repository:
        raise ValueError("Source repository must use owner/name format.")
    if not all(re.fullmatch(r"[0-9a-fA-F]{40}", sha)
               for sha in (commit.parent_sha, commit.commit_sha)):
        raise ValueError("Source commits must contain full Git SHA hashes.")
    if problem.source_commit_sha != commit.commit_sha:
        raise ValueError("Challenge and maintainer evidence refer to different commits.")
    for path in problem.relevant_files:
        parts = path.split("/")
        if not path or path.startswith("/") or "\\" in path or ":" in path or any(
            part in ("", ".", "..") for part in parts
        ):
            raise ValueError("Relevant files must use repository-relative paths.")


def workspace(commit: CommitData, problem: GeneratedProblem) -> dict:
    validate_source(commit, problem)
    url = f"https://github.com/{commit.repository}"
    name = commit.repository.split("/")[1]
    folder = f"accelerate-{name}-{commit.parent_sha[:12]}"
    directories = sorted({str(PurePosixPath(path).parent) for path in problem.relevant_files})
    changed = {file.path: file for file in commit.files_changed}
    files = []
    for path in problem.relevant_files:
        file = changed.get(path)
        exists_before = file is None or file.status not in {"added", "copied"}
        before_path = (file.previous_path or path) if file else path
        files.append({"path": path, "available_at_base": exists_before,
                      "url": f"{url}/blob/{commit.parent_sha}/{quote(before_path, safe='/')}"
                      if exists_before else None})
    return {
        "repository_url": url,
        "base_sha": commit.parent_sha,
        "checkout_commands": [
            f'git clone --no-checkout {url}.git "{folder}"',
            f'cd "{folder}"',
            f"git switch --detach {commit.parent_sha}",
            f"git switch -c accelerate/{commit.parent_sha[:12]}",
        ],
        "relevant_directories": directories,
        "files": files,
        "local_diff_command": f"git diff {commit.parent_sha}",
    }


def solution(commit: CommitData) -> dict:
    url = f"https://github.com/{commit.repository}"
    return {
        "commit_sha": commit.commit_sha,
        "commit_url": f"{url}/commit/{commit.commit_sha}",
        "message": commit.message,
        "diff": commit.diff,
        "pull_request_description": commit.pull_request_description,
        "comparison_commands": [
            f"git fetch origin {commit.commit_sha}",
            f"git diff {commit.parent_sha} {commit.commit_sha}",
            f"git diff {commit.parent_sha}",
        ],
        "note": "Compare behavior and trade-offs. A different patch can still be correct. "
                "The working-tree diff includes tracked files; use git add -N <new-file> "
                "to include a new file. These commands do not apply the maintainer patch.",
    }
