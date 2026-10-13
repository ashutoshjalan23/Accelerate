"""Focused tests for GitHub content decoding."""

import base64
import json
import pathlib
import sys
import unittest
from urllib.request import Request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.integrations.github import GitHubClientAdapter


class GitHubAdapterTests(unittest.TestCase):
    def test_get_file_decodes_wrapped_base64_content(self) -> None:
        source = "line one\nline two\n"
        encoded = base64.b64encode(source.encode("utf-8")).decode("ascii")
        wrapped = "\n".join(
            encoded[index : index + 8] for index in range(0, len(encoded), 8)
        )

        def http_get(request: Request) -> bytes:
            return json.dumps(
                {"type": "file", "encoding": "base64", "content": wrapped}
            ).encode("utf-8")

        github = GitHubClientAdapter(http_get=http_get)

        self.assertEqual(
            github.get_file("owner/repository", "src/example.py", "sha"), source
        )


if __name__ == "__main__":
    unittest.main()
