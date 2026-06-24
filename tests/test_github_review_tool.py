from types import SimpleNamespace

from bioops.tools.github_review_tool import GitHubReviewTool


class FakeRequestParser:
    def parse(self, message: str):
        return None


class FakeGithub:
    def __init__(self, repo):
        self.repo = repo

    def get_repo(self, repo_name):
        self.requested_repo_name = repo_name
        return self.repo


class FakeGitHubReviewTool(GitHubReviewTool):
    def __init__(self, repo):
        super().__init__(token="fake-token", request_parser=FakeRequestParser())
        self.fake_github = FakeGithub(repo)

    def _github(self):
        return self.fake_github


def fake_file(
    filename="src/app.py",
    status="modified",
    additions=10,
    deletions=2,
    changes=12,
    patch="@@ fake patch @@",
):
    return SimpleNamespace(
        filename=filename,
        status=status,
        additions=additions,
        deletions=deletions,
        changes=changes,
        patch=patch,
    )


def test_fetch_pull_request_requires_repo_and_pr_number():
    tool = GitHubReviewTool(token="fake-token", request_parser=FakeRequestParser())

    result = tool.fetch_pull_request(repo_name=None, pr_number=None)

    assert result.status == "not configured"
    assert result.repo is None
    assert result.pr_number is None
    assert "repo=<owner/repo> or GitHub PR URL" in result.missing_config
    assert "pr=<number> or GitHub PR URL" in result.missing_config


def test_fetch_pull_request_maps_pr_context_without_network():
    pull = SimpleNamespace(
        title="Add review agent",
        body="Implements GitHub review flow.",
        user=SimpleNamespace(login="mayar"),
        base=SimpleNamespace(ref="main"),
        head=SimpleNamespace(ref="feature/review-agent"),
        get_files=lambda: [
            fake_file(filename="src/bioops/agents/review_agent.py"),
        ],
    )

    repo = SimpleNamespace(get_pull=lambda number: pull)
    tool = FakeGitHubReviewTool(repo)

    result = tool.fetch_pull_request(
        repo_name="Mayaro8/BioOps",
        pr_number=7,
    )

    assert result.status == "ok"
    assert result.repo == "Mayaro8/BioOps"
    assert result.pr_number == 7
    assert result.title == "Add review agent"
    assert result.author == "mayar"
    assert result.base_branch == "main"
    assert result.head_branch == "feature/review-agent"
    assert len(result.changed_files) == 1
    assert result.changed_files[0].filename == "src/bioops/agents/review_agent.py"
    assert result.changed_files[0].status == "modified"
    assert result.changed_files[0].additions == 10
    assert result.changed_files[0].deletions == 2
    assert result.changed_files[0].patch == "@@ fake patch @@"


def test_list_open_pull_requests_requires_repo():
    tool = GitHubReviewTool(token="fake-token", request_parser=FakeRequestParser())

    result = tool.list_open_pull_requests(repo_name=None)

    assert result.status == "not configured"
    assert result.repo is None
    assert result.missing_config == ["repo=<owner/repo> or GitHub repo URL"]


def test_list_open_pull_requests_maps_pr_summaries_without_network():
    pull = SimpleNamespace(
        number=3,
        title="Fix cluster monitor",
        user=SimpleNamespace(login="mayar"),
        base=SimpleNamespace(ref="main"),
        head=SimpleNamespace(ref="feature/cluster-health"),
        changed_files=4,
        additions=40,
        deletions=8,
        html_url="https://github.com/Mayaro8/BioOps/pull/3",
    )

    repo = SimpleNamespace(get_pulls=lambda state: [pull])
    tool = FakeGitHubReviewTool(repo)

    result = tool.list_open_pull_requests(repo_name="Mayaro8/BioOps")

    assert result.status == "ok"
    assert result.repo == "Mayaro8/BioOps"
    assert len(result.pull_requests) == 1

    summary = result.pull_requests[0]
    assert summary.number == 3
    assert summary.title == "Fix cluster monitor"
    assert summary.author == "mayar"
    assert summary.base_branch == "main"
    assert summary.head_branch == "feature/cluster-health"
    assert summary.changed_files == 4
    assert summary.additions == 40
    assert summary.deletions == 8
    assert summary.url == "https://github.com/Mayaro8/BioOps/pull/3"


def test_fetch_repo_overview_requires_repo():
    tool = GitHubReviewTool(token="fake-token", request_parser=FakeRequestParser())

    result = tool.fetch_repo_overview(repo_name=None)

    assert result.status == "not configured"
    assert result.repo is None
    assert result.missing_config == ["repo=<owner/repo> or GitHub repo URL"]


def test_fetch_repo_overview_maps_repo_metadata_without_network():
    repo = SimpleNamespace(
        full_name="Mayaro8/BioOps",
        default_branch="main",
        private=False,
        language="Python",
        description="BioOps multi-agent assistant",
        get_contents=lambda path: [
            SimpleNamespace(path="README.md"),
            SimpleNamespace(path="src"),
        ],
        get_git_tree=lambda branch, recursive: SimpleNamespace(
            tree=[
                SimpleNamespace(path="README.md"),
                SimpleNamespace(path="src/bioops/main.py"),
            ]
        ),
    )

    tool = FakeGitHubReviewTool(repo)

    result = tool.fetch_repo_overview(repo_name="Mayaro8/BioOps")

    assert result.status == "ok"
    assert result.repo == "Mayaro8/BioOps"
    assert result.name == "Mayaro8/BioOps"
    assert result.default_branch == "main"
    assert result.private is False
    assert result.language == "Python"
    assert result.description == "BioOps multi-agent assistant"
    assert result.root_files == ["README.md", "src"]
    assert result.tree_paths == ["README.md", "src/bioops/main.py"]


def test_compare_branches_requires_repo_base_and_head():
    tool = GitHubReviewTool(token="fake-token", request_parser=FakeRequestParser())

    result = tool.compare_branches(repo_name=None, base=None, head=None)

    assert result.status == "not configured"
    assert result.repo is None
    assert result.base is None
    assert result.head is None
    assert "repo=<owner/repo> or GitHub repo URL" in result.missing_config
    assert "base=<branch>" in result.missing_config
    assert "head=<branch>" in result.missing_config


def test_compare_branches_maps_changed_files_without_network():
    comparison = SimpleNamespace(
        total_commits=2,
        ahead_by=2,
        behind_by=0,
        files=[
            fake_file(
                filename="src/bioops/tools/github_review_tool.py",
                status="modified",
                additions=20,
                deletions=5,
                changes=25,
                patch="@@ compare patch @@",
            )
        ],
    )

    repo = SimpleNamespace(compare=lambda base, head: comparison)
    tool = FakeGitHubReviewTool(repo)

    result = tool.compare_branches(
        repo_name="Mayaro8/BioOps",
        base="main",
        head="feature/review-agent",
    )

    assert result.status == "ok"
    assert result.repo == "Mayaro8/BioOps"
    assert result.base == "main"
    assert result.head == "feature/review-agent"
    assert result.commits == 2
    assert result.ahead_by == 2
    assert result.behind_by == 0
    assert len(result.changed_files) == 1
    assert result.changed_files[0].filename == "src/bioops/tools/github_review_tool.py"
    assert result.changed_files[0].patch == "@@ compare patch @@"
