from __future__ import annotations

"""
MangaKakalot / MangaNato / MangaNelo scraper.

NOTE: As of mid-2026 the original mangakakalot.com and manganato.com domains
redirect to parked/dead pages.  This scraper is kept as a best-effort
implementation that can be revived if the sites come back, but the primary
HTML-based aggregator source is now MangaPill (see mangapill.py).

The scraper still *can_handle* old URLs so that previously-imported manga
records still resolve, and its search falls back gracefully to empty results
when the site is unreachable.
"""

import re
from typing import List, Optional
from urllib.parse import quote_plus, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from .base import BaseScraper, ChapterData, MangaData


class MangaKakalotScraper(BaseScraper):
    name = "mangakakalot"
    label = "MangaKakalot (legacy)"
    supports_search = True
    supports_url_import = True

    _chapter_hint_re = re.compile(
        r"(chapter|chap\.?|episode|read|vol(?:ume)?\.?)", re.I
    )
    _number_re = re.compile(r"(\d+(?:\.\d+)?)")

    @classmethod
    def can_handle(cls, reference: str) -> bool:
        lowered = reference.lower()
        return any(
            domain in lowered
            for domain in ("mangakakalot", "manganato", "manganelo", "chapmanganato")
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> List[MangaData]:
        """Try to search mangakakalot.com.  Returns [] if the site is dead."""
        url = f"https://mangakakalot.com/search/story/{quote_plus(query)}"
        try:
            resp = self.get(url, timeout=10)
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results: List[MangaData] = []

        # Old selectors — may work if the site ever returns to its old design
        for node in soup.select(
            ".story_item, .item, .list-truyen-item-wrap, "
            ".search-story-item, .panel_story_list .story_item"
        ):
            anchor = node.select_one("a[href]")
            if not anchor:
                continue
            manga_url = urljoin(url, anchor.get("href"))
            title = self._clean_text(
                node.select_one(".story_name, .item_title, h3, h3 a") or anchor
            )
            cover = node.select_one("img")
            cover_url = (
                urljoin(url, cover.get("src") or cover.get("data-src"))
                if cover
                else ""
            )
            results.append(
                MangaData(
                    title=title or "Untitled",
                    alt_titles=[],
                    author=self._extract_meta_value(node, "author"),
                    artist=self._extract_meta_value(node, "artist"),
                    description="",
                    cover_url=cover_url,
                    status="unknown",
                    source_id=self._normalize_url(manga_url),
                    content_type="manga",
                    chapters=[],
                )
            )

        return results

    # ------------------------------------------------------------------
    # Details
    # ------------------------------------------------------------------

    def get_manga_details(self, source_id: str) -> MangaData:
        url = self._normalize_url(source_id)
        resp = self.get(url, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        if self._looks_like_chapter_page(url, soup):
            title = self._page_title(soup, default="Untitled")
            chapter_number = self._extract_number(title) or "1"
            return MangaData(
                title=title,
                alt_titles=[],
                author="Unknown",
                artist="Unknown",
                description="",
                cover_url=self._cover_url(soup, url),
                status="unknown",
                source_id=url,
                content_type="manga",
                chapters=[
                    ChapterData(
                        number=chapter_number,
                        title=title,
                        volume=None,
                        source_url=url,
                    )
                ],
            )

        title = self._page_title(soup, default="Untitled")
        description = self._meta_content(soup, "description")
        cover_url = self._cover_url(soup, url)
        author = self._extract_meta_value(soup, "author") or "Unknown"
        chapters = self._extract_chapter_links(soup, url)

        return MangaData(
            title=title,
            alt_titles=[],
            author=author,
            artist=author,
            description=description,
            cover_url=cover_url,
            status="unknown",
            source_id=url,
            content_type="manga",
            chapters=chapters,
        )

    # ------------------------------------------------------------------
    # Chapter pages
    # ------------------------------------------------------------------

    def get_chapter_pages(self, chapter_url: str) -> List[str]:
        url = self._normalize_url(chapter_url)
        pages: List[str] = []
        visited = set()
        current = url

        for _ in range(250):
            if current in visited:
                break
            visited.add(current)

            try:
                resp = self.get(current, timeout=15)
            except Exception:
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            for img in soup.select(
                ".container-chapter-reader img, #vungdoc img, "
                "img[itemprop='image'], .reading-content img, img"
            ):
                candidate = (
                    img.get("data-src")
                    or img.get("data-original")
                    or img.get("src")
                )
                if not candidate:
                    continue
                candidate = urljoin(current, candidate.strip())
                if self._looks_like_image(candidate) and candidate not in pages:
                    pages.append(candidate)

            next_url = self._find_next_page(soup, current)
            if not next_url or next_url in visited:
                break
            current = next_url

        return pages

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_chapter_links(
        self, soup: BeautifulSoup, base_url: str
    ) -> List[ChapterData]:
        chapters: List[ChapterData] = []
        seen = set()
        for anchor in soup.select(
            ".chapter-list a[href], .row-content-chapter a[href], "
            "a.chapter-name[href], a[href*='chapter']"
        ):
            href = anchor.get("href")
            if not href:
                continue
            full_url = self._normalize_url(urljoin(base_url, href))
            if full_url in seen:
                continue
            text = self._clean_text(anchor)
            if not self._looks_like_chapter_link(text + " " + full_url):
                continue
            seen.add(full_url)
            number = self._extract_number(text) or str(len(chapters) + 1)
            volume = self._extract_volume(text)
            chapters.append(
                ChapterData(
                    number=number,
                    title=text or f"Chapter {number}",
                    volume=volume,
                    source_url=full_url,
                )
            )
        return chapters

    def _looks_like_chapter_page(self, url: str, soup: BeautifulSoup) -> bool:
        if "chapter" in url.lower():
            return True
        return bool(
            soup.select(".container-chapter-reader img, #vungdoc img, .reading-content img")
        )

    def _find_next_page(
        self, soup: BeautifulSoup, base_url: str
    ) -> Optional[str]:
        for selector in (
            "a.next",
            "a[rel='next']",
            "a.next-page",
            ".next a",
            "a[title*='Next' i]",
        ):
            node = soup.select_one(selector)
            if node and node.get("href"):
                return self._normalize_url(urljoin(base_url, node["href"]))
        return None

    def _page_title(self, soup: BeautifulSoup, default: str = "") -> str:
        for selector in ('meta[property="og:title"]', "h1", "title"):
            node = soup.select_one(selector)
            if not node:
                continue
            value = (
                node.get("content")
                if node.name == "meta"
                else node.get_text(" ", strip=True)
            )
            if value:
                return value
        return default

    def _meta_content(self, soup: BeautifulSoup, name: str) -> str:
        node = soup.select_one(
            f'meta[name="{name}"], meta[property="og:{name}"]'
        )
        return node.get("content", "") if node else ""

    def _cover_url(self, soup: BeautifulSoup, base_url: str) -> str:
        node = soup.select_one(
            'meta[property="og:image"], meta[name="twitter:image"]'
        )
        if node and node.get("content"):
            return urljoin(base_url, node["content"])
        image = soup.select_one(
            ".panel-story-info img, .info-image img, img"
        )
        if image and image.get("src"):
            return urljoin(base_url, image["src"])
        return ""

    def _extract_meta_value(self, node: BeautifulSoup, key: str) -> str:
        meta = node.select_one(
            f'.{key}, [data-{key}], [data-type="{key}"]'
        )
        if meta:
            return self._clean_text(meta)
        return ""

    def _clean_text(self, node) -> str:
        if node is None:
            return ""
        return (
            " ".join(node.stripped_strings)
            if hasattr(node, "stripped_strings")
            else str(node).strip()
        )

    def _extract_number(self, text: str) -> Optional[str]:
        match = self._number_re.search(text or "")
        return match.group(1) if match else None

    def _extract_volume(self, text: str) -> Optional[str]:
        match = re.search(
            r"(?:vol(?:ume)?\.?\s*)(\d+(?:\.\d+)?)", text or "", re.I
        )
        return match.group(1) if match else None

    def _looks_like_chapter_link(self, text: str) -> bool:
        lowered = text.lower()
        return bool(self._chapter_hint_re.search(lowered)) and not any(
            blocked in lowered
            for blocked in ("login", "register", "privacy", "terms", "contact")
        )

    def _looks_like_image(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.path.lower().endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif")
        )

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
        )
