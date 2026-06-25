from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
import time
from typing import Any

from bioops.tools.submit_master_contract import (
    find_missing_config_creator_params,
    normalize_params,
)


@dataclass
class SubmitMasterLaunchRequest:
    params: dict[str, Any]
    config_creator_dir: str = "submit_master_files/submit-master-config-creator"
    submit_master_dir: str = "submit_master_files/argo-submit-master"
    python_executable: str = "python3"
    contour: str = "prod"
    debug_mode: bool = False
    tolerate_config_creator_upload_failure: bool = True


@dataclass
class SubmitMasterLaunchResult:
    status: str
    missing: list[str]
    generated_config: str | None
    config_creator_returncode: int | None
    submit_master_returncode: int | None
    stdout: str
    stderr: str
    message: str


class OriginalSubmitMasterLauncher:
    """
    Runs the real Config Creator, then runs the real SubmitMaster.

    This class does not rebuild SubmitMaster JSON itself.
    It passes CLI/agent params into handler.sh as environment variables,
    lets Config Creator generate JSON, then calls:

        python main.py --config <generated-json>
    """

    def launch(self, request: SubmitMasterLaunchRequest) -> SubmitMasterLaunchResult:
        params = normalize_params(request.params)
        missing_report = find_missing_config_creator_params(params)

        if not missing_report.ready:
            return SubmitMasterLaunchResult(
                status="missing_parameters",
                missing=missing_report.missing,
                generated_config=None,
                config_creator_returncode=None,
                submit_master_returncode=None,
                stdout="",
                stderr="",
                message="SubmitMaster launch needs more parameters.",
            )

        config_creator_dir = Path(request.config_creator_dir).resolve()
        submit_master_dir = Path(request.submit_master_dir).resolve()

        if not config_creator_dir.exists():
            return self._error(f"Config Creator directory not found: {config_creator_dir}")

        if not submit_master_dir.exists():
            return self._error(f"SubmitMaster directory not found: {submit_master_dir}")

        before_jsons = self._json_files(config_creator_dir)

        env = os.environ.copy()
        env.update(params)

        config_creator_proc = subprocess.run(
            ["bash", "handler.sh"],
            cwd=config_creator_dir,
            env=env,
            text=True,
            capture_output=True,
        )

        generated_config = self._find_newest_generated_json(
            config_creator_dir=config_creator_dir,
            before_jsons=before_jsons,
        )

        if generated_config is None:
            return SubmitMasterLaunchResult(
                status="config_creator_failed",
                missing=[],
                generated_config=None,
                config_creator_returncode=config_creator_proc.returncode,
                submit_master_returncode=None,
                stdout=config_creator_proc.stdout,
                stderr=config_creator_proc.stderr,
                message="Config Creator did not produce a JSON config.",
            )

        if (
            config_creator_proc.returncode != 0
            and not request.tolerate_config_creator_upload_failure
        ):
            return SubmitMasterLaunchResult(
                status="config_creator_failed",
                missing=[],
                generated_config=str(generated_config),
                config_creator_returncode=config_creator_proc.returncode,
                submit_master_returncode=None,
                stdout=config_creator_proc.stdout,
                stderr=config_creator_proc.stderr,
                message="Config Creator failed before SubmitMaster was launched.",
            )

        submit_command = [
            request.python_executable,
            "main.py",
            "--config",
            str(generated_config),
            "--contour",
            request.contour,
        ]

        if request.debug_mode:
            submit_command.append("--debug-mode")

        submit_proc = subprocess.run(
            submit_command,
            cwd=submit_master_dir,
            text=True,
            capture_output=True,
        )

        status = "completed" if submit_proc.returncode == 0 else "submit_master_failed"

        return SubmitMasterLaunchResult(
            status=status,
            missing=[],
            generated_config=str(generated_config),
            config_creator_returncode=config_creator_proc.returncode,
            submit_master_returncode=submit_proc.returncode,
            stdout=(
                "CONFIG_CREATOR_STDOUT:\n"
                + config_creator_proc.stdout
                + "\n\nSUBMIT_MASTER_STDOUT:\n"
                + submit_proc.stdout
            ),
            stderr=(
                "CONFIG_CREATOR_STDERR:\n"
                + config_creator_proc.stderr
                + "\n\nSUBMIT_MASTER_STDERR:\n"
                + submit_proc.stderr
            ),
            message="Original Config Creator and SubmitMaster launch path finished.",
        )

    def _json_files(self, directory: Path) -> set[Path]:
        return set(directory.glob("*.json"))

    def _find_newest_generated_json(
        self,
        config_creator_dir: Path,
        before_jsons: set[Path],
    ) -> Path | None:
        after_jsons = set(config_creator_dir.glob("*.json"))
        new_jsons = list(after_jsons - before_jsons)

        if not new_jsons:
            new_jsons = list(after_jsons)

        if not new_jsons:
            return None

        return max(new_jsons, key=lambda path: path.stat().st_mtime)

    def _error(self, message: str) -> SubmitMasterLaunchResult:
        return SubmitMasterLaunchResult(
            status="error",
            missing=[],
            generated_config=None,
            config_creator_returncode=None,
            submit_master_returncode=None,
            stdout="",
            stderr=message,
            message=message,
        )
