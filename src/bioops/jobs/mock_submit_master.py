from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from kubernetes import client, config


def build_workflow(plan: dict, *, namespace: str, image: str) -> dict:
    tasks = []
    templates = []
    for sample in plan["samples"]:
        sample_id = sample["sample_id"]
        safe_sample = re.sub(r"[^a-z0-9-]+", "-", sample_id.lower()).strip("-")
        previous = None
        for step in plan["steps"]:
            step_name = step["name"]
            task_name = f"{safe_sample}-{step_name}"
            task = {"name": task_name, "template": task_name}
            if previous:
                task["dependencies"] = [previous]
            tasks.append(task)
            templates.append({
                "name": task_name,
                "metadata": {"labels": {
                    "pipeline_step": step_name,
                    "bioops.dev/stage": str(step["stage"]),
                    "bioops.dev/sample-id": sample_id,
                }},
                "container": {
                    "image": image,
                    "command": ["python", "-c"],
                    "args": [
                        "import time; "
                        f"print('START {step_name}: {step['description']}'); "
                        f"print('sample={sample_id}'); "
                        f"print('inputs={json.dumps(sample['inputs'], sort_keys=True)}'); "
                        "time.sleep(2); "
                        f"print('DONE {step_name}')"
                    ],
                },
            })
            previous = task_name

    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Workflow",
        "metadata": {
            "generateName": "mock-fastq-pipeline-",
            "namespace": namespace,
            "labels": {
                "bioops.dev/workload": "submit-master",
                "bioops.dev/batch-id": plan["batch_id"],
                "bioops.dev/pipeline": "mock-fastq",
            },
        },
        "spec": {
            "serviceAccountName": "bioops-executor",
            "entrypoint": "pipeline",
            "templates": [{"name": "pipeline", "dag": {"tasks": tasks}}, *templates],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--namespace", default="bioops-dev")
    args = parser.parse_args()
    plan = json.loads(Path(args.config).read_text(encoding="utf-8"))
    image = os.environ["MOCK_PIPELINE_IMAGE"]

    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    created = client.CustomObjectsApi().create_namespaced_custom_object(
        group="argoproj.io",
        version="v1alpha1",
        namespace=args.namespace,
        plural="workflows",
        body=build_workflow(plan, namespace=args.namespace, image=image),
    )
    print(json.dumps({
        "status": "submitted",
        "workflow": created.get("metadata", {}).get("name", "unknown"),
        "steps": len(plan["steps"]),
    }))


if __name__ == "__main__":
    main()
