"""LLM adapters used by the agent workflows."""

import json
import os
import re
import time
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .schemas import CodeContext, CommitAssessment, CommitData


CURATOR_ASSESSMENT_PROMPT = """\
You are the Curator and Scout Agent for Accelerate.

Decide whether the supplied open-source commit can be transformed into a
self-contained programming or system-design problem that a learner can
actually solve and an evaluator can assess.

Read the commit message, pull request description, changed files, and diff.
Accept a commit only when you can describe a concrete learner task with:
1. a specific problem or failure mode,
2. observable expected behavior or explicit system-design requirements,
3. a meaningful implementation or design decision for the learner, and
4. an objective way to evaluate the result.

The task may be an executable programming problem (for example, correcting
runtime behavior, implementing an algorithm, or improving concurrency or
performance) or a system-design problem (for example, defining an API,
data model, consistency strategy, or migration plan). It must be grounded in
the evidence and solvable without access to the original repository or
undocumented external context.

Reject commits that are merely documentation, formatting, typo, dependency,
release, routine maintenance, or configuration-only changes. In particular,
reject changes that only rename environment variables, update configuration
names, reorganize settings, or change deployment metadata unless the diff
also demonstrates a substantial behavioral, reliability, security, or
performance problem that can independently become a learner challenge.
Reject changes whose primary substance is dropping support for a language or
runtime version, changing package metadata, updating CI matrices, changing
documentation, or removing compatibility code unless the commit contains a
separate, concrete runtime behavior or system-design problem that a learner
can implement and that can be evaluated independently of the release or
support-policy decision.
Reject vague changes whose commit message and diff do not establish a
specific problem, expected behavior, meaningful engineering trade-off, and
evaluation criteria.
Also reject changes that require substantial unavailable repository context.

Do not infer significance from the number of changed files or the size of the
diff. Base the decision on the actual evidence. Set suitable to false when
the evidence is insufficient, and explain the missing evidence in rationale.

Before accepting, mentally write one sentence beginning with "The learner
must..." and one sentence beginning with "The evaluator can verify...". If
either sentence cannot be specific and grounded in the commit, reject it.

Return only valid JSON matching this schema:
{{"suitable": boolean, "rationale": " concise evidence-based explanation "}}

Commit evidence:
{commit}
"""

ANALYST_PROMPT = """\
You are the Engineering Analyst Agent for Accelerate.

Reconstruct the exact engineering problem addressed by this commit from the
commit metadata, diff, and before/after source. Distinguish facts visible in
the code from reasonable inferences. Produce a self-contained explanation
that another engineer could use to create a programming or system-design
challenge.

Explain:
1. what was broken or inefficient before the change,
2. why the old behavior failed or did not meet its requirements,
3. what behavior the fix establishes,
4. the requirements and constraints a learner should satisfy, and
5. any repository paths or evidence still needed to make the explanation
   reliable.

Only put concrete repository-relative file paths in missing_context. Each
item must contain only the path, with no explanation, punctuation, or
additional text. Use an empty list when no extra file is required.
Return only valid JSON matching this schema:
{{"issue_explanation": "...", "requirements": ["..."],
"missing_context": ["..."]}}

Commit:
{commit}

Before code:
{before_code}

After code:
{after_code}
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
        gemini_retries: int = 2,
        retry_delay_seconds: float = 2.0,
    ) -> None:
        if gemini_retries < 0:
            raise ValueError("gemini_retries must be zero or greater.")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be zero or greater.")
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.gemini_model = gemini_model or os.getenv(
            "GEMINI_MODEL", "gemini-3.5-flash"
        )
        self.openrouter_api_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
        self.openrouter_model = openrouter_model or os.getenv(
            "OPENROUTER_MODEL", "qwen/qwen3-coder"
        )
        self.openrouter_url = openrouter_url
        self._http_post = http_post or self._default_http_post
        self.gemini_retries = gemini_retries
        self.retry_delay_seconds = retry_delay_seconds

    def assess_commit(self, commit: CommitData) -> CommitAssessment:
        """Ask the primary provider, then use the configured fallback."""

        prompt = CURATOR_ASSESSMENT_PROMPT.format(
            commit=json.dumps(commit.model_dump(mode="json"), indent=2)
        )
        errors: list[str] = []

        if self.gemini_api_key:
            try:
                return self._assess_with_gemini_with_retry(prompt)
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
        fallback_hint = ""
        if self.gemini_api_key and not self.openrouter_api_key:
            fallback_hint = (
                " Configure OPENROUTER_API_KEY to enable the configured fallback."
            )
        raise RuntimeError(
            "All configured LLM providers failed: " + "; ".join(errors) + fallback_hint
        )

    def explain_change(
        self,
        commit: CommitData,
        before_code: dict[str, str],
        after_code: dict[str, str],
    ) -> CodeContext:
        """Analyze a commit and its source context with provider fallback."""

        prompt = ANALYST_PROMPT.format(
            commit=json.dumps(commit.model_dump(mode="json"), indent=2),
            before_code=json.dumps(before_code, indent=2),
            after_code=json.dumps(after_code, indent=2),
        )
        data = self._generate_json(prompt)
        try:
            requirements = data.get("requirements", [])
            missing_context = data.get("missing_context", [])
            if not isinstance(requirements, list) or not all(
                isinstance(item, str) for item in requirements
            ):
                raise TypeError("requirements must be a list of strings")
            if not isinstance(missing_context, list) or not all(
                isinstance(item, str) for item in missing_context
            ):
                raise TypeError("missing_context must be a list of strings")
            missing_context = [
                self._normalize_context_path(item) for item in missing_context
            ]
            return CodeContext(
                commit=commit,
                before_code=before_code,
                after_code=after_code,
                issue_explanation=data["issue_explanation"],
                requirements=requirements,
                missing_context=missing_context,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("The LLM returned invalid engineering analysis JSON.") from error

    @staticmethod
    def _normalize_context_path(value: str) -> str:
        """Extract a repository path when a model adds a short explanation."""

        candidate = value.strip().splitlines()[0].strip()
        candidate = re.split(r"\s+(?:-|—|:)\s+", candidate, maxsplit=1)[0]
        candidate = candidate.strip("`'\"")
        if (
            not candidate
            or candidate.startswith(("/", "\\"))
            or ".." in candidate.split("/")
            or not re.fullmatch(r"[A-Za-z0-9._/-]+", candidate)
        ):
            raise ValueError(
                f"LLM returned an invalid repository path in missing_context: {value!r}"
            )
        return candidate

    def _generate_json(self, prompt: str) -> dict[str, object]:
        errors: list[str] = []
        if self.gemini_api_key:
            try:
                return self._parse_json(self._generate_with_gemini_with_retry(prompt))
            except Exception as error:
                errors.append(f"Gemini: {error}")
        if self.openrouter_api_key:
            try:
                return self._parse_json(self._generate_with_openrouter(prompt))
            except Exception as error:
                errors.append(f"OpenRouter: {error}")
        if not errors:
            raise RuntimeError(
                "No LLM provider is configured. Set GEMINI_API_KEY or "
                "OPENROUTER_API_KEY."
            )
        raise RuntimeError("All configured LLM providers failed: " + "; ".join(errors))

    def _generate_with_gemini_with_retry(self, prompt: str) -> str | None:
        attempts = self.gemini_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                return self._generate_with_gemini(prompt)
            except Exception as error:
                last_error = error
                if attempt == attempts - 1:
                    break
                time.sleep(self.retry_delay_seconds * (2**attempt))
        raise RuntimeError(
            f"Gemini failed after {attempts} attempts: {last_error}"
        ) from last_error

    def _assess_with_gemini_with_retry(self, prompt: str) -> CommitAssessment:
        attempts = self.gemini_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                return self._assess_with_gemini(prompt)
            except Exception as error:
                last_error = error
                if attempt == attempts - 1:
                    break
                time.sleep(self.retry_delay_seconds * (2**attempt))
        raise RuntimeError(f"Gemini failed after {attempts} attempts: {last_error}") from last_error

    def _assess_with_gemini(self, prompt: str) -> CommitAssessment:
        return self._parse_assessment(self._generate_with_gemini(prompt))

    def _generate_with_gemini(self, prompt: str) -> str | None:
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
        return response.text

    def _assess_with_openrouter(self, prompt: str) -> CommitAssessment:
        return self._parse_assessment(self._generate_with_openrouter(prompt))

    def _generate_with_openrouter(self, prompt: str) -> str:
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
        if not isinstance(content, str):
            raise RuntimeError("OpenRouter returned non-text completion content.")
        return content

    @staticmethod
    def _parse_json(content: str | None) -> dict[str, object]:
        if not content:
            raise RuntimeError("The LLM returned an empty response.")
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError) as error:
            raise RuntimeError("The LLM returned invalid JSON.") from error
        if not isinstance(data, dict):
            raise RuntimeError("The LLM returned a JSON value instead of an object.")
        return data

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
