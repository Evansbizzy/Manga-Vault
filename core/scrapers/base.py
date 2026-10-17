import requests
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class ChapterData:
    number: str
    title: str
    volume: Optional[str]
    source_url: str
    language: str = "en"
    pages: Optional[List[str]] = None


@dataclass
class MangaData:
    title: str
    alt_titles: List[str]
    author: str
    artist: str
    description: str
    cover_url: str
    status: str
    source_id: str
    content_type: str
    chapters: List[ChapterData]


class BaseScraper(ABC):
    name: str = "base"
    base_url: str = ""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.get_headers())
        self.last_request_time = 0
        self.rate_limit_delay = 1  # seconds between requests
        self.max_retries = 3

    def get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        }

    def _rate_limit(self):
        """Ensure we don't hammer the server"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def get(self, url: str, **kwargs):
        kwargs.setdefault("timeout", 30)
        for attempt in range(self.max_retries):
            self._rate_limit()
            try:
                resp = self.session.get(url, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.exceptions.HTTPError as e:
                if resp.status_code == 429:
                    wait = min(2 ** attempt * 2, 30)
                    time.sleep(wait)
                    continue
                if resp.status_code >= 500 and attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
        return resp

    @abstractmethod
    def search(self, query: str) -> List[MangaData]:
        """Search for manga by title"""
        pass

    @abstractmethod
    def get_manga_details(self, source_id: str) -> MangaData:
        """Get full manga info with all chapters"""
        pass

    @abstractmethod
    def get_chapter_pages(self, chapter_url: str) -> List[str]:
        """Get all image URLs for a chapter at once"""
        pass

    def _referer_for_url(self, url: str) -> str:
        """Return an appropriate Referer header for an image URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/"

    def download_chapter_images(self, chapter_url: str) -> List[bytes]:
        """
        Download ALL pages of a chapter at once.
        Returns list of image bytes.
        """
        page_urls = self.get_chapter_pages(chapter_url)
        if not page_urls:
            return []

        from concurrent.futures import ThreadPoolExecutor, as_completed

        images = [None] * len(page_urls)

        def download_single(args):
            idx, url = args
            for attempt in range(self.max_retries):
                try:
                    session = requests.Session()
                    headers = self.get_headers()
                    headers["Referer"] = self._referer_for_url(url)
                    headers["Accept"] = "image/avif,image/webp,image/png,image/jpeg,*/*"
                    session.headers.update(headers)
                    resp = session.get(url, timeout=30)
                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "")
                    if resp.content and (
                        "image" in content_type
                        or len(resp.content) > 1024
                    ):
                        return idx, resp.content
                    return idx, None
                except Exception as e:
                    if attempt < self.max_retries - 1:
                        time.sleep(1 * (attempt + 1))
                        continue
                    print(f"Failed to download {url}: {e}")
            return idx, None

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(download_single, (i, url)): i
                for i, url in enumerate(page_urls)
            }
            for future in as_completed(futures):
                idx, data = future.result()
                if data:
                    images[idx] = data

        return [img for img in images if img is not None]
