from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent


class KnowledgeAgent(BaseAgent):
    """Answers questions about pipeline-v3.0 documentation and step metadata."""

    name = "knowledge"
    description = "Answers questions about pipeline-v3.0 documentation."

    def __init__(self, config_path: str = "configs/knowledge_sources.yaml"):
        self.config_path = Path(config_path)
        self.knowledge = self._load_knowledge()

    def run(self, message: str) -> str:
        message_lower = message.lower()

        matched_step = self._find_step(message_lower)
        if matched_step:
            return self._format_step_answer(matched_step)

        if self._is_pipeline_overview_question(message_lower):
            return self._format_pipeline_overview()

        return self._format_not_found_answer()

    def _load_knowledge(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Knowledge config not found: {self.config_path}")

        with self.config_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

        if not data:
            raise ValueError(f"Knowledge config is empty: {self.config_path}")

        return data

    def _find_step(self, message: str) -> dict[str, Any] | None:
        steps = self.knowledge.get("steps", {})

        for step_id, step_data in steps.items():
            step_name = str(step_data.get("name", ""))
            aliases = [step_id.lower(), step_name.lower()]

            if any(alias and alias in message for alias in aliases):
                return step_data

        return None

    def _is_pipeline_overview_question(self, message: str) -> bool:
        keywords = [
            "pipeline",
            "overview",
            "steps",
            "order",
            "sequence",
            "pipeline-v3.0",
        ]

        return any(keyword in message for keyword in keywords)

    def _format_pipeline_overview(self) -> str:
        pipeline = self.knowledge.get("pipeline", {})
        steps = self.knowledge.get("steps", {})

        if not steps:
            return "No pipeline steps are configured yet."

        ordered_steps = sorted(
            steps.values(),
            key=lambda step: step.get("order", 9999),
        )

        lines = [
            f"Pipeline: {pipeline.get('name', 'pipeline-v3.0')}",
            "",
            pipeline.get("description", "No pipeline description configured."),
            "",
            "Configured steps:",
        ]

        for step in ordered_steps:
            lines.append(
                f"{step.get('order', '?')}. {step.get('name', 'unknown')} — "
                f"{step.get('description', 'No description configured.')}"
            )

        lines.extend(
            [
                "",
                "Sources:",
                "- Step documentation/repository links are shown in specific step answers.",
            ]
        )

        return "\n".join(lines)

    def _format_step_answer(self, step: dict[str, Any]) -> str:
        return "\n".join(
            [
                f"Step: {step.get('name', 'unknown')}",
                "",
                "Purpose:",
                step.get("description", "No description configured."),
                "",
                "Inputs:",
                self._format_list(step.get("inputs", [])),
                "",
                "Outputs:",
                self._format_list(step.get("outputs", [])),
                "",
                "How it works:",
                step.get("how_it_works", "No explanation configured."),
                "",
                "Run parameters:",
                self._format_list(step.get("run_parameters", [])),
                "",
                "Sources:",
                f"- Documentation: {step.get('docs_url', 'Not configured')}",
                f"- Repository: {step.get('repo_url', 'Not configured')}",
            ]
        )

    def _format_list(self, values: list[str]) -> str:
        if not values:
            return "- Not configured"

        return "\n".join(f"- {value}" for value in values)

    def _format_not_found_answer(self) -> str:
        return (
            "I could not find a matching pipeline step in the configured knowledge sources.\n\n"
            "Try asking about:\n"
            "- pipeline overview\n"
            "- configured steps\n"
            "- a specific step name\n\n"
            "If this is a real pipeline-v3.0 step, add it to configs/knowledge_sources.yaml."
        )