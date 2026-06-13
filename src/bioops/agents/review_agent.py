from bioops.agents.base import BaseAgent
from bioops.tools.git_review import GitReviewTool, RepoReview, ReviewIssue
from bioops.tools.llm_review import LLMReviewTool


class ReviewAgent(BaseAgent):
    """Reviews repositories and returns structured review comments."""

    name = "review"
    description = "Reviews code repositories, PRs/MRs, risks, style, and logic issues."

    def __init__(
        self,
        review_tool: GitReviewTool | None = None,
        llm_review_tool: LLMReviewTool | None = None,
    ):
        self.review_tool = review_tool or GitReviewTool()
        self.llm_review_tool = llm_review_tool or LLMReviewTool()

    def run(self, message: str) -> str:
        repo_path = self._extract_repo_path(message)
        review = self.review_tool.review_local_repo(repo_path)
        llm_review = self.llm_review_tool.review(repo_path, review)

        return self._format_report(repo_path, review, llm_review)

    def _extract_repo_path(self, message: str) -> str:
        words = message.split()

        for word in words:
            if word.startswith("./") or word.startswith("/"):
                return word

        return "."

    def _format_report(
        self,
        repo_path: str,
        review: RepoReview,
        llm_review: str,
    ) -> str:
        issues = review.issues

        lines = [
            "Review Agent Report",
            "",
            f"Target repo/path: {repo_path}",
            "",
            "Changed files:",
        ]

        if review.changed_files:
            for file_path in review.changed_files:
                lines.append(f"- {file_path}")
        else:
            lines.append("- No changed files detected.")

        lines.extend(
            [
                "",
                "Deterministic severity summary:",
                f"- High: {self._count_by_severity(issues, 'high')}",
                f"- Medium: {self._count_by_severity(issues, 'medium')}",
                f"- Low: {self._count_by_severity(issues, 'low')}",
                "",
            ]
        )

        if issues:
            lines.append("Deterministic findings:")
            for issue in issues:
                lines.append(f"- [{issue.severity}] {issue.file}: {issue.message}")
        else:
            lines.append("Deterministic findings: none detected.")

        lines.extend(
            [
                "",
                "LLM architecture review:",
                llm_review,
            ]
        )

        return "\n".join(lines)

    def _count_by_severity(self, issues: list[ReviewIssue], severity: str) -> int:
        return sum(issue.severity == severity for issue in issues)