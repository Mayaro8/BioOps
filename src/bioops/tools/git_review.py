from dataclasses import dataclass
from pathlib import Path
import py_compile
import subprocess


@dataclass
class ReviewIssue:
    severity: str
    file: str
    message: str
    suggestion: str


@dataclass
class RepoReview:
    changed_files: list[str]
    diff_text: str
    issues: list[ReviewIssue]


class GitReviewTool:
    """Performs lightweight repository and branch review checks."""

    LARGE_FILE_LIMIT_BYTES = 10 * 1024 * 1024
    MAX_DIFF_CHARS = 20_000

    def review_local_repo(
        self,
        repo_path: str = ".",
        base_ref: str = "main",
    ) -> RepoReview:
        root = Path(repo_path).resolve()

        changed_files = self._get_changed_files(root, base_ref)
        diff_text = self._get_diff_text(root, base_ref)

        issues: list[ReviewIssue] = []

        issues.extend(self._check_tracked_generated_files(root))
        issues.extend(self._check_suspicious_root_files(root))
        issues.extend(self._check_large_files(root))
        issues.extend(self._check_python_files(root, changed_files))
        issues.extend(self._check_review_agent_integration(root))

        return RepoReview(
            changed_files=changed_files,
            diff_text=diff_text,
            issues=issues,
        )

    def _get_changed_files(self, root: Path, base_ref: str) -> list[str]:
        changed_files = set()

        diff_output = self._git(
            root,
            ["diff", "--name-only", f"{base_ref}...HEAD"],
        )

        if not diff_output.strip():
            diff_output = self._git(root, ["diff", "--name-only"])

        for line in diff_output.splitlines():
            file_path = line.strip()
            if file_path:
                changed_files.add(file_path)

        status_output = self._git(root, ["status", "--short"])

        for line in status_output.splitlines():
            if not line.strip():
                continue

            file_path = line[3:].strip()

            if " -> " in file_path:
                file_path = file_path.split(" -> ", 1)[1]

            if file_path:
                changed_files.add(file_path)

        return sorted(changed_files)

    def _get_diff_text(self, root: Path, base_ref: str) -> str:
        diff_text = self._git(root, ["diff", f"{base_ref}...HEAD"])

        if not diff_text.strip():
            diff_text = self._git(root, ["diff"])

        if len(diff_text) > self.MAX_DIFF_CHARS:
            return (
                diff_text[: self.MAX_DIFF_CHARS]
                + "\n\n[Diff truncated because it was too long.]"
            )

        return diff_text

    def _check_python_files(
        self,
        root: Path,
        changed_files: list[str],
    ) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        paths = self._python_paths_to_check(root, changed_files)

        for path in paths:
            relative_path = str(path.relative_to(root))

            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                issues.append(
                    ReviewIssue(
                        severity="medium",
                        file=relative_path,
                        message="Could not read Python file as UTF-8.",
                        suggestion="Check and fix the file encoding.",
                    )
                )
                continue

            lines = text.splitlines()

            if len(lines) == 1 and len(lines[0]) > 300:
                issues.append(
                    ReviewIssue(
                        severity="high",
                        file=relative_path,
                        message=(
                            "Python file appears collapsed into one very long line."
                        ),
                        suggestion=(
                            "Reformat the file with normal line breaks, "
                            "then run pytest."
                        ),
                    )
                )

            for line_number, line in enumerate(lines, start=1):
                if len(line) > 120:
                    issues.append(
                        ReviewIssue(
                            severity="low",
                            file=relative_path,
                            message=(
                                f"Line {line_number} is longer than "
                                "120 characters."
                            ),
                            suggestion="Wrap the line for readability.",
                        )
                    )
                    break

            try:
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as error:
                issues.append(
                    ReviewIssue(
                        severity="high",
                        file=relative_path,
                        message="Python syntax check failed.",
                        suggestion=str(error),
                    )
                )

        return issues

    def _python_paths_to_check(
        self,
        root: Path,
        changed_files: list[str],
    ) -> list[Path]:
        if changed_files:
            paths = [
                root / file_path
                for file_path in changed_files
                if file_path.endswith(".py") and (root / file_path).exists()
            ]
        else:
            paths = list(root.rglob("*.py"))

        return [
            path
            for path in paths
            if ".venv" not in path.parts and "__pycache__" not in path.parts
        ]

    def _check_review_agent_integration(
        self,
        root: Path,
    ) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []

        review_agent_exists = (
            root / "src/bioops/agents/review_agent.py"
        ).exists()

        graph_path = root / "src/bioops/graph_orchestrator.py"
        config_path = root / "configs/agents.yaml"
        test_path = root / "tests/test_review_agent.py"

        if not review_agent_exists:
            return issues

        if graph_path.exists():
            graph_text = graph_path.read_text(encoding="utf-8")

            if "ReviewAgent" not in graph_text or '"review"' not in graph_text:
                issues.append(
                    ReviewIssue(
                        severity="high",
                        file=str(graph_path.relative_to(root)),
                        message=(
                            "ReviewAgent exists but does not appear to be "
                            "routed in the graph orchestrator."
                        ),
                        suggestion=(
                            "Import ReviewAgent, instantiate it, add review "
                            "keywords, add a review node, and route "
                            "selected_agent='review'."
                        ),
                    )
                )

        if config_path.exists():
            config_text = config_path.read_text(encoding="utf-8")

            if "review" not in config_text:
                issues.append(
                    ReviewIssue(
                        severity="medium",
                        file=str(config_path.relative_to(root)),
                        message=(
                            "ReviewAgent exists but no review entry was found "
                            "in agents.yaml."
                        ),
                        suggestion="Add a review agent config entry.",
                    )
                )

        if not test_path.exists():
            issues.append(
                ReviewIssue(
                    severity="high",
                    file="tests/test_review_agent.py",
                    message="ReviewAgent exists but has no dedicated test file.",
                    suggestion=(
                        "Add tests for path extraction, report formatting, "
                        "and review checks."
                    ),
                )
            )

        return issues

    def _check_tracked_generated_files(
        self,
        root: Path,
    ) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        tracked_files = self._git(root, ["ls-files"])

        for file_path in tracked_files.splitlines():
            if "__pycache__" in file_path or file_path.endswith(".pyc"):
                issues.append(
                    ReviewIssue(
                        severity="medium",
                        file=file_path,
                        message="Generated Python cache file is tracked by Git.",
                        suggestion=(
                            "Remove it with git rm and keep __pycache__/ "
                            "in .gitignore."
                        ),
                    )
                )

        return issues

    def _check_suspicious_root_files(
        self,
        root: Path,
    ) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []

        suspicious_files = [
            "requirements.txt",
            "kubectl",
            "minikube-linux-amd64",
        ]

        for file_name in suspicious_files:
            if (root / file_name).exists():
                issues.append(
                    ReviewIssue(
                        severity="medium",
                        file=file_name,
                        message="Suspicious root-level file exists.",
                        suggestion=(
                            "Delete it if it is not intentionally part of "
                            "the repository."
                        ),
                    )
                )

        return issues

    def _check_large_files(
        self,
        root: Path,
    ) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []

        for path in root.iterdir():
            if not path.is_file():
                continue

            size_bytes = path.stat().st_size

            if size_bytes > self.LARGE_FILE_LIMIT_BYTES:
                size_mb = round(size_bytes / 1024 / 1024, 2)

                issues.append(
                    ReviewIssue(
                        severity="high",
                        file=path.name,
                        message=(
                            f"Large file detected in repo root: {size_mb} MB."
                        ),
                        suggestion=(
                            "Remove large binaries from Git and add them "
                            "to .gitignore."
                        ),
                    )
                )

        return issues

    def _git(self, root: Path, args: list[str]) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=root,
                check=False,
                text=True,
                capture_output=True,
            )
        except FileNotFoundError:
            return ""

        if result.returncode != 0:
            return ""

        return result.stdout