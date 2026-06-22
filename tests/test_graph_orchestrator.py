from bioops.graph_orchestrator import router_node, route_after_router


def test_router_selects_knowledge_for_gvcf():
    state = {
        "message": "What does bam to gvcf output?",
        "selected_agent": "",
        "response": "",
    }

    result = router_node(state)

    assert result["selected_agent"] == "knowledge"


def test_router_selects_general_for_unrelated_message():
    state = {
        "message": "hello there",
        "selected_agent": "",
        "response": "",
    }

    result = router_node(state)

    assert result["selected_agent"] == "general"


def test_route_after_router_returns_selected_agent():
    state = {
        "message": "hello",
        "selected_agent": "general",
        "response": "",
    }

    assert route_after_router(state) == "general"
