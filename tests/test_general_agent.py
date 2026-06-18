from bioops.agents.general_agent import GeneralAgent


def test_general_agent_returns_configuration_message_without_azure(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_CHAT_DEPLOYMENT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_MODEL", raising=False)

    agent = GeneralAgent()
    response = agent.run("hello")

    assert "general LLM fallback is not configured" in response
    assert "AZURE_OPENAI_CHAT_DEPLOYMENT" in response
