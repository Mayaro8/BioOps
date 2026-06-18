import os
from dataclasses import dataclass

import requests
from dotenv import load_dotenv


@dataclass
class BitrixSendResult:
    ok: bool
    message: str
    status_code: int | None = None


class BitrixTool:
    """Send BioOps notifications to Bitrix24 using an inbound webhook."""

    def __init__(
        self,
        webhook_url: str | None = None,
        dialog_id: str | None = None,
        timeout_seconds: int = 10,
    ) -> None:
        load_dotenv()

        self.webhook_url = (webhook_url or os.getenv("BITRIX_WEBHOOK_URL") or "").strip()
        self.dialog_id = (dialog_id or os.getenv("BITRIX_DIALOG_ID") or "").strip()
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.webhook_url and self.dialog_id)

    def _method_url(self, method: str) -> str:
        """Build Bitrix REST method URL.

        Bitrix inbound webhook URLs usually look like:
        https://domain.bitrix24.ru/rest/USER_ID/WEBHOOK_CODE/

        REST methods are called as:
        https://domain.bitrix24.ru/rest/USER_ID/WEBHOOK_CODE/im.message.add.json
        """
        method = method.removesuffix(".json")
        return f"{self.webhook_url.rstrip('/')}/{method}.json"

    def send_message(self, message: str, system: bool = False) -> BitrixSendResult:
        if not self.is_configured():
            return BitrixSendResult(
                ok=False,
                message="Bitrix is not configured. Set BITRIX_WEBHOOK_URL and BITRIX_DIALOG_ID.",
            )

        payload = {
            "DIALOG_ID": self.dialog_id,
            "MESSAGE": message,
            "SYSTEM": "Y" if system else "N",
            "URL_PREVIEW": "N",
        }

        try:
            response = requests.post(
                self._method_url("im.message.add"),
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as error:
            return BitrixSendResult(
                ok=False,
                message=f"Bitrix request failed: {error}",
            )

        if response.ok:
            return BitrixSendResult(
                ok=True,
                message="Bitrix message sent successfully.",
                status_code=response.status_code,
            )

        return BitrixSendResult(
            ok=False,
            message=f"Bitrix returned HTTP {response.status_code}: {response.text[:500]}",
            status_code=response.status_code,
        )
