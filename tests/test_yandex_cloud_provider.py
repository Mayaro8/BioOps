from datetime import datetime, timezone
from types import SimpleNamespace

from yandex.cloud.compute.v1.instance_pb2 import Instance, Resources

from bioops.tools.yandex_cloud_provider import (
    YandexBillingProvider,
    YandexCloudProvider,
    load_service_account_key,
)


class FakeComputeClient:
    def List(self, request):  # noqa: N802 - matches generated Yandex SDK method.
        assert request.folder_id == "folder-1"
        instance = Instance(
            id="vm-1",
            name="reader-vm",
            status=Instance.Status.RUNNING,
            resources=Resources(cores=4, memory=8 * 1024**3, gpus=1),
        )
        instance.created_at.FromDatetime(datetime(2026, 7, 1, tzinfo=timezone.utc))
        return SimpleNamespace(instances=[instance])


class FakeBillingClient:
    def GetBillingAccountUsageReport(self, request):  # noqa: N802
        assert request.billing_account_id == "billing-1"
        assert list(request.folder_ids) == ["folder-1"]
        return SimpleNamespace(
            currency="RUB",
            cost=SimpleNamespace(value="12.50"),
            expense=SimpleNamespace(value="10.00"),
            credit_details=SimpleNamespace(
                credit=SimpleNamespace(value="1.00"),
                monetary_grant_credit=SimpleNamespace(value="0"),
                volume_incentive_credit=SimpleNamespace(value="0"),
                cud_credit=SimpleNamespace(value="0"),
                free_credit=SimpleNamespace(value="1.50"),
            ),
        )


class FakeSdk:
    def __init__(self, service_account_key):
        assert service_account_key == {"id": "key-1"}

    def client(self, stub):
        if "Instance" in stub.__name__:
            return FakeComputeClient()
        return FakeBillingClient()


def fake_sdk_factory(**kwargs):
    return FakeSdk(**kwargs)


def test_yandex_compute_provider_normalizes_read_only_instance() -> None:
    provider = YandexCloudProvider(
        folder_id="folder-1",
        service_account_key={"id": "key-1"},
        sdk_factory=fake_sdk_factory,
    )

    vms = provider.list_vms()

    assert len(vms) == 1
    assert vms[0].status == "RUNNING"
    assert vms[0].cpu_cores == 4
    assert vms[0].memory_gb == 8
    assert vms[0].gpu_count == 1
    assert vms[0].started_at is None
    assert vms[0].created_at == datetime(2026, 7, 1, tzinfo=timezone.utc)


def test_yandex_billing_provider_returns_folder_month_to_date_total() -> None:
    provider = YandexBillingProvider(
        billing_account_id="billing-1",
        folder_id="folder-1",
        service_account_key={"id": "key-1"},
        sdk_factory=fake_sdk_factory,
        now_provider=lambda: datetime(2026, 7, 23, 12, tzinfo=timezone.utc),
    )

    summary = provider.get_month_to_date_summary()

    assert str(summary.cost) == "12.50"
    assert str(summary.credits) == "2.50"
    assert str(summary.expense) == "10.00"
    assert summary.period_start == datetime(2026, 7, 1, tzinfo=timezone.utc)


def test_load_service_account_key_from_json() -> None:
    assert load_service_account_key(None, '{"id": "key-1"}') == {"id": "key-1"}
