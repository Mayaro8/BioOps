from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from openai import AzureOpenAI


VALID_INTENTS = {
    "build_or_launch",
    "monitor",
    "failed_pods",
    "restart_failed_pods",
    "explain_config",
    "refuse",
}


@dataclass
class SubmitMasterPlannerDecision:
    intent: str
    candidate_stage: str | None = None
    candidate_step: str | None = None
    candidate_platform: str | None = None
    provided_parameters: dict[str, Any] = field(default_factory=dict)
    user_confirmed: bool = False
    explanation: str = ""
    refusal_reason: str = ""


class SubmitMasterLLMPlanner:
    """
    LLM-only interpretation layer for Submit Master requests.

    It does not launch anything. It converts a user message into a strict JSON
    decision. Python then validates parameters and safety.
    """

    def __init__(self) -> None:
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

    def plan(
        self,
        message: str,
        context: dict[str, Any],
    ) -> SubmitMasterPlannerDecision:
        if not self.enabled or self.client is None:
            raise RuntimeError(
                "Azure OpenAI is not configured for Submit Master LLM planning."
            )

        prompt = self._build_prompt(message=message, context=context)

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict JSON planning layer for a "
                            "bioinformatics Submit Master agent."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_completion_tokens=1200,
            )
        except TypeError:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict JSON planning layer for a "
                            "bioinformatics Submit Master agent."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1200,
            )

        content = response.choices[0].message.content or ""
        return self._parse_response(content)

    def _build_prompt(self, message: str, context: dict[str, Any]) -> str:
        return f"""
Convert the user request into strict JSON for Submit Master planning.

Do not invent missing values. Do not launch anything. Do not claim a config is
ready. Only extract intent, likely stage, likely step, likely platform, and
provided parameters.

Python code will compare provided parameters to required parameters and decide
whether the request is complete.

Valid intents:
- build_or_launch
- monitor
- failed_pods
- restart_failed_pods
- explain_config
- refuse

Rules:
- If user asks to generate, prepare, run, launch, or submit a pipeline step:
  intent = build_or_launch.
- If user asks for status, logs, cost, ETA, or running state:
  intent = monitor.
- If user asks for failed pods or failure causes:
  intent = failed_pods.
- If user asks to restart, retry, or rerun failed pods/workflows:
  intent = restart_failed_pods.
- If user only asks what parameters/config are needed:
  intent = explain_config.
- If request is unrelated or unsafe:
  intent = refuse.
- If the user explicitly says confirm=true or clearly confirms launch, set user_confirmed=true.
- If user provides stage directly, preserve it.
- If user provides platform/sequencing type, map it to candidate_platform and seq_type.
- Keep all useful parameters in provided_parameters.
- Return JSON only.

Context:
{json.dumps(context, indent=2, sort_keys=True)}

Return exactly this JSON shape:
{{
  "intent": "build_or_launch",
  "candidate_stage": null,
  "candidate_step": null,
  "candidate_platform": null,
  "provided_parameters": {{
    "stage": null,
    "step": null,
    "steps_order": null,
    "seq_type": null,
    "cluster_name": null,
    "mongo_cluster_name": null,
    "namespace": null,
    "sample_ids": null,
    "batch_id": null,
    "workflow_name": null,
    "confirm": false,
    "wait": true,
    "only_good": true,
    "delay": 0,
    "delay_step": 1,
    "chunk_size": 1,
    "contour": null,
    "extra_params": {{}}
  }},
  "user_confirmed": false,
  "explanation": "short explanation",
  "refusal_reason": ""
}}

User request:
{message}
""".strip()

    def _parse_response(self, content: str) -> SubmitMasterPlannerDecision:
        data = self._parse_json(content)

        if not isinstance(data, dict):
            raise ValueError("Submit Master planner returned invalid JSON.")

        intent = str(data.get("intent", "")).strip().lower()
        if intent not in VALID_INTENTS:
            raise ValueError(f"Invalid Submit Master intent: {intent}")

        provided = data.get("provided_parameters") or {}
        if not isinstance(provided, dict):
            provided = {}

        return SubmitMasterPlannerDecision(
            intent=intent,
            candidate_stage=self._string_or_none(data.get("candidate_stage")),
            candidate_step=self._string_or_none(data.get("candidate_step")),
            candidate_platform=self._string_or_none(data.get("candidate_platform")),
            provided_parameters=provided,
            user_confirmed=bool(data.get("user_confirmed", False)),
            explanation=str(data.get("explanation", "") or "").strip(),
            refusal_reason=str(data.get("refusal_reason", "") or "").strip(),
        )

    def _parse_json(self, content: str) -> Any:
        cleaned = content.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
            cleaned = cleaned.removesuffix("```").strip()

        return json.loads(cleaned)

    def _string_or_none(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
