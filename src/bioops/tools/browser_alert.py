from __future__ import annotations

import os

import requests


class BrowserAlertClient:
    """Send a scheduled monitor report to the BioOps alert inbox."""

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
    ) -> None:
        self.url = (
            url
            or os.getenv("BIOOPS_ALERT_URL")
            or "http://bioops-api:8000/internal/alerts"
        )
        self.token = (
            token
            if token is not None
            else os.getenv("BIOOPS_INTERNAL_ALERT_TOKEN", "")
        )

    def send(
        self,
        *,
        title: str,
        message: str,
        severity: str,
    ) -> dict:
        headers = {}

        if self.token:
            headers["X-BioOps-Alert-Token"] = self.token

        response = requests.post(
            self.url,
            json={
                "title": title,
                "message": message,
                "severity": severity,
            },
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
