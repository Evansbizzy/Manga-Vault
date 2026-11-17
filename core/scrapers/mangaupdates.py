from __future__ import annotations

import hashlib
from typing import List

from django.core.cache import cache

from .base import BaseScraper, MangaData

class MangaUpdatesScraper(BaseScraper):
    name = "mangaupdates"
    label = "MangaUpdates (catalog)"
    base_url = "https://www.mangaupdates.com"
    api_url = "https://api.mangaupdates.com/v1/series/search"
    supports_search = True
    supports_url_import = False
    supports_read = False
    cache_timeout = 6 * 60 * 60

    def search(self, query: str) -> List[MangaData]:
        normalized_query = query.strip()
        cache_key = "mangaupdates-search:" + hashlib.sha256(
            normalized_query.casefold().encode("utf-8")
        ).hexdigest()
        cached = cache.get(cache_key)
        if cached is not None:
            return [self._as_manga(item) for item in cached]

        response = self.post(
            self.api_url,
            json={"search": normalized_query, "stype": "title", "page": 1, "perpage": 20},
            headers={"Accept": "application/json", "User-Agent": "MangaVault/1.0 (catalog search)"},
            timeout=(4, 10),
        )
        data = response.json()
        results = []
        seen_ids = set()
        for hit in data.get("results", []):
            record = hit.get("record") or {}
            series_id = str(record.get("series_id") or "").strip()
            title = str(record.get("title") or "").strip()
            if not series_id.isdigit() or not title or series_id in seen_ids:
                continue
            seen_ids.add(series_id)
            image = record.get("image") or {}
            image_urls = image.get("url") or {}
            results.append({
                "title": title,
                "alt_titles": [],
                "author": "Unknown",
                "artist": "Unknown",
                "description": str(record.get("description") or ""),
                "cover_url": str(image_urls.get("thumb") or image_urls.get("original") or ""),
                "status": "unknown",
                "source_id": series_id,
                "content_type": self._content_type(record.get("type")),
                "chapters": [],
                "external_url": f"{self.base_url}/series.html?id={series_id}",
            })

        cache.set(cache_key, results, self.cache_timeout)
        return [self._as_manga(item) for item in results]

    def get_manga_details(self, source_id: str) -> MangaData:
        raise NotImplementedError("MangaUpdates is a catalog source and does not provide readable chapters")

    def get_chapter_pages(self, chapter_url: str) -> List[str]:
        return []

    @staticmethod
    def _content_type(value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized in {"manhwa", "manhua", "webtoon"}:
            return normalized
        return "manga"

    @staticmethod
    def _as_manga(item: dict) -> MangaData:
        return MangaData(**item)
