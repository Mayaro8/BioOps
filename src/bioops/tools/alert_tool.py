import os
from dataclasses import dataclass
from datetime import datetime, timezone

from dotenv import load_dotenv

from bioops.tools.bitrix_tool import BitrixTool


@dataclass
class AlertResult:
    ok: bool
    channel: str
    message: str


class AlertTool:
    """Deliver BioOps alerts/status reports to console or external channels."""

    def __init__(self, channel: str | None = None) -> None:
        load_dotenv()
        self.channel = (channel or os.getenv("ALERT_CHANNEL") or "console").strip().lower()

    def send_alert(self, title: str, message: str, severity: str = "warning") -> AlertResult:
        formatted = self._format_message(
            prefix="[BIOOPS ALERT]",
            title=title,
            message=message,
            severity=severity,
        )
        return self._send(formatted)

    def send_status(self, title: str, message: str) -> AlertResult:
        formatted = self._format_message(
            prefix="[BIOOPS STATUS]",
            title=title,
            message=message,
            severity="info",
        )
        return self._send(formatted)

    def _format_message(
        self,
        prefix: str,
        title: str,
        message: str,
        severity: str,
    ) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        return (
            f"{prefix} {title}\n"
            f"Severity: {severity}\n"
            f"Time: {timestamp}\n\n"
            f"{message}"
        )

    def _send(self, formatted_message: str) -> AlertResult:
        if self.channel == "bitrix":
            bitrix = BitrixTool()
            result = bitrix.send_message(formatted_message)

            if result.ok:
                return AlertResult(
                    ok=True,
                    channel="bitrix",
                    message=result.message,
                )

            print(formatted_message)
            print(f"[BIOOPS ALERT DELIVERY FAILED] {result.message}")

            return AlertResult(
                ok=False,
                channel="bitrix",
                message=result.message,
            )

        print(formatted_message)

        return AlertResult(
            ok=True,
            channel="console",
            message="Alert printed to console.",
        )
