from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bioops.tools.submit_master_parameter_matcher import StepSpec, SubmitMasterParameterMatcher


@dataclass
class SubmitMasterInterpretation:
    status: str
    candidate_stage: str | None = None
    candidate_step: str | None = None
    candidate_platform: str | None = None
    explanation: str = ""
    clarification_question: str = ""
    alternatives: list[str] = field(default_factory=list)


class SubmitMasterInterpreter:
    """
    LLM-assisted interpretation layer.

    The LLM planner extracts intent/parameters first.
    This interpreter resolves ambiguous human wording against known deterministic step specs.
    It never launches anything.
    """

    def __init__(self, matcher: SubmitMasterParameterMatcher | None = None):
        self.matcher = matcher or SubmitMasterParameterMatcher()

    def interpret(
        self,
        message: str,
        provided_parameters: dict[str, Any],
        candidate_stage: str | None = None,
        candidate_step: str | None = None,
        candidate_platform: str | None = None,
    ) -> SubmitMasterInterpretation:
        text = self._canonical(message)
        step_text = self._canonical(
            candidate_step
            or provided_parameters.get("step")
            or provided_parameters.get("steps_order")
            or ""
        )

        platform = candidate_platform or provided_parameters.get("seq_type") or "illumina"

        exact = self._find_exact_step(step_text)
        if exact:
            return SubmitMasterInterpretation(
                status="interpreted",
                candidate_stage=exact.stage,
                candidate_step=exact.step,
                candidate_platform=exact.platform,
                explanation=(
                    f'I interpreted "{candidate_step or provided_parameters.get("step") or exact.step}" '
                    f"as {exact.stage}/{exact.step}/{exact.platform}."
                ),
            )

        message_hits = self._find_steps_mentioned_in_message(text)
        if len(message_hits) == 1:
            hit = message_hits[0]
            return SubmitMasterInterpretation(
                status="interpreted",
                candidate_stage=hit.stage,
                candidate_step=hit.step,
                candidate_platform=hit.platform,
                explanation=(
                    f"I found a sensible Submit Master step in the prompt: "
                    f"{hit.stage}/{hit.step}/{hit.platform}."
                ),
            )

        if self._looks_like_numbered_step(step_text) or self._looks_like_numbered_step(text):
            alternatives = self._stage_alternatives(candidate_stage, platform)
            return SubmitMasterInterpretation(
                status="needs_clarification",
                candidate_stage=candidate_stage,
                candidate_step=candidate_step,
                candidate_platform=str(platform),
                explanation="The prompt used numbered wording such as step2, which is ambiguous.",
                clarification_question=(
                    "Which Submit Master step do you mean? "
                    "Please choose one of the possible steps or provide the exact step name."
                ),
                alternatives=alternatives,
            )

        if len(message_hits) > 1:
            return SubmitMasterInterpretation(
                status="needs_clarification",
                candidate_stage=candidate_stage,
                candidate_step=candidate_step,
                candidate_platform=str(platform),
                explanation="The prompt matches more than one known Submit Master step.",
                clarification_question="Which step do you want to run?",
                alternatives=[
                    f"{item.stage}/{item.step}/{item.platform}" for item in message_hits
                ],
            )

        return SubmitMasterInterpretation(
            status="interpreted",
            candidate_stage=candidate_stage,
            candidate_step=candidate_step,
            candidate_platform=str(platform) if platform else None,
            explanation="No extra interpretation was needed beyond the LLM planner output.",
        )

    def _find_exact_step(self, step_text: str) -> StepSpec | None:
        if not step_text:
            return None
        for spec in self.matcher.step_specs:
            if self._canonical(spec.step) == step_text:
                return spec
        return None

    def _find_steps_mentioned_in_message(self, text: str) -> list[StepSpec]:
        hits = []
        for spec in self.matcher.step_specs:
            step = self._canonical(spec.step)
            if step and step in text:
                hits.append(spec)
        return hits

    def _stage_alternatives(self, candidate_stage: str | None, platform: Any) -> list[str]:
        platform_text = self._canonical(platform or "illumina")
        stage_text = self._canonical_stage(candidate_stage) if candidate_stage else None

        specs = self.matcher.step_specs
        if stage_text:
            specs = [spec for spec in specs if self._canonical_stage(spec.stage) == stage_text]

        specs = [
            spec for spec in specs
            if self._canonical(spec.platform) == platform_text
        ]

        if not specs:
            specs = self.matcher.step_specs

        return [f"{spec.stage}/{spec.step}/{spec.platform}" for spec in specs]

    def _looks_like_numbered_step(self, text: str) -> bool:
        value = self._canonical(text)
        return "step2" in value or "step_2" in value or value in {"2", "second_step"}

    def _canonical_stage(self, value: Any) -> str:
        text = self._canonical(value)
        if text.isdigit():
            return f"stage{text}"
        return text

    def _canonical(self, value: Any) -> str:
        return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
