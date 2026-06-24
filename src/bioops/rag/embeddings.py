import os

from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()


class AzureEmbeddingClient:
    """Creates embedding vectors using Azure OpenAI."""

    def __init__(self):
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        )
        self.deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

        if not self.deployment:
            raise ValueError("Missing AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

    def embed_text(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model=self.deployment,
            input=text,
        )
        return response.data[0].embedding

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.deployment,
            input=texts,
        )
        return [item.embedding for item in response.data]
