from bioops.agents.base import BaseAgent
from bioops.rag.chat import AzureChatClient
from bioops.rag.embeddings import AzureEmbeddingClient
from bioops.rag.qdrant_store import QdrantKnowledgeStore


class KnowledgeAgent(BaseAgent):
    """Answers questions using BioOps documentation and Qdrant RAG."""

    name = "knowledge"
    description = "Answers questions using BioOps documentation and Qdrant RAG."

    def __init__(self, top_k: int = 5):
        self.top_k = top_k
        self.embedder = AzureEmbeddingClient()
        self.store = QdrantKnowledgeStore()
        self.chat = AzureChatClient()

    def run(self, message: str) -> str:
        expanded_query = self._expand_query(message)
        query_vector = self.embedder.embed_text(expanded_query)
        chunks = self.store.search(query_vector, limit=self.top_k)

        if not chunks:
            return "I could not find relevant BioOps knowledge in Qdrant."

        answer = self.chat.answer_from_chunks(
            question=message,
            chunks=chunks,
        )

        return answer.strip()

    def _expand_query(self, message: str) -> str:
        """Expand short user queries to improve vector retrieval."""
        message_clean = message.strip()

        expansion_terms = [
            "BioOps",
            "pipeline-v3.0",
            "pipeline step",
            "input data",
            "output data",
            "run parameters",
            "documentation",
            "repository",
        ]

        domain_terms = {
            "gvcf": "bam to gvcf gvcf to vcf haplotype caller variant calling output gvcf file",
            "bam": "bam file alignment input haplotype caller bam to gvcf",
            "vcf": "vcf file variant calling gvcf to vcf output",
            "haplotype": "haplotype caller bam to gvcf variant calling",
        }

        extra_terms = []
        message_lower = message_clean.lower()

        for keyword, terms in domain_terms.items():
            if keyword in message_lower:
                extra_terms.append(terms)

        if len(message_clean.split()) <= 3:
            extra_terms.extend(expansion_terms)

        if not extra_terms:
            return message_clean

        return f"{message_clean}\n\nSearch context: {' '.join(extra_terms)}"