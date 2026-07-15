from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from bioops.agents.batch_status_agent import BatchStatusAgent
from bioops.agents.bucket_agent import BucketAgent
from bioops.agents.submit_master_agent import SubmitMasterAgent
from bioops.tools.bucket_inventory import BucketObject
from bioops.tools.llm_action_router import ActionDecision


class FakeActionRouter:
    def __init__(self, action: str, parameters=None):
        self.decision = ActionDecision(
            action=action,
            parameters=parameters or {},
            reason="test",
        )

    def route(self, _message: str) -> ActionDecision:
        return self.decision


class FailingActionRouter:
    def route(self, _message: str):
        raise RuntimeError("router unavailable")


class FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def list_rows(self, limit=20):
        return self.rows[:limit]

    def find_by_batch_id(self, batch_id):
        return [row for row in self.rows if row.get("batch_id") == batch_id]


class FakeInventoryTool:
    def __init__(self):
        self.inventory_file = "inventory_2026-07-07.csv"
        self.objects = [
            BucketObject(
                key="results/batch-1/a.imputation.vcf.gz",
                size=300,
                storage_class="COLD",
            ),
            BucketObject(
                key="results/batch-1/a.beagle.imputation.vcf.gz",
                size=400,
                storage_class="COLD",
            ),
        ]

    def filter_objects(self, prefix=None, extension=None, name_suffix=None, **_kwargs):
        rows = list(self.objects)
        if prefix:
            normalized = prefix.strip("/") + "/"
            rows = [row for row in rows if row.key.startswith(normalized)]
        if name_suffix:
            suffix = name_suffix.lstrip(".")
            rows = [
                row
                for row in rows
                if row.key.endswith("." + suffix)
                and not row.key.endswith(".beagle." + suffix)
            ]
        elif extension:
            rows = [row for row in rows if row.key.endswith("." + extension.lstrip("."))]
        return rows

    def top_prefixes(self, depth=1, limit=20):
        return [{"prefix": "results/", "objects": 2, "bytes": 700}]

    def extension_breakdown(self, limit=20):
        return [{"extension": ".vcf.gz", "objects": 2, "bytes": 700}]

    def inventory_date(self):
        return "2026-07-07"

    @staticmethod
    def format_bytes(value):
        return f"{value} B"

    @staticmethod
    def normalize_key(value):
        return (value or "").strip().strip("/")


def test_submit_master_batch_action_calls_monitor():
    agent = SubmitMasterAgent.__new__(SubmitMasterAgent)
    agent.action_router = FakeActionRouter("batch_status", {"batch_id": "B104"})
    agent.monitor = SimpleNamespace(render_batch_status=lambda value: f"batch report {value}")
    agent.launcher = None
    agent.d4_namespace = "bioops-dev"
    agent.d4_workflow_prefix = "bioops-submit-master"
    agent.d4_workflow_template = "bioops-submit-master-local"
    agent.d4_log_tail_lines = 80

    assert agent.run("flexible wording") == "batch report B104"


def test_submit_master_action_router_failure_is_fail_closed():
    agent = SubmitMasterAgent.__new__(SubmitMasterAgent)
    agent.action_router = FailingActionRouter()

    response = agent.run("retry it")

    assert "action_routing_error" in response
    assert "No specialist operation was started" in response


def test_batch_status_completed_and_stale_actions(tmp_path: Path):
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    rows = [
        {
            "batch_id": "batch-complete",
            "workflow_name": "wf-complete",
            "status": "Succeeded",
            "last_checked_at": old_time,
        },
        {
            "batch_id": "batch-stale",
            "workflow_name": "wf-stale",
            "status": "Running",
            "last_checked_at": old_time,
        },
    ]

    completed = BatchStatusAgent(
        config_path=tmp_path / "missing.yaml",
        action_router=FakeActionRouter("completed"),
        store=FakeStore(rows),
    ).run("finished batches")
    stale = BatchStatusAgent(
        config_path=tmp_path / "missing.yaml",
        action_router=FakeActionRouter("stale"),
        store=FakeStore(rows),
    ).run("old active batches")

    assert "batch-complete" in completed
    assert "batch-stale" not in completed
    assert "batch-stale" in stale
    assert "batch-complete" not in stale


def test_batch_status_specific_batch_uses_llm_parameter(tmp_path: Path):
    rows = [
        {
            "batch_id": "batch-140325",
            "workflow_name": "wf-1",
            "status": "Running",
        }
    ]
    agent = BatchStatusAgent(
        config_path=tmp_path / "missing.yaml",
        action_router=FakeActionRouter(
            "specific_batch", {"batch_id": "batch-140325"}
        ),
        store=FakeStore(rows),
    )

    response = agent.run("wording no longer needs a regex")

    assert "Batch Status: batch-140325" in response
    assert "wf-1" in response


def test_bucket_agent_uses_llm_parameters_and_preserves_suffix_semantics(tmp_path: Path):
    agent = BucketAgent(
        config_path=tmp_path / "missing.yaml",
        inventory_tool=FakeInventoryTool(),
        action_router=FakeActionRouter(
            "list_files",
            {
                "prefix": "results/batch-1/",
                "name_suffix": "imputation.vcf.gz",
                "limit": 10,
            },
        ),
    )

    response = agent.run("natural language is interpreted by the LLM")

    assert "results/batch-1/a.imputation.vcf.gz" in response
    assert "a.beagle.imputation.vcf.gz" not in response
    assert "Inventory date: 2026-07-07" in response
