"""LLM adapters used by the agent workflows."""

import json
import os
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .schemas import CommitAssessment, CommitData


CURATOR_ASSESSMENT_PROMPT = """\
You are the Curator and Scout Agent for AceProgramming.

Decide whether the supplied open-source commit can be transformed into a
self-contained programming or system-design problem for learners.

Read the commit message, pull request description, changed files, and diff.
Accept a commit only when it contains a distinct engineering problem such as
a bug fix, algorithmic improvement, performance optimization, concurrency
correction, or architectural change. The resulting challenge must be
grounded in the evidence and solvable without access to the original
repository or undocumented external context.

Reject commits that are merely documentation, formatting, typo, dependency,
release, or routine maintenance changes; changes whose purpose is ambiguous;
or changes that require substantial unavailable repository context.

Return only valid JSON matching this schema:
{"suitable": boolean, "rationale": " concise evidence-based explanation "}

Commit evidence:
{commit}
"""


class CuratorLLMClient:
    """Assess commits with Gemini and fall back to OpenRouter on failure."""

    def __init__(
        self,
        *,
        gemini_api_key: str | None = None,
        gemini_model: str | None = None,
        openrouter_api_key: str | None = None,
        openrouter_model: str | None = None,
        openrouter_url: str = "https://openrouter.ai/api/v1/chat/completions",
        http_post: Callable[[Request], bytes] | None = None,
    ) -> None:
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.gemini_model = gemini_model or os.getenv(
            "GEMINI_MODEL", "gemini-2.5-flash"
        )
        self.openrouter_api_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
        self.openrouter_model = openrouter_model or os.getenv(
            "OPENROUTER_MODEL", "qwen/qwen3-coder"
        )
        self.openrouter_url = openrouter_url
        self._http_post = http_post or self._default_http_post

    def assess_commit(self, commit: CommitData) -> CommitAssessment:
        """Ask the primary provider, then use the configured fallback."""

        prompt = CURATOR_ASSESSMENT_PROMPT.format(
            commit=json.dumps(commit.model_dump(mode="json"), indent=2)
        )
        errors: list[str] = []

        if self.gemini_api_key:
            try:
                return self._assess_with_gemini(prompt)
            except Exception as error:
                errors.append(f"Gemini: {error}")

        if self.openrouter_api_key:
            try:
                return self._assess_with_openrouter(prompt)
            except Exception as error:
                errors.append(f"OpenRouter: {error}")

        if not errors:
            raise RuntimeError(
                "No LLM provider is configured. Set GEMINI_API_KEY or "
                "OPENROUTER_API_KEY."
            )
        raise RuntimeError("All configured LLM providers failed: " + "; ".join(errors))

    def _assess_with_gemini(self, prompt: str) -> CommitAssessment:
        try:
            from google import genai
        except ImportError as error:
            raise RuntimeError(
                "The Google GenAI SDK is required for Gemini support."
            ) from error

        client = genai.Client(api_key=self.gemini_api_key)
        response = client.models.generate_content(
            model=self.gemini_model,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        return self._parse_assessment(response.text)

    def _assess_with_openrouter(self, prompt: str) -> CommitAssessment:
        payload = json.dumps(
            {
                "model": self.openrouter_model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        request = Request(
            self.openrouter_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        response = json.loads(self._http_post(request).decode("utf-8"))
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("OpenRouter returned an invalid completion.") from error
        return self._parse_assessment(content)

    @staticmethod
    def _parse_assessment(content: str | None) -> CommitAssessment:
        if not content:
            raise RuntimeError("The LLM returned an empty assessment.")
        try:
            data = json.loads(content)
            return CommitAssessment.model_validate(data)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise RuntimeError("The LLM returned invalid assessment JSON.") from error

    @staticmethod
    def _default_http_post(request: Request) -> bytes:
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except (HTTPError, URLError) as error:
            raise RuntimeError(f"OpenRouter request failed: {error}") from error
