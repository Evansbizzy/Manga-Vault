# Codex Handoff

## Dependency and documentation update

- Updated `requirements.txt` to `Django>=5.2,<5.3`; the previously allowed Django 4.2 series reached end of extended support in April 2026.
- Updated `README.md` to state the Django 5.2 LTS requirement and Python 3.10 compatibility. Django 5.2 is supported through April 2028; review official release notes before a major/minor upgrade.
- The remaining dependencies are unchanged because the recently implemented features require no new packages, and WhiteNoise was deliberately removed to avoid breaking startup in environments where it is not installed.

## Current status

MangaVault now has a more prominent home-page discovery flow and expanded multi-source search, a real asynchronous bulk-download flow, and reduced query work for the library and chapter list. The app remains a Django/Python project; Kotatsu's parser runtime has not been embedded.

## Latest reliability and performance pass

- Removed the library API's per-manga chapter-count queries by using aggregate counts, and removed the chapter-list API's per-chapter volume lookup by building one volume map.
- Cached successfully extracted reader page URLs for 30 minutes, keyed by chapter and source URL, to avoid repeat scraper calls while navigating back to a chapter.
- Replaced the detail-page bulk-download placeholder (which only fetched the chapter list and falsely showed downloads as ready) with the batch-download API and task polling. The modal now displays actual task progress and links only to files that exist.
- Bulk tasks now report failed chapter numbers, finish as `failed` if no chapter succeeded, and retain partial success as a completed task with a clear failure summary.
- Bounded image-proxy transfers to 20 MiB, rejected non-image responses, used connect/read timeouts, and streamed upstream chunks instead of buffering without a size limit.

## SEO, accessibility, and deploy readiness pass

- Added configurable `DJANGO_SITE_URL` canonical tags, per-page title/description/robots metadata, semantic breadcrumbs, and a plain-text `/robots.txt` policy.
- Added a custom branded 404 response/template and gave the reader a single primary `h1`.
- Added deferred Lucide loading with a safe no-icon fallback if its CDN is unavailable; meaningful cover images have descriptive alt text and the hero stack remains intentionally decorative.
- Documented production static collection/serving, custom-domain DNS/HTTPS responsibilities, and canonical URL setup.
- Kept the library and search no-index because they are personal/interactive app surfaces; manga detail pages remain eligible for indexing.
- No custom domain can be registered from code. No compiled bundle or source maps exist to remove; app JavaScript is currently inline, so bundle splitting/source-map cleanup would be inapplicable until a frontend build pipeline exists.
- Django templates already server-render page shells and manga metadata. Search results and the personal library remain client-fetched intentionally; bulk-rendering user-specific records for crawlers is not useful.
- Removed the optional WhiteNoise dependency after it caused `runserver` to fail in an existing virtual environment that had not reinstalled requirements; production static files should be served by the configured host/reverse proxy instead.
- Startup diagnosis: `.venv/bin/python manage.py runserver --noreload` reproduced `ModuleNotFoundError: No module named 'whitenoise'` inside WSGI middleware loading. Removed that middleware/configuration and package requirement; WSGI import and Django checks now pass. This sandbox does not permit binding a local server socket, so full listener startup must be confirmed on the user's machine.

## Online comparison and security pass

- Compared official [Komga account/progress docs](https://komga.org/docs/guides/user-accounts/), [Kavita OPDS docs](https://wiki.kavitareader.com/guides/features/opds/), and [Suwayomi WebUI features](https://github.com/Suwayomi/Suwayomi-WebUI). Common mature features include access roles, per-user read progress, filters/sorting/categories, bulk actions, reading lists, and client sync. Implemented per-user chapter/page progress with resume from the library, plus format/source filters and sorting. Categories, OPDS/client sync, multi-user library separation, and advanced reader preferences remain roadmap work.
- Production requests now require a Django-authenticated session; built-in login/logout pages use CSRF-protected forms, API session auth checks CSRF, login attempts are throttled per IP, and production startup refuses the development secret or wildcard hosts. Local `DEBUG=true` behavior remains available.
- Added DRF anonymous/user throttles and stricter scopes for search, import, download, and image proxy requests; large batch downloads are capped at 100 chapters.
- Centralized scraper HTTP fetches through public-IP validation and manual redirect validation to block localhost/private-network SSRF via imported URLs, scraped page URLs, and the image proxy.
- Added a short DNS-validation cache to avoid repeating lookups for every reader image, capped image bodies, and reject SVG/HTML responses from the image proxy and chapter downloader.
- Replaced unsafe insertion of scraped manga/author/chapter text into `innerHTML` with text nodes/DOM APIs in detail/reader screens.
- Added a unique per-user/per-chapter progress model and API, reader auto-save/restore (localStorage for anonymous development), plus library continue-reading links. Added a schema migration.
- Remaining security caveats: built-in DRF throttling is best-effort rather than a DoS boundary; DNS checks are not IP-pinned to the HTTP socket and so do not fully eliminate DNS rebinding. Deploy with outbound network restrictions, reverse-proxy rate limits, a production cache, and monitoring. Authenticated users currently share one library and can mutate it; do not add untrusted users until ownership/roles are implemented.

## Product completeness roadmap

The following items are still worthwhile before describing the project as production-ready:

1. Add automated scraper fixtures/tests and a regression suite for import, duplicate handling, pagination, page extraction, partial download failures, and API query counts.
2. Add pagination/filtering to library and chapter APIs, and make list pages progressively load rather than returning every saved title/chapter at once.
3. Move persistent background work to a supervised Celery/Redis deployment; the in-process thread fallback is suitable for local use only and tasks currently have no cancellation/retry controls.
4. Add ownership/role checks and per-user libraries before inviting untrusted users; the production gate protects the app, but authenticated accounts share and can modify the same catalog.
5. Introduce per-source cache/timeout/rate-limit policies, user-visible source health, and clear attribution/terms checks. Scraper compatibility is inherently fragile and each source needs live validation.
6. Finish responsive reader controls (reading direction, keyboard/touch navigation, fit mode, and remembered progress), library filters/sorting, and accessible loading/error/empty states.
7. Replace SQLite with PostgreSQL and configure durable media/download storage, backups, structured monitoring, and production secrets/deployment settings for multi-user use.
8. Address image-proxy DNS rebinding/redirect safety with an explicit upstream host allowlist and add cache storage/CDN support if image traffic grows. The current proxy has scheme/private-IP checks, but DNS resolution can still change between validation and connection.

## Validation and resume

Latest validation passed: Django checks including `check --deploy`, Python compilation, `git diff --check`, migration consistency (`makemigrations --check`), migration application to both a temporary SQLite DB and the project DB, and read/save/library-progress API checks. Production middleware tests confirmed login redirects, API 401 responses, and CSRF rejection without a token. SSRF smoke checks blocked loopback, link-local metadata, file URLs, and redirects to loopback. No automated test suite currently exists. Next, add regression tests and complete ownership/category management before allowing untrusted multi-user access.

## Done in this pass

- Rebuilt `templates/core/index.html` into a responsive, dark editorial home page with a prominent search action, quick links, a stack of real library covers, and recently added manga.
- Added MangaHere/FanFox search, series metadata, chapter links, and best-effort chapter image extraction in `core/scrapers/mangahere.py`; source URLs are host-checked before import.
- Added MangaReader search in `core/scrapers/mangareader.py`, reusing the universal HTML parser for details and chapter pages while restricting URLs to its host.
- Registered MangaHere and included its per-source status in the existing all-source search.
- Improved result ranking in `core/scrapers/registry.py` to account for alternate titles, token overlap, prefixes, partial matches, and typo-level similarity.
- Exposed alternate titles through the search API and updated source documentation in `README.md`.
- Fixed MangaHere chapter extraction through its `chapterfun.ashx` reader endpoint, including packed JavaScript URL decoding and paginated chapter image pages.
- Canonicalized MangaHere chapter-page URLs to the series URL and repaired malformed existing MangaHere records on their detail API request; the title, cover, canonical URL, and chapter URLs refresh together.
- Routed covers and reader pages through a source-aware image proxy so upstream sites receive the expected `Referer` header.
- Retained the prior search UX, safe DOM rendering, per-source health reporting, and local `.gitignore` from earlier work.

## Kotatsu parser integration decision

`https://github.com/KotatsuApp/kotatsu-parsers` is a Kotlin/JVM and Android library, whereas this application is Python/Django. Its documented usage also requires a custom `MangaLoaderContext`; it cannot be installed as a Python dependency or called directly by the current scraper classes. The upstream repository is archived/read-only and GPL-3.0. A real integration would require a separate JVM service/bridge and a deliberate license/distribution decision. Do not copy the Kotlin parser implementations into this repository or add an untested sidecar as if it were working integration.

