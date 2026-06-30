import os
from typing import Optional

import requests


class BitrixSender:
    def __init__(self) -> None:
        self.webhook_url = (
            os.getenv("BITRIX_WEBHOOK_URL")
            or os.getenv("BIOOPS_BITRIX_WEBHOOK_URL")
            or os.getenv("BITRIX24_WEBHOOK_URL")
        )

        self.default_dialog_id = (
            os.getenv("BITRIX_DIALOG_ID")
            or os.getenv("BIOOPS_ALERT_DIALOG_ID")
        )

    def send_message(self, text: str, chat_id: Optional[str] = None) -> None:
        if not self.webhook_url:
            print("BITRIX_WEBHOOK_URL is not set")
            return

        dialog_id = chat_id or self.default_dialog_id

        if not dialog_id:
            print("BITRIX_DIALOG_ID is not set")
            return

        payload = {
            "DIALOG_ID": dialog_id,
            "MESSAGE": text,
        }

        response = requests.post(
            f"{self.webhook_url.rstrip('/')}/im.message.add.json",
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
