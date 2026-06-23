from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParameterRequirement:
    name: str
    alternatives: tuple[str, ...] = ()
    required: bool = True
    recommendation: str = ""


@dataclass(frozen=True)
class StepSpec:
    stage: str
    step: str
    platform: str
    required_parameters: tuple[ParameterRequirement, ...]


@dataclass
class StepMatchResult:
    stage: str
    step: str
    platform: str
    completion_percent: int
    ready: bool
    provided_parameters: dict[str, Any] = field(default_factory=dict)
    required_parameters: list[str] = field(default_factory=list)
    missing_parameters: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class SubmitMasterParameterMatcher:
    """
    Deterministically compares provided/default parameters against required
    Submit Master step parameters.

    The LLM proposes intent/stage/step/platform. This matcher decides whether
    the request is actually complete enough to continue.
    """

    def __init__(self, step_specs: list[StepSpec] | None = None):
        self.step_specs = step_specs or self._default_step_specs()

    def match(
        self,
        provided_parameters: dict[str, Any],
        candidate_stage: str | None = None,
        candidate_step: str | None = None,
        candidate_platform: str | None = None,
    ) -> StepMatchResult:
        normalized = self._normalize_parameters(provided_parameters)

        candidates = self._candidate_specs(
            candidate_stage=candidate_stage,
            candidate_step=candidate_step,
            candidate_platform=candidate_platform,
        )

        if not candidates:
            stage = candidate_stage or self._text(normalized.get("stage")) or "unknown"
            step = candidate_step or self._text(normalized.get("step")) or self._text(normalized.get("steps_order")) or "unknown"
            platform = candidate_platform or self._text(normalized.get("seq_type")) or "illumina"
            candidates = [self._generic_spec(stage=stage, step=step, platform=platform)]

        matches = [self._score_candidate(spec, normalized) for spec in candidates]
        matches.sort(key=lambda item: item.completion_percent, reverse=True)
        return matches[0]

    def _candidate_specs(
        self,
        candidate_stage: str | None,
        candidate_step: str | None,
        candidate_platform: str | None,
    ) -> list[StepSpec]:
        specs = self.step_specs

        if candidate_stage:
            stage_value = self._canonical_stage(candidate_stage)
            specs = [spec for spec in specs if self._canonical_stage(spec.stage) == stage_value]

        if candidate_step:
            step_value = self._canonical(candidate_step)
            specs = [
                spec for spec in specs
                if self._canonical(spec.step) == step_value
                or step_value in self._canonical(spec.step)
                or self._canonical(spec.step) in step_value
            ]

        if candidate_platform:
            platform_value = self._canonical(candidate_platform)
            specs = [
                spec for spec in specs
                if self._canonical(spec.platform) == platform_value
            ]

        return specs

    def _score_candidate(self, spec: StepSpec, params: dict[str, Any]) -> StepMatchResult:
        required = [item for item in spec.required_parameters if item.required]
        provided_count = 0
        missing: list[str] = []
        recommendations: list[str] = []

        for requirement in required:
            if self._requirement_satisfied(requirement, params):
                provided_count += 1
            else:
                missing.append(self._requirement_label(requirement))
                if requirement.recommendation:
                    recommendations.append(requirement.recommendation)

        completion = 100
        if required:
            completion = round((provided_count / len(required)) * 100)

        return StepMatchResult(
            stage=spec.stage,
            step=spec.step,
            platform=spec.platform,
            completion_percent=completion,
            ready=completion == 100,
            provided_parameters={
                key: value
                for key, value in params.items()
                if value not in (None, "", [], {})
            },
            required_parameters=[self._requirement_label(item) for item in required],
            missing_parameters=missing,
            recommendations=recommendations,
        )

    def _requirement_satisfied(
        self,
        requirement: ParameterRequirement,
        params: dict[str, Any],
    ) -> bool:
        keys = (requirement.name, *requirement.alternatives)
        return any(self._has_value(params.get(key)) for key in keys)

    def _requirement_label(self, requirement: ParameterRequirement) -> str:
        keys = (requirement.name, *requirement.alternatives)
        return " or ".join(keys)

    def _normalize_parameters(self, params: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(params or {})

        if "platform" in normalized and "seq_type" not in normalized:
            normalized["seq_type"] = normalized["platform"]

        if "sample_id" in normalized and "sample_ids" not in normalized:
            normalized["sample_ids"] = normalized["sample_id"]

        if "sample" in normalized and "sample_ids" not in normalized:
            normalized["sample_ids"] = normalized["sample"]

        if "cluster" in normalized and "cluster_name" not in normalized:
            normalized["cluster_name"] = normalized["cluster"]

        if "step" not in normalized and "steps_order" in normalized:
            normalized["step"] = normalized["steps_order"]

        if "steps_order" not in normalized and "step" in normalized:
            normalized["steps_order"] = normalized["step"]

        return normalized

    def _default_step_specs(self) -> list[StepSpec]:
        common = (
            ParameterRequirement("stage", recommendation="Provide the pipeline stage, for example stage=stage2."),
            ParameterRequirement("step", ("steps_order",), recommendation="Provide the Submit Master step, for example step=haplotypecaller."),
            ParameterRequirement("seq_type", recommendation="Provide sequencing platform, for example seq_type=illumina."),
            ParameterRequirement("cluster_name", recommendation="Provide the Kubernetes cluster name used by Submit Master."),
            ParameterRequirement("namespace", recommendation="Provide the Kubernetes namespace, for example namespace=bioops."),
            ParameterRequirement("sample_ids", ("batch_id",), recommendation="Provide either explicit sample_ids or a batch_id."),
        )

        batch_mongo = common + (
            ParameterRequirement(
                "mongo_cluster_name",
                required=False,
                recommendation="If samples must be resolved from batch_id, provide mongo_cluster_name.",
            ),
        )

        return [
            StepSpec("stage1", "cutadapt", "illumina", common),
            StepSpec("stage1", "fq2bam", "illumina", common),
            StepSpec("stage1", "batch_qc", "illumina", common),
            StepSpec("stage2", "sex_assignment", "illumina", common),
            StepSpec("stage2", "split", "illumina", common),
            StepSpec("stage2", "imputation", "illumina", common),
            StepSpec("stage2", "haplotypecaller", "illumina", batch_mongo),
            StepSpec("stage2", "transfer_vcf", "illumina", common),
            StepSpec("stage3", "beagle", "illumina", common),
            StepSpec("stage3", "hla", "illumina", common),
            StepSpec("stage3", "hla_parser", "illumina", common),
            StepSpec("stage3", "apoe", "illumina", common),
            StepSpec("stage3", "yleaf", "illumina", common),
            StepSpec("stage3", "deep_mito", "illumina", common),
            StepSpec("stage3", "batch_report", "illumina", common),
            StepSpec("stage3", "final_checker", "illumina", common),
        ]

    def _generic_spec(self, stage: str, step: str, platform: str) -> StepSpec:
        return StepSpec(
            stage=stage,
            step=step,
            platform=platform,
            required_parameters=(
                ParameterRequirement("stage"),
                ParameterRequirement("step", ("steps_order",)),
                ParameterRequirement("seq_type"),
                ParameterRequirement("cluster_name"),
                ParameterRequirement("namespace"),
                ParameterRequirement("sample_ids", ("batch_id",)),
            ),
        )

    def _canonical_stage(self, value: str) -> str:
        text = self._canonical(value)
        if text.isdigit():
            return f"stage{text}"
        return text

    def _canonical(self, value: str) -> str:
        return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")

    def _text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _has_value(self, value: Any) -> bool:
        return value not in (None, "", [], {})
