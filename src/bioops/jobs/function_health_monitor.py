from __future__ import annotations

import os

from bioops.tools.browser_alert import BrowserAlertClient
from bioops.tools.periodic_infra_health import (
    FunctionHealthMonitor,
)


def main() -> None:
    monitor = FunctionHealthMonitor(
        path=os.getenv(
            "BIOOPS_E4_MOCK_PATH",
            "/app/data/mock_function_metrics.json",
        ),
        error_rate_threshold_percent=float(
            os.getenv(
                "BIOOPS_FUNCTION_ERROR_RATE",
                "5",
            )
        ),
        load_increase_multiplier=float(
            os.getenv(
                "BIOOPS_FUNCTION_LOAD_MULTIPLIER",
                "3",
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
