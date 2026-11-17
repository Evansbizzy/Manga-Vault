from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase

from core.scrapers.base import BaseScraper, MangaData
from core.scrapers.comick import ComickScraper
from core.scrapers.mangadex import MangaDexScraper
from core.scrapers.mangahere import MangaHereScraper
from core.scrapers.mangakakalot import MangaKakalotScraper
from core.scrapers.mangapill import MangaPillScraper
from core.scrapers.mangareader import MangaReaderScraper
from core.scrapers.mangaupdates import MangaUpdatesScraper
from core.scrapers.registry import (
    _normalize_title,
    _relevance_score,
    list_scrapers,
    search_all,
    search_all_progressively,
)
from core.scrapers.universal import UniversalHtmlScraper
from core.utils.network import safe_request


class SearchRankingTests(SimpleTestCase):
    def test_normalization_ignores_accents_and_punctuation(self):
        self.assertEqual(_normalize_title("  Café: Blue! "), "cafe blue")

    def test_exact_and_alternate_title_match_rank_higher_than_partial(self):
        exact = _relevance_score({"title": "cafe blue", "alt_titles": []}, "cafe blue")
        alternate = _relevance_score({"title": "other", "alt_titles": ["cafe blue"]}, "cafe blue")
        partial = _relevance_score({"title": "cafe blue season two", "alt_titles": []}, "cafe blue")
        typo = _relevance_score({"title": "cafe bue", "alt_titles": []}, "cafe blue")
        self.assertEqual(exact[0], 1.0)
        self.assertEqual(alternate[0], exact[0])
        self.assertGreater(partial[0], typo[0])

    def test_catalog_source_is_searchable_but_not_importable_or_readable(self):
        source = next(item for item in list_scrapers() if item["name"] == "mangaupdates")
        self.assertTrue(source["supports_search"])
        self.assertFalse(source["supports_url_import"])
        self.assertFalse(source["supports_read"])

    def test_search_all_includes_source_capabilities(self):
        class FixtureSource:
            name = "fixture"
            label = "Fixture"
            supports_search = True
            supports_url_import = False
            supports_read = False

            def search(self, query):
                return [MangaData(
                    title="Fixture Manga",
                    alt_titles=[],
                    author="Unknown",
                    artist="Unknown",
                    description="",
                    cover_url="",
                    status="unknown",
                    source_id="fixture-1",
                    content_type="manga",
                    chapters=[],
                    external_url="https://example.org/fixture-1",
                )]

        with patch("core.scrapers.registry.SCRAPER_CLASSES", {"fixture": FixtureSource}):
            results, statuses = search_all("Fixture Manga")

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["supports_import"])
        self.assertFalse(results[0]["supports_read"])
        self.assertEqual(statuses[0]["count"], 1)

    def test_progressive_search_yields_each_source_with_latency_metadata(self):
        class FixtureSource:
            name = "fixture-stream"
            label = "Fixture Stream"
            supports_search = True
            supports_url_import = True
            supports_read = True

            def search(self, query):
                return [MangaData(
                    title="Fixture Stream Manga",
                    alt_titles=[], author="Unknown", artist="Unknown", description="",
                    cover_url="", status="unknown", source_id="fixture-stream-1",
                    content_type="manga", chapters=[],
                )]

        with patch("core.scrapers.registry.SCRAPER_CLASSES", {"fixture-stream": FixtureSource}), \
                patch("core.scrapers.registry.cache.get", return_value=None), \
                patch("core.scrapers.registry.cache.set"):
            events = list(search_all_progressively("Fixture Stream Manga"))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source_status"]["status"], "ok")
        self.assertGreaterEqual(events[0]["source_status"]["duration_ms"], 0)
        self.assertEqual(events[0]["results"][0]["source_id"], "fixture-stream-1")


class MangaUpdatesScraperTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_search_maps_results_and_caches_the_api_response(self):
        scraper = MangaUpdatesScraper()
        response = Mock()
        response.json.return_value = {
            "results": [
                {"record": {
                    "series_id": 12345,
                    "title": "Example Manhwa",
                    "type": "Manhwa",
                    "image": {"url": {"thumb": "https://cdn.mangaupdates.com/example.jpg"}},
                }},
                {"record": {"series_id": "invalid", "title": "Bad result"}},
            ]
        }
        with patch.object(scraper, "post", return_value=response) as post:
            first_results = scraper.search("Example")
            second_results = scraper.search("Example")

        self.assertEqual(len(first_results), 1)
        self.assertEqual(first_results[0].title, "Example Manhwa")
        self.assertEqual(first_results[0].content_type, "manhwa")
        self.assertEqual(first_results[0].external_url, "https://www.mangaupdates.com/series.html?id=12345")
        self.assertEqual(second_results[0].source_id, "12345")
        post.assert_called_once()


class ExistingScraperFixtureTests(SimpleTestCase):
    def test_mangadex_maps_api_result(self):
        item = {
            "id": "manga-id",
            "attributes": {"title": {"en": "Fixture Manga"}, "altTitles": [{"ja": "別名"}], "tags": []},
            "relationships": [],
        }
        result = MangaDexScraper()._parse_manga_basic(item)
        self.assertEqual(result.title, "Fixture Manga")
        self.assertEqual(result.source_id, "manga-id")

    def test_comick_maps_search_json(self):
        scraper = ComickScraper()
        with patch.object(scraper, "_api_get", return_value=[{
            "slug": "fixture-manga", "title": "Fixture Manga", "md_covers": [], "md_authors": [],
        }]):
            results = scraper.search("Fixture Manga")
        self.assertEqual(results[0].title, "Fixture Manga")
        self.assertIn("/comic/fixture-manga", results[0].source_id)

    def test_comick_recognizes_current_official_host_not_lookalikes(self):
        self.assertTrue(ComickScraper.can_handle("https://comick.dev/comic/title"))
        self.assertTrue(ComickScraper.can_handle("https://api.comick.dev/chapter/id"))
        self.assertFalse(ComickScraper.can_handle("https://notcomick.dev/comic/title"))

    def test_mangapill_search_extracts_cover_and_title(self):
        response = Mock(
            text='<a href="/manga/12/fixture"><img src="/cover.jpg" alt="Fixture Manga"></a>',
            url="https://mangapill.com/search?q=Fixture",
        )
        scraper = MangaPillScraper()
        with patch.object(scraper, "get", return_value=response):
            results = scraper.search("Fixture")
        self.assertEqual(results[0].title, "Fixture Manga")
        self.assertEqual(results[0].cover_url, "https://mangapill.com/cover.jpg")

    def test_mangahere_search_extracts_series_link(self):
        response = Mock(
            text='<a href="/manga/fixture"><img alt="Fixture Manga" data-src="/cover.jpg"></a>',
            url="https://www.mangahere.cc/search?title=Fixture",
        )
        scraper = MangaHereScraper()
        with patch.object(scraper, "get", return_value=response):
            results = scraper.search("Fixture")
        self.assertEqual(results[0].title, "Fixture Manga")
        self.assertIn("/manga/fixture", results[0].source_id)

    def test_mangareader_search_extracts_series_link(self):
        response = Mock(
            text='<a href="/manga/fixture"><img alt="Fixture Manga" data-src="/cover.jpg"></a>',
            url="https://mangareader.to/search?keyword=Fixture",
        )
        scraper = MangaReaderScraper()
        with patch.object(scraper, "get", return_value=response):
            results = scraper.search("Fixture")
        self.assertEqual(results[0].title, "Fixture Manga")
        self.assertEqual(results[0].cover_url, "https://mangareader.to/cover.jpg")

    def test_legacy_mangakakalot_search_parses_old_markup(self):
        response = Mock(
            text='<div class="story_item"><a href="https://mangakakalot.com/manga/fixture"><span class="story_name">Fixture Manga</span></a></div>',
            url="https://mangakakalot.com/search/story/Fixture",
        )
        scraper = MangaKakalotScraper()
        with patch.object(scraper, "get", return_value=response):
            results = scraper.search("Fixture")
        self.assertEqual(results[0].title, "Fixture Manga")

    def test_universal_parser_uses_public_metadata_and_chapters(self):
        response = Mock(
            text='<html><head><meta property="og:title" content="Fixture Manga"></head><body><h1>Fixture Manga</h1><a href="/chapter-1">Chapter 1</a></body></html>',
            url="https://reader.example/manga/fixture",
        )
        scraper = UniversalHtmlScraper()
        with patch.object(scraper, "get", return_value=response):
            result = scraper.get_manga_details(response.url)
        self.assertEqual(result.title, "Fixture Manga")
        self.assertEqual(result.chapters[0].number, "1")


class SafeRequestTests(SimpleTestCase):
    @patch("core.utils.network.validate_public_http_url")
    def test_post_redirect_to_get_is_revalidated_and_drops_body(self, validate_url):
        redirect = Mock(status_code=303, headers={"Location": "https://public.example/result"})
        response = Mock(status_code=200, headers={})
        session = Mock()
        session.request.side_effect = [redirect, response]

        result = safe_request(session, "POST", "https://public.example/search", json={"q": "title"})

        self.assertIs(result, response)
        self.assertEqual([call.args[0] for call in session.request.call_args_list], ["POST", "GET"])
        self.assertNotIn("json", session.request.call_args_list[1].kwargs)
        self.assertEqual(validate_url.call_count, 2)


class BaseScraperRetryTests(SimpleTestCase):
    def test_retries_server_errors_but_returns_success(self):
        scraper = MangaUpdatesScraper()
        scraper.rate_limit_delay = 0
        scraper.max_retries = 2
        failing_response = Mock(status_code=503, headers={})
        failing_response.raise_for_status.side_effect = requests.HTTPError(response=failing_response)
        succeeding_response = Mock(status_code=200)
        with patch("core.scrapers.base.safe_request", side_effect=[failing_response, succeeding_response]) as request:
            with patch("core.scrapers.base.time.sleep"):
                self.assertIs(scraper.get("https://example.org"), succeeding_response)
        self.assertEqual(request.call_count, 2)
