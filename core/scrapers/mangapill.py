from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup

from .base import BaseScraper, ChapterData, MangaData


class MangaPillScraper(BaseScraper):
    """Scraper for mangapill.com — a reliable manga aggregator."""

    name = "mangapill"
    label = "MangaPill"
    base_url = "https://mangapill.com"
    supports_search = True
    supports_url_import = True

    _number_re = re.compile(r"(\d+(?:\.\d+)?)")

    @classmethod
    def can_handle(cls, reference: str) -> bool:
        return "mangapill.com" in reference.lower()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> List[MangaData]:
        url = f"{self.base_url}/search?q={quote_plus(query)}"
        resp = self.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        results: List[MangaData] = []

        # Each search result is a grid item with a link to /manga/<id>/...
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if not href.startswith("/manga/") or href.count("/") < 3:
                continue
            # This anchor wraps an image + title
            img = anchor.find("img")
            cover = ""
            if img:
                cover = img.get("data-src") or img.get("src") or ""
                if cover and not cover.startswith("http"):
                    cover = urljoin(self.base_url, cover)

            # Prefer img alt text — it's the cleanest source of the title.
            # The sibling div concatenates title+type+year+genres into one string.
            title = ""
            if img:
                title = img.get("alt", "").strip()
            if not title:
                title_div = anchor.find_next_sibling()
                if title_div:
                    # May contain extra info; grab first text child or first <a>
                    first_a = title_div.find("a")
                    if first_a:
                        title = first_a.get_text(strip=True)
                    else:
                        # Use first line only
                        title = title_div.get_text(strip=True).split("\n")[0]
            if not title:
                title = anchor.get("title") or "Untitled"

            full_url = urljoin(self.base_url, href)

            results.append(
                MangaData(
                    title=title,
                    alt_titles=[],
                    author="Unknown",
                    artist="Unknown",
                    description="",
                    cover_url=cover,
                    status="unknown",
                    source_id=full_url,
                    content_type="manga",
                    chapters=[],
                )
            )

        # Deduplicate by source_id
        seen = set()
        deduped = []
        for m in results:
            if m.source_id not in seen:
                seen.add(m.source_id)
                deduped.append(m)

        return deduped

    # ------------------------------------------------------------------
    # Details
    # ------------------------------------------------------------------

    def get_manga_details(self, source_id: str) -> MangaData:
        url = self._to_full_url(source_id)
        resp = self.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Title
        h1 = soup.select_one("h1")
        title = h1.get_text(strip=True) if h1 else "Untitled"

        # Cover
        og_img = soup.select_one('meta[property="og:image"]')
        cover_url = og_img["content"] if og_img and og_img.get("content") else ""
        if cover_url and not cover_url.startswith("http"):
            cover_url = urljoin(url, cover_url)

        # Description
        og_desc = soup.select_one('meta[property="og:description"], meta[name="description"]')
        description = og_desc["content"] if og_desc and og_desc.get("content") else ""

        # Metadata (Type, Status, Year, Genres)
        status = "unknown"
        content_type = "manga"
        author = "Unknown"
        page_text = soup.get_text(" ", strip=True).lower()

        # Extract status and type from the info section
        for div in soup.find_all("div"):
            text = div.get_text(" ", strip=True)
            if text.startswith("Status") and len(text) < 50:
                status = text.replace("Status", "").strip().lower()
            elif text.startswith("Type") and len(text) < 50:
                t = text.replace("Type", "").strip().lower()
                if "manhwa" in t:
                    content_type = "manhwa"
                elif "manhua" in t:
                    content_type = "manhua"
                elif "webtoon" in t or "long strip" in t:
                    content_type = "webtoon"

        # Extract author from the info row
        for a_tag in soup.find_all("a", href=True):
            if "/author/" in a_tag["href"]:
                author = a_tag.get_text(strip=True)
                break

        # Chapters
        chapters = self._extract_chapters(soup)

        return MangaData(
            title=title,
            alt_titles=[],
            author=author,
            artist=author,
            description=description,
            cover_url=cover_url,
            status=status,
            source_id=url,
            content_type=content_type,
            chapters=chapters,
        )

    # ------------------------------------------------------------------
    # Chapter pages
    # ------------------------------------------------------------------

    def get_chapter_pages(self, chapter_url: str) -> List[str]:
        url = self._to_full_url(chapter_url)
        resp = self.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        pages: List[str] = []
        for img in soup.find_all("img"):
            src = img.get("data-src") or img.get("src") or ""
            if not src:
                continue
            full = urljoin(url, src.strip())
            # MangaPill CDN images contain /file/mangap/ or are numbered chapter pages
            parsed = urlparse(full)
            path_lower = parsed.path.lower()
            if any(k in full.lower() for k in ["mangap", "chapter", "/file/"]):
                if full not in pages:
                    pages.append(full)
            elif path_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")):
                # Numbered page images
                if full not in pages:
                    pages.append(full)

        return pages

    def _referer_for_url(self, url: str) -> str:
        """MangaPill CDN needs mangapill.com as referer."""
        return f"{self.base_url}/"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_chapters(self, soup: BeautifulSoup) -> List[ChapterData]:
        chapters: List[ChapterData] = []
        seen = set()

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "/chapters/" not in href:
                continue
            full_url = urljoin(self.base_url, href)
            if full_url in seen:
                continue
            seen.add(full_url)

            text = a_tag.get_text(strip=True)
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

    def _extract_number(self, text: str) -> Optional[str]:
        # Try "Chapter X" pattern first
        match = re.search(r"Chapter\s+(\d+(?:\.\d+)?)", text, re.I)
        if match:
            return match.group(1)
        match = self._number_re.search(text or "")
        return match.group(1) if match else None

    def _extract_volume(self, text: str) -> Optional[str]:
        match = re.search(r"(?:vol(?:ume)?\.?\s*)(\d+(?:\.\d+)?)", text or "", re.I)
        return match.group(1) if match else None

    def _to_full_url(self, source_id: str) -> str:
        if source_id.startswith("http"):
            return source_id
        return f"{self.base_url}{source_id}"
