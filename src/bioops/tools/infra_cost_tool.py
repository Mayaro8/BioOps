import os
from dataclasses import dataclass


@dataclass
class InfraCostSummary:
    status: str
    yandex_cloud_configured: bool
    clickhouse_configured: bool
    queue_configured: bool
    cloud_functions_configured: bool
    missing_config: list[str]
    checks_available_now: list[str]
    checks_blocked_until_access: list[str]


class InfraCostTool:
    """Safe MVP tool for infrastructure and cost monitoring."""

    def __init__(
        self,
        yandex_cloud_id: str | None = None,
        yandex_folder_id: str | None = None,
        yandex_service_account_key_path: str | None = None,
        clickhouse_dsn: str | None = None,
        queue_url: str | None = None,
        cloud_functions_endpoint: str | None = None,
    ):
        self.yandex_cloud_id = yandex_cloud_id or os.getenv("YC_CLOUD_ID")
        self.yandex_folder_id = yandex_folder_id or os.getenv("YC_FOLDER_ID")
        self.yandex_service_account_key_path = (
            yandex_service_account_key_path
            or os.getenv("YC_SERVICE_ACCOUNT_KEY_PATH")
        )
        self.clickhouse_dsn = clickhouse_dsn or os.getenv("BIOOPS_CLICKHOUSE_DSN")
        self.queue_url = queue_url or os.getenv("BIOOPS_QUEUE_URL")
        self.cloud_functions_endpoint = (
            cloud_functions_endpoint
            or os.getenv("BIOOPS_CLOUD_FUNCTIONS_ENDPOINT")
        )

    def summarize(self) -> InfraCostSummary:
        yandex_configured = bool(
            self.yandex_cloud_id
            and self.yandex_folder_id
            and self.yandex_service_account_key_path
        )
        clickhouse_configured = bool(self.clickhouse_dsn)
        queue_configured = bool(self.queue_url)
        cloud_functions_configured = bool(self.cloud_functions_endpoint)

        missing_config = self._missing_config()

        return InfraCostSummary(
            status="configured" if not missing_config else "not fully configured",
            yandex_cloud_configured=yandex_configured,
            clickhouse_configured=clickhouse_configured,
            queue_configured=queue_configured,
            cloud_functions_configured=cloud_functions_configured,
            missing_config=missing_config,
            checks_available_now=[
                "report configured/missing infrastructure integrations",
                "explain which cost and health checks are blocked by missing access",
            ],
            checks_blocked_until_access=[
                "Yandex Cloud VM inventory and cost checks",
                "GPU VM runtime and expensive VM alerts",
                "ClickHouse health and mutation/backlog checks",
                "queue backlog checks",
                "Cloud Functions status/log checks",
            ],
        )

    def _missing_config(self) -> list[str]:
        missing: list[str] = []

        if not self.yandex_cloud_id:
            missing.append("YC_CLOUD_ID")
        if not self.yandex_folder_id:
            missing.append("YC_FOLDER_ID")
        if not self.yandex_service_account_key_path:
            missing.append("YC_SERVICE_ACCOUNT_KEY_PATH")
        if not self.clickhouse_dsn:
            missing.append("BIOOPS_CLICKHOUSE_DSN")
        if not self.queue_url:
            missing.append("BIOOPS_QUEUE_URL")
        if not self.cloud_functions_endpoint:
            missing.append("BIOOPS_CLOUD_FUNCTIONS_ENDPOINT")

        return missing
