from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from bioops.rag.chunking import chunk_text
from bioops.rag.schemas import KnowledgeChunk


DEFAULT_API_URL = "https://api.wiki.yandex.net/v1"
DEFAULT_WEB_URL = "https://wiki.yandex.com"


class YandexWikiError(RuntimeError):
    """Raised when Yandex Wiki configuration or retrieval fails."""


@dataclass(frozen=True)
class YandexWikiPage:
    page_id: int
    slug: str
    title: str
    content: str
    modified_at: str = ""


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


class YandexWikiClient:
    """Read one accessible Yandex Wiki page subtree through the public API."""

    def __init__(
        self,
        *,
        token: str | None = None,
        org_id: str | None = None,
        org_header: str | None = None,
        auth_scheme: str | None = None,
        api_url: str | None = None,
        web_url: str | None = None,
        timeout_seconds: float | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.token = token or os.getenv("YANDEX_WIKI_TOKEN", "")
        self.org_id = org_id or os.getenv("YANDEX_WIKI_ORG_ID", "")
        self.org_header = org_header or os.getenv(
            "YANDEX_WIKI_ORG_HEADER",
            "X-Org-Id",
        )
        self.auth_scheme = auth_scheme or os.getenv(
            "YANDEX_WIKI_AUTH_SCHEME",
            "OAuth",
        )
        self.api_url = (
            api_url or os.getenv("YANDEX_WIKI_API_URL", DEFAULT_API_URL)
        ).rstrip("/")
        self.web_url = (
            web_url or os.getenv("YANDEX_WIKI_WEB_URL", DEFAULT_WEB_URL)
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds or float(
            os.getenv("YANDEX_WIKI_TIMEOUT_SECONDS", "15")
        )
        self.session = session or requests.Session()

    def fetch_subtree(
        self,
        root_slug: str,
        *,
        max_pages: int = 1000,
    ) -> list[YandexWikiPage]:
        self._validate(root_slug)

        summaries = self._list_descendants(
            root_slug=root_slug,
            max_pages=max_pages,
        )
        pages: list[YandexWikiPage] = []

        for summary in summaries:
            page_id = summary.get("id")

            if page_id is None:
                continue

            details = self._get_json(
                f"/pages/{page_id}",
                params={"fields": "content,attributes"},
            )
            attributes = details.get("attributes", {}) or {}
            pages.append(
                YandexWikiPage(
                    page_id=int(details.get("id", page_id)),
                    slug=str(
                        details.get("slug")
                        or summary.get("slug")
                        or ""
                    ),
                    title=str(details.get("title") or "Untitled page"),
                    content=str(details.get("content") or ""),
                    modified_at=str(attributes.get("modified_at") or ""),
                )
            )

        return pages

    def _list_descendants(
        self,
        *,
        root_slug: str,
        max_pages: int,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor = ""
        seen_cursors: set[str] = set()

        while len(results) < max_pages:
            params: dict[str, Any] = {
                "slug": root_slug,
                "include_self": "true",
                "actuality": "actual",
                "page_size": min(100, max_pages - len(results)),
            }

            if cursor:
                params["cursor"] = cursor

            payload = self._get_json(
                "/pages/descendants",
                params=params,
            )
            batch = payload.get("results", []) or []

            if not isinstance(batch, list):
                raise YandexWikiError(
                    "Yandex Wiki descendants response has invalid results."
                )

            results.extend(
                item for item in batch if isinstance(item, dict)
            )

            next_cursor = str(payload.get("next_cursor") or "")

            if not next_cursor:
                break
            if next_cursor in seen_cursors:
                raise YandexWikiError(
                    "Yandex Wiki descendants pagination repeated a cursor."
                )

            seen_cursors.add(next_cursor)
            cursor = next_cursor

        return results[:max_pages]

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = self.session.get(
                f"{self.api_url}{path}",
                params=params,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise YandexWikiError(
                f"Yandex Wiki request failed: {error}"
            ) from error
        except ValueError as error:
            raise YandexWikiError(
                "Yandex Wiki returned invalid JSON."
            ) from error

        if not isinstance(payload, dict):
            raise YandexWikiError(
                "Yandex Wiki returned an unexpected response."
            )

        return payload

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"{self.auth_scheme} {self.token}",
            self.org_header: self.org_id,
            "Accept": "application/json",
            "User-Agent": "BioOps-Knowledge-Agent/1.0",
        }

    def _validate(self, root_slug: str) -> None:
        missing = []

        if not self.token:
            missing.append("YANDEX_WIKI_TOKEN")
        if not self.org_id:
            missing.append("YANDEX_WIKI_ORG_ID")
        if not root_slug.strip():
            missing.append("YANDEX_WIKI_ROOT_SLUG")
        if self.org_header not in {"X-Org-Id", "X-Cloud-Org-Id"}:
            raise YandexWikiError(
                "YANDEX_WIKI_ORG_HEADER must be X-Org-Id or X-Cloud-Org-Id."
            )
        if self.auth_scheme not in {"OAuth", "Bearer"}:
            raise YandexWikiError(
                "YANDEX_WIKI_AUTH_SCHEME must be OAuth or Bearer."
            )

        if missing:
            raise YandexWikiError(
                "Missing Yandex Wiki configuration: " + ", ".join(missing)
            )


def wiki_pages_to_chunks(
    pages: list[YandexWikiPage],
    *,
    web_url: str = DEFAULT_WEB_URL,
) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    base_url = web_url.rstrip("/")

    for page in pages:
        text = f"# {page.title}\n\n{page.content}".strip()

        if not page.content.strip():
            continue

        page_chunks = chunk_text(
            text=text,
            source=f"yandex-wiki:{page.slug}",
        )

        for chunk in page_chunks:
            chunk.metadata.update(
                {
                    "source_kind": "yandex_wiki",
                    "page_id": page.page_id,
                    "page_slug": page.slug,
                    "page_title": page.title,
                    "page_url": f"{base_url}/{page.slug.lstrip('/')}",
                    "modified_at": page.modified_at,
                }
            )

        chunks.extend(page_chunks)

    return chunks
