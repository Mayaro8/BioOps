from bioops.tools.periodic_infra_health import (
    DatabaseHealthMonitor,
    FunctionHealthMonitor,
    QueueHealthMonitor,
)


def test_database_mock_reports_expected_alerts():
    report = DatabaseHealthMonitor(
        "deploy/k8s/config/mock_database_health.json"
    ).check()

    assert report.alerts == 3
    assert report.severity == "warning"
    assert "pipeline-mysql" in report.message
    assert "pipeline-clickhouse" in report.message
    assert "mutation_42" in report.message


def test_queue_mock_reports_drain_problems():
    report = QueueHealthMonitor(
        "deploy/k8s/config/mock_queue_metrics.json"
    ).check()

    assert report.alerts == 3
    assert report.severity == "warning"
    assert "pipeline-submit" in report.message
    assert "oldest message" in report.message
    assert "drain rate" in report.message


def test_function_mock_reports_load_and_errors():
    report = FunctionHealthMonitor(
        "deploy/k8s/config/mock_function_metrics.json"
    ).check()

    assert report.alerts == 3
    assert report.severity == "critical"
    assert "batch-dispatch" in report.message
    assert "error rate" in report.message
    assert "critical log error" in report.message
