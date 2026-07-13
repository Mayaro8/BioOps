from __future__ import annotations

import os

from bioops.tools.browser_alert import BrowserAlertClient
from bioops.tools.periodic_infra_health import (
    QueueHealthMonitor,
)


def main() -> None:
    monitor = QueueHealthMonitor(
        path=os.getenv(
            "BIOOPS_E3_MOCK_PATH",
            "/app/data/mock_queue_metrics.json",
        ),
        oldest_age_threshold_seconds=float(
            os.getenv(
                "BIOOPS_QUEUE_OLDEST_SECONDS",
                "900",
            )
        ),
        minimum_drain_rate_per_minute=float(
            os.getenv(
                "BIOOPS_QUEUE_MIN_DRAIN_RATE",
                "1",
            )
        ),
        maximum_drain_time_minutes=float(
            os.getenv(
                "BIOOPS_QUEUE_MAX_DRAIN_MINUTES",
                "60",
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
