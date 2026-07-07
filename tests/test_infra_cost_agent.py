from pathlib import Path

import yaml

from bioops.agents.infra_cost_agent import InfraCostAgent


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "mock_compute_vms.json"
)


def write_config(
    tmp_path: Path,
    *,
    runtime_threshold_hours: float = 3,
    fixture_path: Path = FIXTURE_PATH,
) -> Path:
    config = {
        "agents": {
            "infra_cost": {
                "enabled": True,
                "description": "Test infra agent config.",
                "compute": {
                    "provider": "mock",
                    "mock_inventory_path": str(fixture_path),
                    "monthly_cost_threshold_rub": 50_000,
                    "runtime_threshold_hours": runtime_threshold_hours,
                    "fixed_now": "2026-07-07T12:00:00Z",
                },
            }
        }
    }

    path = tmp_path / "agents.yaml"
    path.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
    return path


def test_infra_cost_agent_reports_e1_alerting_vms(tmp_path: Path) -> None:
    config_path = write_config(tmp_path)

    agent = InfraCostAgent(config_path=str(config_path))
    report = agent.run("check expensive VMs")

    assert "Infra & Cost Report" in report
    assert "- Checked: 6" in report
    assert "- Alerts: 2" in report
    assert "WARNING: expensive-cpu-long" in report
    assert "WARNING: gpu-long" in report
    assert "70,000 RUB" in report
    assert "Action: confirm that the VM is still required" in report


def test_infra_cost_agent_reports_no_alerts_when_runtime_threshold_high(
    tmp_path: Path,
) -> None:
    config_path = write_config(tmp_path, runtime_threshold_hours=10)

    agent = InfraCostAgent(config_path=str(config_path))
    report = agent.run("check expensive VMs")

    assert "- Checked: 6" in report
    assert "- Alerts: 0" in report
    assert "No expensive long-running VMs detected." in report
    assert "WARNING:" not in report


def test_infra_cost_agent_reports_unavailable_when_fixture_missing(
    tmp_path: Path,
) -> None:
    missing_fixture = tmp_path / "missing_vms.json"
    config_path = write_config(tmp_path, fixture_path=missing_fixture)

    agent = InfraCostAgent(config_path=str(config_path))
    report = agent.run("check expensive VMs")

    assert "Status: unavailable" in report
    assert "failed to check Compute Cloud VMs" in report
    assert "Action: verify infra_cost.compute configuration" in report
