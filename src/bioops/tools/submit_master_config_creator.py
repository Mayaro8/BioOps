from __future__ import annotations

import ast
import csv
import re
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from bioops.tools.submit_master_methods import METHOD_MAP as FALLBACK_METHOD_MAP
from bioops.tools.submit_master_stages import (
    STAGE1_ALL_STEPS as FALLBACK_STAGE1_ALL_STEPS,
    STAGE2_ALL_STEPS as FALLBACK_STAGE2_ALL_STEPS,
    STAGE3_ALL_STEPS as FALLBACK_STAGE3_ALL_STEPS,
    STAGE3_NO_BEAGLE_STEPS as FALLBACK_STAGE3_NO_BEAGLE_STEPS,
)


TEXT_SUFFIXES = {".py", ".sh", ".tsv", ".csv", ".txt", ".json", ".yaml", ".yml"}

COMMON_CONFIG_KEYS = {
    "submit_method",
    "k8s_cluster_name",
    "cluster_name",
    "mongo_cluster_name",
    "namespace",
    "delay_config",
    "delay",
    "delay_step",
    "chunk_size",
    "wait",
    "only_good",
    "sample_ids",
    "sample_id",
    "samples",
    "batch_id",
    "run_id",
    "contour",
    "workflow_file",
    "confirm",
}

RUNTIME_NAMES = {
    "self",
    "cls",
    "client",
    "api_client",
    "core_api",
    "custom_api",
    "logger",
    "config",
    "kwargs",
    "args",
}

RUNTIME_SELF_ATTRS = {
    "logger",
    "config",
    "args",
    "namespace",
    "k8s_cluster_name",
    "cluster_name",
    "mongo_cluster_name",
    "sample_ids",
    "batch_id",
    "delay_config",
    "wait",
    "only_good",
    "run_id",
    "contour",
}


@dataclass(frozen=True)
class SubmitMethodContract:
    submit_method: str
    required_parameters: tuple[str, ...] = ()
    optional_parameters: tuple[str, ...] = ()
    provided_by_config_creator: tuple[str, ...] = ()
    source: str = "fallback"

    def user_required_parameters(self) -> tuple[str, ...]:
        provided = set(self.provided_by_config_creator)
        return tuple(
            param
            for param in self.required_parameters
            if param not in provided
        )

    def all_parameters(self) -> tuple[str, ...]:
        return tuple(
            _dedupe_keep_order(
                (
                    *self.required_parameters,
                    *self.optional_parameters,
                    *self.provided_by_config_creator,
                )
            )
        )


@dataclass(frozen=True, kw_only=True)
class SubmitMasterConfigCreatorCatalog:
    method_map: dict[str, str]
    method_contracts: dict[str, SubmitMethodContract] = field(default_factory=dict)
    stage1_all_steps: dict[str, list[str]]
    stage2_all_steps: dict[str, list[str]]
    stage3_all_steps: list[str]
    stage3_no_beagle_steps: list[str]
    source: str = "fallback"
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, repo_root: Path | None = None) -> "SubmitMasterConfigCreatorCatalog":
        root = repo_root or _discover_repo_root()
        warnings: list[str] = []

        config_creator_sources, creator_source, creator_warnings = _read_config_creator_sources(root)
        submit_master_sources, submit_source, submit_warnings = _read_submit_master_sources(root)
        warnings.extend(creator_warnings)
        warnings.extend(submit_warnings)

        method_map = dict(FALLBACK_METHOD_MAP)
        stage1_all_steps = {k: v.copy() for k, v in FALLBACK_STAGE1_ALL_STEPS.items()}
        stage2_all_steps = {k: v.copy() for k, v in FALLBACK_STAGE2_ALL_STEPS.items()}
        stage3_all_steps = FALLBACK_STAGE3_ALL_STEPS.copy()
        stage3_no_beagle_steps = FALLBACK_STAGE3_NO_BEAGLE_STEPS.copy()

        parsed_creator = _parse_config_creator_sources(config_creator_sources)
        method_map.update(parsed_creator.method_map)

        for platform, steps in parsed_creator.stage1_all_steps.items():
            if steps:
                stage1_all_steps[platform] = steps
        for platform, steps in parsed_creator.stage2_all_steps.items():
            if steps:
                stage2_all_steps[platform] = steps
        if parsed_creator.stage3_all_steps:
            stage3_all_steps = parsed_creator.stage3_all_steps
        if parsed_creator.stage3_no_beagle_steps:
            stage3_no_beagle_steps = parsed_creator.stage3_no_beagle_steps

        contracts = _extract_submit_method_contracts(submit_master_sources)
        creator_key_contracts = _extract_creator_entry_contracts(config_creator_sources)

        merged_contracts: dict[str, SubmitMethodContract] = {}

        for submit_method in set(method_map.values()) | set(contracts) | set(creator_key_contracts):
            signature_contract = contracts.get(submit_method)
            creator_contract = creator_key_contracts.get(submit_method)

            required = []
            optional = []

            if signature_contract:
                required.extend(signature_contract.required_parameters)
                optional.extend(signature_contract.optional_parameters)

            provided_by_creator = []

            if creator_contract:
                # Config Creator dictionary entries mean: this key is already
                # assigned by the creator layer, so the user should not be asked
                # for it unless no value is actually provided elsewhere.
                provided_by_creator.extend(creator_contract.provided_by_config_creator)
                optional.extend(creator_contract.optional_parameters)

            provided_by_creator = [
                p
                for p in _dedupe_keep_order(_canonical_param(p) for p in provided_by_creator)
                if p and p not in COMMON_CONFIG_KEYS
            ]

            required = [
                p for p in _dedupe_keep_order(_canonical_param(p) for p in required)
                if p
                and p not in COMMON_CONFIG_KEYS
                and p not in provided_by_creator
            ]
            optional = [
                p for p in _dedupe_keep_order(_canonical_param(p) for p in optional)
                if p and p not in COMMON_CONFIG_KEYS and p not in required
            ]

            merged_contracts[submit_method] = SubmitMethodContract(
                submit_method=submit_method,
                required_parameters=tuple(required),
                optional_parameters=tuple(optional),
                provided_by_config_creator=tuple(provided_by_creator),
                source=f"{submit_source}; {creator_source}",
            )

        if not submit_master_sources:
            warnings.append("Original submit_master source was not readable; method contracts may be incomplete.")
        if not config_creator_sources:
            warnings.append("Original config_creator source was not readable; using BioOps fallback step maps.")

        return cls(
            method_map=method_map,
            method_contracts=merged_contracts,
            stage1_all_steps=stage1_all_steps,
            stage2_all_steps=stage2_all_steps,
            stage3_all_steps=stage3_all_steps,
            stage3_no_beagle_steps=stage3_no_beagle_steps,
            source=f"submit_master={submit_source}; config_creator={creator_source}",
            warnings=warnings,
        )

    def contract_for_step(self, step: str) -> SubmitMethodContract | None:
        method = self.method_map.get(_canonical_step(step))
        if not method:
            return None
        return self.method_contracts.get(method)

    def contract_for_method(self, submit_method: str) -> SubmitMethodContract | None:
        return self.method_contracts.get(submit_method)


@dataclass
class _ParsedCreatorSources:
    method_map: dict[str, str] = field(default_factory=dict)
    stage1_all_steps: dict[str, list[str]] = field(default_factory=dict)
    stage2_all_steps: dict[str, list[str]] = field(default_factory=dict)
    stage3_all_steps: list[str] = field(default_factory=list)
    stage3_no_beagle_steps: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def load_default_submit_master_config_creator_catalog() -> SubmitMasterConfigCreatorCatalog:
    return SubmitMasterConfigCreatorCatalog.load()


def _discover_repo_root() -> Path:
    start = Path(__file__).resolve()
    for parent in start.parents:
        if (parent / "submit_master_files").exists():
            return parent
    return start.parents[3]


def _read_config_creator_sources(repo_root: Path) -> tuple[dict[str, str], str, list[str]]:
    return _read_sources(
        extracted_dir=repo_root / "submit_master_files" / "submit-master-config-creator",
        zip_path=repo_root / "submit_master_files" / "config_creator.zip",
        label="config_creator",
    )


def _read_submit_master_sources(repo_root: Path) -> tuple[dict[str, str], str, list[str]]:
    return _read_sources(
        extracted_dir=repo_root / "submit_master_files" / "argo-submit-master",
        zip_path=repo_root / "submit_master_files" / "submit_master.zip",
        label="submit_master",
    )


def _read_sources(
    extracted_dir: Path,
    zip_path: Path,
    label: str,
) -> tuple[dict[str, str], str, list[str]]:
    warnings: list[str] = []

    if extracted_dir.is_dir():
        sources = _read_text_files_from_directory(extracted_dir)
        if sources:
            return sources, str(extracted_dir), warnings
        warnings.append(f"{label}: no readable text files found in {extracted_dir}")

    if zip_path.exists():
        try:
            sources = _read_text_files_from_zip(zip_path)
        except zipfile.BadZipFile:
            sources = {}
            warnings.append(f"{label}: invalid zip archive: {zip_path}")
        if sources:
            return sources, str(zip_path), warnings
        warnings.append(f"{label}: no readable text files found in {zip_path}")

    return {}, "fallback", warnings


def _read_text_files_from_directory(path: Path) -> dict[str, str]:
    sources: dict[str, str] = {}
    for file_path in path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = _safe_read_text(file_path.read_bytes())
        if text is not None:
            sources[str(file_path.relative_to(path))] = text
    return sources


def _read_text_files_from_zip(path: Path) -> dict[str, str]:
    sources: dict[str, str] = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if Path(info.filename).suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = _safe_read_text(archive.read(info.filename))
            if text is not None:
                sources[info.filename] = text
    return sources


def _safe_read_text(raw: bytes) -> str | None:
    for encoding in ("utf-8", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _parse_config_creator_sources(sources: dict[str, str]) -> _ParsedCreatorSources:
    parsed = _ParsedCreatorSources()

    for name, text in sources.items():
        if Path(name).name.lower() in {"methods.tsv", "methods.csv", "methods.txt"}:
            parsed.method_map.update(_parse_methods_table(text))

    # Do not infer stage expansion by scanning whole original stage scripts.
    # Those scripts contain multiple conditional branches, so a simple text scan
    # can mix unrelated steps from different platforms/stages.
    #
    # Keep the existing BioOps stage maps as the canonical stage expansion layer
    # until we add a precise parser for the original config creator control flow.
    return _deduplicate_parsed_creator(parsed)


def _parse_methods_table(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    rows = _read_delimited_rows(text)
    if not rows:
        return result

    header = rows[0] if _row_looks_like_header(rows[0]) else None
    data_rows = rows[1:] if header else rows

    for row in data_rows:
        record = _row_to_record(header, row) if header else {}
        submit_method = _first_present(
            record,
            ("submit_method", "method", "argo_method", "function", "submit_function"),
        )

        if not submit_method:
            submit_method = next((cell for cell in row if cell.startswith("submit_")), "")

        step = _first_present(record, ("step", "steps_order", "name", "key"))
        if not step:
            step = next((cell for cell in row if cell and not cell.startswith("submit_")), "")

        if step and submit_method:
            result[_canonical_step(step)] = submit_method

    return result


def _parse_stage_scripts(sources: dict[str, str], parsed: _ParsedCreatorSources) -> None:
    known_steps = set(FALLBACK_METHOD_MAP) | set(parsed.method_map)

    for name, text in sources.items():
        lowered = name.lower()
        stage = ""
        if "stage1" in lowered or "stage_1" in lowered:
            stage = "stage1"
        elif "stage2" in lowered or "stage_2" in lowered:
            stage = "stage2"
        elif "stage3" in lowered or "stage_3" in lowered:
            stage = "stage3"

        if not stage:
            continue

        if stage in {"stage1", "stage2"}:
            for platform in ("illumina", "salus", "surf", "mgi"):
                steps = _ordered_steps_seen_in_text(text, known_steps, platform)
                if steps:
                    if stage == "stage1":
                        parsed.stage1_all_steps[platform] = steps
                    else:
                        parsed.stage2_all_steps[platform] = steps

        if stage == "stage3":
            steps = _ordered_steps_seen_in_text(text, known_steps, None)
            if steps:
                parsed.stage3_all_steps = steps
                parsed.stage3_no_beagle_steps = [s for s in steps if s != "beagle"]


def _ordered_steps_seen_in_text(text: str, known_steps: set[str], platform: str | None) -> list[str]:
    text_lower = text.lower()
    hits: list[tuple[int, str]] = []

    for step in known_steps:
        if platform and platform not in step and step in {"cutadapt_illumina", "fq2bam_illumina"}:
            if platform != "illumina":
                continue

        patterns = [step, step.replace("_", "-")]
        method = FALLBACK_METHOD_MAP.get(step)
        if method:
            patterns.append(method)

        for pattern in patterns:
            index = text_lower.find(pattern.lower())
            if index >= 0:
                hits.append((index, step))
                break

    hits.sort(key=lambda item: item[0])
    return _dedupe_keep_order(step for _, step in hits)


def _extract_submit_method_contracts(sources: dict[str, str]) -> dict[str, SubmitMethodContract]:
    contracts: dict[str, SubmitMethodContract] = {}

    for name, text in sources.items():
        if Path(name).name != "argo.py":
            continue

        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("submit_"):
                continue

            required = _required_params_from_signature(node)
            optional = _optional_params_from_signature(node)
            required.extend(_self_attrs_read_in_function(node))

            required = [
                p for p in _dedupe_keep_order(_canonical_param(p) for p in required)
                if p and p not in COMMON_CONFIG_KEYS and p not in RUNTIME_NAMES
            ]
            optional = [
                p for p in _dedupe_keep_order(_canonical_param(p) for p in optional)
                if p and p not in COMMON_CONFIG_KEYS and p not in RUNTIME_NAMES and p not in required
            ]

            contracts[node.name] = SubmitMethodContract(
                submit_method=node.name,
                required_parameters=tuple(required),
                optional_parameters=tuple(optional),
                source=name,
            )

    return contracts


def _required_params_from_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    args = list(node.args.args)
    defaults = list(node.args.defaults)
    required_count = len(args) - len(defaults)
    required = []

    for index, arg in enumerate(args):
        if index >= required_count:
            continue
        if arg.arg not in RUNTIME_NAMES:
            required.append(arg.arg)

    for arg in node.args.kwonlyargs:
        default_index = node.args.kwonlyargs.index(arg)
        default = node.args.kw_defaults[default_index]
        if default is None and arg.arg not in RUNTIME_NAMES:
            required.append(arg.arg)

    return required


def _optional_params_from_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    args = list(node.args.args)
    defaults = list(node.args.defaults)
    optional_start = len(args) - len(defaults)
    optional = []

    for arg in args[optional_start:]:
        if arg.arg not in RUNTIME_NAMES:
            optional.append(arg.arg)

    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        if default is not None and arg.arg not in RUNTIME_NAMES:
            optional.append(arg.arg)

    return optional


def _self_attrs_read_in_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    attrs: list[str] = []

    for child in ast.walk(node):
        if not isinstance(child, ast.Attribute):
            continue
        if not isinstance(child.value, ast.Name):
            continue
        if child.value.id != "self":
            continue
        if not isinstance(child.ctx, ast.Load):
            continue
        if child.attr.startswith("_"):
            continue
        if child.attr in RUNTIME_SELF_ATTRS:
            continue
        if child.attr.startswith("submit_"):
            continue
        attrs.append(child.attr)

    return attrs


def _extract_creator_entry_contracts(sources: dict[str, str]) -> dict[str, SubmitMethodContract]:
    contracts: dict[str, SubmitMethodContract] = {}

    for name, text in sources.items():
        if Path(name).suffix.lower() != ".py":
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue

            literal = _dict_literal(node)
            submit_method = literal.get("submit_method")
            if not isinstance(submit_method, str) or not submit_method.startswith("submit_"):
                continue

            keys = [
                _canonical_param(key)
                for key in literal
                if isinstance(key, str)
                and key not in COMMON_CONFIG_KEYS
                and not key.startswith("_")
            ]

            existing = contracts.get(submit_method)
            provided = list(existing.provided_by_config_creator) if existing else []
            provided.extend(keys)

            contracts[submit_method] = SubmitMethodContract(
                submit_method=submit_method,
                required_parameters=existing.required_parameters if existing else (),
                optional_parameters=existing.optional_parameters if existing else (),
                provided_by_config_creator=tuple(_dedupe_keep_order(provided)),
                source=name,
            )

    return contracts


def _dict_literal(node: ast.Dict) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in zip(node.keys, node.values):
        if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
            continue
        key = key_node.value
        value = value_node.value if isinstance(value_node, ast.Constant) else None
        result[key] = value
    return result


def _read_delimited_rows(text: str) -> list[list[str]]:
    lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        return []

    sample = "\n".join(lines[:20])
    delimiter = "\t"
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="\t,;")
        delimiter = dialect.delimiter
    except csv.Error:
        if "," in sample and "\t" not in sample:
            delimiter = ","
        elif ";" in sample and "\t" not in sample:
            delimiter = ";"

    return [[cell.strip() for cell in row] for row in csv.reader(lines, delimiter=delimiter)]


def _row_looks_like_header(row: list[str]) -> bool:
    normalized = {_canonical_param(cell) for cell in row}
    return bool(normalized & {"step", "steps_order", "submit_method", "method", "stage"})


def _row_to_record(header: list[str] | None, row: list[str]) -> dict[str, str]:
    if not header:
        return {}
    return {
        _canonical_param(header[i]): row[i]
        for i in range(min(len(header), len(row)))
        if header[i].strip()
    }


def _first_present(record: dict[str, str], names: Iterable[str]) -> str:
    for name in names:
        value = record.get(name)
        if value:
            return value
    return ""


def _deduplicate_parsed_creator(parsed: _ParsedCreatorSources) -> _ParsedCreatorSources:
    parsed.method_map = {
        _canonical_step(step): method
        for step, method in parsed.method_map.items()
        if step and method
    }
    parsed.stage1_all_steps = {
        _canonical_platform(platform): _dedupe_keep_order(_canonical_step(s) for s in steps)
        for platform, steps in parsed.stage1_all_steps.items()
    }
    parsed.stage2_all_steps = {
        _canonical_platform(platform): _dedupe_keep_order(_canonical_step(s) for s in steps)
        for platform, steps in parsed.stage2_all_steps.items()
    }
    parsed.stage3_all_steps = _dedupe_keep_order(_canonical_step(s) for s in parsed.stage3_all_steps)
    parsed.stage3_no_beagle_steps = _dedupe_keep_order(
        _canonical_step(s) for s in parsed.stage3_no_beagle_steps
    )
    return parsed


def _dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _canonical_step(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _canonical_param(value: Any) -> str:
    return _canonical_step(value)


def _canonical_platform(value: Any) -> str:
    text = _canonical_step(value)
    aliases = {
        "ilumina": "illumina",
        "illumina": "illumina",
        "mgi": "mgi",
        "surf": "surf",
        "surfseq": "surf",
        "salus": "salus",
    }
    return aliases.get(text, text or "illumina")
