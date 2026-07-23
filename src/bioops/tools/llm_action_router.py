from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from openai import AzureOpenAI

from bioops.tools.azure_chat import create_chat_completion


@dataclass(frozen=True)
class ActionDecision:
    """Validated result of one agent's second-stage LLM decision."""

    action: str
    parameters: dict[str, Any]
    reason: str


class LLMActionRouter:
    """Shared LLM-only action router used inside specialist agents.

    The top-level BioOps router chooses an agent. This class performs the
    second decision inside that agent: it converts the original user request
    into one validated action and a bounded parameters dictionary.

    No keyword fallback is used. When Azure is unavailable, JSON is invalid,
    or the model chooses an unsupported action, ``route`` raises and the agent
    returns a fail-closed error without starting an external operation.
    """

    def __init__(
        self,
        *,
        agent_name: str,
        actions: Mapping[str, str],
        parameter_schema: Mapping[str, str] | None = None,
        rules: Iterable[str] | None = None,
        examples: Iterable[Mapping[str, Any]] | None = None,
    ) -> None:
        normalized_actions = {
            str(name).strip().lower(): str(description).strip()
            for name, description in actions.items()
            if str(name).strip()
        }
        if not normalized_actions:
            raise ValueError("LLMActionRouter requires at least one action.")

        self.agent_name = agent_name.strip() or "specialist"
        self.actions = normalized_actions
        self.parameter_schema = {
            str(name).strip(): str(description).strip()
            for name, description in (parameter_schema or {}).items()
            if str(name).strip()
        }
        self.rules = [str(rule).strip() for rule in (rules or []) if str(rule).strip()]
        self.examples = list(examples or [])

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
                timeout=20.0, max_retries=1,
            )

    @property
    def allowed_actions(self) -> set[str]:
        return set(self.actions)

    def route(self, message: str) -> ActionDecision:
        if not self.enabled or self.client is None:
            raise RuntimeError(
                f"{self.agent_name} action router unavailable: Azure OpenAI "
                "environment variables are not fully configured."
            )

        cleaned_message = self._strip_surrogates(message or "")
        prompt = self._strip_surrogates(self._build_prompt(cleaned_message))
        messages = [
            {
                "role": "system",
                "content": (
                    "You select exactly one safe action inside a BioOps specialist "
                    "agent. Return strict JSON only. Never claim an operation ran."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        try:
            response = create_chat_completion(
                self.client,
                model=self.deployment,
                messages=messages,
                max_completion_tokens=500,
            )
        except Exception as error:
            # Fail closed: never guess an action that could start an external
            # operation. The agent turns this into a safe action_routing_error.
            raise RuntimeError(
                f"{self.agent_name} action-router request failed: "
                f"{type(error).__name__}: {error}"
            ) from error

        content = response.choices[0].message.content or ""
        return self._parse_response(content)

    def _build_prompt(self, message: str) -> str:
        action_lines = "\n".join(
            f"- {name}: {description}"
            for name, description in sorted(self.actions.items())
        )
        parameter_lines = (
            "\n".join(
                f"- {name}: {description}"
                for name, description in sorted(self.parameter_schema.items())
            )
            or "- No parameters are supported. Return an empty object."
        )
        rule_lines = "\n".join(f"- {rule}" for rule in self.rules) or "- None."
        example_lines = "\n".join(
            json.dumps(example, ensure_ascii=False) for example in self.examples
        ) or "(none)"
        allowed_values = "|".join(sorted(self.actions))

        return f"""
Select exactly one action for the {self.agent_name} agent.

Allowed actions:
{action_lines}

Allowed parameter fields:
{parameter_lines}

Rules:
{rule_lines}
- Use the full meaning of the request, not isolated keywords.
- Choose only an action listed above.
- Include only supported parameter fields.
- Use null for an unknown optional parameter.
- Do not invent identifiers, paths, extensions, limits, timestamps, or statuses.
- Return JSON only, with no Markdown fence.

Required JSON shape:
{{
  "action": "{allowed_values}",
  "parameters": {{}},
  "reason": "short reason"
}}

Examples:
{example_lines}

User request:
{message}
""".strip()

    def _parse_response(self, content: str) -> ActionDecision:
        data = self._parse_json(self._strip_surrogates(content))
        if not isinstance(data, dict):
            raise ValueError(
                f"{self.agent_name} action router returned non-JSON or invalid JSON."
            )

        action = data.get("action")
        parameters = data.get("parameters", {})
        reason = data.get("reason", "")

        if not isinstance(action, str):
            raise ValueError("Action-router response is missing string field 'action'.")
        action = action.strip().lower()
        if action not in self.actions:
            raise ValueError(
                f"Action router returned unsupported action for {self.agent_name}: "
                f"{action}"
            )

        if parameters is None:
            parameters = {}
        if not isinstance(parameters, dict):
            raise ValueError("Action-router field 'parameters' must be an object.")

        unsupported_parameters = set(parameters) - set(self.parameter_schema)
        if unsupported_parameters:
            raise ValueError(
                "Action router returned unsupported parameters: "
                f"{sorted(unsupported_parameters)}"
            )

        normalized_parameters = {
            key: self._normalize_parameter_value(value)
            for key, value in parameters.items()
        }
        if not isinstance(reason, str) or not reason.strip():
            reason = "No reason provided."

        return ActionDecision(
            action=action,
            parameters=normalized_parameters,
            reason=reason.strip(),
        )

    @staticmethod
    def _normalize_parameter_value(value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        return value

    @staticmethod
    def _parse_json(content: str) -> Any:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
            cleaned = cleaned.removesuffix("```").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _strip_surrogates(text: str) -> str:
        return "".join(
            char for char in text if not 0xD800 <= ord(char) <= 0xDFFF
        )


def format_action_routing_error(agent_name: str, error: Exception) -> str:
    """Create one consistent fail-closed user response for all specialist agents."""

    return "\n".join(
        [
            f"{agent_name} action routing failed",
            "",
            "Status: action_routing_error",
            f"Error: {type(error).__name__}: {error}",
            "",
            "No specialist operation was started.",
            "No keyword fallback was used.",
        ]
    )
