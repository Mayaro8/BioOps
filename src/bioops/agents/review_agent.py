import subprocess
from pathlib import Path

from bioops.agents.base import BaseAgent
from bioops.tools.github_review_tool import (
    GitHubBranchCompareContext,
    GitHubChangedFile,
    GitHubOpenPullRequestsContext,
    GitHubPullRequestContext,
    GitHubRepoOverviewContext,
    GitHubReviewTool,
)
from bioops.tools.llm_review import LLMReviewTool


class ReviewAgent(BaseAgent):
    """
    Reviews local repositories and GitHub repositories/PRs.

    Supported GitHub modes:
    - review repo=owner/repo
    - check open PRs repo=owner/repo
    - review repo=owner/repo pr=12
    - review https://github.com/owner/repo/pull/12
    - review repo=owner/repo base=main head=feature/x

    Supported local mode:
    - review path=/app
    """

    name = "review"
    description = (
        "Reviews repositories, GitHub PRs, changed files, risks, style, "
        "logic issues, and missing tests."
    )

    def __init__(
        self,
        github_tool: GitHubReviewTool | None = None,
        llm_review_tool: LLMReviewTool | None = None,
        default_repo_path: str = ".",
    ):
        self.github_tool = github_tool or GitHubReviewTool()
        self.llm_review_tool = llm_review_tool or LLMReviewTool()
        self.default_repo_path = default_repo_path

    def run(self, message: str) -> str:
        request = self.github_tool.parse_request(message)

        if request.mode == "pr":
            context = self.github_tool.fetch_pull_request(
                repo_name=request.repo,
                pr_number=request.pr_number,
            )
            return self._format_github_pr_report(context)

        if request.mode == "open_prs":
            context = self.github_tool.list_open_pull_requests(
                repo_name=request.repo,
            )
            return self._format_open_prs_report(context)

        if request.mode == "compare":
            context = self.github_tool.compare_branches(
                repo_name=request.repo,
                base=request.base,
                head=request.head,
            )
            return self._format_branch_compare_report(context)

        if request.mode == "repo":
            context = self.github_tool.fetch_repo_overview(
                repo_name=request.repo,
            )
            return self._format_repo_overview_report(context)

        repo_path = self._parse_path(message) or self.default_repo_path
        return self._review_local_repo(repo_path)

    def _parse_path(self, message: str) -> str | None:
        for token in message.split():
            if token.startswith("path="):
                return token.split("=", 1)[1]
        return None

    def _format_repo_overview_report(
        self,
        context: GitHubRepoOverviewContext,
    ) -> str:
        lines = [
            "GitHub Repository Review Report",
            "",
            f"Status: {context.status}",
            f"Repository: {context.repo or 'not provided'}",
            "",
        ]

        if context.status == "not configured":
            lines.append("Missing configuration:")
            lines.extend(f"- {item}" for item in context.missing_config)
            return "\n".join(lines)

        if context.status == "error":
            lines.extend(
                [
                    "Failed to fetch GitHub repository.",
                    f"Error: {context.error}",
                ]
            )
            return "\n".join(lines)

        paths = context.tree_paths
        root_files = set(context.root_files)

        has_readme = any(path.lower().startswith("readme") for path in root_files)
        has_tests = any(path.startswith("tests/") for path in paths)
        has_src = any(path.startswith("src/bioops/") for path in paths)
        has_dockerfile = "Dockerfile" in root_files
        has_compose = any(
            name in root_files
            for name in {"docker-compose.yml", "compose.yml", "compose.yaml"}
        )
        has_requirements = "requirements.txt" in root_files
        has_workflows = any(path.startswith(".github/workflows/") for path in paths)
        has_pycache = any("__pycache__" in path or path.endswith(".pyc") for path in paths)
        has_env = ".env" in root_files

        issues: list[str] = []
        risks: list[str] = []
        suggestions: list[str] = []

        if not has_readme:
            issues.append("README file was not found at repository root.")
        if not has_src:
            issues.append("Expected src/bioops package was not found.")
        if not has_tests:
            risks.append("No tests directory detected.")
        if not has_dockerfile:
            risks.append("Dockerfile was not found.")
        if not has_compose:
            risks.append("Docker Compose file was not found.")
        if not has_requirements:
            risks.append("requirements.txt was not found.")
        if not has_workflows:
            suggestions.append("Consider adding GitHub Actions for pytest/build checks.")
        if has_pycache:
            risks.append("Generated Python cache files appear to be committed.")
        if has_env:
            risks.append(".env appears at repository root; secrets must not be committed.")
        if has_tests and has_src:
            suggestions.append("Run pytest and Docker build before merging agent changes.")

        lines.extend(
            [
                f"Default branch: {context.default_branch}",
                f"Private: {context.private}",
                f"Language: {context.language or 'unknown'}",
                f"Description: {context.description or 'none'}",
                f"Files indexed from tree: {len(paths)}",
                "",
                "Repository checks:",
                f"- README: {'present' if has_readme else 'missing'}",
                f"- src/bioops package: {'present' if has_src else 'missing'}",
                f"- tests/: {'present' if has_tests else 'missing'}",
                f"- Dockerfile: {'present' if has_dockerfile else 'missing'}",
                f"- Docker Compose: {'present' if has_compose else 'missing'}",
                f"- requirements.txt: {'present' if has_requirements else 'missing'}",
                f"- GitHub Actions: {'present' if has_workflows else 'missing'}",
                "",
                "Found issues:",
            ]
        )

        lines.extend(f"- {item}" for item in issues) if issues else lines.append("- none")

        lines.extend(["", "Risks:"])
        lines.extend(f"- {item}" for item in risks) if risks else lines.append("- none")

        lines.extend(["", "Style / logic remarks:"])
        lines.append("- Repository overview only; no patch-level logic review was performed.")

        lines.extend(["", "Suggestions:"])
        lines.extend(f"- {item}" for item in suggestions) if suggestions else lines.append("- none")

        lines.extend(
            [
                "",
                "No GitHub comments were posted.",
                "No repository files were modified.",
            ]
        )

        return "\n".join(lines)

    def _format_open_prs_report(
        self,
        context: GitHubOpenPullRequestsContext,
    ) -> str:
        lines = [
            "GitHub Open PRs Report",
            "",
            f"Status: {context.status}",
            f"Repository: {context.repo or 'not provided'}",
            "",
        ]

        if context.status == "not configured":
            lines.append("Missing configuration:")
            lines.extend(f"- {item}" for item in context.missing_config)
            return "\n".join(lines)

        if context.status == "error":
            lines.extend(
                [
                    "Failed to fetch open PRs.",
                    f"Error: {context.error}",
                ]
            )
            return "\n".join(lines)

        lines.extend(
            [
                f"Open PRs: {len(context.pull_requests)}",
                "",
                "PRs:",
            ]
        )

        if not context.pull_requests:
            lines.append("- none")
        else:
            for pr in context.pull_requests[:20]:
                lines.append(
                    f"- #{pr.number}: {pr.title} "
                    f"[{pr.head_branch} -> {pr.base_branch}, "
                    f"{pr.changed_files} files, +{pr.additions}/-{pr.deletions}]"
                )

        lines.extend(["", "Risks:"])
        risky_prs = [
            pr
            for pr in context.pull_requests
            if pr.changed_files > 20 or pr.additions + pr.deletions > 1000
        ]

        if risky_prs:
            for pr in risky_prs:
                lines.append(f"- PR #{pr.number} is large and needs careful review.")
        else:
            lines.append("- No large open PRs detected.")

        lines.extend(
            [
                "",
                "No GitHub comments were posted.",
                "No PR status was modified.",
            ]
        )

        return "\n".join(lines)

    def _format_github_pr_report(
        self,
        context: GitHubPullRequestContext,
    ) -> str:
        lines = [
            "GitHub PR Review Report",
            "",
            f"Status: {context.status}",
            f"Repository: {context.repo or 'not provided'}",
            f"PR number: {context.pr_number or 'not provided'}",
            "",
        ]

        if context.status == "not configured":
            lines.append("Missing configuration:")
            lines.extend(f"- {item}" for item in context.missing_config)
            lines.extend(
                [
                    "",
                    "No GitHub data was fetched.",
                    "No GitHub comments were posted.",
                    "No PR status was modified.",
                ]
            )
            return "\n".join(lines)

        if context.status == "error":
            lines.extend(
                [
                    "Failed to fetch GitHub PR.",
                    f"Error: {context.error}",
                    "",
                    "No GitHub comments were posted.",
                    "No PR status was modified.",
                ]
            )
            return "\n".join(lines)

        return self._format_changed_files_review(
            title="GitHub PR Review Report",
            status=context.status,
            repo=context.repo,
            subject=f"PR #{context.pr_number}: {context.title}",
            base=context.base_branch,
            head=context.head_branch,
            author=context.author,
            changed_files=context.changed_files,
        )

    def _format_branch_compare_report(
        self,
        context: GitHubBranchCompareContext,
    ) -> str:
        lines = [
            "GitHub Branch Compare Review Report",
            "",
            f"Status: {context.status}",
            f"Repository: {context.repo or 'not provided'}",
            f"Base: {context.base or 'not provided'}",
            f"Head: {context.head or 'not provided'}",
            "",
        ]

        if context.status == "not configured":
            lines.append("Missing configuration:")
            lines.extend(f"- {item}" for item in context.missing_config)
            return "\n".join(lines)

        if context.status == "error":
            lines.extend(
                [
                    "Failed to compare branches.",
                    f"Error: {context.error}",
                ]
            )
            return "\n".join(lines)

        lines.extend(
            [
                f"Commits: {context.commits}",
                f"Ahead by: {context.ahead_by}",
                f"Behind by: {context.behind_by}",
                "",
            ]
        )

        lines.append(
            self._format_changed_files_review(
                title="Changed Files Review",
                status=context.status,
                repo=context.repo,
                subject=f"{context.base}...{context.head}",
                base=context.base or "",
                head=context.head or "",
                author="",
                changed_files=context.changed_files,
                include_header=False,
            )
        )

        return "\n".join(lines)

    def _format_changed_files_review(
        self,
        title: str,
        status: str,
        repo: str | None,
        subject: str,
        base: str,
        head: str,
        author: str,
        changed_files: list[GitHubChangedFile],
        include_header: bool = True,
    ) -> str:
        total_additions = sum(file.additions for file in changed_files)
        total_deletions = sum(file.deletions for file in changed_files)

        issues = self._detect_issues(changed_files)
        risks = self._detect_risks(changed_files)
        remarks = self._detect_style_logic_remarks(changed_files)
        suggestions = self._detect_suggestions(changed_files)

        llm_review = self._run_llm_patch_review(
            repo=repo,
            subject=subject,
            base=base,
            head=head,
            changed_files=changed_files,
            issues=issues,
            risks=risks,
            remarks=remarks,
            suggestions=suggestions,
        )

        lines: list[str] = []

        if include_header:
            lines.extend(
                [
                    title,
                    "",
                    f"Status: {status}",
                    f"Repository: {repo or 'not provided'}",
                    f"Subject: {subject}",
                ]
            )

            if author:
                lines.append(f"Author: {author}")

            lines.extend(
                [
                    f"Base branch: {base}",
                    f"Head branch: {head}",
                    "",
                ]
            )

        lines.extend(
            [
                f"Changed files: {len(changed_files)}",
                f"Diff size: +{total_additions}/-{total_deletions}",
                "",
                "Changed files summary:",
            ]
        )

        if changed_files:
            for file in changed_files[:20]:
                lines.append(
                    f"- {file.filename} [{file.status}, +{file.additions}/-{file.deletions}]"
                )
            if len(changed_files) > 20:
                lines.append(f"- ... {len(changed_files) - 20} more files")
        else:
            lines.append("- none")

        lines.extend(["", "Found issues:"])
        lines.extend(f"- {item}" for item in issues) if issues else lines.append("- none")

        lines.extend(["", "Risks:"])
        lines.extend(f"- {item}" for item in risks) if risks else lines.append("- none")

        lines.extend(["", "Style / logic remarks:"])
        lines.extend(f"- {item}" for item in remarks) if remarks else lines.append("- none")

        lines.extend(["", "Suggestions:"])
        lines.extend(f"- {item}" for item in suggestions) if suggestions else lines.append("- none")

        lines.extend(
            [
                "",
                "LLM patch review:",
                llm_review,
                "",
                "Review note:",
                "- This is a read-only review using deterministic checks plus optional LLM patch analysis.",
                "- No GitHub comments were posted.",
                "- No PR status was modified.",
            ]
        )

        return "\n".join(lines)

    def _build_patch_text(
        self,
        changed_files: list[GitHubChangedFile],
        max_files: int = 12,
        max_patch_chars: int = 12000,
    ) -> str:
        patch_sections: list[str] = []
        total_chars = 0

        for file in changed_files[:max_files]:
            patch = (file.patch or "").strip()
            if not patch:
                continue

            section = (
                f"File: {file.filename}\n"
                f"Status: {file.status}, +{file.additions}/-{file.deletions}\n"
                "Patch:\n"
                f"{patch}\n"
            )

            if total_chars + len(section) > max_patch_chars:
                remaining = max_patch_chars - total_chars
                if remaining > 500:
                    patch_sections.append(section[:remaining] + "\n[Patch truncated]")
                break

            patch_sections.append(section)
            total_chars += len(section)

        if not patch_sections:
            return "[No patch text available. Review based on changed-file metadata only.]"

        return "\n---\n".join(patch_sections)

    def _run_llm_patch_review(
        self,
        repo: str | None,
        subject: str,
        base: str,
        head: str,
        changed_files: list[GitHubChangedFile],
        issues: list[str],
        risks: list[str],
        remarks: list[str],
        suggestions: list[str],
    ) -> str:
        if not changed_files:
            return "LLM patch review unavailable: no changed files were provided."

        patch_text = self._build_patch_text(changed_files)

        deterministic_context = "\n".join(
            [
                "Deterministic issues:",
                *(f"- {item}" for item in issues or ["none"]),
                "",
                "Deterministic risks:",
                *(f"- {item}" for item in risks or ["none"]),
                "",
                "Style / logic remarks:",
                *(f"- {item}" for item in remarks or ["none"]),
                "",
                "Suggestions:",
                *(f"- {item}" for item in suggestions or ["none"]),
            ]
        )

        prompt = "\n".join(
            [
                "Review this BioOps GitHub patch.",
                "",
                f"Repository: {repo or 'not provided'}",
                f"Subject: {subject}",
                f"Base branch: {base}",
                f"Head branch: {head}",
                "",
                deterministic_context,
                "",
                "Patch text:",
                "```diff",
                patch_text,
                "```",
                "",
                "Return a concise patch-level review with exactly these sections:",
                "",
                "1. Verdict: one sentence.",
                "2. Top issues: maximum 3 bullets.",
                "3. Risks: maximum 2 bullets.",
                "4. Next steps: maximum 3 bullets.",
                "",
                "Keep the full review under 250 words.",
                "Do not invent files, APIs, tests, or behavior not shown in the patch.",
                "Do not suggest posting comments, merging, approving, or modifying GitHub.",
            ]
        )

        return self.llm_review_tool.review_prompt(prompt)

    def _detect_issues(self, files: list[GitHubChangedFile]) -> list[str]:
        filenames = [file.filename for file in files]
        issues: list[str] = []

        if any("__pycache__" in file or file.endswith(".pyc") for file in filenames):
            issues.append("Generated Python cache files appear in the change set.")

        if any(file == ".env" or file.endswith((".pem", ".key", ".crt")) for file in filenames):
            issues.append("Potential secret or credential-like file appears in the change set.")

        return issues

    def _detect_risks(self, files: list[GitHubChangedFile]) -> list[str]:
        filenames = [file.filename for file in files]
        risks: list[str] = []

        if any(file in {"requirements.txt", "Dockerfile", "docker-compose.yml"} for file in filenames):
            risks.append("Dependency/container files changed; Docker rebuild and full tests are needed.")

        if any(file.startswith("src/bioops/agents/") for file in filenames):
            if not any(file.startswith("tests/") for file in filenames):
                risks.append("Agent code changed without corresponding test changes.")

        if any(file.startswith("src/bioops/tools/") for file in filenames):
            if not any(file.startswith("tests/") for file in filenames):
                risks.append("Tool code changed without corresponding test changes.")

        large_files = [file.filename for file in files if file.changes > 500]
        if large_files:
            risks.append("Large changed files need careful review: " + ", ".join(large_files[:5]))

        return risks

    def _detect_style_logic_remarks(self, files: list[GitHubChangedFile]) -> list[str]:
        filenames = [file.filename for file in files]
        remarks: list[str] = []

        if any(file.startswith("src/bioops/agents/") for file in filenames):
            remarks.append("Agent changes should preserve concise report formatting and safe side-effect behavior.")

        if any(file.startswith("src/bioops/tools/") for file in filenames):
            remarks.append("Tool changes should handle missing configuration and external API errors gracefully.")

        if any(file.startswith("src/bioops/rag/") for file in filenames):
            remarks.append("RAG changes should be tested with ingest plus retrieval queries.")

        return remarks

    def _detect_suggestions(self, files: list[GitHubChangedFile]) -> list[str]:
        filenames = [file.filename for file in files]
        suggestions: list[str] = []

        if any(file.startswith("src/bioops/agents/") for file in filenames):
            suggestions.append("Run orchestrator routing tests for affected agents.")

        if any(file.startswith("src/bioops/tools/") for file in filenames):
            suggestions.append("Add unit tests for success, missing-config, and error paths.")

        if any(file.startswith("src/bioops/rag/") for file in filenames):
            suggestions.append("Re-run RAG ingest and test KnowledgeAgent retrieval.")

        if any(file in {"requirements.txt", "Dockerfile", "docker-compose.yml"} for file in filenames):
            suggestions.append("Run docker compose build bioops and pytest inside Docker.")

        if not any(file.startswith("tests/") for file in filenames):
            suggestions.append("Add or update tests for the changed behavior.")

        return suggestions

    def _review_local_repo(self, repo_path: str) -> str:
        path = Path(repo_path).resolve()

        if not path.exists():
            return (
                "Repository Review Report\n\n"
                "Status: error\n"
                f"Path does not exist: {path}"
            )

        changed_files = self._get_changed_files(path)
        tracked_files = self._get_tracked_files(path)
        python_files = [
            file
            for file in tracked_files
            if file.endswith(".py") and "__pycache__" not in file
        ]
        test_files = [
            file
            for file in tracked_files
            if file.startswith("tests/") and file.endswith(".py")
        ]
        suspicious_files = self._find_suspicious_files(path, tracked_files)
        syntax_result = self._check_python_syntax(path, python_files)

        risks: list[str] = []
        suggestions: list[str] = []

        if suspicious_files:
            risks.append("Suspicious generated/cache/large files are tracked:")
            risks.extend(f" - {file}" for file in suspicious_files[:10])

        if not test_files:
            risks.append("No tests detected under tests/.")

        if changed_files and not any(file.startswith("tests/") for file in changed_files):
            suggestions.append("Consider adding or updating tests for the changed code.")

        lines = [
            "Repository Review Report",
            "",
            "Status: ok",
            f"Path: {path}",
            "",
            "Findings:",
            f"- {len(changed_files)} changed Git-tracked files detected.",
            f"- {len(python_files)} tracked Python files detected.",
            f"- {len(test_files)} tracked test files detected.",
            "",
            "Changed files:",
        ]

        lines.extend(f"- {file}" for file in changed_files[:20]) if changed_files else lines.append("- none")

        lines.extend(["", "Syntax check:", f"- {syntax_result}"])

        lines.extend(["", "Risks:"])
        lines.extend(f"- {item}" for item in risks) if risks else lines.append("- No major deterministic risks detected.")

        lines.extend(["", "Suggestions:"])
        lines.extend(f"- {item}" for item in suggestions) if suggestions else lines.append("- No immediate suggestions.")

        lines.extend(
            [
                "",
                "No repository files were modified.",
                "No GitHub comments were posted.",
            ]
        )

        return "\n".join(lines)

    def _get_changed_files(self, repo_path: Path) -> list[str]:
        result = self._run_git(repo_path, ["status", "--short"])

        if not result:
            return []

        files: list[str] = []
        for line in result.splitlines():
            file_path = line[3:].strip()
            if " -> " in file_path:
                file_path = file_path.split(" -> ", 1)[1]
            files.append(file_path)

        return files

    def _get_tracked_files(self, repo_path: Path) -> list[str]:
        result = self._run_git(repo_path, ["ls-files"])

        if not result:
            return []

        return [line.strip() for line in result.splitlines() if line.strip()]

    def _find_suspicious_files(
        self,
        repo_path: Path,
        tracked_files: list[str],
    ) -> list[str]:
        suspicious: list[str] = []
        patterns = [
            "__pycache__",
            ".pytest_cache",
            ".pyc",
            ".env",
            ".pem",
            ".key",
            "kubectl",
            "minikube-linux-amd64",
        ]

        for file in tracked_files:
            if any(pattern in file for pattern in patterns):
                suspicious.append(file)
                continue

            full_path = repo_path / file
            if full_path.exists() and full_path.is_file():
                try:
                    if full_path.stat().st_size > 20 * 1024 * 1024:
                        suspicious.append(file)
                except OSError:
                    continue

        return suspicious

    def _check_python_syntax(
        self,
        repo_path: Path,
        python_files: list[str],
    ) -> str:
        if not python_files:
            return "no Python files found"

        files_to_check = python_files[:100]

        try:
            result = subprocess.run(
                ["python", "-m", "py_compile", *files_to_check],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except Exception as error:
            return f"failed to run syntax check: {type(error).__name__}: {error}"

        if result.returncode == 0:
            return f"passed for {len(files_to_check)} Python files"

        error_text = result.stderr.strip() or result.stdout.strip()
        return f"failed: {error_text[:500]}"

    def _run_git(self, repo_path: Path, args: list[str]) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except Exception:
            return ""

        if result.returncode != 0:
            return ""

        return result.stdout.strip()