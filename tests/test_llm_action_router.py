from types import SimpleNamespace

import pytest

from bioops.tools.llm_action_router import LLMActionRouter


class FakeCompletions:
    def __init__(self, content: str):
        self.content = content

    def create(self, **_kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class FakeClient:
    def __init__(self, content: str):
        self.chat = SimpleNamespace(completions=FakeCompletions(content))


def _router(content: str) -> LLMActionRouter:
    router = LLMActionRouter(
        agent_name="Test Agent",
        actions={"summary": "Summarize.", "help": "Help."},
        parameter_schema={"limit": "Optional integer."},
    )
    router.enabled = True
    router.client = FakeClient(content)
    router.deployment = "test"
    return router


def test_returns_validated_action_decision():
    decision = _router(
        '{"action":"summary","parameters":{"limit":5},"reason":"requested"}'
    ).route("summarize")

    assert decision.action == "summary"
    assert decision.parameters == {"limit": 5}
    assert decision.reason == "requested"


def test_rejects_unsupported_action():
    with pytest.raises(ValueError, match="unsupported action"):
        _router(
            '{"action":"delete","parameters":{},"reason":"bad"}'
        ).route("delete")


def test_rejects_unsupported_parameter():
    with pytest.raises(ValueError, match="unsupported parameters"):
        _router(
            '{"action":"summary","parameters":{"path":"x"},"reason":"bad"}'
        ).route("summary")


def test_fails_closed_without_azure_configuration(monkeypatch):
    for name in (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_CHAT_DEPLOYMENT",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)

    router = LLMActionRouter(
        agent_name="Test Agent",
        actions={"help": "Help."},
    )
    with pytest.raises(RuntimeError, match="action router unavailable"):
        router.route("help")
