import pytest

from bioops.tools.llm_router import LLMRouterTool


def test_parse_valid_router_json():
    tool = LLMRouterTool()

    decision = tool._parse_decision(
        '{"agent": "cluster_health", "confidence": 0.88, "reason": "pod status question"}'
    )

    assert decision.agent == "cluster_health"
    assert decision.confidence == 0.88
    assert decision.reason == "pod status question"


def test_parse_router_json_inside_markdown_block():
    tool = LLMRouterTool()

    decision = tool._parse_decision(
        '''```json
{"agent": "review", "confidence": 0.91, "reason": "PR review request"}
```'''
    )

    assert decision.agent == "review"
    assert decision.confidence == 0.91


def test_rejects_unknown_agent():
    tool = LLMRouterTool()

    with pytest.raises(ValueError):
        tool._parse_decision(
            '{"agent": "fake_agent", "confidence": 0.7, "reason": "bad"}'
        )


def test_rejects_removed_echo_agent():
    tool = LLMRouterTool()

    with pytest.raises(ValueError):
        tool._parse_decision(
            '{"agent": "echo", "confidence": 0.7, "reason": "old fallback"}'
        )


def test_clamps_confidence_to_one():
    tool = LLMRouterTool()

    decision = tool._parse_decision(
        '{"agent": "knowledge", "confidence": 2.5, "reason": "docs question"}'
    )

    assert decision.confidence == 1.0
