"""Read-only Yandex Cloud providers used by the Infra & Cost agent.

The service-account key is supplied at runtime through the environment.  This
module never writes to Yandex Cloud and deliberately does not log credentials.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from bioops.tools.compute_cloud_monitor import VMInstance


@dataclass(frozen=True)
class BillingSummary:
    """Month-to-date billing totals for the configured folder."""

    currency: str
    cost: Decimal
    credits: Decimal
    expense: Decimal
    period_start: datetime
    period_end: datetime


class YandexCloudProvider:
    """Load Compute instances from one Yandex Cloud folder, read-only."""

    def __init__(
        self,
        folder_id: str,
        service_account_key: dict[str, str],
        sdk_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not folder_id:
            raise ValueError("YC_FOLDER_ID must be configured for Yandex Compute.")

        self.folder_id = folder_id
        self._service_account_key = service_account_key
        self._sdk_factory = sdk_factory

    @classmethod
    def from_key_path(cls, folder_id: str, key_path: str | Path) -> "YandexCloudProvider":
        path = Path(key_path)
        if not path.is_file():
            raise FileNotFoundError(f"Yandex service-account key file does not exist: {path}")

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Yandex service-account key file is not valid JSON.") from exc

        if not isinstance(payload, dict):
            raise ValueError("Yandex service-account key must be a JSON object.")

        return cls(folder_id=folder_id, service_account_key=payload)

    @classmethod
    def from_key_json(cls, folder_id: str, key_json: str) -> "YandexCloudProvider":
        try:
            payload = json.loads(key_json)
        except json.JSONDecodeError as exc:
            raise ValueError("YC_SERVICE_ACCOUNT_KEY_JSON is not valid JSON.") from exc

        if not isinstance(payload, dict):
            raise ValueError("YC_SERVICE_ACCOUNT_KEY_JSON must contain a JSON object.")

        return cls(folder_id=folder_id, service_account_key=payload)

    def list_vms(self) -> list[VMInstance]:
        """Return current instances. Compute has no last-start timestamp."""

        from yandex.cloud.compute.v1.instance_service_pb2 import ListInstancesRequest
        from yandex.cloud.compute.v1.instance_service_pb2_grpc import InstanceServiceStub

        response = self._sdk().client(InstanceServiceStub).List(
            ListInstancesRequest(folder_id=self.folder_id)
        )
        return [self._to_vm(instance) for instance in response.instances]

    def _sdk(self) -> Any:
        if self._sdk_factory is not None:
            return self._sdk_factory(service_account_key=self._service_account_key)

        import yandexcloud

        return yandexcloud.SDK(service_account_key=self._service_account_key)

    @staticmethod
    def _to_vm(instance: Any) -> VMInstance:
        resources = instance.resources
        created_at = _protobuf_timestamp_to_datetime(getattr(instance, "created_at", None))
        status = _enum_name(instance, "status")

        return VMInstance(
            id=str(instance.id),
            name=str(instance.name),
            status=status,
            # The Compute API has a creation timestamp, not a reliable last-start time.
            # Keeping this unset prevents false long-running alerts after a restart.
            started_at=None,
            cpu_cores=int(resources.cores),
            memory_gb=float(resources.memory) / (1024**3),
            gpu_count=int(resources.gpus),
            projected_monthly_cost_rub=0.0,
            created_at=created_at,
        )


class YandexBillingProvider:
    """Fetch folder-scoped month-to-date billing totals, read-only."""

    def __init__(
        self,
        billing_account_id: str,
        folder_id: str,
        service_account_key: dict[str, str],
        sdk_factory: Callable[..., Any] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        if not billing_account_id:
            raise ValueError("YC_BILLING_ACCOUNT_ID must be configured for billing.")
        if not folder_id:
            raise ValueError("YC_FOLDER_ID must be configured for billing.")

        self.billing_account_id = billing_account_id
        self.folder_id = folder_id
        self._service_account_key = service_account_key
        self._sdk_factory = sdk_factory
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def get_month_to_date_summary(self) -> BillingSummary:
        from google.protobuf.timestamp_pb2 import Timestamp
        from yandex.cloud.billing.usage_records.v1.consumption_core_service_pb2 import (
            UsageReportRequest,
        )
        from yandex.cloud.billing.usage_records.v1.consumption_core_service_pb2_grpc import (
            ConsumptionCoreServiceStub,
        )

        period_end = _as_utc(self._now_provider())
        period_start = period_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_timestamp = Timestamp()
        start_timestamp.FromDatetime(period_start)
        end_timestamp = Timestamp()
        end_timestamp.FromDatetime(period_end)

        request = UsageReportRequest(
            billing_account_id=self.billing_account_id,
            folder_ids=[self.folder_id],
            start_date=start_timestamp,
            end_date=end_timestamp,
            aggregation_period=(
                UsageReportRequest.DESCRIPTOR.fields_by_name[
                    "aggregation_period"
                ].enum_type.values_by_name["DAY"].number
            ),
        )
        response = self._sdk().client(ConsumptionCoreServiceStub).GetBillingAccountUsageReport(
            request
        )

        credits = getattr(response, "credit_details", None)
        return BillingSummary(
            currency=str(response.currency),
            cost=_decimal_value(response.cost),
            credits=sum(
                (
                    _decimal_value(getattr(credits, field, None))
                    for field in (
                        "credit",
                        "monetary_grant_credit",
                        "volume_incentive_credit",
                        "cud_credit",
                        "free_credit",
                    )
                ),
                Decimal("0"),
            ),
            expense=_decimal_value(response.expense),
            period_start=period_start,
            period_end=period_end,
        )

    def _sdk(self) -> Any:
        if self._sdk_factory is not None:
            return self._sdk_factory(service_account_key=self._service_account_key)

        import yandexcloud

        return yandexcloud.SDK(service_account_key=self._service_account_key)


def load_service_account_key(key_path: str | None, key_json: str | None) -> dict[str, str]:
    """Load a service-account key from a mounted file or a secret environment value."""

    if key_path:
        return YandexCloudProvider.from_key_path("unused", key_path)._service_account_key
    if key_json:
        return YandexCloudProvider.from_key_json("unused", key_json)._service_account_key
    raise ValueError(
        "Configure YC_SERVICE_ACCOUNT_KEY_PATH or YC_SERVICE_ACCOUNT_KEY_JSON."
    )


def _decimal_value(value: Any) -> Decimal:
    raw_value = getattr(value, "value", "0") if value is not None else "0"
    try:
        return Decimal(str(raw_value or "0"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Yandex billing returned an invalid decimal: {raw_value!r}") from exc


def _protobuf_timestamp_to_datetime(value: Any) -> datetime | None:
    if value is None or not getattr(value, "seconds", 0):
        return None
    return value.ToDatetime(tzinfo=timezone.utc)


def _enum_name(message: Any, field_name: str) -> str:
    field = message.DESCRIPTOR.fields_by_name[field_name]
    return field.enum_type.values_by_number[int(getattr(message, field_name))].name


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
