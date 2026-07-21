from __future__ import annotations

import pytest

from bioops.rag.yandex_wiki import (
    YandexWikiClient,
    YandexWikiError,
    YandexWikiPage,
    wiki_pages_to_chunks,
)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls: list[dict] = []

    def get(self, url, *, params, headers, timeout):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeResponse(self.payloads.pop(0))


def test_yandex_wiki_client_fetches_paginated_subtree() -> None:
    session = FakeSession(
        [
            {
                "results": [{"id": 10, "slug": "bioops"}],
                "next_cursor": "next-page",
            },
            {
                "results": [{"id": 11, "slug": "bioops/pipeline"}],
                "next_cursor": "",
            },
            {
                "id": 10,
                "slug": "bioops",
                "title": "BioOps",
                "content": "Company documentation.",
                "attributes": {"modified_at": "2026-07-21T08:00:00Z"},
            },
            {
                "id": 11,
                "slug": "bioops/pipeline",
                "title": "Pipeline",
                "content": "Pipeline documentation.",
                "attributes": {},
            },
        ]
    )
    client = YandexWikiClient(
        token="wiki-token",
        org_id="org-123",
        session=session,
    )

    pages = client.fetch_subtree("bioops")

    assert [page.slug for page in pages] == [
        "bioops",
        "bioops/pipeline",
    ]
    assert session.calls[1]["params"]["cursor"] == "next-page"
    assert session.calls[0]["headers"]["Authorization"] == (
        "OAuth wiki-token"
    )
    assert session.calls[0]["headers"]["X-Org-Id"] == "org-123"
    assert session.calls[2]["params"]["fields"] == "content,attributes"


def test_yandex_wiki_client_requires_read_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "YANDEX_WIKI_TOKEN",
        "YANDEX_WIKI_ORG_ID",
        "YANDEX_WIKI_ROOT_SLUG",
    ):
        monkeypatch.delenv(name, raising=False)

    client = YandexWikiClient(session=FakeSession([]))

    with pytest.raises(YandexWikiError, match="YANDEX_WIKI_TOKEN"):
        client.fetch_subtree("")


def test_wiki_pages_to_chunks_preserves_source_metadata() -> None:
    chunks = wiki_pages_to_chunks(
        [
            YandexWikiPage(
                page_id=42,
                slug="bioops/pipeline",
                title="Pipeline",
                content="The pipeline starts with FASTQ validation.",
                modified_at="2026-07-21T08:00:00Z",
            )
        ],
        web_url="https://wiki.example",
    )

    assert len(chunks) == 1
    assert chunks[0].text.startswith("# Pipeline")
    assert chunks[0].metadata["source_kind"] == "yandex_wiki"
    assert chunks[0].metadata["page_url"] == (
        "https://wiki.example/bioops/pipeline"
    )
