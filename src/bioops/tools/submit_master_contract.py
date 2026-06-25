from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CONFIG_CREATOR_REQUIRED_PARAMS = [
    "stage",
    "seq_type",
    "mode",
    "cluster_num",
    "mongo_cluster_label",
    "batch_id",
    "batch_date_id",
    "run_num",
    "samples_ids_str",
]

CONFIG_CREATOR_OPTIONAL_PARAMS = [
    "run_id",
    "input_paths_list",
    "runs_list",
    "tel_chat",
    "tel_token",
    "config_output_dir",
    "bitrix_task_id",
    "exclude_samples",
    "output_reports_path_s3",
    "batchids_prs",
    "mode_prs",
]


@dataclass(frozen=True)
class MissingParameterReport:
    missing: list[str]

    @property
    def ready(self) -> bool:
        return not self.missing


def normalize_key(key: str) -> str:
    return key.strip().replace("-", "_")


def normalize_params(params: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        clean_key = normalize_key(str(key))
        clean_value = str(value).strip()
        if clean_key and clean_value:
            normalized[clean_key] = clean_value
    return normalized


def find_missing_config_creator_params(params: dict[str, Any]) -> MissingParameterReport:
    normalized = normalize_params(params)
    missing = [key for key in CONFIG_CREATOR_REQUIRED_PARAMS if not normalized.get(key)]
    return MissingParameterReport(missing=missing)


def split_cli_like_params(message: str) -> dict[str, str]:
    """
    Parse simple key=value tokens from a BioOps message.

    Example:
        launch submit master stage=3 mode=hla batch_id=batch123
    """
    parsed: dict[str, str] = {}

    for token in message.replace("\n", " ").split():
        if "=" not in token:
            continue

        key, value = token.split("=", 1)
        key = normalize_key(key)
        value = value.strip().strip("\"'")

        if key and value:
            parsed[key] = value

    return parsed
