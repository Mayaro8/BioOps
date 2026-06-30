from fastapi import FastAPI, Request

from bioops.graph_orchestrator import run_graph
from bioops.tools.bitrix_sender import BitrixSender


app = FastAPI(title="BioOps Bitrix API")
sender = BitrixSender()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "bioops-bitrix",
    }


def extract_message(data: dict) -> str:
    return (
        data.get("message")
        or data.get("MESSAGE")
        or data.get("text")
        or data.get("TEXT")
        or data.get("PARAMS", {}).get("MESSAGE")
        or data.get("event", {}).get("text")
        or ""
    )


def extract_chat_id(data: dict) -> str | None:
    return (
        data.get("chat_id")
        or data.get("DIALOG_ID")
        or data.get("dialog_id")
        or data.get("PARAMS", {}).get("DIALOG_ID")
        or data.get("event", {}).get("dialog_id")
        or None
    )


@app.post("/bitrix/message")
async def bitrix_message(request: Request):
    data = await request.json()

    message = extract_message(data).strip()
    chat_id = extract_chat_id(data)

    if not message:
        answer = "BioOps received an empty message."
    else:
        try:
            answer = run_graph(message)
        except Exception as error:
            answer = (
                "BioOps failed while processing your message.\n\n"
                f"Error: {type(error).__name__}: {error}"
            )

    sender.send_message(text=answer, chat_id=chat_id)

    return {
        "ok": True,
        "received": message,
        "chat_id": chat_id,
        "answer": answer,
    }
