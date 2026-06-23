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
    ready: bool
    provided_parameters: dict[str, Any] = field(default_factory=dict)
    required_parameters: list[str] = field(default_factory=list)
    missing_parameters: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    explanation: str = ""
    refusal_reason: str = ""


class SubmitMasterLLMPlanner:
    """
    Converts natural-language Submit Master requests into strict JSON plans.

    This tool does not launch workflows and does not mutate infrastructure.
    It only plans, compares provided vs required parameters, and asks for
    missing information when the request is incomplete.
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
                "Submit Master LLM planner unavailable: Azure OpenAI environment "
                "variables are not fully configured."
            )

        prompt = self._build_prompt(message=message, context=context)

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict planning layer for a bioinformatics "
                            "Submit Master agent. Return JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
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
                            "You are a strict planning layer for a bioinformatics "
                            "Submit Master agent. Return JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                max_tokens=1200,
            )
        except Exception as error:
            raise RuntimeError(
                f"Submit Master LLM planner request failed: {type(error).__name__}: {error}"
            ) from error

        content = response.choices[0].message.content or ""
        return self._parse_response(content)

    def _build_prompt(self, message: str, context: dict[str, Any]) -> str:
        return f"""
Convert the user request into a strict JSON planning decision for Submit Master.

The Submit Master agent prepares original-compatible submit-master JSON configs,
safe launch plans, monitoring reports, and failed-pod reports.

Do not invent missing deployment values.
Do not assume sample IDs, batch IDs, clusters, namespaces, stages, or steps.
If required information is missing, set ready=false and ask targeted questions.
If the request is unsafe, unsupported, or unclear, set intent="refuse" or ready=false.
A real launch is only possible when the user clearly requests confirmation, but
Python code will enforce the final safety gate using YAML allow_launch.

Valid intents:
- build_or_launch: generate config and possibly prepare/launch Submit Master
- monitor: monitor running/completed Submit Master workflows
- failed_pods: report failed pods and log-derived causes
- restart_failed_pods: restart failed pods; currently not implemented, refuse safely
- explain_config: explain which parameters are needed and why
- refuse: refuse or ask user to rephrase safely

Important required-parameter rules:
- For build_or_launch, compare the user-provided values to the required config values:
  stage, step or steps_order, seq_type, cluster_name, namespace, and either sample_ids or batch_id.
- If batch_id is used and mongo_cluster_name is required by the deployment context, ask for it.
- For monitor, require batch_id or workflow_name.
- For failed_pods, require batch_id or workflow_name.
- For restart_failed_pods, refuse because D5 is not implemented yet.
- Always include required_parameters, provided_parameters, missing_parameters, recommendations, and questions.

Context from YAML/environment/known Submit Master maps:
{json.dumps(context, indent=2, sort_keys=True)}

Return JSON only with exactly this shape:
{{
  "intent": "build_or_launch|monitor|failed_pods|restart_failed_pods|explain_config|refuse",
  "ready": true,
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
  "required_parameters": [],
  "missing_parameters": [],
  "recommendations": [],
  "questions": [],
  "explanation": "short explanation",
  "refusal_reason": ""
}}

User request:
{message}
""".strip()

    def _parse_response(self, content: str) -> SubmitMasterPlannerDecision:
        data = self._parse_json(content)

        if not isinstance(data, dict):
            raise ValueError("Submit Master LLM planner returned invalid JSON.")

        intent = str(data.get("intent", "")).strip().lower()
        if intent not in VALID_INTENTS:
            raise ValueError(f"Submit Master LLM planner returned invalid intent: {intent}")

        provided = data.get("provided_parameters", {})
        if not isinstance(provided, dict):
            provided = {}

        required = data.get("required_parameters", [])
        missing = data.get("missing_parameters", [])
        recommendations = data.get("recommendations", [])
        questions = data.get("questions", [])

        return SubmitMasterPlannerDecision(
            intent=intent,
            ready=bool(data.get("ready", False)),
            provided_parameters=provided,
            required_parameters=self._string_list(required),
            missing_parameters=self._string_list(missing),
            recommendations=self._string_list(recommendations),
            questions=self._string_list(questions),
            explanation=str(data.get("explanation", "") or "").strip(),
            refusal_reason=str(data.get("refusal_reason", "") or "").strip(),
        )

    def _parse_json(self, content: str) -> Any:
        cleaned = content.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
            cleaned = cleaned.removesuffix("```").strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []

        return [str(item) for item in value if str(item).strip()]
