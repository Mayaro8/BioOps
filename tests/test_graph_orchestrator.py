from bioops.graph_orchestrator import keyword_route, route_after_router, router_node
from bioops.tools.llm_router import RouterDecision


class FakeLLMRouter:
    def __init__(self, agent: str):
        self.agent = agent

    def route(self, message: str) -> RouterDecision:
        return RouterDecision(
            agent=self.agent,
            confidence=0.95,
            reason="test decision",
        )


class FailingLLMRouter:
    def route(self, message: str) -> RouterDecision:
        raise RuntimeError("router unavailable")


def test_keyword_route_selects_knowledge_for_gvcf():
    assert keyword_route("What does bam to gvcf output?") == "knowledge"


def test_keyword_route_selects_general_for_unrelated_message():
    assert keyword_route("hello there") == "general"


def test_router_node_uses_llm_decision(monkeypatch):
    import bioops.graph_orchestrator as graph_orchestrator

    monkeypatch.setattr(
        graph_orchestrator,
        "llm_router_tool",
        FakeLLMRouter("cluster_health"),
    )

    state = {
        "message": "Are any pods failing?",
        "selected_agent": "",
        "response": "",
    }

    result = router_node(state)

    assert result["selected_agent"] == "cluster_health"


def test_router_node_falls_back_to_keyword_router(monkeypatch):
    import bioops.graph_orchestrator as graph_orchestrator

    monkeypatch.setattr(
        graph_orchestrator,
        "llm_router_tool",
        FailingLLMRouter(),
    )

    state = {
        "message": "Review this pull request",
        "selected_agent": "",
        "response": "",
    }

    result = router_node(state)

    assert result["selected_agent"] == "review"


def test_route_after_router_returns_selected_agent():
    state = {
        "message": "hello",
        "selected_agent": "general",
        "response": "",
    }

    assert route_after_router(state) == "general"
