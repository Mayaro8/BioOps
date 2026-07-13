from __future__ import annotations

import os

from bioops.tools.browser_alert import BrowserAlertClient
from bioops.tools.periodic_infra_health import (
    DatabaseHealthMonitor,
)


def main() -> None:
    monitor = DatabaseHealthMonitor(
        path=os.getenv(
            "BIOOPS_E2_MOCK_PATH",
            "/app/data/mock_database_health.json",
        ),
        cpu_threshold_percent=float(
            os.getenv(
                "BIOOPS_DB_CPU_THRESHOLD",
                "85",
            )
        ),
        memory_threshold_percent=float(
            os.getenv(
                "BIOOPS_DB_MEMORY_THRESHOLD",
                "90",
            )
        ),
        mutation_age_threshold_minutes=float(
            os.getenv(
                "BIOOPS_MUTATION_AGE_MINUTES",
                "30",
            )
        ),
    )

    report = monitor.check()

    BrowserAlertClient().send(
        title=report.title,
        message=report.message,
        severity=report.severity,
    )


if __name__ == "__main__":
    main()
