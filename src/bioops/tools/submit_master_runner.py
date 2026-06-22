from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class SubmitMasterLaunchRequest:
    config_text: str
    confirm: bool
    allow_launch: bool
    submit_master_entrypoint: str = ""
    generated_config_dir: str = "logs/submit_master_configs"
    contour: str = "prod"
    python_executable: str = "python"
    timeout_seconds: int = 900
    label_parts: dict[str, str] = field(default_factory=dict)


@dataclass
class SubmitMasterLaunchResult:
    launched: bool
    saved_config_path: str | None
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    message: str
    blocked_reason: str | None = None


class SubmitMasterRunner:
    """Saves generated submit-master JSON and safely launches the original submit master.

    Launch is blocked unless both:
    - confirm=True from user request
    - allow_launch=True from BioOps config
    """

    def prepare_or_launch(self, request: SubmitMasterLaunchRequest) -> SubmitMasterLaunchResult:
        saved_config_path = self._write_config(
            config_text=request.config_text,
            generated_config_dir=request.generated_config_dir,
            label_parts=request.label_parts,
        )

        command = self._build_command(
            python_executable=request.python_executable,
            submit_master_entrypoint=request.submit_master_entrypoint,
            config_path=saved_config_path,
            contour=request.contour,
        )

        if not request.confirm:
            return SubmitMasterLaunchResult(
                launched=False,
                saved_config_path=str(saved_config_path),
                command=command,
                returncode=None,
                stdout="",
                stderr="",
                message="Dry run only. Config was saved, but submit master was not launched because confirm=false.",
                blocked_reason="confirm=false",
            )

        if not request.allow_launch:
            return SubmitMasterLaunchResult(
                launched=False,
                saved_config_path=str(saved_config_path),
                command=command,
                returncode=None,
                stdout="",
                stderr="",
                message="Launch blocked. Set allow_launch=true in configs/agents.yaml to enable real submit-master launch.",
                blocked_reason="allow_launch=false",
            )

        if not request.submit_master_entrypoint:
            return SubmitMasterLaunchResult(
                launched=False,
                saved_config_path=str(saved_config_path),
                command=command,
                returncode=None,
                stdout="",
                stderr="",
                message="Launch blocked. submit_master_entrypoint is not configured.",
                blocked_reason="missing submit_master_entrypoint",
            )

        entrypoint = Path(request.submit_master_entrypoint)
        if not entrypoint.exists():
            return SubmitMasterLaunchResult(
                launched=False,
                saved_config_path=str(saved_config_path),
                command=command,
                returncode=None,
                stdout="",
                stderr="",
                message=f"Launch blocked. submit_master_entrypoint does not exist: {entrypoint}",
                blocked_reason="submit_master_entrypoint not found",
            )

        try:
            completed = subprocess.run(
                command,
                check=False,
                text=True,
                capture_output=True,
                timeout=request.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return SubmitMasterLaunchResult(
                launched=True,
                saved_config_path=str(saved_config_path),
                command=command,
                returncode=None,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                message=f"Submit master launch timed out after {request.timeout_seconds} seconds.",
                blocked_reason="timeout",
            )
        except OSError as exc:
            return SubmitMasterLaunchResult(
                launched=False,
                saved_config_path=str(saved_config_path),
                command=command,
                returncode=None,
                stdout="",
                stderr=str(exc),
                message="Submit master launch failed before process start.",
                blocked_reason="process start failed",
            )

        if completed.returncode == 0:
            message = "Submit master launched and exited successfully."
            blocked_reason = None
        else:
            message = "Submit master launched but exited with a non-zero return code."
            blocked_reason = "non-zero return code"

        return SubmitMasterLaunchResult(
            launched=True,
            saved_config_path=str(saved_config_path),
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            message=message,
            blocked_reason=blocked_reason,
        )

    def _write_config(
        self,
        config_text: str,
        generated_config_dir: str,
        label_parts: dict[str, str],
    ) -> Path:
        output_dir = Path(generated_config_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        label = self._build_label(label_parts)

        filename = f"submit_master_{timestamp}"
        if label:
            filename += f"_{label}"
        filename += ".json"

        output_path = output_dir / filename
        output_path.write_text(config_text, encoding="utf-8")
        return output_path

    def _build_label(self, label_parts: dict[str, str]) -> str:
        raw = "_".join(
            str(value)
            for value in label_parts.values()
            if value not in {None, ""}
        )
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_")

    def _build_command(
        self,
        python_executable: str,
        submit_master_entrypoint: str,
        config_path: Path,
        contour: str,
    ) -> list[str]:
        if not submit_master_entrypoint:
            return []

        return [
            python_executable,
            submit_master_entrypoint,
            "--config",
            str(config_path),
            "--contour",
            contour,
        ]
