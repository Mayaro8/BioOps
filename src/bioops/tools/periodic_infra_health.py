from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


def load_json_records(path: str) -> list[dict]:
    data = json.loads(
        Path(path).read_text(encoding="utf-8")
    )

    if not isinstance(data, list):
        raise ValueError(
            f"{path} must contain a JSON list."
        )

    return data


@dataclass(frozen=True)
class HealthReport:
    title: str
    severity: str
    message: str
    alerts: int


class DatabaseHealthMonitor:
    """E2 MongoDB, MySQL and ClickHouse health monitor."""

    def __init__(
        self,
        path: str,
        cpu_threshold_percent: float = 85,
        memory_threshold_percent: float = 90,
        mutation_age_threshold_minutes: float = 30,
    ) -> None:
        self.path = path
        self.cpu_threshold = float(
            cpu_threshold_percent
        )
        self.memory_threshold = float(
            memory_threshold_percent
        )
        self.mutation_age_threshold = float(
            mutation_age_threshold_minutes
        )

    def check(self) -> HealthReport:
        hosts = load_json_records(self.path)
        findings: list[str] = []

        for host in hosts:
            engine = str(
                host.get("engine", "database")
            ).lower()
            name = str(
                host.get("name", "unknown")
            )
            identity = f"{engine}:{name}"

            if not host.get("reachable", False):
                findings.append(
                    f"CRITICAL {identity}: "
                    "connection unavailable"
                )

            cpu = float(
                host.get("cpu_percent", 0)
            )

            if cpu > self.cpu_threshold:
                findings.append(
                    f"WARNING {identity}: "
                    f"CPU {cpu:.1f}% exceeds "
                    f"{self.cpu_threshold:.1f}%"
                )

            memory = float(
                host.get("memory_percent", 0)
            )

            if memory > self.memory_threshold:
                findings.append(
                    f"WARNING {identity}: "
                    f"RAM {memory:.1f}% exceeds "
                    f"{self.memory_threshold:.1f}%"
                )

            if engine != "clickhouse":
                continue

            for mutation in host.get(
                "mutations",
                [],
            ):
                is_done = bool(
                    mutation.get("is_done", False)
                )
                age = float(
                    mutation.get("age_minutes", 0)
                )

                if is_done:
                    continue

                if age <= self.mutation_age_threshold:
                    continue

                mutation_id = mutation.get(
                    "id",
                    "unknown",
                )
                database = mutation.get(
                    "database",
                    "unknown",
                )
                table = mutation.get(
                    "table",
                    "unknown",
                )
                reason = (
                    mutation.get(
                        "latest_fail_reason"
                    )
                    or "still running"
                )

                findings.append(
                    f"WARNING {identity}: mutation "
                    f"{mutation_id} on "
                    f"{database}.{table} is "
                    f"{age:.1f} minutes old "
                    f"({reason})"
                )

        lines = [
            "E2 Database Health Report",
            f"- Hosts checked: {len(hosts)}",
            f"- Alerts: {len(findings)}",
        ]

        if findings:
            lines.extend(
                [
                    "",
                    "Findings:",
                    *[
                        f"- {finding}"
                        for finding in findings
                    ],
                    "",
                    (
                        "Action: inspect the affected "
                        "database host or mutation."
                    ),
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    (
                        "MongoDB, MySQL and ClickHouse "
                        "checks are healthy."
                    ),
                ]
            )

        severity = (
            "critical"
            if any(
                finding.startswith("CRITICAL")
                for finding in findings
            )
            else (
                "warning"
                if findings
                else "info"
            )
        )

        return HealthReport(
            title=(
                "Database health alert"
                if findings
                else "Database health OK"
            ),
            severity=severity,
            message="\n".join(lines),
            alerts=len(findings),
        )


class QueueHealthMonitor:
    """E3 generic queue drain-health monitor."""

    def __init__(
        self,
        path: str,
        oldest_age_threshold_seconds: float = 900,
        minimum_drain_rate_per_minute: float = 1,
        maximum_drain_time_minutes: float = 60,
    ) -> None:
        self.path = path
        self.oldest_age_threshold = float(
            oldest_age_threshold_seconds
        )
        self.minimum_drain_rate = float(
            minimum_drain_rate_per_minute
        )
        self.maximum_drain_time = float(
            maximum_drain_time_minutes
        )

    def check(self) -> HealthReport:
        queues = load_json_records(self.path)
        findings: list[str] = []

        for queue in queues:
            name = str(
                queue.get("name", "unknown")
            )
            depth = float(
                queue.get("depth", 0)
            )
            oldest_age = float(
                queue.get(
                    "oldest_message_age_seconds",
                    0,
                )
            )
            drain_rate = float(
                queue.get(
                    "messages_out_per_minute",
                    0,
                )
            )

            if depth <= 0:
                continue

            if oldest_age > self.oldest_age_threshold:
                findings.append(
                    f"WARNING {name}: oldest message "
                    f"is {oldest_age:.0f} seconds old"
                )

            if drain_rate < self.minimum_drain_rate:
                findings.append(
                    f"WARNING {name}: drain rate is "
                    f"{drain_rate:.2f} messages/minute"
                )

            if drain_rate > 0:
                estimated_minutes = (
                    depth / drain_rate
                )

                if (
                    estimated_minutes
                    > self.maximum_drain_time
                ):
                    findings.append(
                        f"WARNING {name}: estimated "
                        f"drain time is "
                        f"{estimated_minutes:.1f} minutes"
                    )

        lines = [
            "E3 Queue Health Report",
            f"- Queues checked: {len(queues)}",
            f"- Alerts: {len(findings)}",
        ]

        if findings:
            lines.extend(
                [
                    "",
                    "Findings:",
                    *[
                        f"- {finding}"
                        for finding in findings
                    ],
                    "",
                    (
                        "Action: inspect consumers and "
                        "processing throughput."
                    ),
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "Queues are draining normally.",
                ]
            )

        return HealthReport(
            title=(
                "Queue health alert"
                if findings
                else "Queue health OK"
            ),
            severity=(
                "warning"
                if findings
                else "info"
            ),
            message="\n".join(lines),
            alerts=len(findings),
        )


class FunctionHealthMonitor:
    """E4 Cloud Functions load/error monitor."""

    def __init__(
        self,
        path: str,
        error_rate_threshold_percent: float = 5,
        load_increase_multiplier: float = 3,
    ) -> None:
        self.path = path
        self.error_rate_threshold = float(
            error_rate_threshold_percent
        )
        self.load_multiplier = float(
            load_increase_multiplier
        )

    def check(self) -> HealthReport:
        functions = load_json_records(self.path)
        findings: list[str] = []

        for function in functions:
            name = str(
                function.get("name", "unknown")
            )
            invocations = float(
                function.get("invocations", 0)
            )
            baseline = float(
                function.get(
                    "baseline_invocations",
                    0,
                )
            )
            errors = float(
                function.get("errors", 0)
            )
            critical_log_errors = int(
                function.get(
                    "critical_log_errors",
                    0,
                )
            )

            error_rate = (
                errors / invocations * 100
                if invocations > 0
                else 0
            )

            if (
                error_rate
                > self.error_rate_threshold
            ):
                findings.append(
                    f"CRITICAL {name}: error rate "
                    f"{error_rate:.1f}% exceeds "
                    f"{self.error_rate_threshold:.1f}%"
                )

            if (
                baseline > 0
                and invocations
                > baseline * self.load_multiplier
            ):
                findings.append(
                    f"WARNING {name}: load "
                    f"{invocations:.0f} is more than "
                    f"{self.load_multiplier:.1f}x "
                    "the baseline"
                )

            if critical_log_errors > 0:
                findings.append(
                    f"CRITICAL {name}: "
                    f"{critical_log_errors} critical "
                    "log error(s)"
                )

        lines = [
            "E4 Cloud Functions Health Report",
            f"- Functions checked: {len(functions)}",
            f"- Alerts: {len(findings)}",
        ]

        if findings:
            lines.extend(
                [
                    "",
                    "Findings:",
                    *[
                        f"- {finding}"
                        for finding in findings
                    ],
                    "",
                    (
                        "Action: inspect function logs, "
                        "load and recent deployments."
                    ),
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    (
                        "Cloud Functions load and "
                        "errors are healthy."
                    ),
                ]
            )

        severity = (
            "critical"
            if any(
                finding.startswith("CRITICAL")
                for finding in findings
            )
            else (
                "warning"
                if findings
                else "info"
            )
        )

        return HealthReport(
            title=(
                "Cloud Functions alert"
                if findings
                else "Cloud Functions OK"
            ),
            severity=severity,
            message="\n".join(lines),
            alerts=len(findings),
        )
