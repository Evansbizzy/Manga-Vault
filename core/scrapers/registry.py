from __future__ import annotations

import logging
from typing import Dict, List, Optional, Type
from urllib.parse import urlparse

from .base import BaseScraper
from .comick import ComickScraper
from .mangadex import MangaDexScraper
from .mangakakalot import MangaKakalotScraper
from .mangapill import MangaPillScraper
from .universal import UniversalHtmlScraper

logger = logging.getLogger(__name__)

SCRAPER_CLASSES: Dict[str, Type[BaseScraper]] = {
    MangaDexScraper.name: MangaDexScraper,
    ComickScraper.name: ComickScraper,
    MangaPillScraper.name: MangaPillScraper,
    MangaKakalotScraper.name: MangaKakalotScraper,
    UniversalHtmlScraper.name: UniversalHtmlScraper,
}


def register_scraper(scraper_cls: Type[BaseScraper]) -> Type[BaseScraper]:
    SCRAPER_CLASSES[scraper_cls.name] = scraper_cls
    return scraper_cls


def list_scrapers() -> List[dict]:
    scrapers = []
    for name, scraper_cls in SCRAPER_CLASSES.items():
        scraper = scraper_cls()
        scrapers.append({
            "name": name,
            "label": getattr(scraper, "label", name.title()),
            "supports_search": getattr(scraper, "supports_search", False),
            "supports_url_import": getattr(scraper, "supports_url_import", False),
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


def search_all(query: str) -> List[dict]:
    results: List[dict] = []
    for scraper_cls in SCRAPER_CLASSES.values():
        scraper = scraper_cls()
        if not getattr(scraper, "supports_search", False):
            continue
        try:
            for item in scraper.search(query):
                results.append({
                    "source": scraper.name,
                    "title": item.title,
                    "author": item.author,
                    "cover": item.cover_url,
                    "source_id": item.source_id,
                    "content_type": item.content_type,
                    "chapters_count": len(item.chapters),
                })
        except Exception as exc:
            logger.warning("Scraper %s failed for query %r: %s", scraper.name, query, exc)
            continue
    return results


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
