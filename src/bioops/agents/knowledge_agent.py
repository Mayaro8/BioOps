import logging
import os

from bioops.agents.base import BaseAgent
from bioops.rag.chat import AzureChatClient
from bioops.rag.embeddings import AzureEmbeddingClient
from bioops.rag.qdrant_store import QdrantKnowledgeStore
from bioops.rag.schemas import RetrievedChunk
from bioops.rag.yandex_wiki import env_flag
from bioops.tools.llm_query_rewriter import LLMQueryRewriter


logger = logging.getLogger(__name__)


class KnowledgeAgent(BaseAgent):
    """Answers from indexed Yandex Wiki pages, then bundled docs."""

    name = "knowledge"
    description = (
        "Answers from indexed Yandex Wiki pages first, with bundled docs "
        "as fallback."
    )

    def __init__(
        self,
        top_k: int = 5,
        query_rewriter: LLMQueryRewriter | None = None,
    ):
        self.top_k = top_k
        self.query_rewriter = query_rewriter or LLMQueryRewriter()
        self.embedder = AzureEmbeddingClient()
        self.store = QdrantKnowledgeStore()
        self.wiki_store: QdrantKnowledgeStore | None = None

        if env_flag("YANDEX_WIKI_ENABLED"):
            docs_collection = os.getenv(
                "QDRANT_COLLECTION",
                "bioops_knowledge",
            )
            wiki_collection = os.getenv(
                "QDRANT_WIKI_COLLECTION",
                f"{docs_collection}_wiki",
            )
            self.wiki_store = QdrantKnowledgeStore(
                collection_name=wiki_collection,
            )

        self.wiki_min_score = float(
            os.getenv("YANDEX_WIKI_MIN_SCORE", "0.35")
        )
        self.chat = AzureChatClient()

    def run(self, message: str) -> str:
        try:
            rewritten_query = self.query_rewriter.rewrite(message)
        except Exception as error:
            return self._format_query_rewrite_error(error)

        query_vector = self.embedder.embed_text(rewritten_query)

        wiki_chunks = self._search_wiki(query_vector)

        if wiki_chunks:
            return self.chat.answer_from_chunks(
                question=message,
                chunks=wiki_chunks,
            ).strip()

        chunks = self.store.search(
            query_vector,
            limit=self.top_k,
        )

        if not chunks:
            return (
                "I could not find relevant BioOps knowledge in Yandex Wiki "
                "or the bundled documentation."
            )

        answer = self.chat.answer_from_chunks(
            question=message,
            chunks=chunks,
        )

        return answer.strip()

    def _search_wiki(
        self,
        query_vector: list[float],
    ) -> list[RetrievedChunk]:
        wiki_store = getattr(self, "wiki_store", None)

        if wiki_store is None:
            return []

        try:
            chunks = wiki_store.search(
                query_vector,
                limit=self.top_k,
            )
        except Exception:
            logger.warning(
                "Yandex Wiki knowledge search failed; using bundled docs.",
                exc_info=True,
            )
            return []

        minimum_score = getattr(self, "wiki_min_score", 0.35)

        return [
            chunk
            for chunk in chunks
            if getattr(chunk, "score", None) is None
            or float(chunk.score) >= minimum_score
        ]

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
