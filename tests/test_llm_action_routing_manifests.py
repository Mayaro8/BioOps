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


def test_api_mounts_bucket_inventory_and_registry_image():
    deployment = yaml.safe_load(
        (ROOT / "deploy/k8s/bioops-api/deployment.yaml").read_text(encoding="utf-8")
    )
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    image_name, separator, image_tag = container["image"].rpartition(":")
    assert image_name == (
        "cr.yandex/crp5l1da4kinv8ofomr5/fastmri-students/bioops"
    )
    assert separator == ":"
    assert image_tag

    mounts = {row["name"]: row for row in container["volumeMounts"]}
    assert mounts["bucket-inventory"]["mountPath"] == "/app/data/bucket_inventory.csv"
    assert mounts["bucket-inventory"]["subPath"] == "bucket_inventory.csv"

    volumes = {row["name"]: row for row in pod_spec["volumes"]}
    assert volumes["bucket-inventory"]["configMap"]["name"] == "bioops-bucket-inventory"


def test_api_optionally_mounts_multi_cluster_kubeconfig():
    deployment = yaml.safe_load(
        (ROOT / "deploy/k8s/bioops-api/deployment.yaml").read_text(
            encoding="utf-8"
        )
    )
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    environment = {row["name"]: row for row in container["env"]}
    assert environment["KUBECONFIG"]["value"] == (
        "/etc/bioops/kubeconfig/config"
    )

    mounts = {row["name"]: row for row in container["volumeMounts"]}
    assert mounts["cluster-kubeconfig"]["readOnly"] is True

    volumes = {row["name"]: row for row in pod_spec["volumes"]}
    secret = volumes["cluster-kubeconfig"]["secret"]
    assert secret == {
        "secretName": "bioops-cluster-kubeconfig",
        "optional": True,
    }
