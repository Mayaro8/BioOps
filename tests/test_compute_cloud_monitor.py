from datetime import datetime, timezone
from pathlib import Path

import pytest

from bioops.tools.compute_cloud_monitor import (
    ComputeCloudMonitor,
    MockComputeProvider,
)


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "mock_compute_vms.json"
)

FIXED_NOW = datetime(
    2026,
    7,
    7,
    12,
    0,
    tzinfo=timezone.utc,
)


def build_monitor() -> ComputeCloudMonitor:
    provider = MockComputeProvider(FIXTURE_PATH)

    return ComputeCloudMonitor(
        provider=provider,
        monthly_cost_threshold_rub=50_000,
        runtime_threshold_hours=3,
        now_provider=lambda: FIXED_NOW,
    )


def test_mock_provider_loads_all_vms() -> None:
    provider = MockComputeProvider(FIXTURE_PATH)

    vms = provider.list_vms()

    assert len(vms) == 6
    assert vms[0].name == "cheap-cpu-long"
    assert vms[0].started_at is not None
    assert vms[4].gpu_count == 1


def test_e1_alerts_only_for_expensive_long_running_vms() -> None:
    monitor = build_monitor()

    alerts = monitor.check_vms()

    assert {alert.vm_name for alert in alerts} == {
        "expensive-cpu-long",
        "gpu-long",
    }


def test_expensive_cpu_vm_over_three_hours_alerts() -> None:
    monitor = build_monitor()

    alerts = monitor.check_vms()
    alert = next(
        item
        for item in alerts
        if item.vm_name == "expensive-cpu-long"
    )

    assert alert.runtime_hours == pytest.approx(5.0)
    assert alert.projected_monthly_cost_rub == 70_000
    assert alert.gpu_count == 0
    assert any(
        "monthly cost" in reason.lower()
        for reason in alert.reasons
    )


def test_gpu_vm_over_three_hours_alerts_even_below_cost_threshold() -> None:
    monitor = build_monitor()

    alerts = monitor.check_vms()
    alert = next(
        item
        for item in alerts
        if item.vm_name == "gpu-long"
    )

    assert alert.runtime_hours == pytest.approx(5.0)
    assert alert.projected_monthly_cost_rub == 40_000
    assert alert.gpu_count == 1
    assert any(
        "GPU" in reason
        for reason in alert.reasons
    )


def test_cheap_cpu_vm_does_not_alert() -> None:
    monitor = build_monitor()

    alert_names = {
        alert.vm_name
        for alert in monitor.check_vms()
    }

    assert "cheap-cpu-long" not in alert_names


def test_expensive_vm_under_three_hours_does_not_alert() -> None:
    monitor = build_monitor()

    alert_names = {
        alert.vm_name
        for alert in monitor.check_vms()
    }

    assert "expensive-cpu-short" not in alert_names


def test_gpu_vm_under_three_hours_does_not_alert() -> None:
    monitor = build_monitor()

    alert_names = {
        alert.vm_name
        for alert in monitor.check_vms()
    }

    assert "gpu-short" not in alert_names


def test_stopped_expensive_vm_does_not_alert() -> None:
    monitor = build_monitor()

    alert_names = {
        alert.vm_name
        for alert in monitor.check_vms()
    }

    assert "stopped-expensive" not in alert_names


def test_threshold_values_are_configurable() -> None:
    provider = MockComputeProvider(FIXTURE_PATH)

    monitor = ComputeCloudMonitor(
        provider=provider,
        monthly_cost_threshold_rub=15_000,
        runtime_threshold_hours=5,
        now_provider=lambda: FIXED_NOW,
    )

    alert_names = {
        alert.vm_name
        for alert in monitor.check_vms()
    }

    # Runtime must be greater than the threshold, not equal to it.
    assert "expensive-cpu-long" not in alert_names
    assert "gpu-long" not in alert_names
    assert "cheap-cpu-long" in alert_names
