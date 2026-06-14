import json
import os
import urllib.error
import urllib.request


class AlertTool:
    """
    Sends BioOps alerts to a configured webhook.

    If no webhook is configured, the alert is printed to stdout.
    This keeps local/dev runs safe and avoids crashing scheduled jobs.
    """

    def __init__(
        self,
        webhook_url: str | None = None,
        timeout_seconds: int = 10,
    ):
        self.webhook_url = webhook_url or os.getenv("BIOOPS_ALERT_WEBHOOK_URL")
        self.timeout_seconds = timeout_seconds

    def send(self, title: str, message: str) -> bool:
        """
        Send an alert.

        Returns:
            True if the alert was sent to a webhook.
            False if no webhook was configured or sending failed.
        """
        if not self.webhook_url:
            self._print_disabled_alert(title, message)
            return False

        payload = {
            "text": f"{title}\n\n{message}",
        }

        request = urllib.request.Request(
            self.webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                response.read()

            print(f"[BIOOPS ALERT SENT] {title}")
            return True

        except (urllib.error.URLError, TimeoutError) as error:
            self._print_failed_alert(title, message, error)
            return False

    def _print_disabled_alert(self, title: str, message: str) -> None:
        print(f"[BIOOPS ALERT DISABLED] {title}")
        print("Reason: BIOOPS_ALERT_WEBHOOK_URL is not configured.")
        print(message)

    def _print_failed_alert(
        self,
        title: str,
        message: str,
        error: Exception,
    ) -> None:
        print(f"[BIOOPS ALERT FAILED] {title}")
        print(f"Reason: {error}")
        print(message)