from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_ROOT = ROOT / "deploy" / "k8s" / "cluster-health"


def test_hourly_health_cronjob_is_suspended() -> None:
    cronjob = yaml.safe_load(
        (MANIFEST_ROOT / "cronjob.yaml").read_text(encoding="utf-8")
    )
    assert cronjob["spec"]["schedule"] == "0 * * * *"
    assert cronjob["spec"]["suspend"] is True
    command = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"][
        "containers"
    ][0]["command"]
    assert command[-2:] == ["--mode", "status"]


def test_error_cronjob_is_suspended_and_runs_every_thirty_minutes() -> None:
    cronjob = yaml.safe_load(
        (MANIFEST_ROOT / "error-cronjob.yaml").read_text(encoding="utf-8")
    )
    assert cronjob["spec"]["schedule"] == "*/30 * * * *"
    assert cronjob["spec"]["suspend"] is True
    command = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"][
        "containers"
    ][0]["command"]
    assert command[-2:] == ["--mode", "errors"]


def test_kustomization_includes_both_monitors() -> None:
    kustomization = yaml.safe_load(
        (MANIFEST_ROOT / "kustomization.yaml").read_text(encoding="utf-8")
    )
    assert "cronjob.yaml" in kustomization["resources"]
    assert "error-cronjob.yaml" in kustomization["resources"]
