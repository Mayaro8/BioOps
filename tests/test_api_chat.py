from fastapi.testclient import TestClient

from bioops.api import bitrix_app


client = TestClient(bitrix_app.app)


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "bioops-api",
    }


def test_chat_page_is_available() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "BioOps Chat" in response.text
    assert 'fetch("/chat"' in response.text


def test_chat_endpoint_calls_orchestrator(monkeypatch) -> None:
    monkeypatch.setattr(
        bitrix_app,
        "run_graph",
        lambda message: f"Answer for: {message}",
    )

    response = client.post(
        "/chat",
        json={"message": "Show failed batches"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "message": "Show failed batches",
        "answer": "Answer for: Show failed batches",
    }


def test_chat_rejects_empty_message() -> None:
    response = client.post(
        "/chat",
        json={"message": "   "},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Message cannot be empty."


def test_extracts_flat_bitrix_payload() -> None:
    payload = {
        "data[message][text]": "Latest batch status",
        "data[chat][dialogId]": "chat123",
    }

    assert bitrix_app.extract_message(payload) == "Latest batch status"
    assert bitrix_app.extract_chat_id(payload) == "chat123"


def test_extracts_nested_bitrix_payload() -> None:
    payload = {
        "data": {
            "message": {
                "text": "Check cluster health",
                "chatId": "123",
            },
            "chat": {
                "dialogId": "chat456",
            },
        }
    }

    assert bitrix_app.extract_message(payload) == "Check cluster health"
    assert bitrix_app.extract_chat_id(payload) == "chat456"
