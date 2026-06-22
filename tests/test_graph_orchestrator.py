from bioops import graph_orchestrator as go


class FakeDecision:
    def __init__(self, agent: str):
        self.agent = agent
        self.reason = "test"


class FakeRouter:
    def __init__(self, agent: str):
        self.agent = agent

    def route(self, message: str):
        return FakeDecision(self.agent)


class FailingRouter:
    def route(self, message: str):
        raise RuntimeError("router unavailable")


def test_router_uses_llm_selected_general(monkeypatch):
    monkeypatch.setattr(go, "llm_router_tool", FakeRouter("general"))

    result = go.router_node(
        {
            "message": "hello",
            "selected_agent": "",
            "response": "",
        }
    )

    assert result["selected_agent"] == "general"


def test_router_uses_llm_selected_knowledge(monkeypatch):
    monkeypatch.setattr(go, "llm_router_tool", FakeRouter("knowledge"))

    result = go.router_node(
        {
            "message": "explain the bam to gvcf pipeline step",
            "selected_agent": "",
            "response": "",
        }
    )

    assert result["selected_agent"] == "knowledge"


def test_router_failure_returns_routing_error_not_general(monkeypatch):
    monkeypatch.setattr(go, "llm_router_tool", FailingRouter())

    result = go.router_node(
        {
            "message": "hello",
            "selected_agent": "",
            "response": "",
        }
    )

    assert result["selected_agent"] == go.ROUTING_ERROR
    assert "routing_error" in result["response"]
    assert "No keyword fallback was used" in result["response"]


def test_invalid_llm_agent_returns_routing_error(monkeypatch):
    monkeypatch.setattr(go, "llm_router_tool", FakeRouter("echo"))

    result = go.router_node(
        {
            "message": "hello",
            "selected_agent": "",
            "response": "",
        }
    )

    assert result["selected_agent"] == go.ROUTING_ERROR
    assert "unsupported agent" in result["response"]


def test_route_after_router_rejects_removed_echo_agent():
    result = go.route_after_router(
        {
            "message": "hello",
            "selected_agent": "echo",
            "response": "",
        }
    )

    assert result == go.ROUTING_ERROR
