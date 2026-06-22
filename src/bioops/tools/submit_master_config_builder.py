from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from bioops.tools.submit_master_clusters import resolve_cluster, resolve_mongo_cluster
from bioops.tools.submit_master_methods import METHOD_MAP
from bioops.tools.submit_master_stages import (
    STAGE1_ALL_STEPS,
    STAGE2_ALL_STEPS,
    STAGE3_ALL_STEPS,
    STAGE3_NO_BEAGLE_STEPS,
)

MONGO_CLUSTER_STEPS = {"sex_bitrix"}


@dataclass
class SubmitMasterConfigInput:
    stage: str
    steps_order: str
    seq_type: str = "illumina"
    cluster_name: str = ""
    mongo_cluster_name: str = ""
    namespace: str = "default"
    sample_ids: list[str] = field(default_factory=list)
    batch_id: str | None = None
    run_id: str | None = None
    delay: int = 0
    delay_step: int = 1
    chunk_size: int = 1
    wait: bool = True
    only_good: bool = True
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubmitMasterConfigResult:
    entries: list[dict[str, Any]]
    json_text: str
    errors: list[str]
    warnings: list[str]


class SubmitMasterConfigBuilder:
    """Build original-compatible submit-master JSON configs.

    This class is side-effect free. It does not launch Argo or Kubernetes jobs.
    """

    def build(self, request: SubmitMasterConfigInput) -> SubmitMasterConfigResult:
        errors: list[str] = []
        warnings: list[str] = []

        stage = self._normalize_stage(request.stage)
        seq_type = (request.seq_type or "illumina").strip().lower()
        cluster_name = resolve_cluster(request.cluster_name)
        mongo_cluster_name = resolve_mongo_cluster(request.mongo_cluster_name, cluster_name)

        steps = self._resolve_steps(stage, seq_type, request.steps_order)

        if not stage:
            errors.append("stage is required")

        if not request.steps_order:
            errors.append("step or steps_order is required")

        if not cluster_name:
            errors.append("cluster_name is required")

        if not request.sample_ids and not request.batch_id:
            errors.append("sample_ids or batch_id is required")

        if not steps:
            errors.append("No steps resolved from stage/steps_order/seq_type")

        entries: list[dict[str, Any]] = []

        for step in steps:
            method_name = METHOD_MAP.get(step)

            if not method_name:
                errors.append(f"Unsupported submit-master step: {step}")
                continue

            step_cluster = mongo_cluster_name if step in MONGO_CLUSTER_STEPS else cluster_name

            entry: dict[str, Any] = {
                "submit_method": method_name,
                "k8s_cluster_name": step_cluster,
                "namespace": request.namespace or "default",
                "delay_config": {
                    "delay": request.delay,
                    "step": request.delay_step,
                    "chunk_size": request.chunk_size,
                },
                "wait": request.wait,
                "only_good": request.only_good,
            }

            if request.sample_ids:
                entry["sample_ids"] = [{"sample_id": sample_id} for sample_id in request.sample_ids]

            if request.batch_id:
                entry["batch_id"] = request.batch_id

            if request.run_id:
                entry["run_id"] = request.run_id

            for key, value in request.extra_params.items():
                if key not in entry and value not in {None, ""}:
                    entry[key] = value

            entries.append(entry)

        json_text = json.dumps(entries, indent=2, ensure_ascii=False)

        return SubmitMasterConfigResult(
            entries=entries,
            json_text=json_text,
            errors=errors,
            warnings=warnings,
        )

    def _normalize_stage(self, stage: str | None) -> str:
        value = (stage or "").strip().lower().replace("_", "").replace("-", "")

        if value in {"1", "stage1"}:
            return "stage1"

        if value in {"2", "stage2"}:
            return "stage2"

        if value in {"3", "stage3"}:
            return "stage3"

        return value

    def _resolve_steps(self, stage: str, seq_type: str, steps_order: str | None) -> list[str]:
        raw_steps = [
            item.strip().lower()
            for item in (steps_order or "").split(",")
            if item.strip()
        ]

        if not raw_steps:
            return []

        if raw_steps[0] == "all":
            if stage == "stage1":
                return STAGE1_ALL_STEPS.get(seq_type, [])

            if stage == "stage2":
                return STAGE2_ALL_STEPS.get(seq_type, [])

            if stage == "stage3":
                return STAGE3_ALL_STEPS.copy()

        if raw_steps[0] == "no_bgl" and stage == "stage3":
            return STAGE3_NO_BEAGLE_STEPS.copy()

        return raw_steps
