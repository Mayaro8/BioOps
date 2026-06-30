import json
import os
from typing import Any

from openai import AzureOpenAI


ALLOWED_GITHUB_REVIEW_MODES = {"local", "repo", "open_prs", "pr", "compare"}


class LLMGitHubRequestParser:
    """LLM-only parser for GitHub review requests."""

    def __init__(self):
        self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.api_version = os.getenv("AZURE_OPENAI_API_VERSION")
        self.deployment = (
            os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
            or os.getenv("AZURE_OPENAI_DEPLOYMENT")
            or os.getenv("AZURE_OPENAI_MODEL")
        )

        self.enabled = all(
            [
                self.endpoint,
                self.api_key,
                self.api_version,
                self.deployment,
            ]
        )

        self.client = None
        if self.enabled:
            self.client = AzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
                timeout=30.0,
            )

    def parse(self, message: str) -> dict[str, Any] | None:
        if not self.enabled or self.client is None:
            return None

        prompt = self._build_prompt(message)

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You parse BioOps ReviewAgent requests into strict JSON. "
                            "Return JSON only. Do not explain."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                max_completion_tokens=400,
            )
        except TypeError:
            try:
                response = self.client.chat.completions.create(
                    model=self.deployment,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You parse BioOps ReviewAgent requests into strict JSON. "
                                "Return JSON only. Do not explain."
                            ),
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    max_tokens=400,
                )
            except Exception:
                return None
        except Exception:
            return None

        content = response.choices[0].message.content or ""
        data = self._parse_json(content)

        if not isinstance(data, dict):
            return None

        return self._validate(data)

    def _build_prompt(self, message: str) -> str:
        return f"""
Classify this BioOps ReviewAgent request.

Allowed modes:
- local: user wants to review a local working tree or local path.
- repo: user wants a GitHub repository overview only.
- open_prs: user asks to list, check, summarize, or review open pull requests without naming one specific PR number.
- pr: user asks to review one specific pull request number or one specific GitHub pull request URL.
- compare: user asks to compare two branches.

Decision rules:
- Use the full context, not individual keywords.
- "review pull requests in repo=X" means open_prs unless one specific PR number is provided.
- "review PR 12" means pr.
- A GitHub URL ending in /pull/12 means pr.
- If both base and head branches are provided, choose compare.
- If a GitHub repository is provided but no PR/list/compare intent exists, choose repo.
- If the user refers to local code or a local path and no GitHub repository is provided, choose local.
- Extract repo as owner/name when present.
- Extract pr_number as an integer when present.
- Extract base and head branch names when present.
- Extract path for local mode when present.
- Use null for missing fields.

Return exactly this JSON shape:
{{
  "mode": "local|repo|open_prs|pr|compare",
  "repo": "owner/name or null",
  "pr_number": 12,
  "base": "branch or null",
  "head": "branch or null",
  "path": "local path or null"
}}

User message:
{message}
""".strip()

    def _parse_json(self, content: str) -> Any:
        cleaned = content.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
            cleaned = cleaned.removesuffix("```").strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None

    def _validate(self, data: dict[str, Any]) -> dict[str, Any] | None:
        mode = data.get("mode")

        if not isinstance(mode, str):
            return None

        mode = mode.strip().lower()

        if mode not in ALLOWED_GITHUB_REVIEW_MODES:
            return None

        repo = data.get("repo")
        repo = repo.strip().removesuffix(".git") if isinstance(repo, str) and repo.strip() else None

        pr_number = data.get("pr_number")
        if pr_number is not None:
            try:
                pr_number = int(pr_number)
            except (TypeError, ValueError):
                pr_number = None

        base = data.get("base")
        base = base.strip() if isinstance(base, str) and base.strip() else None

        head = data.get("head")
        head = head.strip() if isinstance(head, str) and head.strip() else None

        path = data.get("path")
        path = path.strip() if isinstance(path, str) and path.strip() else None

        return {
            "mode": mode,
            "repo": repo,
            "pr_number": pr_number,
            "base": base,
            "head": head,
            "path": path,
        }
