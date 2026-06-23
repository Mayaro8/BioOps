from __future__ import annotations

CLUSTER_MAP: dict[str, str] = {
    "1": "pipeline-v3",
    "2": "pipeline-v3-2",
    "3": "pipeline-v3-3",
    "4": "pipeline-v3-4",
    "5": "pipeline-v3-common-2",
    "6": "pipeline-v3-common-3",
    "7": "pipeline-v3-common-4",
}

MONGO_CLUSTER_MAP: dict[str, str] = {
    "common": "pipeline-v3-4",
    "dev": "analysis-pipeline-dev",
    "prod": "analysis-pipeline-test",
    "5": "pipeline-v3-common-2",
    "6": "pipeline-v3-common-3",
    "7": "pipeline-v3-common-4",
}


def resolve_cluster(value: str | None) -> str:
    if not value:
        return ""

    normalized = value.strip()
    return CLUSTER_MAP.get(normalized, normalized)


def resolve_mongo_cluster(value: str | None, fallback_cluster: str = "") -> str:
    if not value:
        return fallback_cluster

    normalized = value.strip().lower()
    return MONGO_CLUSTER_MAP.get(normalized, value.strip())
