from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_storage_is_enabled_in_both_agent_configs():
    for relative in ("configs/agents.yaml", "deploy/k8s/config/agents.yaml"):
        config = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
        storage = config["agents"]["storage"]
        assert storage["enabled"] is True
        assert storage["inventory_path"] == "data/bucket_inventory.csv"


def test_kustomize_generates_demo_bucket_inventory_configmap():
    config = yaml.safe_load(
        (ROOT / "deploy/k8s/config/kustomization.yaml").read_text(encoding="utf-8")
    )
    generators = {row["name"]: row for row in config["configMapGenerator"]}
    assert generators["bioops-bucket-inventory"]["files"] == [
        "bucket_inventory.csv=bucket-inventory.csv"
    ]


def test_api_mounts_bucket_inventory_and_new_image_tag():
    deployment = yaml.safe_load(
        (ROOT / "deploy/k8s/bioops-api/deployment.yaml").read_text(encoding="utf-8")
    )
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    assert container["image"].endswith(":k8s-demo-llm-routing-20260710")

    mounts = {row["name"]: row for row in container["volumeMounts"]}
    assert mounts["bucket-inventory"]["mountPath"] == "/app/data/bucket_inventory.csv"
    assert mounts["bucket-inventory"]["subPath"] == "bucket_inventory.csv"

    volumes = {row["name"]: row for row in pod_spec["volumes"]}
    assert volumes["bucket-inventory"]["configMap"]["name"] == "bioops-bucket-inventory"
