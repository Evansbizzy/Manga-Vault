import requests
import time
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass
from urllib.parse import urlparse

from core.utils.network import safe_request, safe_get

logger = logging.getLogger(__name__)


class ChapterImageDownloadError(ValueError):
    """One or more required page images could not be retrieved safely."""


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
    external_url: str = ""


class BaseScraper(ABC):
    name: str = "base"
    base_url: str = ""
    image_content_types = {
        'image/avif', 'image/bmp', 'image/gif', 'image/jpeg', 'image/png', 'image/webp',
    }

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
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def request(self, method: str, url: str, **kwargs):
        kwargs.setdefault("timeout", 30)
        for attempt in range(self.max_retries):
            self._rate_limit()
            try:
                resp = safe_request(self.session, method, url, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.exceptions.HTTPError:
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After", "")
                    try:
                        wait = min(max(float(retry_after), 0), 60)
                    except ValueError:
                        wait = min(2 ** attempt * 2, 30)
                    if attempt == self.max_retries - 1:
                        raise
                    time.sleep(wait)
                    continue
                if resp.status_code >= 500 and attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
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

    def image_referer(self, image_url: str = "") -> str:
        """Return the site origin that should be sent when fetching images."""
        parsed = urlparse(self.base_url)
        return f"{parsed.scheme}://{parsed.netloc}/" if parsed.netloc else self._referer_for_url(image_url)

    def download_chapter_images(self, chapter_url: str) -> List[bytes]:
        """
        Download ALL pages of a chapter at once.
        Returns list of image bytes.
        """
        page_urls = self.get_chapter_pages(chapter_url)
        if not page_urls:
            return []

        return self.download_chapter_images_from_urls(page_urls)

    def download_chapter_images_from_urls(self, page_urls: List[str]) -> List[bytes]:
        """Fetch a previously extracted page list without re-parsing the source."""
        if not page_urls:
            return []

        from concurrent.futures import ThreadPoolExecutor, as_completed

        images = [None] * len(page_urls)
        failed = []

        def download_single(args):
            idx, url = args
            for attempt in range(self.max_retries):
                session = requests.Session()
                try:
                    headers = self.get_headers()
                    headers["Referer"] = self.image_referer(url)
                    headers["Accept"] = "image/avif,image/webp,image/png,image/jpeg,*/*"
                    session.headers.update(headers)
                    resp = safe_get(session, url, timeout=30, stream=True)
                    with resp:
                        resp.raise_for_status()
                        content_type = resp.headers.get('content-type', '').split(';', 1)[0].lower()
                        if content_type not in self.image_content_types and content_type not in {
                            "application/octet-stream", "binary/octet-stream", ""
                        }:
                            return idx, None
                        content_length = resp.headers.get('content-length')
                        if content_length and int(content_length) > 20 * 1024 * 1024:
                            return idx, None
                        image_data = bytearray()
                        for chunk in resp.iter_content(chunk_size=64 * 1024):
                            image_data.extend(chunk)
                            if len(image_data) > 20 * 1024 * 1024:
                                return idx, None
                        image_bytes = bytes(image_data)
                        return idx, image_bytes if self._is_supported_image(image_bytes) else None
                except Exception as e:
                    if attempt < self.max_retries - 1:
                        time.sleep(1 * (attempt + 1))
                        continue
                    logger.warning("Page image request failed (page %s): %s", idx + 1, e)
                finally:
                    session.close()
            return idx, None

        with ThreadPoolExecutor(max_workers=min(4, len(page_urls))) as executor:
            futures = {
                executor.submit(download_single, (i, url)): i
                for i, url in enumerate(page_urls)
            }
            for future in as_completed(futures):
                idx, data = future.result()
                if data:
                    images[idx] = data
                else:
                    failed.append(idx + 1)

        if failed:
            first_failed = ", ".join(str(page) for page in sorted(failed)[:10])
            remaining = len(failed) - 10
            suffix = f" and {remaining} more" if remaining > 0 else ""
            page_label = "page" if len(failed) == 1 else "pages"
            raise ChapterImageDownloadError(
                f"{self.label if hasattr(self, 'label') else self.name} could not retrieve "
                f"{page_label} {first_failed}{suffix} "
                f"({len(failed)} of {len(page_urls)} pages failed). No incomplete archive was created."
            )

        return [img for img in images if img is not None]

    @staticmethod
    def _is_supported_image(image_data: bytes) -> bool:
        """Accept known image signatures, not error HTML mislabeled as an image."""
        return bool(
            image_data.startswith(b"\xff\xd8\xff")
            or image_data.startswith(b"\x89PNG\r\n\x1a\n")
            or image_data.startswith((b"GIF87a", b"GIF89a"))
            or image_data.startswith(b"BM")
            or (image_data.startswith(b"RIFF") and image_data[8:12] == b"WEBP")
            or (image_data[4:8] == b"ftyp" and any(
                brand in image_data[8:32] for brand in (b"avif", b"avis")
            ))
        )
