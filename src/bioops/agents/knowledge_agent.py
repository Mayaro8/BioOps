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
        message_lower = message.lower().strip()

        matched_step = self._find_step(message_lower)

        if matched_step:
            requested_field = self._detect_requested_field(message_lower)

            if requested_field:
                return self._format_step_field_answer(matched_step, requested_field)

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
            description = str(step_data.get("description", ""))

            aliases = [
                step_id.lower(),
                step_name.lower(),
                description.lower(),
            ]

            aliases.extend(
                str(alias).lower()
                for alias in step_data.get("aliases", [])
            )

            if any(alias and alias in message for alias in aliases):
                return step_data

        return None

    def _detect_requested_field(self, message: str) -> str | None:
        field_keywords = {
            "inputs": [
                "input",
                "inputs",
                "take",
                "takes",
                "require",
                "requires",
                "needed",
            ],
            "outputs": [
                "output",
                "outputs",
                "produce",
                "produces",
                "result",
                "results",
                "generate",
                "generates",
            ],
            "run_parameters": [
                "parameter",
                "parameters",
                "param",
                "params",
                "argument",
                "arguments",
                "option",
                "options",
            ],
            "how_it_works": [
                "how",
                "how it works",
                "explain",
                "logic",
                "what does it do",
                "purpose",
            ],
            "docs_url": [
                "docs",
                "documentation",
                "manual",
            ],
            "repo_url": [
                "repo",
                "repository",
                "github",
                "source code",
            ],
        }

        for field, keywords in field_keywords.items():
            if any(keyword in message for keyword in keywords):
                return field

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

    def _format_step_field_answer(self, step: dict[str, Any], field: str) -> str:
        step_name = step.get("name", "unknown")

        field_titles = {
            "inputs": "Inputs",
            "outputs": "Outputs",
            "run_parameters": "Run parameters",
            "how_it_works": "How it works",
            "docs_url": "Documentation",
            "repo_url": "Repository",
        }

        title = field_titles.get(field, field)
        value = step.get(field)

        if field in {"inputs", "outputs", "run_parameters"}:
            formatted_value = self._format_list(value or [])
        else:
            formatted_value = value or "Not configured"

        return "\n".join(
            [
                f"Step: {step_name}",
                "",
                f"{title}:",
                formatted_value,
                "",
                "Primary source:",
                self._get_primary_source(step),
            ]
        )

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
                "",
                "Primary source:",
                self._get_primary_source(step),
            ]
        )

    def _get_primary_source(self, step: dict[str, Any]) -> str:
        docs_url = step.get("docs_url")
        repo_url = step.get("repo_url")

        if docs_url and docs_url != "TODO: add documentation link":
            return docs_url

        if repo_url and repo_url != "TODO: add repository link":
            return repo_url

        return "Not configured"

    def _format_list(self, values: list[str]) -> str:
        if not values:
            return "- Not configured"

        return "\n".join(f"- {value}" for value in values)

    def _format_not_found_answer(self) -> str:
        steps = self.knowledge.get("steps", {})

        if not steps:
            return (
                "I could not find a matching pipeline step because no steps are "
                "configured in configs/knowledge_sources.yaml."
            )

        configured_steps = "\n".join(
            f"- {step.get('name', step_id)}"
            for step_id, step in steps.items()
        )

        return (
            "I could not find a matching pipeline step in the configured knowledge sources.\n\n"
            "Try asking about one of these configured steps:\n"
            f"{configured_steps}\n\n"
            "You can ask for inputs, outputs, run parameters, how the step works, "
            "documentation, or repository links."
        )