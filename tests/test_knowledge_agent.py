from bioops.agents.knowledge_agent import KnowledgeAgent


def test_expand_query_short_gvcf_query_adds_context():
    agent = KnowledgeAgent.__new__(KnowledgeAgent)

    expanded = agent._expand_query("gvcf")

    assert "gvcf" in expanded
    assert "Search context:" in expanded
    assert "bam to gvcf" in expanded
    assert "pipeline step" in expanded


def test_expand_query_long_unrelated_query_returns_clean_message():
    agent = KnowledgeAgent.__new__(KnowledgeAgent)

    expanded = agent._expand_query("hello this is unrelated text")

    assert expanded == "hello this is unrelated text"

