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


def test_init_retry_watchdog_runs_each_minute_without_confirmation() -> None:
    cronjob = yaml.safe_load(
        (MANIFEST_ROOT / "init-retry-cronjob.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert cronjob["spec"]["schedule"] == "* * * * *"
    assert cronjob["spec"]["suspend"] is False
    assert cronjob["spec"]["concurrencyPolicy"] == "Forbid"
    command = cronjob["spec"]["jobTemplate"]["spec"]["template"][
        "spec"
    ]["containers"][0]["command"]
    assert "bioops.jobs.init_retry_watchdog" in command
    assert "30" in command


def test_kustomization_includes_all_monitors() -> None:
    kustomization = yaml.safe_load(
        (MANIFEST_ROOT / "kustomization.yaml").read_text(encoding="utf-8")
    )
    assert "cronjob.yaml" in kustomization["resources"]
    assert "error-cronjob.yaml" in kustomization["resources"]
    assert "init-retry-cronjob.yaml" in kustomization["resources"]


def test_cluster_health_rbac_can_delete_stuck_pods() -> None:
    documents = list(
        yaml.safe_load_all(
            (MANIFEST_ROOT / "rbac.yaml").read_text(encoding="utf-8")
        )
    )
    role = next(item for item in documents if item["kind"] == "Role")
    pod_rule = next(
        rule for rule in role["rules"] if "pods" in rule["resources"]
    )
    assert "delete" in pod_rule["verbs"]


def test_parent_workflow_steps_have_five_on_error_retries() -> None:
    workflow = yaml.safe_load(
        (ROOT / "deploy" / "argo" / "mock-fastq-pipeline-template.yaml")
        .read_text(encoding="utf-8")
    )
    container_templates = [
        template
        for template in workflow["spec"]["templates"]
        if "container" in template
    ]
    for template in container_templates:
        assert template["retryStrategy"] == {
            "limit": "5",
            "retryPolicy": "OnError",
        }


def test_node_health_cluster_role_is_read_only() -> None:
    documents = list(
        yaml.safe_load_all(
            (MANIFEST_ROOT / "rbac.yaml").read_text(encoding="utf-8")
        )
    )
    role = next(item for item in documents if item["kind"] == "ClusterRole")
    assert {verb for rule in role["rules"] for verb in rule["verbs"]} == {
        "get",
        "list",
    }
    resources = {
        resource
        for rule in role["rules"]
        for resource in rule["resources"]
    }
    assert resources == {"nodes", "pods"}
