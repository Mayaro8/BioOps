import os
import re
from dataclasses import dataclass, field

from github import Github
from github.GithubException import GithubException


@dataclass
class GitHubChangedFile:
    filename: str
    status: str
    additions: int
    deletions: int
    changes: int
    patch: str = ""


@dataclass
class GitHubPullRequestSummary:
    number: int
    title: str
    author: str
    base_branch: str
    head_branch: str
    changed_files: int
    additions: int
    deletions: int
    url: str


@dataclass
class GitHubRequest:
    mode: str
    repo: str | None = None
    pr_number: int | None = None
    base: str | None = None
    head: str | None = None


@dataclass
class GitHubPullRequestContext:
    status: str
    repo: str | None
    pr_number: int | None
    title: str = ""
    body: str = ""
    author: str = ""
    base_branch: str = ""
    head_branch: str = ""
    changed_files: list[GitHubChangedFile] = field(default_factory=list)
    missing_config: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class GitHubOpenPullRequestsContext:
    status: str
    repo: str | None
    pull_requests: list[GitHubPullRequestSummary] = field(default_factory=list)
    missing_config: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class GitHubRepoOverviewContext:
    status: str
    repo: str | None
    name: str = ""
    default_branch: str = ""
    private: bool = False
    language: str = ""
    description: str = ""
    root_files: list[str] = field(default_factory=list)
    tree_paths: list[str] = field(default_factory=list)
    missing_config: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class GitHubBranchCompareContext:
    status: str
    repo: str | None
    base: str | None
    head: str | None
    commits: int = 0
    ahead_by: int = 0
    behind_by: int = 0
    changed_files: list[GitHubChangedFile] = field(default_factory=list)
    missing_config: list[str] = field(default_factory=list)
    error: str | None = None


class GitHubReviewTool:
    """
    Read-only GitHub tool for ReviewAgent.

    Supported modes:
    - repo overview: repo=owner/repo
    - open PR listing: check open PRs repo=owner/repo
    - PR review: repo=owner/repo pr=12
    - branch compare: repo=owner/repo base=main head=feature/x

    This tool does not post comments, approve, merge, close, or modify GitHub.
    """

    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("GITHUB_TOKEN")

    def parse_request(self, message: str) -> GitHubRequest:
        repo = self._parse_repo(message)
        pr_number = self._parse_pr_number(message)
        base = self._parse_key(message, "base")
        head = self._parse_key(message, "head")

        lowered = message.lower()

        if repo and pr_number is not None:
            return GitHubRequest(mode="pr", repo=repo, pr_number=pr_number)

        if repo and base and head:
            return GitHubRequest(mode="compare", repo=repo, base=base, head=head)

        if repo and self._asks_for_open_prs(lowered):
            return GitHubRequest(mode="open_prs", repo=repo)

        if repo:
            return GitHubRequest(mode="repo", repo=repo)

        return GitHubRequest(mode="local")

    def fetch_pull_request(
        self,
        repo_name: str | None,
        pr_number: int | None,
    ) -> GitHubPullRequestContext:
        missing_config = self._missing_repo_pr(repo_name, pr_number)

        if missing_config:
            return GitHubPullRequestContext(
                status="not configured",
                repo=repo_name,
                pr_number=pr_number,
                missing_config=missing_config,
            )

        try:
            repo = self._github().get_repo(repo_name)
            pull = repo.get_pull(pr_number)

            changed_files = [
                GitHubChangedFile(
                    filename=file.filename,
                    status=file.status,
                    additions=file.additions,
                    deletions=file.deletions,
                    changes=file.changes,
                    patch=file.patch or "",
                )
                for file in pull.get_files()
            ]

            return GitHubPullRequestContext(
                status="ok",
                repo=repo_name,
                pr_number=pr_number,
                title=pull.title or "",
                body=pull.body or "",
                author=pull.user.login if pull.user else "",
                base_branch=pull.base.ref if pull.base else "",
                head_branch=pull.head.ref if pull.head else "",
                changed_files=changed_files,
            )

        except GithubException as error:
            return GitHubPullRequestContext(
                status="error",
                repo=repo_name,
                pr_number=pr_number,
                error=self._format_github_error(error),
            )

    def list_open_pull_requests(
        self,
        repo_name: str | None,
    ) -> GitHubOpenPullRequestsContext:
        if not repo_name:
            return GitHubOpenPullRequestsContext(
                status="not configured",
                repo=repo_name,
                missing_config=["repo=<owner/repo> or GitHub repo URL"],
            )

        try:
            repo = self._github().get_repo(repo_name)

            pull_requests: list[GitHubPullRequestSummary] = []
            for pull in repo.get_pulls(state="open"):
                pull_requests.append(
                    GitHubPullRequestSummary(
                        number=pull.number,
                        title=pull.title or "",
                        author=pull.user.login if pull.user else "",
                        base_branch=pull.base.ref if pull.base else "",
                        head_branch=pull.head.ref if pull.head else "",
                        changed_files=int(getattr(pull, "changed_files", 0) or 0),
                        additions=int(getattr(pull, "additions", 0) or 0),
                        deletions=int(getattr(pull, "deletions", 0) or 0),
                        url=pull.html_url or "",
                    )
                )

            return GitHubOpenPullRequestsContext(
                status="ok",
                repo=repo_name,
                pull_requests=pull_requests,
            )

        except GithubException as error:
            return GitHubOpenPullRequestsContext(
                status="error",
                repo=repo_name,
                error=self._format_github_error(error),
            )

    def fetch_repo_overview(
        self,
        repo_name: str | None,
    ) -> GitHubRepoOverviewContext:
        if not repo_name:
            return GitHubRepoOverviewContext(
                status="not configured",
                repo=repo_name,
                missing_config=["repo=<owner/repo> or GitHub repo URL"],
            )

        try:
            repo = self._github().get_repo(repo_name)

            root_files: list[str] = []
            for item in repo.get_contents(""):
                root_files.append(item.path)

            tree_paths: list[str] = []
            try:
                tree = repo.get_git_tree(repo.default_branch, recursive=True)
                tree_paths = [
                    item.path
                    for item in tree.tree
                    if item.path
                ]
            except GithubException:
                tree_paths = root_files

            return GitHubRepoOverviewContext(
                status="ok",
                repo=repo_name,
                name=repo.full_name,
                default_branch=repo.default_branch or "",
                private=bool(repo.private),
                language=repo.language or "",
                description=repo.description or "",
                root_files=root_files,
                tree_paths=tree_paths,
            )

        except GithubException as error:
            return GitHubRepoOverviewContext(
                status="error",
                repo=repo_name,
                error=self._format_github_error(error),
            )

    def compare_branches(
        self,
        repo_name: str | None,
        base: str | None,
        head: str | None,
    ) -> GitHubBranchCompareContext:
        missing_config: list[str] = []

        if not repo_name:
            missing_config.append("repo=<owner/repo> or GitHub repo URL")

        if not base:
            missing_config.append("base=<branch>")

        if not head:
            missing_config.append("head=<branch>")

        if missing_config:
            return GitHubBranchCompareContext(
                status="not configured",
                repo=repo_name,
                base=base,
                head=head,
                missing_config=missing_config,
            )

        try:
            repo = self._github().get_repo(repo_name)
            comparison = repo.compare(base, head)

            changed_files = [
                GitHubChangedFile(
                    filename=file.filename,
                    status=file.status,
                    additions=file.additions,
                    deletions=file.deletions,
                    changes=file.changes,
                    patch=file.patch or "",
                )
                for file in comparison.files
            ]

            return GitHubBranchCompareContext(
                status="ok",
                repo=repo_name,
                base=base,
                head=head,
                commits=int(getattr(comparison, "total_commits", 0) or 0),
                ahead_by=int(getattr(comparison, "ahead_by", 0) or 0),
                behind_by=int(getattr(comparison, "behind_by", 0) or 0),
                changed_files=changed_files,
            )

        except GithubException as error:
            return GitHubBranchCompareContext(
                status="error",
                repo=repo_name,
                base=base,
                head=head,
                error=self._format_github_error(error),
            )

    def _github(self) -> Github:
        if self.token:
            return Github(self.token)

        return Github()

    def _parse_repo(self, message: str) -> str | None:
        repo_match = re.search(
            r"repo=([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
            message,
        )
        if repo_match:
            return repo_match.group(1).removesuffix(".git")

        github_url_match = re.search(
            r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
            message,
        )
        if github_url_match:
            return github_url_match.group(1).removesuffix(".git")

        return None

    def _parse_pr_number(self, message: str) -> int | None:
        pr_match = re.search(
            r"(?:pr|pull_request|pull-request)=#?(\d+)",
            message,
            flags=re.IGNORECASE,
        )
        if pr_match:
            return int(pr_match.group(1))

        github_url_match = re.search(
            r"github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/(\d+)",
            message,
            flags=re.IGNORECASE,
        )
        if github_url_match:
            return int(github_url_match.group(1))

        plain_match = re.search(r"\bpr\s+#?(\d+)\b", message.lower())
        if plain_match:
            return int(plain_match.group(1))

        return None

    def _parse_key(self, message: str, key: str) -> str | None:
        match = re.search(rf"\b{key}=([^\s]+)", message)
        if not match:
            return None

        return match.group(1)

    def _asks_for_open_prs(self, lowered: str) -> bool:
        phrases = [
            "open prs",
            "open pr",
            "open pull requests",
            "pull requests",
            "list prs",
            "list pr",
            "check prs",
            "check pr",
        ]

        return any(phrase in lowered for phrase in phrases)

    def _missing_repo_pr(
        self,
        repo_name: str | None,
        pr_number: int | None,
    ) -> list[str]:
        missing: list[str] = []

        if not repo_name:
            missing.append("repo=<owner/repo> or GitHub PR URL")

        if pr_number is None:
            missing.append("pr=<number> or GitHub PR URL")

        return missing

    def _format_github_error(self, error: GithubException) -> str:
        return f"{error.status}: {error.data}"
