from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Type
from urllib.parse import urlparse

from .base import BaseScraper
from .comick import ComickScraper
from .mangadex import MangaDexScraper
from .mangakakalot import MangaKakalotScraper
from .mangahere import MangaHereScraper
from .mangareader import MangaReaderScraper
from .mangapill import MangaPillScraper
from .universal import UniversalHtmlScraper

logger = logging.getLogger(__name__)

SCRAPER_CLASSES: Dict[str, Type[BaseScraper]] = {
    MangaDexScraper.name: MangaDexScraper,
    ComickScraper.name: ComickScraper,
    MangaPillScraper.name: MangaPillScraper,
    MangaKakalotScraper.name: MangaKakalotScraper,
    MangaHereScraper.name: MangaHereScraper,
    MangaReaderScraper.name: MangaReaderScraper,
    UniversalHtmlScraper.name: UniversalHtmlScraper,
}


def register_scraper(scraper_cls: Type[BaseScraper]) -> Type[BaseScraper]:
    SCRAPER_CLASSES[scraper_cls.name] = scraper_cls
    return scraper_cls


def list_scrapers() -> List[dict]:
    scrapers = []
    for name, scraper_cls in SCRAPER_CLASSES.items():
        scrapers.append({
            "name": name,
            "label": getattr(scraper_cls, "label", name.title()),
            "supports_search": getattr(scraper_cls, "supports_search", False),
            "supports_url_import": getattr(scraper_cls, "supports_url_import", False),
        })
    return scrapers


def get_scraper(source: Optional[str] = None, reference: Optional[str] = None) -> BaseScraper:
    if source and source not in {"auto", "all"}:
        scraper_cls = SCRAPER_CLASSES.get(source)
        if scraper_cls is None:
            raise ValueError(f"Unknown scraper source: {source}")
        return scraper_cls()

    if reference and _looks_like_url(reference):
        for scraper_cls in SCRAPER_CLASSES.values():
            if scraper_cls.name == UniversalHtmlScraper.name:
                continue
            detector = getattr(scraper_cls, "can_handle", None)
            if callable(detector) and detector(reference):
                return scraper_cls()
        universal = SCRAPER_CLASSES[UniversalHtmlScraper.name]
        return universal()

    return MangaDexScraper()


def search_all(query: str) -> tuple[List[dict], List[dict]]:
    searchable = [
        scraper_cls
        for scraper_cls in SCRAPER_CLASSES.values()
        if getattr(scraper_cls, "supports_search", False)
    ]

    def search_source(scraper_cls):
        source_name = getattr(scraper_cls, "name", scraper_cls.__name__.lower())
        source_label = getattr(scraper_cls, "label", source_name.title())
        try:
            scraper = scraper_cls()
            items = scraper.search(query) or []
            return source_name, source_label, items, None
        except Exception as exc:
            logger.warning("Scraper %s failed for query %r: %s", source_name, query, exc)
            return source_name, source_label, [], exc

    with ThreadPoolExecutor(max_workers=min(4, max(len(searchable), 1))) as executor:
        source_results = list(executor.map(search_source, searchable))

    results: List[dict] = []
    source_status: List[dict] = []
    seen = set()
    query_key = _normalize_title(query)

    for source_name, source_label, items, error in source_results:
        source_status.append({
            "source": source_name,
            "label": source_label,
            "status": "error" if error else "ok",
            "count": len(items),
            "message": "Could not reach this source" if error else "",
        })
        for item in items:
            source_id = str(item.source_id or "").strip().rstrip("/").casefold()
            identity = (source_name, source_id or _normalize_title(item.title))
            if identity in seen:
                continue
            seen.add(identity)
            results.append({
                "source": source_name,
                "title": item.title,
                "alt_titles": item.alt_titles,
                "author": item.author,
                "cover": item.cover_url,
                "source_id": item.source_id,
                "content_type": item.content_type,
                "chapters_count": len(item.chapters),
            })

    results.sort(key=lambda result: _relevance_score(result, query_key), reverse=True)
    return results, source_status


def _normalize_title(value: str) -> str:
    return re.sub(r"[^\w]+", " ", (value or "").casefold(), flags=re.UNICODE).strip()


def _relevance_score(result: dict, query: str) -> tuple[float, int]:
    candidates = [result.get("title", ""), *(result.get("alt_titles") or [])]
    best_score = 0.0
    for candidate in candidates:
        title = _normalize_title(candidate)
        if not title:
            continue
        if title == query:
            score = 1.0
        elif title.startswith(query) or query.startswith(title):
            score = 0.92
        elif query in title or title in query:
            score = 0.86
        else:
            query_terms = set(query.split())
            title_terms = set(title.split())
            overlap = len(query_terms & title_terms) / max(len(query_terms), 1)
            similarity = SequenceMatcher(None, query, title).ratio()
            score = max(overlap * 0.8, similarity * 0.75)
        best_score = max(best_score, score)
    return best_score, -len(result.get("title", ""))


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
