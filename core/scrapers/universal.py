from __future__ import annotations

import json
import re
from html import unescape
from typing import List, Optional
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from .base import BaseScraper, ChapterData, MangaData


class UniversalHtmlScraper(BaseScraper):
    name = "universal"
    label = "Any HTML Site"
    supports_search = False
    supports_url_import = True

    _chapter_hint_re = re.compile(r"(chapter|chap\.?|read|manga|comic|vol\.?|volume|c/\d+)", re.I)
    _number_re = re.compile(r"(\d+(?:\.\d+)?)")

    @classmethod
    def can_handle(cls, reference: str) -> bool:
        return reference.startswith("http://") or reference.startswith("https://")

    def search(self, query: str) -> List[MangaData]:
        raise NotImplementedError("Generic HTML scraper does not support search")

    def get_manga_details(self, source_id: str) -> MangaData:
        url = self._normalize_url(source_id)
        resp = self.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        jsonld = self._extract_json_ld(soup)

        title = self._pick_text(
            soup,
            [
                ('meta[property="og:title"]', "content"),
                ('meta[name="twitter:title"]', "content"),
                "h1",
                "title",
            ],
            default=self._jsonld_text(jsonld, ("name",), default="Untitled"),
        )
        description = self._pick_text(
            soup,
            [
                ('meta[property="og:description"]', "content"),
                ('meta[name="description"]', "content"),
                "p",
            ],
            default=self._jsonld_text(jsonld, ("description",), default=""),
        )
        cover_url = self._pick_text(
            soup,
            [
                ('meta[property="og:image"]', "content"),
                ('meta[name="twitter:image"]', "content"),
            ],
            default=self._jsonld_image(jsonld),
        )
        if cover_url:
            cover_url = urljoin(url, cover_url)

        author = self._pick_text(
            soup,
            [
                ('meta[name="author"]', "content"),
                '.author',
                '.manga-author',
                '.creator',
            ],
            default=self._jsonld_text(jsonld, ("author", "name"), default="Unknown"),
        )
        artist = author

        chapters = self._extract_chapter_links(soup, url)
        if not chapters:
            chapters = self._extract_chapter_links_from_jsonld(jsonld, url)
        if not chapters:
            chapters = self._extract_chapter_links_from_page_links(soup, url)
        if not chapters and self._page_looks_like_chapter(soup):
            chapters = [ChapterData(number="1", title=title, volume=None, source_url=url)]

        content_type = self._infer_content_type(soup, jsonld)

        return MangaData(
            title=title,
            alt_titles=self._jsonld_alt_titles(jsonld),
            author=author,
            artist=artist,
            description=description,
            cover_url=cover_url,
            status="unknown",
            source_id=url,
            content_type=content_type,
            chapters=chapters,
        )

    def get_chapter_pages(self, chapter_url: str) -> List[str]:
        url = self._normalize_url(chapter_url)
        visited = set()
        pages: List[str] = []
        current = url

        for _ in range(250):
            if current in visited:
                break
            visited.add(current)

            resp = self.get(current, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            page_images = self._extract_images(soup, current)
            if not page_images:
                page_images = self._extract_embedded_images(soup, current)
            for image in page_images:
                if image not in pages:
                    pages.append(image)

            iframe_images = self._extract_iframe_images(soup, current)
            for image in iframe_images:
                if image not in pages:
                    pages.append(image)

            next_url = self._find_next_page(soup, current)
            if not next_url or next_url in visited:
                break
            current = next_url

        return pages

    def _extract_chapter_links(self, soup: BeautifulSoup, base_url: str) -> List[ChapterData]:
        seen = set()
        chapters: List[ChapterData] = []
        selectors = [
            "a[href*='chapter']",
            "a[href*='chap']",
            "a[href*='read']",
            "a[href*='comic']",
            "a[href*='manga']",
            ".chapter a[href]",
            ".chapter-item a[href]",
            ".chapter-list a[href]",
            ".list-chapter a[href]",
            ".row-content-chapter a[href]",
            "a.chapter-name[href]",
        ]
        for anchor in soup.select(", ".join(selectors)):
            href = anchor.get("href")
            if not href:
                continue
            full_url = self._normalize_url(urljoin(base_url, href))
            if full_url in seen:
                continue
            text = self._clean_text(anchor) or href
            if not self._looks_like_chapter_link(f"{text} {full_url}"):
                continue
            seen.add(full_url)
            number = self._extract_number(text) or str(len(chapters) + 1)
            volume = self._extract_volume(text)
            chapters.append(
                ChapterData(
                    number=number,
                    title=text,
                    volume=volume,
                    source_url=full_url,
                )
            )

        return self._dedupe_and_sort_chapters(chapters)

    def _extract_chapter_links_from_jsonld(self, jsonld: List[dict], base_url: str) -> List[ChapterData]:
        chapters: List[ChapterData] = []
        for item in jsonld:
            main_entity = item.get("mainEntity")
            if isinstance(main_entity, list):
                entities = main_entity
            elif isinstance(main_entity, dict):
                entities = [main_entity]
            else:
                entities = []

            for entity in entities:
                if not isinstance(entity, dict):
                    continue
                url = entity.get("url") or entity.get("@id")
                if not url:
                    continue
                url = self._normalize_url(urljoin(base_url, url))
                title = entity.get("name") or entity.get("headline") or "Chapter"
                number = self._extract_number(title) or str(len(chapters) + 1)
                chapters.append(
                    ChapterData(
                        number=number,
                        title=title,
                        volume=self._extract_volume(title),
                        source_url=url,
                    )
                )
        return self._dedupe_and_sort_chapters(chapters)

    def _extract_chapter_links_from_page_links(self, soup: BeautifulSoup, base_url: str) -> List[ChapterData]:
        chapters: List[ChapterData] = []
        for anchor in soup.find_all("a", href=True):
            href = urljoin(base_url, anchor["href"].strip())
            text = self._clean_text(anchor)
            if not self._looks_like_chapter_link(f"{text} {href}"):
                continue
            chapters.append(
                ChapterData(
                    number=self._extract_number(text) or str(len(chapters) + 1),
                    title=text or f"Chapter {len(chapters) + 1}",
                    volume=self._extract_volume(text),
                    source_url=self._normalize_url(href),
                )
            )
        return self._dedupe_and_sort_chapters(chapters)

    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        images: List[str] = []
        for img in soup.find_all("img"):
            candidate = (
                img.get("data-src")
                or img.get("data-lazy-src")
                or img.get("data-original")
                or img.get("src")
            )
            if not candidate:
                continue
            candidate = urljoin(base_url, candidate.strip())
            if self._looks_like_image(candidate):
                images.append(candidate)
        return self._dedupe_ordered(images)

    def _extract_embedded_images(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        blobs: List[str] = []
        for tag in soup.find_all(["script", "style"]):
            text = tag.string or tag.get_text(" ", strip=True)
            if text:
                blobs.append(text)
        text = "\n".join(blobs)
        urls = self._find_image_urls(text, base_url)
        return self._dedupe_ordered(urls)

    def _extract_iframe_images(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        images: List[str] = []
        for iframe in soup.find_all("iframe", src=True):
            src = urljoin(base_url, iframe["src"])
            if self._looks_like_image(src):
                images.append(src)
        return self._dedupe_ordered(images)

    def _find_next_page(self, soup: BeautifulSoup, base_url: str) -> Optional[str]:
        candidates = []
        for selector in [
            'a[rel="next"]',
            'link[rel="next"]',
            'a.next',
            'button.next',
            'a[aria-label*="next" i]',
            'a[title*="next" i]',
            '.next a',
            '.nav-next a',
        ]:
            for node in soup.select(selector):
                href = node.get("href")
                if href:
                    candidates.append(urljoin(base_url, href))
        if candidates:
            return self._normalize_url(candidates[0])

        script_text = "\n".join(tag.get_text(" ", strip=True) for tag in soup.find_all("script"))
        for pattern in [
            r'next(?:Page|_page|Url|_url)?["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            r'["\']next["\']\s*:\s*["\']([^"\']+)["\']',
        ]:
            match = re.search(pattern, script_text, re.I)
            if match:
                return self._normalize_url(urljoin(base_url, unescape(match.group(1))))
        return None

    def _page_looks_like_chapter(self, soup: BeautifulSoup) -> bool:
        text = soup.get_text(" ", strip=True).lower()
        return "chapter" in text and bool(soup.find_all("img"))

    def _infer_content_type(self, soup: BeautifulSoup, jsonld: List[dict]) -> str:
        text = soup.get_text(" ", strip=True).lower()
        types = " ".join(str(item.get("@type", "")) for item in jsonld).lower()
        joined = f"{text} {types}"
        if "webtoon" in joined or "long strip" in joined:
            return "webtoon"
        if "manhwa" in joined:
            return "manhwa"
        return "manga"

    def _pick_text(self, soup: BeautifulSoup, selectors: List[str], default: str = "") -> str:
        for selector in selectors:
            node = soup.select_one(selector)
            if not node:
                continue
            if node.name == "meta":
                value = node.get("content")
            elif node.name == "title":
                value = node.get_text(" ", strip=True)
            else:
                value = node.get_text(" ", strip=True)
            if value:
                return value
        return default

    def _clean_text(self, node) -> str:
        if node is None:
            return ""
        return " ".join(node.stripped_strings) if hasattr(node, "stripped_strings") else str(node).strip()

    def _looks_like_chapter_link(self, text: str) -> bool:
        lowered = text.lower()
        if not self._chapter_hint_re.search(lowered):
            return False
        if any(blocked in lowered for blocked in ("login", "logout", "register", "privacy", "terms", "contact", "archive")):
            return False
        return True

    def _extract_number(self, text: str) -> Optional[str]:
        match = self._number_re.search(text)
        if match:
            return match.group(1)
        return None

    def _extract_volume(self, text: str) -> Optional[str]:
        match = re.search(r"(?:vol(?:ume)?\.?\s*)(\d+(?:\.\d+)?)", text, re.I)
        if match:
            return match.group(1)
        return None

    def _looks_like_image(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"))

    def _dedupe_ordered(self, items: List[str]) -> List[str]:
        seen = set()
        ordered = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    def _dedupe_and_sort_chapters(self, chapters: List[ChapterData]) -> List[ChapterData]:
        seen = set()
        ordered: List[ChapterData] = []
        for chapter in chapters:
            if chapter.source_url in seen:
                continue
            seen.add(chapter.source_url)
            ordered.append(chapter)
        return ordered

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))

    def _extract_json_ld(self, soup: BeautifulSoup) -> List[dict]:
        items: List[dict] = []
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = script.string or script.get_text(" ", strip=True)
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            if isinstance(parsed, list):
                items.extend([item for item in parsed if isinstance(item, dict)])
            elif isinstance(parsed, dict):
                items.append(parsed)
        return items

    def _jsonld_text(self, jsonld: List[dict], keys: tuple[str, ...], default: str = "") -> str:
        for item in jsonld:
            current: object = item
            ok = True
            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    ok = False
                    break
            if ok and isinstance(current, str) and current.strip():
                return current.strip()
        return default

    def _jsonld_image(self, jsonld: List[dict]) -> str:
        for item in jsonld:
            image = item.get("image")
            if isinstance(image, str) and image.strip():
                return image.strip()
            if isinstance(image, list) and image:
                first = image[0]
                if isinstance(first, str) and first.strip():
                    return first.strip()
                if isinstance(first, dict) and first.get("url"):
                    return first["url"]
        return ""

    def _jsonld_alt_titles(self, jsonld: List[dict]) -> List[str]:
        titles: List[str] = []
        for item in jsonld:
            alt = item.get("alternateName")
            if isinstance(alt, str):
                titles.append(alt)
            elif isinstance(alt, list):
                titles.extend([v for v in alt if isinstance(v, str)])
        return [title for title in titles if title]

    def _find_image_urls(self, text: str, base_url: str) -> List[str]:
        urls: List[str] = []
        for match in re.finditer(r'https?://[^"\']+\.(?:jpg|jpeg|png|gif|webp|bmp|avif)(?:\?[^"\']*)?', text, re.I):
            urls.append(self._normalize_url(match.group(0)))
        for match in re.finditer(r'["\']([^"\']+\.(?:jpg|jpeg|png|gif|webp|bmp|avif)(?:\?[^"\']*)?)["\']', text, re.I):
            candidate = match.group(1).strip()
            if candidate.startswith("http"):
                urls.append(self._normalize_url(candidate))
            else:
                urls.append(self._normalize_url(urljoin(base_url, candidate)))
        return urls
