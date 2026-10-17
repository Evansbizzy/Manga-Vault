from __future__ import annotations

import logging
import random
import re
import time
from typing import List, Optional
from urllib.parse import quote_plus

from .base import BaseScraper, ChapterData, MangaData

logger = logging.getLogger(__name__)


class ComickScraper(BaseScraper):
    """
    Scraper for Comick.io — uses the public JSON API.

    API base: https://api.comick.io
    Endpoints:
        - Search:   GET /v1.0/search?q=<query>&limit=25&page=1
        - Details:  GET /comic/<slug>  (returns manga info)
        - Chapters: GET /comic/<hid>/chapters?lang=en&limit=300
        - Pages:    GET /chapter/<hid>  (returns chapter with images)
    """

    name = "comick"
    label = "Comick.io"
    base_url = "https://comick.io"
    api_base = "https://api.comick.io"
    supports_search = True
    supports_url_import = True

    _slug_re = re.compile(r"comick\.(?:io|app)/comic/([^/]+)")

    @classmethod
    def can_handle(cls, reference: str) -> bool:
        return "comick.io" in reference.lower() or "comick.app" in reference.lower()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> List[MangaData]:
        url = f"{self.api_base}/v1.0/search?q={quote_plus(query)}&limit=25&page=1"
        resp = self._api_get(url)
        results: List[MangaData] = []

        for item in resp:
            md_covers = item.get("md_covers") or []
            cover_url = ""
            if md_covers:
                b2key = md_covers[0].get("b2key", "")
                if b2key:
                    cover_url = f"https://meo.comick.pictures/{b2key}"

            slug = item.get("slug", "")
            content_type = self._detect_type(item)

            results.append(
                MangaData(
                    title=item.get("title") or item.get("slug") or "Untitled",
                    alt_titles=[],
                    author=", ".join(
                        a.get("name", "") for a in (item.get("md_authors") or [])
                    ) or "Unknown",
                    artist="Unknown",
                    description=item.get("desc") or "",
                    cover_url=cover_url,
                    status=self._map_status(item.get("status")),
                    source_id=f"{self.base_url}/comic/{slug}",
                    content_type=content_type,
                    chapters=[],
                )
            )

        return results

    # ------------------------------------------------------------------
    # Details
    # ------------------------------------------------------------------

    def get_manga_details(self, source_id: str) -> MangaData:
        slug = self._extract_slug(source_id)
        url = f"{self.api_base}/comic/{slug}"
        data = self._api_get(url)
        comic = data.get("comic", data)

        md_covers = comic.get("md_covers") or []
        cover_url = ""
        if md_covers:
            b2key = md_covers[0].get("b2key", "")
            if b2key:
                cover_url = f"https://meo.comick.pictures/{b2key}"

        authors = ", ".join(
            a.get("name", "") for a in (data.get("authors") or comic.get("md_authors") or [])
        ) or "Unknown"
        artists = ", ".join(
            a.get("name", "") for a in (data.get("artists") or [])
        ) or authors

        content_type = self._detect_type(comic)
        hid = comic.get("hid", slug)

        # Fetch chapters
        chapters = self._fetch_all_chapters(hid)

        return MangaData(
            title=comic.get("title") or slug,
            alt_titles=comic.get("md_titles", []),
            author=authors,
            artist=artists,
            description=comic.get("desc") or "",
            cover_url=cover_url,
            status=self._map_status(comic.get("status")),
            source_id=source_id if source_id.startswith("http") else f"{self.base_url}/comic/{slug}",
            content_type=content_type,
            chapters=chapters,
        )

    # ------------------------------------------------------------------
    # Chapter pages
    # ------------------------------------------------------------------

    def get_chapter_pages(self, chapter_url: str) -> List[str]:
        # chapter_url is like https://api.comick.io/chapter/<hid>
        # or https://comick.io/comic/<slug>/<chap-hid>-chapter-N-en
        hid = self._extract_chapter_hid(chapter_url)
        url = f"{self.api_base}/chapter/{hid}"
        data = self._api_get(url)
        chapter_data = data.get("chapter", data)

        images = chapter_data.get("md_images") or chapter_data.get("images") or []
        pages = []
        for img in images:
            b2key = img.get("b2key", "")
            if b2key:
                pages.append(f"https://meo.comick.pictures/{b2key}")

        return pages

    def _referer_for_url(self, url: str) -> str:
        return f"{self.base_url}/"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _api_get(self, url: str):
        """Make API request with proper headers and rate limiting."""
        time.sleep(random.uniform(0.3, 0.8))
        resp = self.get(url, headers={
            "Accept": "application/json",
            "Referer": f"{self.base_url}/",
        })
        return resp.json()

    def _fetch_all_chapters(self, hid: str) -> List[ChapterData]:
        """Fetch EN and FR chapters separately, merge, deduplicate by hid."""
        chapters: List[ChapterData] = []
        seen_hids: set = set()

        for lang in ("en", "fr"):
            page = 1
            while True:
                url = f"{self.api_base}/comic/{hid}/chapters?lang={lang}&limit=300&page={page}"
                try:
                    data = self._api_get(url)
                except Exception:
                    break

                ch_list = data.get("chapters") or []
                if not ch_list:
                    break

                for ch in ch_list:
                    ch_hid = ch.get("hid", "")
                    if ch_hid in seen_hids:
                        continue
                    seen_hids.add(ch_hid)

                    chap_num = str(ch.get("chap") or ch.get("chapter") or len(chapters) + 1)
                    vol_num = str(ch.get("vol") or "") if ch.get("vol") else None
                    title = ch.get("title") or f"Chapter {chap_num}"

                    chapters.append(
                        ChapterData(
                            number=chap_num,
                            title=title,
                            volume=vol_num,
                            source_url=f"{self.api_base}/chapter/{ch_hid}",
                            language=lang,
                        )
                    )

                total = data.get("total", 0)
                if len(chapters) >= total or len(ch_list) < 300:
                    break
                page += 1

        return chapters

    def _extract_slug(self, source_id: str) -> str:
        match = self._slug_re.search(source_id)
        if match:
            return match.group(1)
        # Maybe it's already a slug
        return source_id.rstrip("/").rsplit("/", 1)[-1]

    def _extract_chapter_hid(self, chapter_url: str) -> str:
        # From API URL: https://api.comick.io/chapter/<hid>
        if "/chapter/" in chapter_url:
            parts = chapter_url.rstrip("/").split("/chapter/")
            if len(parts) > 1:
                hid = parts[-1].split("?")[0]
                # If it's a slug like "abcdef-chapter-1-en", extract just the hid
                if "-" in hid:
                    return hid.split("-")[0]
                return hid
        return chapter_url.rstrip("/").rsplit("/", 1)[-1]

    def _detect_type(self, item: dict) -> str:
        country = (item.get("country") or "").lower()
        if country in ("kr", "ko"):
            return "manhwa"
        elif country in ("cn", "zh"):
            return "manhua"
        elif country == "jp":
            return "manga"
        return "manga"

    def _map_status(self, status_code) -> str:
        mapping = {
            1: "ongoing",
            2: "completed",
            3: "cancelled",
            4: "hiatus",
        }
        return mapping.get(status_code, "unknown")
