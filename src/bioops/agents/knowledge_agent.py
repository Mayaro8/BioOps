from bioops.agents.base import BaseAgent
from bioops.rag.chat import AzureChatClient
from bioops.rag.embeddings import AzureEmbeddingClient
from bioops.rag.qdrant_store import QdrantKnowledgeStore
from bioops.tools.llm_query_rewriter import LLMQueryRewriter


class KnowledgeAgent(BaseAgent):
    """Answers questions using BioOps documentation and Qdrant RAG."""

    name = "knowledge"
    description = "Answers questions using BioOps documentation and Qdrant RAG."

    def __init__(
        self,
        top_k: int = 5,
        query_rewriter: LLMQueryRewriter | None = None,
    ):
        self.top_k = top_k
        self.query_rewriter = query_rewriter or LLMQueryRewriter()
        self.embedder = AzureEmbeddingClient()
        self.store = QdrantKnowledgeStore()
        self.chat = AzureChatClient()

    def run(self, message: str) -> str:
        try:
            rewritten_query = self.query_rewriter.rewrite(message)
        except Exception as error:
            return self._format_query_rewrite_error(error)

        query_vector = self.embedder.embed_text(rewritten_query)
        chunks = self.store.search(query_vector, limit=self.top_k)

        if not chunks:
            return "I could not find relevant BioOps knowledge in Qdrant."

        answer = self.chat.answer_from_chunks(
            question=message,
            chunks=chunks,
        )

        return answer.strip()

    def _format_query_rewrite_error(self, error: Exception) -> str:
        return "\n".join(
            [
                "Knowledge query rewriting failed",
                "",
                "Status: query_rewrite_error",
                f"Error: {type(error).__name__}: {error}",
                "",
                "The Knowledge Agent now uses LLM-only query rewriting.",
                "No keyword expansion fallback was used.",
                "No Qdrant search was run.",
            ]
        )
