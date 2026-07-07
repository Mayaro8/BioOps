"""Compute Cloud VM monitoring for BioOps Epic E1.

The monitoring logic is provider-independent. During development and testing,
VM data can be loaded from JSON using MockComputeProvider. A real Yandex Cloud
provider can later implement the same list_vms() interface.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class VMInstance:
    """Normalized information about one Compute Cloud VM."""

    id: str
    name: str
    status: str
    started_at: datetime | None
    cpu_cores: int
    memory_gb: float
    gpu_count: int
    projected_monthly_cost_rub: float


@dataclass(frozen=True)
class VMAlert:
    """E1 alert generated for an expensive, long-running VM."""

    vm_id: str
    vm_name: str
    runtime_hours: float
    projected_monthly_cost_rub: float
    gpu_count: int
    reasons: tuple[str, ...]


class ComputeProvider(Protocol):
    """Interface implemented by mock and real cloud providers."""

    def list_vms(self) -> list[VMInstance]:
        """Return normalized VM information."""


class MockComputeProvider:
    """Load mock Compute Cloud VM records from a JSON file."""

    def __init__(self, fixture_path: str | Path) -> None:
        self.fixture_path = Path(fixture_path)

    def list_vms(self) -> list[VMInstance]:
        if not self.fixture_path.exists():
            raise FileNotFoundError(
                f"Mock VM fixture does not exist: {self.fixture_path}"
            )

        with self.fixture_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if not isinstance(payload, list):
            raise ValueError("Mock VM fixture must contain a JSON list.")

        return [self._parse_vm(record) for record in payload]

    @staticmethod
    def _parse_vm(record: object) -> VMInstance:
        if not isinstance(record, dict):
            raise ValueError("Every mock VM record must be a JSON object.")

        return VMInstance(
            id=str(record["id"]),
            name=str(record["name"]),
            status=str(record["status"]).upper(),
            started_at=_parse_datetime(record.get("started_at")),
            cpu_cores=int(record.get("cpu_cores", 0)),
            memory_gb=float(record.get("memory_gb", 0)),
            gpu_count=int(record.get("gpu_count", 0)),
            projected_monthly_cost_rub=float(
                record.get("projected_monthly_cost_rub", 0)
            ),
        )


class ComputeCloudMonitor:
    """Evaluate Compute Cloud VMs according to Epic E1."""

    def __init__(
        self,
        provider: ComputeProvider,
        monthly_cost_threshold_rub: float = 50_000,
        runtime_threshold_hours: float = 3,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        if monthly_cost_threshold_rub < 0:
            raise ValueError("monthly_cost_threshold_rub cannot be negative.")

        if runtime_threshold_hours < 0:
            raise ValueError("runtime_threshold_hours cannot be negative.")

        self.provider = provider
        self.monthly_cost_threshold_rub = monthly_cost_threshold_rub
        self.runtime_threshold_hours = runtime_threshold_hours
        self.now_provider = now_provider or (
            lambda: datetime.now(timezone.utc)
        )

    def check_vms(self) -> list[VMAlert]:
        """Return alerts for expensive VMs running over the time threshold."""

        now = _ensure_utc(self.now_provider())
        alerts: list[VMAlert] = []

        for vm in self.provider.list_vms():
            alert = self._evaluate_vm(vm, now)
            if alert is not None:
                alerts.append(alert)

        return alerts

    def _evaluate_vm(
        self,
        vm: VMInstance,
        now: datetime,
    ) -> VMAlert | None:
        if vm.status.upper() != "RUNNING":
            return None

        if vm.started_at is None:
            return None

        started_at = _ensure_utc(vm.started_at)
        runtime_hours = (now - started_at).total_seconds() / 3600

        # E1 requires the VM to have run for more than three hours.
        if runtime_hours <= self.runtime_threshold_hours:
            return None

        over_cost_threshold = (
            vm.projected_monthly_cost_rub
            > self.monthly_cost_threshold_rub
        )
        has_gpu = vm.gpu_count > 0

        # E1 defines an expensive VM as:
        # monthly projected cost > threshold OR VM has a GPU.
        if not (over_cost_threshold or has_gpu):
            return None

        reasons: list[str] = []

        if over_cost_threshold:
            reasons.append(
                "Projected monthly cost "
                f"{vm.projected_monthly_cost_rub:,.0f} RUB exceeds "
                f"{self.monthly_cost_threshold_rub:,.0f} RUB."
            )

        if has_gpu:
            reasons.append(
                f"VM has {vm.gpu_count} GPU(s)."
            )

        reasons.append(
            f"VM has been running for {runtime_hours:.2f} hours, "
            f"exceeding {self.runtime_threshold_hours:.2f} hours."
        )

        return VMAlert(
            vm_id=vm.id,
            vm_name=vm.name,
            runtime_hours=runtime_hours,
            projected_monthly_cost_rub=vm.projected_monthly_cost_rub,
            gpu_count=vm.gpu_count,
            reasons=tuple(reasons),
        )


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError("started_at must be an ISO-8601 string or null.")

    normalized = value.strip()

    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Invalid ISO-8601 datetime: {value!r}"
        ) from exc

    return _ensure_utc(parsed)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)
