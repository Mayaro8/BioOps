import subprocess
from pathlib import Path

from bioops.tools.submit_master_runner import (
    SubmitMasterLaunchRequest,
    SubmitMasterRunner,
)


def test_runner_dry_run_saves_config_without_launch(tmp_path):
    runner = SubmitMasterRunner()

    result = runner.prepare_or_launch(
        SubmitMasterLaunchRequest(
            config_text='[{"submit_method": "submit_hla"}]',
            confirm=False,
            allow_launch=False,
            submit_master_entrypoint="/tmp/fake_main.py",
            generated_config_dir=str(tmp_path),
            contour="prod",
        )
    )

    assert result.launched is False
    assert result.saved_config_path is not None
    assert Path(result.saved_config_path).exists()
    assert result.blocked_reason == "confirm=false"
    assert "submit_master" in Path(result.saved_config_path).name


def test_runner_blocks_when_allow_launch_false(tmp_path):
    entrypoint = tmp_path / "main.py"
    entrypoint.write_text("print('hello')", encoding="utf-8")

    runner = SubmitMasterRunner()

    result = runner.prepare_or_launch(
        SubmitMasterLaunchRequest(
            config_text='[{"submit_method": "submit_hla"}]',
            confirm=True,
            allow_launch=False,
            submit_master_entrypoint=str(entrypoint),
            generated_config_dir=str(tmp_path),
            contour="prod",
        )
    )

    assert result.launched is False
    assert result.blocked_reason == "allow_launch=false"
    assert result.command[0] == "python"


def test_runner_blocks_missing_entrypoint(tmp_path):
    runner = SubmitMasterRunner()

    result = runner.prepare_or_launch(
        SubmitMasterLaunchRequest(
            config_text='[{"submit_method": "submit_hla"}]',
            confirm=True,
            allow_launch=True,
            submit_master_entrypoint="",
            generated_config_dir=str(tmp_path),
            contour="prod",
        )
    )

    assert result.launched is False
    assert result.blocked_reason == "missing submit_master_entrypoint"


def test_runner_launches_when_confirm_and_allow_launch_true(monkeypatch, tmp_path):
    entrypoint = tmp_path / "main.py"
    entrypoint.write_text("print('submit master')", encoding="utf-8")

    calls = {}

    def fake_run(command, check, text, capture_output, timeout):
        calls["command"] = command
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="ok",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = SubmitMasterRunner()

    result = runner.prepare_or_launch(
        SubmitMasterLaunchRequest(
            config_text='[{"submit_method": "submit_hla"}]',
            confirm=True,
            allow_launch=True,
            submit_master_entrypoint=str(entrypoint),
            generated_config_dir=str(tmp_path),
            contour="dev",
        )
    )

    assert result.launched is True
    assert result.returncode == 0
    assert result.stdout == "ok"
    assert calls["command"][0] == "python"
    assert calls["command"][1] == str(entrypoint)
    assert "--config" in calls["command"]
    assert "--contour" in calls["command"]
    assert "dev" in calls["command"]
