from __future__ import annotations

import re
from typing import List
from urllib.parse import quote_plus, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from .base import BaseScraper, ChapterData, MangaData


class MangaHereScraper(BaseScraper):
    name = "mangahere"
    label = "MangaHere"
    base_url = "https://www.mangahere.cc"
    supports_search = True
    supports_url_import = True

    _chapter_re = re.compile(r"(?:/c\d+(?:\.\d+)?/|chapter[-_/]?\d|/read/)", re.I)
    _number_re = re.compile(r"(?:chapter|ch\.?|episode|vol(?:ume)?\.?)\s*(\d+(?:\.\d+)?)", re.I)

    @classmethod
    def can_handle(cls, reference: str) -> bool:
        host = (urlparse(reference).hostname or "").lower()
        return host == "mangahere.cc" or host.endswith(".mangahere.cc") or host == "fanfox.net" or host.endswith(".fanfox.net")

    def search(self, query: str) -> List[MangaData]:
        response = self.get(f"{self.base_url}/search?title={quote_plus(query)}", timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        seen = set()

        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "").strip()
            if not re.search(r"/manga/[^/?#]+/?(?:[?#].*)?$", href, re.I):
                continue
            manga_url = self._normalize_url(urljoin(response.url, href))
            if not self.can_handle(manga_url):
                continue
            if manga_url in seen:
                continue

            image = anchor.select_one("img")
            title = (
                anchor.get("title")
                or (image.get("alt") if image else "")
                or anchor.get_text(" ", strip=True)
            ).strip()
            if not title or title.casefold() in {"read manga online", "manga here"}:
                continue

            cover = ""
            if image:
                cover = image.get("data-src") or image.get("data-original") or image.get("src") or ""
                cover = urljoin(manga_url, cover)

            seen.add(manga_url)
            results.append(MangaData(
                title=title,
                alt_titles=[],
                author="Unknown",
                artist="Unknown",
                description="",
                cover_url=cover,
                status="unknown",
                source_id=manga_url,
                content_type="manga",
                chapters=[],
            ))

        return results

    def get_manga_details(self, source_id: str) -> MangaData:
        url = self._series_url(self._normalize_url(source_id))
        response = self.get(url, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")
        title = self._first_text(soup, (
            "h1",
            ".detail-info span.detail-info-right-title-font",
            ".detail-main-info h1",
            ".detail-info h1",
        ))
        if not title:
            meta_title = soup.select_one('meta[property="og:title"]')
            title = meta_title.get("content", "").strip() if meta_title else "Untitled"

        cover = soup.select_one('meta[property="og:image"], meta[name="twitter:image"]')
        cover_url = cover.get("content", "").strip() if cover else ""
        if not cover_url:
            cover_image = soup.select_one(".detail-info img, .detail-info-cover img, .info-image img")
            if cover_image:
                cover_url = (
                    cover_image.get("data-src")
                    or cover_image.get("data-original")
                    or cover_image.get("src")
                    or ""
                )
        cover_url = urljoin(url, cover_url) if cover_url else ""
        description = soup.select_one('meta[property="og:description"], meta[name="description"]')
        description_text = description.get("content", "").strip() if description else ""

        chapters = []
        seen = set()
        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "").strip()
            label = anchor.get_text(" ", strip=True)
            if not href or not self._chapter_re.search(urlparse(href).path):
                continue
            chapter_url = self._normalize_url(urljoin(url, href))
            if chapter_url in seen:
                continue
            seen.add(chapter_url)
            match = self._number_re.search(label) or re.search(r"/c(\d+(?:\.\d+)?)/", href, re.I)
            number = match.group(1) if match else str(len(chapters) + 1)
            chapters.append(ChapterData(
                number=number,
                title=label or f"Chapter {number}",
                volume=None,
                source_url=chapter_url,
            ))

        return MangaData(
            title=title,
            alt_titles=[],
            author="Unknown",
            artist="Unknown",
            description=description_text,
            cover_url=cover_url,
            status="unknown",
            source_id=url,
            content_type="manga",
            chapters=chapters,
        )

    def get_chapter_pages(self, chapter_url: str) -> List[str]:
        url = self._normalize_url(chapter_url)
        response = self.get(url, timeout=15, headers={"Referer": self._series_url(url)})
        soup = BeautifulSoup(response.text, "html.parser")
        page_select = soup.select_one("select.mangaread-page, select.m")
        if page_select:
            page_urls = []
            page_numbers = []
            for option in page_select.select("option"):
                page_number = option.get_text(strip=True)
                if not page_number.isdigit():
                    page_number = option.get("value", "")
                if page_number.isdigit():
                    page_numbers.append(int(page_number))
            chapter_dir = url.rsplit("/", 1)[0] + "/"
            for page_number in page_numbers:
                page_url = urljoin(chapter_dir, f"{page_number}.html")
                page_response = self.get(
                    page_url,
                    timeout=15,
                    headers={"Referer": url},
                )
                page_urls.extend(self._page_urls_from_html(BeautifulSoup(page_response.text, "html.parser"), page_url))
            if page_urls:
                return list(dict.fromkeys(page_urls))

        if re.search(r"var\s+chapterid\s*=", response.text) and re.search(r"var\s+imagecount\s*=", response.text):
            pages = self._chapterfun_pages(soup, url, response.text)
            if pages:
                return pages

        return self._page_urls_from_html(soup, url)

    def _page_urls_from_html(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        pages = []
        for image in soup.select("#viewer img, img#image, #chapter_img, #cp_img, .reader-main img, .read_img img, .chapter-content img"):
            candidate = image.get("data-src") or image.get("data-original") or image.get("src") or ""
            candidate = urljoin(base_url, candidate.strip())
            if candidate.startswith(("http://", "https://")) and candidate not in pages:
                pages.append(candidate)
        return pages

    def _chapterfun_pages(self, soup: BeautifulSoup, chapter_url: str, html: str) -> List[str]:
        chapter_id = re.search(r"var\s+chapterid\s*=\s*['\"]?(\d+)", html)
        image_count = re.search(r"var\s+imagecount\s*=\s*['\"]?(\d+)", html)
        if not chapter_id or not image_count:
            return []

        key_input = soup.select_one("#dm5_key")
        key = key_input.get("value", "") if key_input else ""
        endpoint = urljoin(self.base_url + "/", "chapterfun.ashx")
        pages = []
        for page_number in range(1, min(int(image_count.group(1)), 500) + 1):
            params = urlencode({"cid": chapter_id.group(1), "page": page_number, "key": key})
            response = self.get(
                f"{endpoint}?{params}",
                timeout=15,
                headers={
                    "Referer": chapter_url,
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            unpacked = self._unpack_packer(response.text)
            base_match = re.search(r'var\s+pix\s*=\s*["\']([^"\']+)', unpacked)
            values_match = re.search(r"var\s+pvalue\s*=\s*\[(.*?)\]", unpacked, re.S)
            if not base_match or not values_match:
                continue
            image_values = re.findall(r"[\"']([^\"']+)[\"']", values_match.group(1))
            if not image_values:
                continue
            image_url = image_values[0]
            if image_url.startswith("//"):
                image_url = "https:" + image_url
            elif image_url.startswith("/"):
                image_url = base_match.group(1).rstrip("/") + image_url
            elif not image_url.startswith(("http://", "https://")):
                image_url = urljoin(base_match.group(1).rstrip("/") + "/", image_url)
            if image_url not in pages:
                pages.append(image_url)
        return pages

    def _unpack_packer(self, source: str) -> str:
        match = re.search(
            r"\}\(['\"](.*?)['\"],\s*(\d+),\s*(\d+),\s*['\"](.*?)['\"]\.split\(['\"]\|['\"]\)",
            source,
            re.S,
        )
        if not match:
            return source
        payload, radix, _, symbols = match.groups()
        words = symbols.split("|")
        base = int(radix)

        def replace_token(token_match):
            token = token_match.group(0)
            try:
                index = int(token, base if base <= 36 else 36)
            except ValueError:
                return token
            return words[index] if index < len(words) and words[index] else token

        return re.sub(r"\b\w+\b", replace_token, payload.replace("\\'", "'").replace("\\\\", "\\"))

    def _first_text(self, soup: BeautifulSoup, selectors: tuple[str, ...]) -> str:
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                value = element.get_text(" ", strip=True)
                if value:
                    return value
        return ""

    def _normalize_url(self, value: str) -> str:
        url = urljoin(self.base_url, value)
        if not self.can_handle(url):
            raise ValueError("URL is not from MangaHere or FanFox")
        return url

    def _series_url(self, url: str) -> str:
        parsed = urlparse(url)
        match = re.match(r"^(/manga/[^/]+/)", parsed.path, re.I)
        if not match:
            return url
        return urlunparse((parsed.scheme, parsed.netloc, match.group(1), "", "", ""))

    def image_referer(self, image_url: str = "") -> str:
        parsed = urlparse(image_url)
        host = parsed.hostname or ""
        if host.endswith("fanfox.net"):
            return "https://fanfox.net/"
        return "https://www.mangahere.cc/"

    def _referer_for_url(self, url: str) -> str:
        return self.image_referer(url)
