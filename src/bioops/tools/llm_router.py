import json
import os
from dataclasses import dataclass
from typing import Any

from openai import AzureOpenAI


DEFAULT_ALLOWED_AGENTS = {"general", "knowledge", "cluster_health", "review"}

# Backward-compatible alias for older imports/tests.
ALLOWED_AGENTS = DEFAULT_ALLOWED_AGENTS


@dataclass
class RouterDecision:
    agent: str
    reason: str


class LLMRouterTool:
    """LLM-only router for BioOps agent selection."""

    def __init__(self, allowed_agents: set[str] | list[str] | tuple[str, ...] | None = None):
        self.allowed_agents = set(allowed_agents or DEFAULT_ALLOWED_AGENTS)

        # General must always exist as the safe fallback category.
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

    def route(self, message: str) -> RouterDecision:
        if not self.enabled or self.client is None:
            raise RuntimeError(
                "LLM router unavailable: Azure OpenAI environment variables "
                "are not fully configured."
            )

        prompt = self._build_prompt(message)

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You route BioOps user requests to exactly one enabled agent. "
                            "Return strict JSON only."
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
                            "You route BioOps user requests to exactly one enabled agent. "
                            "Return strict JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                max_tokens=250,
            )
        except Exception as error:
            raise RuntimeError(
                f"LLM router request failed: {type(error).__name__}: {error}"
            ) from error

        content = response.choices[0].message.content or ""
        return self._parse_response(content)

    def _build_prompt(self, message: str) -> str:
        agent_descriptions = {
            "general": (
                "general conversation, greetings, broad questions, unclear requests, "
                "or anything that does not require a specialist BioOps tool"
            ),
            "knowledge": (
                "questions about BioOps documentation, pipeline steps, workflow metadata, "
                "command examples, source code explanations, or stored project knowledge"
            ),
            "cluster_health": (
                "Kubernetes cluster state, pods, pod logs, failed/running jobs, health monitor, "
                "Bitrix health alerts, cost, ETA, or pipeline runtime status"
            ),
            "review": (
                "code review, repository review, GitHub pull requests, branch comparison, "
                "diffs, suspicious files, implementation risks, or missing tests"
            ),
        }

        allowed_lines = "\n".join(
            f"- {agent}: {agent_descriptions[agent]}"
            for agent in sorted(self.allowed_agents)
        )

        allowed_agent_values = "|".join(sorted(self.allowed_agents))

        return f"""
Choose exactly one enabled BioOps agent for this user request.

Enabled agents:
{allowed_lines}

Rules:
- Use full context, not single keywords.
- Choose only one of the enabled agents listed above.
- Do not choose an agent that is not listed above.
- Do not choose review only because the word "review" appears if the user is asking about health logs or documentation.
- Do not choose knowledge only because the word "explain" appears; decide whether the explanation needs docs, cluster status, code review, or general response.
- Return JSON only.

JSON shape:
{{
  "agent": "{allowed_agent_values}",
  "reason": "short reason"
}}

User request:
{message}
""".strip()

    def _parse_response(self, content: str) -> RouterDecision:
        data = self._parse_json(content)

        if not isinstance(data, dict):
            raise ValueError("LLM router returned non-JSON or invalid JSON content.")

        agent = data.get("agent")
        reason = data.get("reason", "")

        if not isinstance(agent, str):
            raise ValueError("LLM router response is missing string field 'agent'.")

        agent = agent.strip().lower()

        if agent not in self.allowed_agents:
            raise ValueError(
                f"LLM router returned disabled or unsupported agent: {agent}"
            )

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
