import json
import os
from dataclasses import dataclass

from openai import AzureOpenAI


ALLOWED_AGENTS = {
    "general",
    "knowledge",
    "cluster_health",
    "review",
    "batch_status",
    "submit_master",
    "storage",
    "infra_cost",
}


@dataclass
class RouterDecision:
    agent: str
    confidence: float
    reason: str


class LLMRouterTool:
    """Routes a user message to one BioOps agent using Azure OpenAI."""

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
                timeout=10.0,
            )

    def route(self, message: str) -> RouterDecision:
        if not self.enabled or self.client is None:
            raise RuntimeError("LLM router unavailable: Azure OpenAI is not configured.")

        prompt = self._build_prompt(message)

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the routing layer for BioOps, a multi-agent "
                            "bioinformatics operations assistant. Choose exactly one "
                            "agent. Return only valid JSON."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                max_completion_tokens=250,
            )
        except TypeError:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the routing layer for BioOps, a multi-agent "
                            "bioinformatics operations assistant. Choose exactly one "
                            "agent. Return only valid JSON."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                max_tokens=250,
            )

        content = response.choices[0].message.content or ""
        return self._parse_decision(content)

    def _build_prompt(self, message: str) -> str:
        return "\n".join(
            [
                "Choose exactly one BioOps agent for this user message.",
                "",
                "Available agents:",
                "",
                "- knowledge: answers questions about project docs, pipeline metadata, source code, pipeline steps, inputs, outputs, and explanations.",
                "- cluster_health: checks Kubernetes cluster health, pods, logs, pod failures, pod status, running steps, and unhealthy containers.",
                "- batch_status: summarizes batch/job/pipeline progress, completed batches, failed batches, running batches, and completion status.",
                "- submit_master: validates sample or batch submission requests and previews or prepares Argo workflow submission commands.",
                "- review: reviews repositories, pull requests, merge requests, branch diffs, code changes, risks, style, logic issues, and missing tests.",
                "- storage: answers read-only questions about bucket contents, object storage, prefixes, inventory files, file counts, and total storage size.",
                "- infra_cost: checks infrastructure health, cloud costs, expensive VMs, Yandex Cloud, queues, ClickHouse, and Cloud Functions.",
                "- general: fallback for greetings, unclear requests, unsupported requests, and normal conversation.",
                "",
                "Return only JSON in this exact shape:",
                "{",
                '  "agent": "one of: general, knowledge, cluster_health, review, batch_status, submit_master, storage, infra_cost",',
                '  "confidence": 0.0,',
                '  "reason": "short reason"',
                "}",
                "",
                "Rules:",
                "- Do not invent new agent names.",
                "- Prefer the most operational/specific agent.",
                "- Use general only when no specialist BioOps agent clearly fits.",
                "",
                "User message:",
                message,
            ]
        )

    def _parse_decision(self, content: str) -> RouterDecision:
        data = self._extract_json(content)

        agent = str(data.get("agent", "")).strip()
        confidence = float(data.get("confidence", 0.0))
        reason = str(data.get("reason", "")).strip()

        if agent not in ALLOWED_AGENTS:
            raise ValueError(f"LLM router returned unsupported agent: {agent}")

        confidence = max(0.0, min(1.0, confidence))

        return RouterDecision(
            agent=agent,
            confidence=confidence,
            reason=reason,
        )

    def _extract_json(self, content: str) -> dict:
        text = content.strip()

        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()

        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"LLM router returned non-JSON content: {content}")

        return json.loads(text[start : end + 1])
