# Codex Handoff

## Five priority improvements (2026-11-12)

- **Account isolation:** added `Manga.owner` and owner-scoped uniqueness. Imports, library APIs, series/chapter/page/progress/download/task/delete endpoints, reader/detail pages, and chapter/volume file responses now require and scope to the account owner. The migration preserves legacy rows as ownerless. This local database had one account, so its 37 legacy titles were assigned to that account after verifying it was the sole user. On another database, review ownership and run `python manage.py claim_legacy_library <username>` explicitly.
- **Library organization:** added per-title reading status (`unread`, `reading`, `completed`, `paused`, `dropped`) and up to 12 personal labels, including a library status filter and label search. The series API validates owner-scoped changes.
- **Scraper and regression reliability:** added offline progressive-search and cross-account API regression cases; CI runs Django system checks, migration drift checks, and the test suite on pushes and pull requests. Provider duration/cache/result logs and UI timing badges show source health for each streamed search.
- **Production setup:** added `DATABASE_URL` support for PostgreSQL or SQLite, `REDIS_URL` shared cache support, environment-configurable durable media/download paths, a DB/cache `/healthz/` endpoint, console source logs, and disabled thread fallback in production by default. When a broker is down in production, the task is marked failed and the API returns 503 rather than silently launching unmanaged work. Added the PostgreSQL driver requirement.
- **Documentation:** updated README and walkthrough with migration/legacy-claim steps, account ownership, deployment variables, CI, and current remaining tasks.
- **Validation:** Django system checks, migration drift check, Python compilation, template loading, JavaScript syntax, `git diff --check`, and all 24 offline tests passed. `/healthz/` returned `200 ok`. Migrations `0005_manga_owner` and `0006_manga_library_organization` were applied locally, and all 37 legacy titles were assigned to the sole existing account. `check --deploy` reports the expected development-mode HTTPS/DEBUG warnings; production environment settings were not supplied for a clean deploy check.
- **Remaining:** other databases with legacy rows need an explicit claim command. Production hosting still needs actual PostgreSQL/Redis, durable volume mounts, worker supervision, backups/restore drill, and proxy streaming configuration. Expand parser fixtures and add worker retry/cancellation coverage before calling the service production-ready.

## Progressive search and source timing (2026-11-12)

- Added `GET /api/search/stream/?q=<title>`, an authenticated/throttled NDJSON endpoint that yields each provider's results as soon as its concurrent request finishes. It sends `Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no` so a reverse proxy can forward events instead of buffering the whole response.
- The search UI now consumes the stream, shows each source as searching/complete/unavailable, renders early matches, and preserves cancellation when a new query replaces an old one. Single-source searches still use the existing JSON endpoint.
- Each source event includes `duration_ms` and cache status. Backend logs record source, duration, cache hit, result count, and success/failure for operational comparison.
- Validation: Django system check, Python compilation, search-template loading, JavaScript syntax check, and `git diff --check` passed. Automated tests were not run in this pass.
- Stop point: progressive all-source results and source timing are implemented. Confirm that the actual production proxy forwards NDJSON chunks without buffering. Next, instrument p50/p95 by source in deployment and tune shared Redis caching and source timeouts from those measurements.

## Search latency and rendering pass (2026-11-11)

- Reviewed the requested Open Otaku site, but the web viewer could not fetch its pages and I could not verify that the public OtakuReader repository is its implementation. That repository's README describes direct MangaDex/ComicK source adapters, local reading history, and offline/PWA support; MangaVault keeps its server-side provider adapters and uses bounded, cached source requests rather than adding unverified proxy rotation.
- Search now queries enabled providers concurrently (up to eight workers), caches each provider's successful results for three minutes, and exposes cache hits in the source status row. Provider failures are not cached.
- Search workers make one bounded-latency attempt so slow or retrying hosts do not add several backoff periods. MangaDex, Comick, MangaPill, MangaHere, and MangaReader search calls now use explicit connect/read timeouts. Import, chapter detail, and download retry behavior remains separate.
- Search results still include every relevant result from each provider, but the browser appends them in batches of 24. This reduces initial DOM construction and image requests while preserving the complete list behind a Show more button.
- The home-page manga query now annotates chapter counts in SQL, removing the per-card count query.
- Method references: [Django low-level cache API](https://docs.djangoproject.com/en/6.1/topics/cache/), [Requests timeout guidance](https://requests.readthedocs.io/en/latest/user/advanced/), and the [OtakuReader README](https://github.com/jrspapio-lab/otakureader). The requested live site's relation to that repository remains unverified.
- Stop point: search cache/concurrency, provider search timeouts, batched display, and home-page query optimization are implemented. Django system checks, targeted compilation, and whitespace validation remain to be run; the automated tests are intentionally not run in this pass. Next, measure provider-specific latency and cache hit rate in the deployment environment; consider Redis-backed shared caching and cursor pagination only if those measurements justify them.

## Open Otaku comparison and UX update (2026-11-11)

- Attempted to inspect `https://open-otaku.me` directly, but the public web viewer could not load the domain. Search surfaced the `jrspapio-lab/otakureader` repository; its README describes an API-adapter design for MangaDex/ComicK, paged LTR/RTL and Webtoon reading, local downloads, library search/filtering, history, PWA installation, and app-shell offline behavior. I could not confirm that repository is the code behind the requested domain or inspect its live UI/source implementation.
- MangaVault already has server-side source adapters, source selection, CBZ downloads, reader modes, and library filters. Added two practical interface improvements: the home page now shows the signed-in user's unfinished reading progress with direct chapter/page resume links, and discovery result cards explain whether a result imports into the reader or only opens as an external catalog listing.
- Home reading history is scoped to the signed-in user and excludes completed chapters. No schema or dependency changes were needed. README and this handoff were updated.
- Stop point: personalized continue-reading and explicit source-capability labels are implemented. This comparison did not justify adding proxy rotation or blanket challenge bypassing. Next useful improvements are library categories/status filters, chapter release notifications, and a separately designed installable/offline experience that does not cache authenticated pages or API responses.

## Product polish and walkthrough (2026-11-11)

- Compared mature reader/library workflows from Mihon, Komga, Kavita, and Kotatsu. Useful patterns include reader preferences, progress continuity, library organization, account boundaries, backups, and OPDS interoperability. `PRODUCT_WALKTHROUGH.md` includes source links, user/operator workflows, limitations, and a staged roadmap.
- Added public About, Privacy, Terms of Service, and Content Policy pages, footer links, and `SITE_CONTACT_EMAIL` configuration for operator contact details. The starter policies explain source limitations and require operator review before public deployment.
- Added a custom vector identity at `static/core/brand-mark.svg` and connected it to the browser favicon, navbar, and footer.
- Improved reader controls with remembered scroll/page mode and LTR/RTL keyboard navigation. Progress restoration resumes the saved page in scroll mode, and visibility tracking uses `IntersectionObserver` instead of scanning every page on every scroll event.
- Updated `README.md` with reader controls, contact configuration, policy pages, and product guide.
- Historical stop point: the shared library had no ownership boundary at that stage. Account-level ownership and regression coverage were added in the 2026-11-12 priority pass above. Remaining reader fit/touch/spread settings, reading lists, OPDS, backup/restore, and source permission checks remain future work.

## Chapter and search reliability (2026-11-11)

- Added a shared 15-minute cache for successfully extracted chapter page URLs. Browser reading and CBZ downloads now use the same validated page list, so the two paths cannot silently disagree about whether a chapter has pages.
- A chapter import is rejected before writing database records if the source returns no usable title, stable series ID, or chapter links. The generic HTML importer no longer invents a chapter just because a URL contains the word `chapter`; it must find reader images.
- MangaPill extraction now checks reader-specific/lazy image attributes and page alt text and no longer mistakes every image on the `mangapill` host for a page. The currently indexed official Naruto Chapter 5 page lists 19 reader pages ([MangaPill Chapter 5](https://mangapill.com/chapters/3069-10005000/naruto-chapter-5)); the previous parser could miss extensionless CDN links.
- MangaDex page extraction falls back to the API's `dataSaver` filename list when full-quality `data` is absent.
- CBZ creation validates image signatures, retries image requests, and fails with the page numbers that could not be retrieved instead of creating a successful-looking partial archive. Archive writes are atomic, language variants have distinct filenames, and existing archives are reused only when their current filename/page count/size are consistent.
- Older partial downloads are marked unavailable when a repair is attempted. The task UI now shows the failure reason and accurately labels partial completion. Volume builds validate each chapter before packaging.
- Search rejects one-character queries, drops malformed/weakly relevant results, reports counts for matches actually shown, and omits legacy MangaKakalot search because that endpoint is parked/unavailable. Legacy URL imports remain enabled.
- Stop point: reliability guards and source-specific parser fixes are implemented. External sources can still remove chapters, block requests, or change markup; these now produce an explicit source/page failure rather than an empty or partial archive. `python3 manage.py check`, Python compilation, and `git diff --check` passed. The automated suite was not run in this pass. Next, add regression tests for every parser's page extraction and verify these sources from the user's network, since upstream access and markup vary by region and hosting provider.

## Dependency and documentation update

- Updated `requirements.txt` to `Django>=5.2,<5.3`; the previously allowed Django 4.2 series reached end of extended support in April 2026.
- Updated `README.md` to state the Django 5.2 LTS requirement and Python 3.10 compatibility. Django 5.2 is supported through April 2028; review official release notes before a major/minor upgrade.
- The remaining dependencies are unchanged because the recently implemented features require no new packages, and WhiteNoise was deliberately removed to avoid breaking startup in environments where it is not installed.

## Current status

MangaVault now has a more prominent home-page discovery flow and expanded multi-source search, a real asynchronous bulk-download flow, and reduced query work for the library and chapter list. The app remains a Django/Python project; Kotatsu's parser runtime has not been embedded.

## Scraper reliability and catalog expansion

- Added MangaUpdates as an additional searchable catalog through its documented public API. It provides metadata and an attributed external link only; it is explicitly not importable or readable in MangaVault, so it cannot create empty reader entries.
- Cached MangaUpdates title searches for six hours and mapped results defensively, ignoring malformed IDs and duplicate records. Its source label is visible on results and links back to the provider as attribution.
- Updated Comick's API/site base URLs to the current official `.dev` hosts, retained legacy URL recognition, and replaced substring host detection with exact domain/subdomain validation.
- Extended source capability metadata to identify search, URL import, and reading support; the search UI opens metadata-only results externally while retaining the existing import flow for reader sources.
- Improved title normalization to ignore accents and punctuation and updated relevance ranking to blend exact/substring matches, token coverage, and fuzzy similarity.
- Routed scraper GET and POST calls through the SSRF-safe request helper, manually validating redirect destinations and converting POST redirects to GET where HTTP semantics require it. Retried transient server errors and honored numeric `Retry-After` values.
- Added offline fixture tests for the existing scraper parsers, MangaUpdates mapping/cache, search ranking, redirect validation, and transient retries. Tests found and fixed a generic-parser bug: `_pick_text` received `(selector, attribute)` tuples but treated them as CSS selector strings, breaking metadata extraction.
- Follow-up runtime fix: aggregate search referenced `scraper_cls` after leaving its worker scope, causing `Search failed: name 'scraper_cls' is not defined`. Source capabilities are now carried in each worker result, with a regression test for all-source search.
- The new source expands discovery, not chapter-reading coverage. MangaUpdates terms require attribution and reasonable spacing/caching. Do not add sources that require bypassing access controls, paywalls, CAPTCHA, or anti-bot restrictions; next prioritize documented, stable reading APIs or openly accessible sources whose terms permit automated use.

## Stop point and next work

This pass stops after one API-based catalog source, a Comick API-host refresh, shared search improvements, safe redirect-aware requests, and regression tests. The complete Django test suite passes (15 tests), as do system checks, Python compilation, and `git diff --check`. Next, evaluate candidate reading sources individually for public API/terms, current uptime, and whether chapter pages are explicitly available for integration. Keep metadata-only sources separate from sources that can be imported/read; do not increase the source count with broken or non-reading entries just to inflate the list.

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
- Remaining security caveats: built-in DRF throttling is best-effort rather than a DoS boundary; DNS checks are not IP-pinned to the HTTP socket and so do not fully eliminate DNS rebinding. Deploy with outbound network restrictions, reverse-proxy rate limits, a shared production cache, and monitoring.

## Product completeness roadmap

The following items are still worthwhile before describing the project as production-ready:

1. Expand the existing scraper fixture tests and add regression coverage for import, duplicate handling, pagination, page extraction, partial download failures, and API query counts.
2. Add pagination/filtering to library and chapter APIs, and make list pages progressively load rather than returning every saved title/chapter at once.
3. Move persistent background work to a supervised Celery/Redis deployment; the in-process thread fallback is suitable for local use only and tasks currently have no cancellation/retry controls.
4. Add administrator audit logs, password reset/session controls, and a privacy export/delete workflow for multi-account deployments.
5. Introduce per-source cache/timeout/rate-limit policies, user-visible source health, and clear attribution/terms checks. Scraper compatibility is inherently fragile and each source needs live validation.
6. Extend reader controls with image fit, touch navigation, and two-page spreads; move preferences from browser-only storage to account settings. Improve accessible loading/error/empty states.
7. Replace SQLite with PostgreSQL and configure durable media/download storage, backups, structured monitoring, and production secrets/deployment settings for multi-user use.
8. Address image-proxy DNS rebinding/redirect safety with an explicit upstream host allowlist and add cache storage/CDN support if image traffic grows. The current proxy has scheme/private-IP checks, but DNS resolution can still change between validation and connection.

## Validation and resume

Previous implementation passes recorded successful deployment checks, migration checks, API progress checks, production middleware checks, and SSRF smoke checks. See the current priority-pass validation at the top of this file; the test status below refers to earlier work.

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

