from bioops.agents.review_agent import ReviewAgent
from bioops.tools.github_review_tool import GitHubChangedFile
from bioops.tools.llm_review import LLMReviewError


class FakeLLMReviewTool:
    def review_prompt(self, prompt: str) -> str:
        assert "Patch text:" in prompt
        assert "src/bioops/test.py" in prompt
        return "1. Verdict: looks testable."



class FailingLLMReviewTool:
    def review_prompt(self, prompt: str) -> str:
        raise LLMReviewError("LLM patch review could not be started: missing Azure config")


def test_review_agent_adds_llm_patch_review_section():
    agent = ReviewAgent(llm_review_tool=FakeLLMReviewTool())

    report = agent._format_changed_files_review(
        title="GitHub PR Review Report",
        status="ok",
        repo="Mayaro8/BioOps",
        subject="PR #1: test",
        base="main",
        head="feature/test",
        author="tester",
        changed_files=[
            GitHubChangedFile(
                filename="src/bioops/test.py",
                status="modified",
                additions=2,
                deletions=1,
                changes=3,
                patch="@@" "\n+print('hello')",
            )
        ],
    )

    assert "LLM patch review:" in report
    assert "1. Verdict: looks testable." in report
    assert "No GitHub comments were posted." in report
    assert "No PR status was modified." in report


def test_review_agent_handles_missing_patch_text():
    agent = ReviewAgent(llm_review_tool=FakeLLMReviewTool())

    patch_text = agent._build_patch_text(
        [
            GitHubChangedFile(
                filename="README.md",
                status="modified",
                additions=1,
                deletions=0,
                changes=1,
                patch="",
            )
        ]
    )

    assert "No patch text available" in patch_text


def test_review_agent_returns_error_when_llm_patch_review_fails():
    agent = ReviewAgent(llm_review_tool=FailingLLMReviewTool())

    report = agent._format_changed_files_review(
        title="GitHub PR Review Report",
        status="ok",
        repo="Mayaro8/BioOps",
        subject="PR #1: test",
        base="main",
        head="feature/test",
        author="tester",
        changed_files=[
            GitHubChangedFile(
                filename="src/bioops/test.py",
                status="modified",
                additions=2,
                deletions=1,
                changes=3,
                patch="@@" "\n+print('hello')",
            )
        ],
    )

    assert "Status: llm_review_error" in report
    assert "Status: ok" not in report
    assert "Patch-level LLM review failed." in report
    assert "No successful PR/branch review was produced." in report
