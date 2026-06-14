from bioops.agents.cluster_health_agent import ClusterHealthAgent


ALERT_KEYWORDS = {
    "Failed",
    "Error",
    "CrashLoopBackOff",
    "ImagePullBackOff",
    "Pending",
}


def needs_alert(report: str) -> bool:
    return any(keyword in report for keyword in ALERT_KEYWORDS)


def main() -> None:
    try:
        agent = ClusterHealthAgent()
        report = agent.run("Scheduled cluster health check")
    except Exception as error:
        print("[BIOOPS ALERT] Cluster health monitor failed")
        print(f"Error: {error}")
        return

    if needs_alert(report):
        print("[BIOOPS ALERT] Cluster health problem detected")
        print(report)
    else:
        print("[BIOOPS OK] Cluster health check passed")
        print(report)


if __name__ == "__main__":
    main()
