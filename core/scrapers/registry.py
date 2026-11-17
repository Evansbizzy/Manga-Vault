from __future__ import annotations

import hashlib
import logging
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Type
from urllib.parse import urlparse

from django.core.cache import cache

from .base import BaseScraper
from .comick import ComickScraper
from .mangadex import MangaDexScraper
from .mangakakalot import MangaKakalotScraper
from .mangahere import MangaHereScraper
from .mangareader import MangaReaderScraper
from .mangapill import MangaPillScraper
from .mangaupdates import MangaUpdatesScraper
from .universal import UniversalHtmlScraper

logger = logging.getLogger(__name__)
MIN_SEARCH_RELEVANCE = 0.55
SEARCH_CACHE_SECONDS = 180

SCRAPER_CLASSES: Dict[str, Type[BaseScraper]] = {
    MangaDexScraper.name: MangaDexScraper,
    ComickScraper.name: ComickScraper,
    MangaPillScraper.name: MangaPillScraper,
    MangaKakalotScraper.name: MangaKakalotScraper,
    MangaHereScraper.name: MangaHereScraper,
    MangaReaderScraper.name: MangaReaderScraper,
    MangaUpdatesScraper.name: MangaUpdatesScraper,
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
            "supports_read": getattr(scraper_cls, "supports_read", True),
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
        supports_import = getattr(scraper_cls, "supports_url_import", False)
        supports_read = getattr(scraper_cls, "supports_read", True)
        try:
            items, was_cached = search_source_cached(scraper_cls, query)
            return source_name, source_label, supports_import, supports_read, items, None, was_cached
        except Exception as exc:
            logger.warning("Scraper %s failed for query %r: %s", source_name, query, exc)
            return source_name, source_label, supports_import, supports_read, [], exc, False

    # Each provider is independent; fan out to all enabled sources so a second
    # wave of requests does not wait behind the first wave's slowest host.
    with ThreadPoolExecutor(max_workers=min(8, max(len(searchable), 1))) as executor:
        source_results = list(executor.map(search_source, searchable))

    results: List[dict] = []
    source_status: List[dict] = []
    seen = set()
    query_key = _normalize_title(query)

    for source_name, source_label, supports_import, supports_read, items, error, was_cached in source_results:
        source_status.append({
            "source": source_name,
            "label": source_label,
            "status": "error" if error else "ok",
            "count": len(items),
            "message": "Could not reach this source" if error else "",
            "cached": was_cached,
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
                "external_url": item.external_url,
                "supports_import": supports_import,
                "supports_read": supports_read,
            })

    results.sort(key=lambda result: _relevance_score(result, query_key), reverse=True)
    results = filter_search_results(results, query)
    visible_counts = Counter(result["source"] for result in results)
    for source in source_status:
        source["count"] = visible_counts.get(source["source"], 0)
    return results, source_status


def search_source_cached(scraper_cls: Type[BaseScraper], query: str):
    """Return source search data from a short cache, or query the provider once."""
    source_name = getattr(scraper_cls, "name", scraper_cls.__name__.lower())
    normalized_query = re.sub(r"\s+", " ", query).strip().casefold()
    digest = hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()
    cache_key = f"source-search:v1:{source_name}:{digest}"
    try:
        cached_items = cache.get(cache_key)
    except Exception:
        logger.warning("Search cache read failed for %s", source_name, exc_info=True)
        cached_items = None
    if cached_items is not None:
        return cached_items, True

    scraper = scraper_cls()
    # Search requests are latency-sensitive. Import/detail flows retain normal
    # retry behavior, while a search reports the source as unavailable quickly.
    scraper.max_retries = 1
    items = scraper.search(query) or []
    try:
        cache.set(cache_key, items, SEARCH_CACHE_SECONDS)
    except Exception:
        logger.warning("Search cache write failed for %s", source_name, exc_info=True)
    return items, False


def search_all_progressively(query: str):
    """Yield one completed source result at a time for streaming search clients."""
    searchable = [
        scraper_cls for scraper_cls in SCRAPER_CLASSES.values()
        if getattr(scraper_cls, "supports_search", False)
    ]

    def run_source(scraper_cls):
        name = getattr(scraper_cls, "name", scraper_cls.__name__.lower())
        label = getattr(scraper_cls, "label", name.title())
        started = time.perf_counter()
        try:
            items, cached = search_source_cached(scraper_cls, query)
            results = [{
                "source": name,
                "title": item.title,
                "alt_titles": item.alt_titles,
                "author": item.author,
                "cover": item.cover_url,
                "source_id": item.source_id,
                "content_type": item.content_type,
                "chapters_count": len(item.chapters),
                "external_url": item.external_url,
                "supports_import": getattr(scraper_cls, "supports_url_import", False),
                "supports_read": getattr(scraper_cls, "supports_read", True),
            } for item in items]
            results = filter_search_results(results, query)
            status = {
                "source": name, "label": label, "status": "ok",
                "count": len(results), "message": "", "cached": cached,
            }
        except Exception as exc:
            logger.warning("Scraper %s failed for query %r: %s", name, query, exc)
            results = []
            status = {
                "source": name, "label": label, "status": "error",
                "count": 0, "message": "Could not reach this source", "cached": False,
            }
        duration_ms = round((time.perf_counter() - started) * 1000)
        status["duration_ms"] = duration_ms
        logger.info(
            "Search source=%s duration_ms=%d cached=%s results=%d status=%s",
            name, duration_ms, status["cached"], len(results), status["status"],
        )
        return {"source_status": status, "results": results}

    executor = ThreadPoolExecutor(max_workers=min(8, max(len(searchable), 1)))
    futures = [executor.submit(run_source, scraper_cls) for scraper_cls in searchable]
    try:
        for future in as_completed(futures):
            yield future.result()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def filter_search_results(results: List[dict], query: str) -> List[dict]:
    """Drop malformed and weakly related search hits before showing them."""
    normalized_query = _normalize_title(query)
    concrete = [
        result for result in results
        if str(result.get("title") or "").strip()
        and str(result.get("source_id") or "").strip()
    ]
    return [
        result for result in concrete
        if _relevance_score(result, normalized_query)[0] >= MIN_SEARCH_RELEVANCE
    ]


def _normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "").casefold()
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", " ", without_marks, flags=re.UNICODE).strip()


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
            score = 0.94
        elif f" {query} " in f" {title} " or f" {title} " in f" {query} ":
            score = 0.90
        else:
            query_terms = set(query.split())
            title_terms = set(title.split())
            shared_terms = len(query_terms & title_terms)
            query_coverage = shared_terms / max(len(query_terms), 1)
            title_coverage = shared_terms / max(len(title_terms), 1)
            token_score = (
                2 * query_coverage * title_coverage
                / max(query_coverage + title_coverage, 1e-9)
            )
            character_score = SequenceMatcher(None, query, title).ratio()
            token_order_score = SequenceMatcher(
                None,
                " ".join(sorted(query_terms)),
                " ".join(sorted(title_terms)),
            ).ratio()
            score = max(
                query_coverage * 0.84,
                token_score * 0.88,
                character_score * 0.76,
                token_order_score * 0.82,
            )
        best_score = max(best_score, score)
    return best_score, -len(result.get("title", ""))


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
