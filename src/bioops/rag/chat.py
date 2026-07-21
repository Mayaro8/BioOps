import os

from dotenv import load_dotenv
from openai import AzureOpenAI

from bioops.rag.schemas import RetrievedChunk

load_dotenv()


class AzureChatClient:
    """Uses Azure OpenAI chat model to synthesize answers from retrieved chunks."""

    def __init__(self):
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        )

        self.deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-5.5")

        if not self.deployment:
            raise ValueError("Missing AZURE_OPENAI_CHAT_DEPLOYMENT in .env")

    def answer_from_chunks(
        self,
        question: str,
        chunks: list[RetrievedChunk],
    ) -> str:
        context = self._format_context(chunks)

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the BioOps Knowledge Agent. "
                        "Answer only using the provided context. "
                        "If the context does not contain the answer, say that the information is not available. "
                        "Keep the answer concise and factual. "
                        "Do not invent sources."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question:\n{question}\n\n"
                        f"Context:\n{context}\n\n"
                        "Write a direct answer. Then add a short Sources section."
                    ),
                },
            ],
            max_completion_tokens=1200,
        )

        return response.choices[0].message.content or ""

    def _format_context(self, chunks: list[RetrievedChunk]) -> str:
        blocks = []

        for index, chunk in enumerate(chunks, start=1):
            source = chunk.metadata.get("source", "unknown source")
            source_url = chunk.metadata.get("page_url", "")
            chunk_number = chunk.metadata.get("chunk_number", "unknown")
            score = chunk.score

            lines = [
                f"[Chunk {index}]",
                f"Source: {source}",
            ]

            if source_url:
                lines.append(f"Source URL: {source_url}")

            lines.extend(
                [
                    f"Chunk number: {chunk_number}",
                    (
                        f"Score: {score:.4f}"
                        if score is not None
                        else "Score: unknown"
                    ),
                    "Text:",
                    chunk.text,
                ]
            )
            blocks.append("\n".join(lines))

        return "\n\n---\n\n".join(blocks)
