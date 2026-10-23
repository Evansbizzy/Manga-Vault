from __future__ import annotations

import re
from typing import List
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup

from .base import MangaData
from .universal import UniversalHtmlScraper


class MangaReaderScraper(UniversalHtmlScraper):
    name = "mangareader"
    label = "MangaReader"
    base_url = "https://mangareader.to"
    supports_search = True
    supports_url_import = True

    @classmethod
    def can_handle(cls, reference: str) -> bool:
        host = (urlparse(reference).hostname or "").lower()
        return host == "mangareader.to" or host.endswith(".mangareader.to")

    def search(self, query: str) -> List[MangaData]:
        response = self.get(
            f"{self.base_url}/search?keyword={quote_plus(query)}", timeout=15
        )
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        seen = set()

        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "").strip()
            if not re.search(r"/manga/[^/?#]+", urlparse(href).path, re.I):
                continue
            manga_url = urljoin(response.url, href)
            if not self.can_handle(manga_url) or manga_url in seen:
                continue

            image = anchor.select_one("img")
            title = (
                anchor.get("title")
                or (image.get("alt") if image else "")
                or anchor.get_text(" ", strip=True)
            ).strip()
            if not title:
                continue

            cover = ""
            if image:
                cover = image.get("data-src") or image.get("data-lazy-src") or image.get("src") or ""
                cover = urljoin(manga_url, cover)

            seen.add(manga_url)
            results.append(MangaData(
                title=title,
                alt_titles=[],
                author="Unknown",
                artist="Unknown",
                description="",
                cover_url=cover,
                status="unknown",
                source_id=manga_url,
                content_type="manga",
                chapters=[],
            ))

        return results

    def _normalize_url(self, value: str) -> str:
        url = urljoin(self.base_url, value)
        if not self.can_handle(url):
            raise ValueError("URL is not from MangaReader")
        return url

