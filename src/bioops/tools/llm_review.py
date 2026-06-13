import os

from openai import AzureOpenAI

from bioops.tools.git_review import RepoReview


class LLMReviewTool:
    """Uses Azure OpenAI to perform concise architecture and code review."""

    def __init__(self):
        self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.api_version = os.getenv("AZURE_OPENAI_API_VERSION")

        self.deployment = (
            os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
            or os.getenv("AZURE_OPENAI_DEPLOYMENT")
            or os.getenv("AZURE_OPENAI_MODEL")
        )

        self.enabled = all(
            [
                self.endpoint,
                self.api_key,
                self.api_version,
                self.deployment,
            ]
        )

        self.client = None

        if self.enabled:
            self.client = AzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
                timeout=30.0,
            )

    def review(self, repo_path: str, review: RepoReview) -> str:
        if not self.enabled or self.client is None:
            return (
                "LLM review unavailable: Azure OpenAI environment variables "
                "are not fully configured."
            )

        prompt = self._build_prompt(repo_path, review)

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior bioinformatics platform engineer "
                            "reviewing code for a multi-agent BioOps assistant. "
                            "Be concise, practical, and strict. Focus only on "
                            "the most important architecture, integration, "
                            "testing, and deployment issues."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                max_completion_tokens=500,
            )
        except Exception as error:
            return f"LLM review failed: {type(error).__name__}: {error}"

        return response.choices[0].message.content or "LLM review returned no content."

    def _build_prompt(self, repo_path: str, review: RepoReview) -> str:
        changed_files = "\n".join(
            f"- {file_path}" for file_path in review.changed_files
        )

        if not changed_files:
            changed_files = "- No changed files detected."

        deterministic_findings = "\n".join(
            (
                f"- [{issue.severity}] {issue.file}: {issue.message} "
                f"Suggestion: {issue.suggestion}"
            )
            for issue in review.issues
        )

        if not deterministic_findings:
            deterministic_findings = "- No deterministic issues found."

        diff_text = review.diff_text.strip()

        if not diff_text:
            diff_text = (
                "[No git diff available. Review based on changed files and "
                "deterministic findings.]"
            )

        prompt_lines = [
            "Review this BioOps repository change.",
            "",
            "Repository/path:",
            repo_path,
            "",
            "Changed files:",
            changed_files,
            "",
            "Deterministic findings:",
            deterministic_findings,
            "",
            "Git diff:",
            "```diff",
            diff_text,
            "```",
            "",
            "Return a concise review with exactly these sections:",
            "",
            "1. Verdict: one sentence.",
            "2. Top issues: maximum 3 bullets.",
            "3. Risks: maximum 2 bullets.",
            "4. Next steps: maximum 3 bullets.",
            "",
            "Keep the full review under 250 words.",
            "Do not invent files or behavior not shown in the diff or findings.",
        ]

        return "\n".join(prompt_lines)  