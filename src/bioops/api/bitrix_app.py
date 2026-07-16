from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from bioops.graph_orchestrator import run_graph
from bioops.tools.notification_store import NotificationStore
from bioops.tools.bitrix_sender import BitrixSender


logger = logging.getLogger(__name__)

app = FastAPI(
    title="BioOps API",
    description="Web chat and optional Bitrix adapter for BioOps agents.",
)

bitrix_sender = BitrixSender()

_notification_store: NotificationStore | None = None


def get_notification_store() -> NotificationStore:
    global _notification_store

    if _notification_store is None:
        db_path = os.getenv(
            "BIOOPS_ALERT_DB_PATH",
            "/data/bioops_notifications.sqlite3",
        )
        _notification_store = NotificationStore(
            db_path
        )

    return _notification_store


class ChatRequest(BaseModel):
    message: str


class AlertRequest(BaseModel):
    title: str
    message: str
    severity: str = "warning"


class ChatResponse(BaseModel):
    ok: bool
    message: str
    answer: str


CHAT_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BioOps Chat</title>

  <style>
    :root {
      color-scheme: light dark;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    body {
      margin: 0;
      background: #111827;
      color: #f9fafb;
    }

    main {
      width: min(900px, calc(100% - 32px));
      margin: 32px auto;
    }

    h1 {
      margin-bottom: 4px;
    }

    .subtitle {
      margin-top: 0;
      color: #9ca3af;
    }

    #notification-panel {
      margin-bottom: 14px;
      padding: 14px;
      border: 1px solid #92400e;
      border-radius: 12px;
      background: #422006;
    }

    #notification-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    #notification-items {
      margin-top: 8px;
    }

    .notification-item {
      margin-top: 8px;
      padding: 10px;
      border-radius: 8px;
      background: #78350f;
      white-space: pre-wrap;
    }

    .notification-item.info {
      background: #1e3a5f;
    }

    .notification-item.critical {
      background: #7f1d1d;
    }

    .notification-time {
      color: #d1d5db;
      font-size: 0.85rem;
    }

    .notification-read {
      min-width: auto;
      margin-top: 8px;
      padding: 6px 10px;
      background: #374151;
    }

    #messages {
      min-height: 420px;
      max-height: 65vh;
      overflow-y: auto;
      padding: 16px;
      border: 1px solid #374151;
      border-radius: 12px;
      background: #1f2937;
    }

    .message {
      margin: 12px 0;
      padding: 12px 14px;
      border-radius: 10px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    .user {
      margin-left: 15%;
      background: #1d4ed8;
    }

    .assistant {
      margin-right: 15%;
      background: #374151;
    }

    .error {
      background: #7f1d1d;
    }

    form {
      display: flex;
      gap: 10px;
      margin-top: 14px;
    }

    textarea {
      flex: 1;
      min-height: 54px;
      resize: vertical;
      padding: 12px;
      border: 1px solid #4b5563;
      border-radius: 10px;
      font: inherit;
    }

    button {
      min-width: 100px;
      border: 0;
      border-radius: 10px;
      padding: 0 18px;
      background: #2563eb;
      color: white;
      font-weight: 600;
      cursor: pointer;
    }

    button:disabled {
      cursor: wait;
      opacity: 0.6;
    }
  
/* BIOOPS_COLLAPSIBLE_ALERTS_CSS */
#notification-header {
  cursor: pointer;
  user-select: none;
}

#notification-header::before {
  content: "▶";
  display: inline-block;
  margin-right: 8px;
  font-size: 0.75rem;
}

#notification-panel[data-open="true"] #notification-header::before {
  content: "▼";
}

#notification-panel[data-open="false"] #notification-items {
  display: none;
}

#notification-items {
  max-height: 220px;
  overflow-y: auto;
}

</style>
</head>

<body>
  <main>
    <h1>BioOps Chat</h1>
    <p class="subtitle">
      Ask about workflows, batches, cluster health, storage, documentation, or code review.
    </p>

    <section
      id="notification-panel"
      aria-live="polite"
    >
      <div id="notification-header">
        <strong>Infrastructure notifications</strong>
        <span>
          Unread:
          <span id="notification-count">0</span>
        </span>
      </div>

      <div id="notification-items">
        No notifications yet.
      </div>
    </section>

    <section id="messages" aria-live="polite">
      <div class="message assistant">
        BioOps is ready. Enter a question below.
      </div>
    </section>

    <form id="chat-form">
      <textarea
        id="message-input"
        name="message"
        placeholder="Example: Show failed batches"
        required
      ></textarea>

      <button id="send-button" type="submit">Send</button>
    </form>
  </main>

  <script>
    const form = document.getElementById("chat-form");
    const input = document.getElementById("message-input");
    const messages = document.getElementById("messages");
    const button = document.getElementById("send-button");
    const notificationItems =
      document.getElementById("notification-items");
    const notificationCount =
      document.getElementById("notification-count");

    function addMessage(text, className) {
      const element = document.createElement("div");
      element.className = `message ${className}`;
      element.textContent = text;
      messages.appendChild(element);
      messages.scrollTop = messages.scrollHeight;
    }

    async function markNotificationRead(id) {
      await fetch(`/alerts/${id}/read`, {
        method: "POST"
      });

      await refreshNotifications();
    }

    async function refreshNotifications() {
      try {
        const response = await fetch(
          "/alerts?limit=10"
        );

        if (!response.ok) {
          return;
        }

        const payload = await response.json();

        notificationCount.textContent =
          payload.unread;

        notificationItems.replaceChildren();

        if (payload.items.length === 0) {
          notificationItems.textContent =
            "No notifications yet.";
          return;
        }

        payload.items.forEach((item) => {
          const element =
            document.createElement("div");

          element.className =
            `notification-item ${item.severity}`;

          const title =
            document.createElement("strong");

          title.textContent =
            `[${item.severity.toUpperCase()}] ` +
            item.title;

          const timestamp =
            document.createElement("div");

          timestamp.className =
            "notification-time";

          const moscowTime =
            new Date(
              item.created_at
            ).toLocaleString(
              "en-GB",
              { timeZone: "Europe/Moscow" }
            );

          timestamp.textContent =
            `${moscowTime} MSK`;

          const message =
            document.createElement("div");

          message.textContent = item.message;

          element.append(
            title,
            timestamp,
            message
          );

          if (!item.is_read) {
            const readButton =
              document.createElement("button");

            readButton.type = "button";
            readButton.className =
              "notification-read";
            readButton.textContent =
              "Mark as read";

            readButton.addEventListener(
              "click",
              () => markNotificationRead(
                item.id
              )
            );

            element.appendChild(readButton);
          }

          notificationItems.appendChild(
            element
          );
        });
      } catch (error) {
        console.error(
          "Could not load notifications",
          error
        );
      }
    }

    refreshNotifications();
    setInterval(
      refreshNotifications,
      15000
    );

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const message = input.value.trim();

      if (!message) {
        return;
      }

      addMessage(message, "user");
      input.value = "";
      button.disabled = true;
      button.textContent = "Working...";

      try {
        const response = await fetch("/chat", {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({ message })
        });

        const payload = await response.json();

        if (!response.ok) {
          throw new Error(payload.detail || "BioOps request failed");
        }

        addMessage(payload.answer, "assistant");
      } catch (error) {
        addMessage(String(error), "error");
      } finally {
        button.disabled = false;
        button.textContent = "Send";
        input.focus();
      }
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
      }
    });
  
/* BIOOPS_COLLAPSIBLE_ALERTS_JS */
(function () {
  function installCollapsibleNotifications() {
    const panel = document.getElementById("notification-panel");
    const header = document.getElementById("notification-header");
    const items = document.getElementById("notification-items");

    if (!panel || !header || !items) {
      console.warn("Notification panel elements were not found.");
      return;
    }

    panel.dataset.open = "false";

    header.setAttribute("role", "button");
    header.setAttribute("tabindex", "0");
    header.setAttribute("aria-expanded", "false");

    function togglePanel() {
      const willOpen = panel.dataset.open !== "true";

      panel.dataset.open = String(willOpen);
      header.setAttribute("aria-expanded", String(willOpen));
    }

    header.addEventListener("click", togglePanel);

    header.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        togglePanel();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      installCollapsibleNotifications
    );
  } else {
    installCollapsibleNotifications();
  }
})();

</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def chat_page() -> str:
    return CHAT_PAGE


@app.post("/internal/alerts")
def create_alert(
    payload: AlertRequest,
    request: Request,
) -> dict:
    expected_token = os.getenv(
        "BIOOPS_INTERNAL_ALERT_TOKEN",
        "",
    )
    supplied_token = request.headers.get(
        "X-BioOps-Alert-Token",
        "",
    )

    if (
        expected_token
        and supplied_token != expected_token
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid alert token.",
        )

    return get_notification_store().create(
        title=payload.title,
        message=payload.message,
        severity=payload.severity,
    )


@app.get("/alerts")
def list_alerts(limit: int = 50) -> dict:
    store = get_notification_store()

    return {
        "items": store.list_recent(limit),
        "unread": store.unread_count(),
    }


@app.post("/alerts/{alert_id}/read")
def mark_alert_read(alert_id: int) -> dict:
    try:
        return get_notification_store().mark_read(
            alert_id
        )
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail="Alert not found.",
        ) from None


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "bioops-api",
    }


def process_message(message: str) -> str:
    clean_message = message.strip()

    if not clean_message:
        raise ValueError("Message cannot be empty.")

    return run_graph(clean_message)


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    message = payload.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    try:
        answer = process_message(message)
    except Exception:
        logger.exception("BioOps failed while processing a chat message.")
        raise HTTPException(
            status_code=500,
            detail="BioOps failed while processing the message.",
        ) from None

    return ChatResponse(
        ok=True,
        message=message,
        answer=answer,
    )


def nested_value(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data

    for key in keys:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


def first_text(*values: Any) -> str:
    for value in values:
        if value is None or isinstance(value, (dict, list, tuple, set)):
            continue

        text = str(value).strip()

        if text:
            return text

    return ""


def extract_message(data: dict[str, Any]) -> str:
    return first_text(
        data.get("data[message][text]"),
        nested_value(data, "data", "message", "text"),
        data.get("message"),
        data.get("MESSAGE"),
        data.get("text"),
        data.get("TEXT"),
        nested_value(data, "PARAMS", "MESSAGE"),
        nested_value(data, "event", "text"),
    )


def extract_chat_id(data: dict[str, Any]) -> str | None:
    chat_id = first_text(
        data.get("data[chat][dialogId]"),
        data.get("data[message][chatId]"),
        nested_value(data, "data", "chat", "dialogId"),
        nested_value(data, "data", "message", "chatId"),
        data.get("chat_id"),
        data.get("DIALOG_ID"),
        data.get("dialog_id"),
        nested_value(data, "PARAMS", "DIALOG_ID"),
        nested_value(data, "event", "dialog_id"),
    )

    return chat_id or None


async def read_request_payload(request: Request) -> dict[str, Any]:
    body = await request.body()

    if not body:
        return {}

    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

        return payload if isinstance(payload, dict) else {}

    try:
        parsed = parse_qs(
            body.decode("utf-8"),
            keep_blank_values=True,
        )
    except UnicodeDecodeError:
        return {}

    return {
        key: values[-1] if values else ""
        for key, values in parsed.items()
    }


@app.post("/bitrix/message")
async def bitrix_message(request: Request) -> dict[str, Any]:
    data = await read_request_payload(request)

    message = extract_message(data)
    chat_id = extract_chat_id(data)

    if not message:
        answer = "BioOps received an empty message."
    else:
        try:
            answer = process_message(message)
        except Exception as error:
            logger.exception("BioOps failed while processing a Bitrix message.")
            answer = (
                "BioOps failed while processing your message.\n\n"
                f"Error: {type(error).__name__}: {error}"
            )

    delivered = False

    try:
        bitrix_sender.send_message(
            text=answer,
            chat_id=chat_id,
        )
        delivered = True
    except Exception:
        logger.exception("Could not send the BioOps response to Bitrix.")

    return {
        "ok": True,
        "received": message,
        "chat_id": chat_id,
        "answer": answer,
        "delivered_to_bitrix": delivered,
    }
