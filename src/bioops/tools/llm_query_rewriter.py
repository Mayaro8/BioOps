import json
import os
from typing import Any

from openai import AzureOpenAI

from bioops.tools.azure_chat import create_chat_completion


class LLMQueryRewriter:
    """LLM-only query rewriter for KnowledgeAgent RAG retrieval."""

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
                timeout=20.0, max_retries=1,
            )

    def rewrite(self, message: str) -> str:
        # Query rewriting is a best-effort optimization for retrieval. If Azure
        # is unavailable or slow, degrade to the original message instead of
        # failing the whole Knowledge request so RAG can still run.
        if not self.enabled or self.client is None:
            return message.strip()

        prompt = self._build_prompt(message)

        try:
            response = create_chat_completion(
                self.client,
                model=self.deployment,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You rewrite BioOps KnowledgeAgent questions into "
                            "better semantic search queries for RAG retrieval. "
                            "Return strict JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                max_completion_tokens=400,
                reasoning_effort="low",
            )
            content = response.choices[0].message.content or ""
            return self._parse_response(content)
        except Exception:
            return message.strip()

    def _build_prompt(self, message: str) -> str:
        return f"""
Rewrite this user question into one search query for BioOps documentation retrieval.

Rules:
- Use full context, not substring keyword matching.
- Preserve the user's intent.
- Add useful BioOps/pipeline terminology only when it is contextually relevant.
- Do not answer the question.
- Do not invent facts, file paths, commands, or pipeline outputs.
- Keep the rewritten query concise but specific.
- Return JSON only.

JSON shape:
{{
  "search_query": "rewritten semantic search query"
}}

User question:
{message}
""".strip()

    def _parse_response(self, content: str) -> str:
        data = self._parse_json(content)

        if not isinstance(data, dict):
            raise ValueError("LLM query rewriter returned invalid JSON.")

        search_query = data.get("search_query")

        if not isinstance(search_query, str) or not search_query.strip():
            raise ValueError(
                "LLM query rewriter response is missing non-empty search_query."
            )

        return search_query.strip()

    def _parse_json(self, content: str) -> Any:
        cleaned = content.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
            cleaned = cleaned.removesuffix("```").strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None
