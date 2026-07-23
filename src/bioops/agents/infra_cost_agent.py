"""Infra & Cost Monitoring Agent for BioOps Epic E.

Current implementation covers Epic E1:
- periodically check Compute Cloud VMs;
- alert when an expensive VM has been running too long;
- expensive means projected monthly cost above threshold OR GPU-equipped.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from bioops.agents.base import BaseAgent
from bioops.tools.compute_cloud_monitor import (
    ComputeCloudMonitor,
    MockComputeProvider,
    VMAlert,
)
from bioops.tools.yandex_cloud_provider import (
    BillingSummary,
    YandexBillingProvider,
    YandexCloudProvider,
    load_service_account_key,
)


class InfraCostAgent(BaseAgent):
    """Reports infrastructure cost risks for BioOps."""

    name = "infra_cost"
    description = (
        "Monitors cloud infrastructure costs, expensive VMs, GPUs, "
        "database health, queues, and cloud functions."
    )

    def __init__(
        self,
        compute_monitor: ComputeCloudMonitor | None = None,
        config_path: str = "configs/agents.yaml",
    ) -> None:
        self.config = self._load_config(config_path)
        self.infra_config = self.config.get("agents", {}).get("infra_cost", {})
        self.compute_config = self.infra_config.get("compute", {})
        self.billing_config = self.infra_config.get("billing", {})

        self.compute_monitor = compute_monitor or self._build_compute_monitor()
        self.billing_provider = self._build_billing_provider()

    def run(self, message: str) -> str:
        """Return a user-facing infrastructure report."""

        try:
            alerts = self.compute_monitor.check_vms()
            total_vms = len(self.compute_monitor.provider.list_vms())
        except Exception as error:
            return (
                "Infra & Cost Report\n\n"
                "Status: unavailable\n"
                f"Reason: failed to check Compute Cloud VMs: {error}\n\n"
                "Action: verify infra_cost.compute configuration and provider access."
            )

        billing_summary, billing_error = self._get_billing_summary()
        return self._format_compute_report(
            total_vms=total_vms,
            alerts=alerts,
            billing_summary=billing_summary,
            billing_error=billing_error,
        )

    def _build_compute_monitor(self) -> ComputeCloudMonitor:
        provider_name = os.getenv(
            "BIOOPS_INFRA_PROVIDER",
            str(self.compute_config.get("provider", "mock")),
        ).lower()

        if provider_name == "yandex":
            folder_id = os.getenv("YC_FOLDER_ID", str(self.compute_config.get("folder_id", "")))
            key = load_service_account_key(
                os.getenv("YC_SERVICE_ACCOUNT_KEY_PATH"),
                os.getenv("YC_SERVICE_ACCOUNT_KEY_JSON"),
            )
            provider = YandexCloudProvider(folder_id=folder_id, service_account_key=key)
        elif provider_name == "mock":
            mock_inventory_path = self.compute_config.get(
                "mock_inventory_path",
                "tests/fixtures/mock_compute_vms.json",
            )
            provider = MockComputeProvider(mock_inventory_path)
        else:
            raise ValueError(
                "Unsupported Compute provider. Expected 'mock' or 'yandex'; "
                f"configured: {provider_name!r}"
            )

        monthly_cost_threshold_rub = float(
            self.compute_config.get("monthly_cost_threshold_rub", 50_000)
        )
        runtime_threshold_hours = float(
            self.compute_config.get("runtime_threshold_hours", 3)
        )

        fixed_now = self.compute_config.get("fixed_now")
        now_provider = None

        if fixed_now:
            parsed_fixed_now = _parse_datetime(str(fixed_now))
            now_provider = lambda: parsed_fixed_now

        return ComputeCloudMonitor(
            provider=provider,
            monthly_cost_threshold_rub=monthly_cost_threshold_rub,
            runtime_threshold_hours=runtime_threshold_hours,
            now_provider=now_provider,
        )

    def _build_billing_provider(self) -> YandexBillingProvider | None:
        provider_name = os.getenv(
            "BIOOPS_INFRA_PROVIDER",
            str(self.compute_config.get("provider", "mock")),
        ).lower()
        if provider_name != "yandex":
            return None

        billing_account_id = os.getenv(
            "YC_BILLING_ACCOUNT_ID",
            str(self.billing_config.get("billing_account_id", "")),
        )
        if not billing_account_id:
            return None

        folder_id = os.getenv("YC_FOLDER_ID", str(self.compute_config.get("folder_id", "")))
        key = load_service_account_key(
            os.getenv("YC_SERVICE_ACCOUNT_KEY_PATH"),
            os.getenv("YC_SERVICE_ACCOUNT_KEY_JSON"),
        )
        return YandexBillingProvider(
            billing_account_id=billing_account_id,
            folder_id=folder_id,
            service_account_key=key,
        )

    def _get_billing_summary(self) -> tuple[BillingSummary | None, str | None]:
        if self.billing_provider is None:
            return None, None
        try:
            return self.billing_provider.get_month_to_date_summary(), None
        except Exception as error:
            return None, str(error)

    @staticmethod
    def _load_config(config_path: str) -> dict[str, Any]:
        path = Path(config_path)

        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def _format_compute_report(
        self,
        total_vms: int,
        alerts: list[VMAlert],
        billing_summary: BillingSummary | None,
        billing_error: str | None,
    ) -> str:
        lines = [
            "Infra & Cost Report",
            "",
            "Compute Cloud VMs:",
            f"- Checked: {total_vms}",
            f"- Alerts: {len(alerts)}",
        ]

        if billing_summary is not None:
            lines.extend(
                [
                    "",
                    "Yandex Cloud billing (month to date, configured folder):",
                    f"- Cost: {billing_summary.cost} {billing_summary.currency}",
                    f"- Credits: {billing_summary.credits} {billing_summary.currency}",
                    f"- Expense: {billing_summary.expense} {billing_summary.currency}",
                ]
            )
        elif billing_error:
            lines.extend(["", f"Billing: unavailable ({billing_error})"])
        elif os.getenv("BIOOPS_INFRA_PROVIDER", "").lower() == "yandex":
            lines.extend(["", "Billing: not configured (set YC_BILLING_ACCOUNT_ID for month-to-date totals)."])

        if not alerts:
            lines.extend(
                [
                    "",
                    "No expensive long-running VMs detected.",
                ]
            )
            return "\n".join(lines)

        lines.extend(
            [
                "",
                "Findings:",
            ]
        )

        for alert in alerts:
            lines.extend(
                [
                    "",
                    f"WARNING: {alert.vm_name}",
                    f"- VM ID: {alert.vm_id}",
                    f"- Runtime: {alert.runtime_hours:.2f} hours",
                    (
                        "- Projected monthly cost: "
                        f"{alert.projected_monthly_cost_rub:,.0f} RUB"
                    ),
                    f"- GPUs: {alert.gpu_count}",
                    "- Reason:",
                ]
            )

            for reason in alert.reasons:
                lines.append(f"  - {reason}")

            lines.extend(
                [
                    "- Action: confirm that the VM is still required; "
                    "stop it if it is idle or no longer needed.",
                ]
            )

        return "\n".join(lines)


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip()

    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    parsed = datetime.fromisoformat(normalized)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)
