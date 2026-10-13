"""GitHub REST API adapter used by the agent workflows."""

import base64
import json
import os
from collections.abc import Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from ..agents.schemas import ChangedFile, CommitData


class GitHubApiError(RuntimeError):
    """Raised when GitHub cannot provide the requested repository data."""


class GitHubClientAdapter:
    """Fetch commit and source evidence through GitHub's REST API."""

    def __init__(
        self,
        *,
        token: str | None = None,
        api_url: str = "https://api.github.com",
        http_get: Callable[[Request], bytes] | None = None,
    ) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.api_url = api_url.rstrip("/")
        self._http_get = http_get or self._default_http_get

    def list_commits(self, repository: str, limit: int = 50) -> Sequence[CommitData]:
        """Return commit evidence in GitHub's newest-first order."""

        owner, name = self._parse_repository(repository)
        if limit < 1:
            raise ValueError("limit must be at least 1.")
        summaries = self._request_json(
            f"/repos/{quote(owner)}/{quote(name)}/commits?per_page={limit}"
        )
        if not isinstance(summaries, list):
            raise GitHubApiError("GitHub returned an invalid commits response.")

        return [
            self._get_commit(owner, name, summary["sha"])
            for summary in summaries
            if isinstance(summary, dict) and isinstance(summary.get("sha"), str)
        ]

    def get_file(self, repository: str, path: str, ref: str) -> str:
        """Return decoded file contents at a commit or branch reference."""

        owner, name = self._parse_repository(repository)
        encoded_path = quote(path, safe="/")
        payload = self._request_json(
            f"/repos/{quote(owner)}/{quote(name)}/contents/{encoded_path}"
            f"?ref={quote(ref)}"
        )
        if not isinstance(payload, dict) or payload.get("type") != "file":
            raise GitHubApiError(f"GitHub did not return a file for path '{path}'.")
        content = payload.get("content")
        encoding = payload.get("encoding")
        if not isinstance(content, str) or encoding != "base64":
            raise GitHubApiError(f"GitHub returned unsupported content for '{path}'.")
        try:
            return base64.b64decode(content, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise GitHubApiError(f"GitHub returned invalid content for '{path}'.") from error

    def _get_commit(self, owner: str, name: str, sha: str) -> CommitData:
        payload = self._request_json(
            f"/repos/{quote(owner)}/{quote(name)}/commits/{quote(sha)}"
        )
        if not isinstance(payload, dict):
            raise GitHubApiError(f"GitHub returned invalid data for commit '{sha}'.")
        commit = payload.get("commit")
        parents = payload.get("parents")
        files = payload.get("files")
        if not isinstance(commit, dict) or not isinstance(parents, list) or not parents:
            raise GitHubApiError(f"Commit '{sha}' is missing required metadata.")

        parent = parents[0].get("sha") if isinstance(parents[0], dict) else None
        message = commit.get("message")
        if not isinstance(parent, str) or not isinstance(message, str):
            raise GitHubApiError(f"Commit '{sha}' has invalid metadata.")

        changed_files = self._parse_files(files)
        return CommitData(
            repository=f"{owner}/{name}",
            commit_sha=sha,
            parent_sha=parent,
            message=message,
            diff=self._build_diff(changed_files),
            files_changed=changed_files,
            pull_request_description=self._get_pull_request_description(owner, name, sha),
        )

    def _get_pull_request_description(
        self, owner: str, name: str, sha: str
    ) -> str | None:
        payload = self._request_json(
            f"/repos/{quote(owner)}/{quote(name)}/commits/{quote(sha)}/pulls"
        )
        if not isinstance(payload, list) or not payload:
            return None
        first = payload[0]
        if not isinstance(first, dict):
            return None
        body = first.get("body")
        return body if isinstance(body, str) and body else None

    @staticmethod
    def _parse_files(payload: object) -> list[ChangedFile]:
        if not isinstance(payload, list):
            raise GitHubApiError("GitHub returned an invalid changed-files response.")
        result: list[ChangedFile] = []
        for file in payload:
            if not isinstance(file, dict) or not isinstance(file.get("filename"), str):
                raise GitHubApiError("GitHub returned an invalid changed-file entry.")
            status = file.get("status")
            result.append(
                ChangedFile(
                    path=file["filename"],
                    status=status if status in {
                        "added",
                        "modified",
                        "removed",
                        "renamed",
                        "copied",
                    } else "unknown",
                    additions=file.get("additions", 0),
                    deletions=file.get("deletions", 0),
                    patch=file.get("patch"),
                )
            )
        return result

    @staticmethod
    def _build_diff(files: list[ChangedFile]) -> str:
        return "\n\n".join(
            f"diff -- {file.path}\n{file.patch or '[patch unavailable]'}" for file in files
        )

    def _request_json(self, path: str) -> object:
        request = Request(
            f"{self.api_url}{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
            },
            method="GET",
        )
        try:
            return json.loads(self._http_get(request).decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise GitHubApiError(
                f"GitHub API request failed with HTTP {error.code}: {detail}"
            ) from error
        except URLError as error:
            raise GitHubApiError(f"GitHub API request failed: {error}") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GitHubApiError("GitHub returned an invalid JSON response.") from error

    @staticmethod
    def _parse_repository(repository: str) -> tuple[str, str]:
        value = repository.strip().rstrip("/")
        if "://" in value:
            parsed = urlparse(value)
            if parsed.netloc.lower() != "github.com":
                raise ValueError("repository must be a github.com URL or owner/name.")
            value = parsed.path.strip("/")
        value = value.removesuffix(".git")
        parts = value.split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("repository must use the 'owner/name' format.")
        return parts[0], parts[1]

    @staticmethod
    def _default_http_get(request: Request) -> bytes:
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except (HTTPError, URLError):
            raise
