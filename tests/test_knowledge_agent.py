from bioops.agents.knowledge_agent import KnowledgeAgent


class FakeQueryRewriter:
    def __init__(self, rewritten_query: str):
        self.rewritten_query = rewritten_query
        self.seen_message = None

    def rewrite(self, message: str) -> str:
        self.seen_message = message
        return self.rewritten_query


class FailingQueryRewriter:
    def rewrite(self, message: str) -> str:
        raise RuntimeError("rewriter unavailable")


class FakeEmbedder:
    def __init__(self):
        self.seen_text = None

    def embed_text(self, text: str):
        self.seen_text = text
        return [0.1, 0.2, 0.3]


class FakeStore:
    def __init__(self):
        self.seen_vector = None
        self.seen_limit = None

    def search(self, query_vector, limit: int):
        self.seen_vector = query_vector
        self.seen_limit = limit
        return ["chunk-1"]


class FakeChat:
    def __init__(self):
        self.seen_question = None
        self.seen_chunks = None

    def answer_from_chunks(self, question: str, chunks):
        self.seen_question = question
        self.seen_chunks = chunks
        return "answer from retrieved chunks"


class ExplodingEmbedder:
    def embed_text(self, text: str):
        raise AssertionError("embedder should not run")


def make_agent():
    agent = KnowledgeAgent.__new__(KnowledgeAgent)
    agent.top_k = 5
    agent.query_rewriter = FakeQueryRewriter(
        "BioOps bam to gvcf pipeline output documentation"
    )
    agent.embedder = FakeEmbedder()
    agent.store = FakeStore()
    agent.chat = FakeChat()
    return agent


def test_knowledge_agent_uses_llm_rewritten_query_for_retrieval():
    agent = make_agent()

    result = agent.run("what does bam to gvcf output?")

    assert result == "answer from retrieved chunks"
    assert agent.query_rewriter.seen_message == "what does bam to gvcf output?"
    assert agent.embedder.seen_text == (
        "BioOps bam to gvcf pipeline output documentation"
    )
    assert agent.store.seen_vector == [0.1, 0.2, 0.3]
    assert agent.store.seen_limit == 5
    assert agent.chat.seen_question == "what does bam to gvcf output?"
    assert agent.chat.seen_chunks == ["chunk-1"]


def test_knowledge_agent_returns_error_when_llm_rewriter_fails():
    agent = KnowledgeAgent.__new__(KnowledgeAgent)
    agent.top_k = 5
    agent.query_rewriter = FailingQueryRewriter()
    agent.embedder = ExplodingEmbedder()
    agent.store = FakeStore()
    agent.chat = FakeChat()

    result = agent.run("what does bam to gvcf output?")

    assert "query_rewrite_error" in result
    assert "No keyword expansion fallback was used" in result
    assert "No Qdrant search was run" in result
