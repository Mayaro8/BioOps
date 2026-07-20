from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PodErrorAnalysis:
    category: str
    severity: str
    likely_cause: str
    evidence: str
    recommended_action: str


def analyze_pod_errors(errors: list[str]) -> list[PodErrorAnalysis]:
    """Classify bounded Kubernetes error evidence for operator notifications."""

    return [_analyze_error(error) for error in errors]


def _analyze_error(error: str) -> PodErrorAnalysis:
    evidence = " ".join(str(error).split())[:400]
    lowered = evidence.casefold()

    if "oomkilled" in lowered or "out of memory" in lowered:
        return PodErrorAnalysis(
            category="resource_exhaustion",
            severity="critical",
            likely_cause="The container exceeded its memory limit.",
            evidence=evidence,
            recommended_action=(
                "Inspect memory usage and limits, then resize or reduce the workload."
            ),
        )

    if "imagepull" in lowered or "image pull" in lowered:
        return PodErrorAnalysis(
            category="image_retrieval",
            severity="critical",
            likely_cause="Kubernetes could not retrieve the configured image.",
            evidence=evidence,
            recommended_action=(
                "Verify the image name, tag, registry access, and pull secret."
            ),
        )

    if "forbidden" in lowered or "permission denied" in lowered:
        return PodErrorAnalysis(
            category="access_control",
            severity="critical",
            likely_cause="The workload lacks a required permission.",
            evidence=evidence,
            recommended_action=(
                "Check the service account, RBAC bindings, mounted credentials, and file access."
            ),
        )

    if "crashloopbackoff" in lowered:
        return PodErrorAnalysis(
            category="application_crash_loop",
            severity="critical",
            likely_cause="The container repeatedly exits during startup or execution.",
            evidence=evidence,
            recommended_action=(
                "Inspect the previous container log and its exit code before retrying."
            ),
        )

    if any(
        marker in lowered
        for marker in ("timeout", "connection refused", "unavailable")
    ):
        return PodErrorAnalysis(
            category="dependency_or_network",
            severity="warning",
            likely_cause="A network service or dependency was unavailable or too slow.",
            evidence=evidence,
            recommended_action=(
                "Check dependency health, Services, endpoints, DNS, and retry policy."
            ),
        )

    if "evicted" in lowered or "nodelost" in lowered:
        return PodErrorAnalysis(
            category="node_or_scheduling",
            severity="warning",
            likely_cause="The pod lost its node or was evicted by Kubernetes.",
            evidence=evidence,
            recommended_action=(
                "Inspect node pressure and scheduling events, then confirm rescheduling."
            ),
        )

    return PodErrorAnalysis(
        category="application_error",
        severity="warning",
        likely_cause="The pod reported an application or container failure.",
        evidence=evidence,
        recommended_action=(
            "Inspect the surrounding pod log and Kubernetes events for the first failure."
        ),
    )
