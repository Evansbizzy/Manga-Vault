import re

from .base import BaseScraper, MangaData, ChapterData
from typing import List

class MangaDexScraper(BaseScraper):
    name = "mangadex"
    label = "MangaDex"
    base_url = "https://api.mangadex.org"
    supports_search = True
    supports_url_import = True

    @classmethod
    def can_handle(cls, reference: str) -> bool:
        lowered = reference.lower()
        return "mangadex.org" in lowered or bool(re.match(r"^[0-9a-f-]{36}$", reference))
    
    def get_headers(self):
        return {
            "User-Agent": "MangaDownloader/1.0",
            "Content-Type": "application/json"
        }

    def image_referer(self, image_url: str = "") -> str:
        return "https://mangadex.org/"
    
    def search(self, query: str) -> List[MangaData]:
        url = f"{self.base_url}/manga"
        params = {
            "title": query,
            "limit": 20,
            "includes[]": ["cover_art", "author", "artist"],
            "availableTranslatedLanguage[]": ["en", "fr"],
        }
        
        resp = self.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        results = []
        for item in data.get("data", []):
            manga = self._parse_manga_basic(item)
            results.append(manga)
        return results
    
    def get_manga_details(self, source_id: str) -> MangaData:
        # Get manga info
        source_id = self._normalize_source_id(source_id)
        url = f"{self.base_url}/manga/{source_id}"
        params = {"includes[]": ["cover_art", "author", "artist"]}
        
        resp = self.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        manga = self._parse_manga_basic(data["data"])
        
        # Get ALL chapters at once
        manga.chapters = self._get_all_chapters(source_id)
        return manga
    
    def _get_all_chapters(self, manga_id: str) -> List[ChapterData]:
        """
        Fetch EN and FR chapters only.
        NO fallback to all languages — if neither exists, return [].
        """
        chapters = []
        offset = 0
        limit = 500
        seen_hids = set()

        while True:
            url = f"{self.base_url}/manga/{manga_id}/feed"
            params = {
                "limit": limit,
                "offset": offset,
                "order[chapter]": "asc",
                "includes[]": ["scanlation_group"],
                "translatedLanguage[]": ["en", "fr"],
            }

            resp = self.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for ch in data.get("data", []):
                ch_id = ch["id"]
                if ch_id in seen_hids:
                    continue
                seen_hids.add(ch_id)

                attr = ch["attributes"]
                lang = attr.get("translatedLanguage", "en")

                # Hard gate — skip anything not EN or FR
                if lang not in ("en", "fr"):
                    continue

                chapters.append(ChapterData(
                    number=str(attr.get("chapter", "0")),
                    title=attr.get("title", "") or f"Chapter {attr.get('chapter', '0')}",
                    volume=str(attr.get("volume")) if attr.get("volume") else None,
                    source_url=ch["id"],
                    language=lang,
                ))

            total = data.get("total", 0)
            offset += limit
            if offset >= total:
                break

        return chapters
    
    def get_chapter_pages(self, chapter_id: str) -> List[str]:
        """Get all image URLs for a chapter"""
        chapter_id = self._normalize_source_id(chapter_id)
        url = f"{self.base_url}/at-home/server/{chapter_id}"
        
        resp = self.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        base = data["baseUrl"]
        chapter = data["chapter"]
        hash_val = chapter["hash"]
        
        # Build all image URLs
        return [f"{base}/data/{hash_val}/{filename}" 
                for filename in chapter["data"]]
    
    def _parse_manga_basic(self, data: dict) -> MangaData:
        attr = data["attributes"]
        rels = {r["type"]: r for r in data.get("relationships", [])}
        
        # Get cover
        cover_filename = ""
        if "cover_art" in rels:
            cover_filename = rels["cover_art"].get("attributes", {}).get("fileName", "")
        
        # Determine content type
        tags = []
        for tag in attr.get("tags", []):
            name = tag.get("attributes", {}).get("name", {})
            tag_name = name.get("en") or next(iter(name.values()), "")
            if tag_name:
                tags.append(tag_name.lower())
        content_type = "manga"
        if "webtoon" in tags or "long strip" in tags:
            content_type = "webtoon"
        elif "manhwa" in tags:
            content_type = "manhwa"
        
        return MangaData(
            title=attr.get("title", {}).get("en") or next(iter(attr.get("title", {}).values()), "Untitled"),
            alt_titles=[next(iter(t.values()), "") for t in attr.get("altTitles", []) if t],
            author=rels.get("author", {}).get("attributes", {}).get("name", "Unknown"),
            artist=rels.get("artist", {}).get("attributes", {}).get("name", "Unknown"),
            description=attr.get("description", {}).get("en") or next(iter(attr.get("description", {}).values()), ""),
            cover_url=f"https://uploads.mangadex.org/covers/{data['id']}/{cover_filename}",
            status=attr.get("status", "unknown"),
            source_id=data["id"],
            content_type=content_type,
            chapters=[]
        )

    def _normalize_source_id(self, value: str) -> str:
        if value.startswith("http://") or value.startswith("https://"):
            parts = [part for part in value.rstrip("/").split("/") if part]
            for part in parts:
                if re.match(r"^[0-9a-f-]{36}$", part):
                    return part
            if parts:
                return parts[-1]
        return value
