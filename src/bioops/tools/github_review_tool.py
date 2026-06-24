import os
from dataclasses import dataclass, field

from github import Github
from github.GithubException import GithubException

from bioops.tools.github_request_parser import LLMGitHubRequestParser


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
    path: str | None = None
    error: str | None = None


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

    def __init__(
        self,
        token: str | None = None,
        request_parser: LLMGitHubRequestParser | None = None,
    ):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.request_parser = request_parser or LLMGitHubRequestParser()

    def parse_request(self, message: str) -> GitHubRequest:
        parsed = self.request_parser.parse(message)

        if parsed is None:
            return GitHubRequest(
                mode="parse_error",
                error=(
                    "Could not parse review request with the LLM parser. "
                    "Check Azure OpenAI configuration or rephrase the request."
                ),
            )

        return GitHubRequest(
            mode=parsed["mode"],
            repo=parsed.get("repo"),
            pr_number=parsed.get("pr_number"),
            base=parsed.get("base"),
            head=parsed.get("head"),
            path=parsed.get("path"),
        )

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
