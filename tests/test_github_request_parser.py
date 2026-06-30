from bioops.tools.github_review_tool import GitHubReviewTool


class FakeRequestParser:
    def __init__(self, result):
        self.result = result

    def parse(self, message: str):
        return self.result


def test_llm_parser_selects_open_prs_for_ambiguous_plural_request():
    tool = GitHubReviewTool(
        request_parser=FakeRequestParser(
            {
                "mode": "open_prs",
                "repo": "Mayaro8/BioOps",
                "pr_number": None,
                "base": None,
                "head": None,
                "path": None,
            }
        )
    )

    request = tool.parse_request("review pull requests in repo=Mayaro8/BioOps")

    assert request.mode == "open_prs"
    assert request.repo == "Mayaro8/BioOps"


def test_llm_parser_selects_specific_pr_when_number_is_present():
    tool = GitHubReviewTool(
        request_parser=FakeRequestParser(
            {
                "mode": "pr",
                "repo": "Mayaro8/BioOps",
                "pr_number": 12,
                "base": None,
                "head": None,
                "path": None,
            }
        )
    )

    request = tool.parse_request("review PR 12 in repo=Mayaro8/BioOps")

    assert request.mode == "pr"
    assert request.repo == "Mayaro8/BioOps"
    assert request.pr_number == 12


def test_no_regex_fallback_when_llm_parser_is_unavailable():
    tool = GitHubReviewTool(request_parser=FakeRequestParser(None))

    request = tool.parse_request("review repo=Mayaro8/BioOps pr=12")

    assert request.mode == "parse_error"
    assert request.error is not None


def test_llm_parser_can_select_local_path_review():
    tool = GitHubReviewTool(
        request_parser=FakeRequestParser(
            {
                "mode": "local",
                "repo": None,
                "pr_number": None,
                "base": None,
                "head": None,
                "path": "/app",
            }
        )
    )

    request = tool.parse_request("review my local repository at /app")

    assert request.mode == "local"
    assert request.path == "/app"
