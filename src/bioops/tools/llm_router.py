import json
import os
from dataclasses import dataclass
from typing import Any

from openai import AzureOpenAI


DEFAULT_ALLOWED_AGENTS = {
    "general",
    "knowledge",
    "cluster_health",
    "review",
    "submit_master",
    "batch_status",
    "storage",
    "infra_cost",
}

ALLOWED_AGENTS = DEFAULT_ALLOWED_AGENTS


@dataclass
class RouterDecision:
    agent: str
    reason: str


class LLMRouterTool:
    """LLM-only router for BioOps agent selection."""

    def __init__(
        self,
        allowed_agents: set[str] | list[str] | tuple[str, ...] | None = None,
    ):
        self.allowed_agents = set(allowed_agents or DEFAULT_ALLOWED_AGENTS)
        self.allowed_agents.add("general")

        unsupported_agents = self.allowed_agents - DEFAULT_ALLOWED_AGENTS
        if unsupported_agents:
            raise ValueError(
                f"Unsupported router agents configured: {sorted(unsupported_agents)}"
            )

        self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.api_version = os.getenv("AZURE_OPENAI_API_VERSION")
        self.deployment = (
            os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
            or os.getenv("AZURE_OPENAI_DEPLOYMENT")
            or os.getenv("AZURE_OPENAI_MODEL")
        )

        self.enabled = all(
            [self.endpoint, self.api_key, self.api_version, self.deployment]
        )

        self.client = None
        if self.enabled:
            self.client = AzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
                timeout=30.0,
            )

    def _strip_surrogates(self, text: str) -> str:
        """Remove invalid Unicode surrogate code points before sending text to Azure."""
        return "".join(
            char for char in text
            if not 0xD800 <= ord(char) <= 0xDFFF
        )

    def route(self, message: str) -> RouterDecision:
        if not self.enabled or self.client is None:
            raise RuntimeError(
                "LLM router unavailable: Azure OpenAI environment variables "
                "are not fully configured."
            )

        message = self._strip_surrogates(message)
        prompt = self._strip_surrogates(self._build_prompt(message))
        messages = [
            {
                "role": "system",
                "content": (
                    "You route BioOps user requests to exactly one enabled agent.\n"
                    "Return strict JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=messages,
                max_completion_tokens=250,
            )
        except TypeError:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=messages,
                max_tokens=250,
            )
        except Exception as error:
            raise RuntimeError(
                f"LLM router request failed: {type(error).__name__}: {error}"
            ) from error

        return self._parse_response(response.choices[0].message.content or "")

    def _build_prompt(self, message: str) -> str:
        agent_descriptions = {
            "general": (
                "general conversation, greetings, broad questions, unclear requests, "
                "or non-specialist BioOps tasks"
            ),
            "knowledge": (
                "BioOps documentation, pipeline step explanations, workflow metadata, "
                "command examples, source code explanations, or stored project knowledge"
            ),
            "cluster_health": (
                "general Kubernetes cluster health, pods, pod logs, failed/running jobs, "
                "health monitor, Bitrix health alerts, cost, ETA, or runtime status "
                "when the request is not specifically about Submit Master"
            ),
            "review": (
                "code review, repository review, GitHub pull requests, branch comparisons, "
                "diffs, implementation risks, suspicious files, or missing tests"
            ),
            "submit_master": (
                "Submit Master and Argo SubmitMaster workflow operations: "
                "D1 config generation, D2 Submit Master launch or run preparation, "
                "D3 Submit Master progress/status/log/error monitoring, "
                "D4 failed Submit Master pod or workflow-node reports, "
                "D5 safe retry or resubmission of failed Submit Master workflows"
            ),
            "batch_status": (
                "Batch Status Agent requests: batch processing statuses, latest batch status, "
                "status of a specific batch, failed batches, running batches, completed batches, "
                "stale batches, status DB records, CSV/JSON status export, or Google Sheet "
                "batch status synchronization"
            ),
            "storage": (
                "Bucket and object-storage inventory questions: bucket structure, "
                "object counts, total size, file types, storage classes, matching "
                "files, prefixes, and inventory freshness"
            ),
            "infra_cost": (
                "Infrastructure and cost monitoring: expensive or long-running "
                "Compute Cloud VMs, projected VM cost, GPU runtime, infrastructure "
                "cost alerts, database health, queues, and Cloud Functions"
            ),
        }

        allowed_lines = "\n".join(
            f"- {agent}: {agent_descriptions[agent]}"
            for agent in sorted(self.allowed_agents)
        )
        allowed_values = "|".join(sorted(self.allowed_agents))

        return f"""
Choose exactly one enabled BioOps agent for this user request.

Enabled agents:
{allowed_lines}

Rules:
- Use full context, not single keywords.
- Choose only one of the enabled agents listed above.
- Do not choose an agent that is not listed above.
- Choose submit_master for requests about Submit Master, Config Creator,
  SubmitMaster Argo workflows, D1/D2/D3/D4/D5, Submit Master progress,
  Submit Master failures, failed Submit Master pods, or safe
  retry/resubmission of Submit Master workflows.
- Choose batch_status for requests about batch status records, latest batch
  status, failed/running/completed batches, or questions such as
  "status of batch N".
- Choose cluster_health for general Kubernetes pod or cluster health questions
  that are not specifically about Submit Master or batch status records.
- Choose storage for questions about bucket contents, object counts, file
  sizes, prefixes, storage classes, or bucket inventory.
- Choose infra_cost for Compute Cloud VM cost, expensive VMs, GPU runtime,
  infrastructure cost alerts, database infrastructure, queues, or
  Cloud Functions.
- Do not choose review only because the word "review" appears when the user is
  asking about health logs or documentation.
- Do not choose knowledge only because the word "explain" appears; decide
  whether the explanation needs docs, cluster status, code review,
  Submit Master operation, batch status, storage, infra cost, or a general
  response.
- Return JSON only.

JSON shape:
{{ "agent": "{allowed_values}", "reason": "short reason" }}

User request:
{message}
""".strip()

    def _parse_response(self, content: str) -> RouterDecision:
        content = self._strip_surrogates(content)
        data = self._parse_json(content)
        if not isinstance(data, dict):
            raise ValueError("LLM router returned non-JSON or invalid JSON content.")

        agent = data.get("agent")
        reason = data.get("reason", "")

        if not isinstance(agent, str):
            raise ValueError("LLM router response is missing string field 'agent'.")

        agent = agent.strip().lower()

        if agent not in self.allowed_agents:
            raise ValueError(f"LLM router returned disabled or unsupported agent: {agent}")

        if not isinstance(reason, str) or not reason.strip():
            reason = "No reason provided."

        return RouterDecision(agent=agent, reason=reason.strip())

    def _parse_json(self, content: str) -> Any:
        cleaned = content.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
            cleaned = cleaned.removesuffix("```").strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None
