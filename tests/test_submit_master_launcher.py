from pathlib import Path
from types import SimpleNamespace

import pytest

from bioops.agents.submit_master_agent import SubmitMasterAgent
from bioops.jobs.mock_fastq_config_creator import create_config
from bioops.jobs.mock_submit_master import build_workflow
from bioops.tools.llm_action_router import ActionDecision
from bioops.tools.submit_master_launcher import SubmitMasterWorkflowLauncher


def seed(directory: Path, samples=("sample1", "sample2")):
    directory.mkdir()
    for sample in samples:
        for name in (
            f"{sample}_R1.fastq.gz",
            f"{sample}_R2.fastq.gz",
            f"{sample}_R1.trimmed.fastq.gz",
            f"{sample}_R2.trimmed.fastq.gz",
            f"{sample}.recalibrated.bam",
            f"{sample}.unrelated.txt",
        ):
            (directory / name).write_text("mock", encoding="utf-8")


class FakeRouter:
    def route(self, _message):
        return ActionDecision(
            "launch_submit_master",
            {"batch_id": "batch140325", "input_prefix": "/mock-data/batch140325", "stage": "all"},
            "test",
        )


def make_agent():
    agent = SubmitMasterAgent.__new__(SubmitMasterAgent)
    agent.action_router = FakeRouter()
    agent.launcher = SimpleNamespace(
        launch_mock=lambda **values: f"launched {values['batch_id']}"
    )
    return agent


def test_launch_assessment_does_not_mutate():
    agent = make_agent()
    agent.launcher = SimpleNamespace(
        launch_mock=lambda **_values: pytest.fail("unconfirmed launch must not run")
    )
    response = agent.run("launch the batch")
    assert "No workflow was created" in response
    assert "CONFIRM MOCK LAUNCH batch140325 /mock-data/batch140325 all" in response


def test_exact_confirmation_launches():
    response = make_agent().run(
        "CONFIRM MOCK LAUNCH batch140325 /mock-data/batch140325 all"
    )
    assert response == "launched batch140325"


@pytest.mark.parametrize(
    ("stage", "expected_type", "expected_keys", "step_count"),
    [
        ("all", "raw_fastq_batch", {"R1", "R2"}, 10),
        ("1", "raw_fastq_batch", {"R1", "R2"}, 3),
        ("2", "trimmed_fastq_batch", {"R1", "R2"}, 4),
        ("3", "recalibrated_bam_batch", {"bam"}, 3),
    ],
)
def test_config_creator_selects_only_stage_inputs(
    tmp_path, stage, expected_type, expected_keys, step_count
):
    directory = tmp_path / "batch"
    seed(directory)
    plan = create_config(
        batch_id="batch140325", input_prefix=str(directory), stage=stage
    )
    assert plan["input"]["type"] == expected_type
    assert len(plan["samples"]) == 2
    assert len(plan["steps"]) == step_count
    for sample in plan["samples"]:
        assert set(sample["inputs"]) == expected_keys
        if stage == "2":
            assert all(".trimmed." in path for path in sample["inputs"].values())


def test_config_creator_rejects_incomplete_pair(tmp_path):
    directory = tmp_path / "batch"
    directory.mkdir()
    (directory / "sample1_R1.fastq.gz").write_text("mock", encoding="utf-8")
    with pytest.raises(ValueError, match="missing R2"):
        create_config(batch_id="batch140325", input_prefix=str(directory))


def test_submit_master_fans_out_one_chain_per_sample(tmp_path):
    directory = tmp_path / "batch"
    seed(directory)
    plan = create_config(batch_id="batch140325", input_prefix=str(directory))
    workflow = build_workflow(plan, namespace="bioops-dev", image="bioops:test")
    tasks = workflow["spec"]["templates"][0]["dag"]["tasks"]
    assert len(tasks) == 20
    assert "dependencies" not in tasks[0]
    assert "dependencies" not in tasks[10]
    assert tasks[9]["dependencies"] == ["sample1-filter-variants"]
    labels = workflow["spec"]["templates"][1]["metadata"]["labels"]
    assert labels["bioops.dev/sample-id"] == "sample1"


def test_launcher_submits_batch_prefix(monkeypatch):
    created = {}

    class FakeApi:
        def create_namespaced_custom_object(self, **kwargs):
            created.update(kwargs)
            return {"metadata": {"name": "bioops-fastq-mock-abc"}}

    monkeypatch.setattr(
        "bioops.tools.submit_master_launcher.config.load_incluster_config", lambda: None
    )
    monkeypatch.setattr(
        "bioops.tools.submit_master_launcher.client.CustomObjectsApi", FakeApi
    )
    response = SubmitMasterWorkflowLauncher(
        "bioops-dev", "bioops-fastq-mock"
    ).launch_mock(
        batch_id="batch140325", input_prefix="/mock-data/batch140325", stage="2"
    )
    values = {
        item["name"]: item["value"]
        for item in created["body"]["spec"]["arguments"]["parameters"]
    }
    assert values == {
        "batch_id": "batch140325",
        "input_prefix": "/mock-data/batch140325",
        "stage": "2",
    }
    assert "Status: submitted" in response
