from fastapi import FastAPI, Request

from bioops.tools.bitrix_sender import BitrixSender

app = FastAPI(title="BioOps Bitrix API")

sender = BitrixSender()


@app.get("/health")
def health():
    return {"status": "ok", "service": "bioops-bitrix"}


@app.post("/bitrix/message")
async def bitrix_message(request: Request):
    data = await request.json()

    message = (
        data.get("message")
        or data.get("MESSAGE")
        or data.get("text")
        or ""
    )

    chat_id = (
        data.get("chat_id")
        or data.get("DIALOG_ID")
        or data.get("dialog_id")
        or None
    )

    answer = f"BioOps received your message: {message}"

    sender.send_message(text=answer, chat_id=chat_id)

    return {
        "ok": True,
        "received": message,
        "chat_id": chat_id,
        "answer": answer,
    }
