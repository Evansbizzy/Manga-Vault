from __future__ import annotations

import hashlib
import logging
from urllib.parse import urlsplit

from django.core.cache import cache

from core.scrapers import get_scraper

logger = logging.getLogger(__name__)


class ChapterPageExtractionError(ValueError):
    """The source could not provide a usable image list for a chapter."""


def get_chapter_page_urls(chapter) -> list[str]:
    source_url = chapter.source_url or ""
    cache_digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
    cache_key = f"chapter-pages:v2:{chapter.pk}:{cache_digest}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    scraper = get_scraper(chapter.manga.source, chapter.manga.source_id)
    label = getattr(scraper, "label", chapter.manga.source)
    try:
        extracted = scraper.get_chapter_pages(source_url) or []
    except Exception as exc:
        logger.warning(
            "Page extraction failed for chapter id=%s source=%s: %s",
            chapter.pk,
            chapter.manga.source,
            exc,
        )
        raise ChapterPageExtractionError(
            f"{label} could not load this chapter's page list: {exc}"
        ) from exc

    pages = []
    seen = set()
    for candidate in extracted:
        if not isinstance(candidate, str):
            continue
        candidate = candidate.strip()
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or candidate in seen:
            continue
        seen.add(candidate)
        pages.append(candidate)

    if not pages:
        raise ChapterPageExtractionError(
            f"{label} returned no readable page images for Chapter {chapter.chapter_number}. "
            "The chapter may be unavailable or its source page format may have changed."
        )

    cache.set(cache_key, pages, 15 * 60)
    return pages
