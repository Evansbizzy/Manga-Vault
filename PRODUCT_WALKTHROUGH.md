# MangaVault Product Walkthrough

This guide explains the current app, the user journey, operator setup, and product work that would move MangaVault toward a polished self-hosted manga library and reader. It describes the code as it exists today; source availability and third-party policies can change.

## Product direction

MangaVault combines source discovery, a local library, browser reading, reading progress, and CBZ downloads. Mature self-hosted readers point to useful patterns: configurable reading direction and page fit, clear account boundaries, resume and progress sync, collection tools, and client interoperability. These are product references, not a promise of feature parity.

- [Mihon project](https://github.com/mihonapp/mihon): reader configuration, library organization, updates, and backups.
- [Komga OPDS guide](https://komga.org/docs/guides/opds/) and [reader integrations](https://komga.org/docs/guides/tritonpanels/): standards-based library access and progress-aware clients.
- [Kavita reader guide](https://wiki.kavitareader.com/guides/readers/comic-manga/) and [reading lists](https://wiki.kavitareader.com/guides/features/readinglists/): configurable reading and curated collections.
- [Kotatsu project](https://github.com/KotatsuApp/Kotatsu): useful reader/product reference. Its parser project is a separate Kotlin/JVM codebase with licensing and runtime implications, so its parsers are not embedded in this Django app.

Source integrations should use documented APIs or pages that permit automated access. MangaVault does not support bypassing paywalls, DRM, logins, CAPTCHA, anti-bot checks, or provider rate limits. Search presence does not establish a right to read or download a work.

## Reader journey

1. Open **Discover** and search a title across available sources. Results identify their source and whether they support import and reading. Catalog-only results open at that provider.
2. Import a result from a reader-capable source, or use a supported source URL.
3. Open a series from **Library** or its detail page. Review its chapters and volumes.
4. Choose **Read** to load chapter pages in the browser. The reader has continuous-scroll and single-page modes. Its LTR/RTL control changes single-page keyboard navigation. Mode and direction are remembered in this browser.
5. Reading progress is saved to the signed-in account on the server. Use the library's continue-reading link to resume.
6. Use chapter or volume download actions to create CBZ archives. Background work uses Celery/Redis when configured and a local development fallback otherwise.
7. Set each series to unread, reading, completed, paused, or dropped; add personal labels and find them through the library filter.

The reader uses an intersection observer to track the visible page instead of walking every image on each scroll event. This avoids repeated full-page scans on long chapters. Covers and reader pages use the source-aware image proxy where supported.

## Pages and navigation

- `/` is the discovery home page.
- `/search/` searches supported catalogs.
- `/library/` lists imported series and progress.
- `/manga/<id>/` shows series details, chapters, volumes, and actions.
- `/reader/<chapter-id>/` displays a chapter.
- `/about/`, `/privacy/`, `/terms/`, and `/content-policy/` describe the software and deployment policies.
- `/robots.txt` excludes private or operational paths from crawlers; a custom 404 page handles unknown URLs.

Public information pages link back into the app and to related policies. The application includes a custom SVG mark at `static/core/brand-mark.svg`, server-rendered page shells, page titles/descriptions, canonical URLs when configured, and semantic breadcrumbs.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. To create an administrator account, run `python manage.py createsuperuser`, then visit `/admin/`. In local `DEBUG=true` mode, Redis is optional. For background task processing, start Redis and run `celery -A manga_downloader worker --loglevel=info`.

## Operator setup

1. Set `DJANGO_SECRET_KEY` to a private random value, `DJANGO_DEBUG=false`, and `DJANGO_ALLOWED_HOSTS` to deployment hostnames.
2. Set `DJANGO_SITE_URL` to the public HTTPS origin for canonical URLs. Configure DNS and TLS at the hosting provider; this application cannot register a domain.
3. Set `SITE_CONTACT_EMAIL` so rights, terms, and privacy pages have a clear operator contact.
4. Configure PostgreSQL with `DATABASE_URL`, Redis with `REDIS_URL` and Celery broker/result URLs, and durable mounted paths for `MEDIA_ROOT` and `DOWNLOADS_DIR`. Serve collected static files and media through the chosen hosting stack.
5. Create administrator accounts directly. There is no public registration. Review the policy pages for the laws, sources, logging, retention, and complaint process applicable to the operator.
6. Confirm backups and restores, outbound network restrictions, log retention, monitoring, HTTPS, and source terms before making the instance public.

Manga, chapter, download, and progress endpoints are scoped to the signed-in account. Existing pre-ownership rows remain ownerless until an operator assigns them with `python manage.py claim_legacy_library <username>`. The starter policy pages are product documentation, not jurisdiction-specific legal advice.

## Current safeguards and boundaries

- Production app/API access requires authentication; login attempts and API operations are throttled.
- Scraper and image requests validate public network destinations and redirects; image/download responses have size and type checks.
- MangaUpdates is metadata discovery only. It is attributed, cached, and cannot be imported as a reader source.
- Scraper integrations are best-effort. Provider markup, rate limits, availability, and content permissions vary. A search result does not guarantee chapter availability.
- CI runs Django checks, verifies migration state, and executes the offline fixture/API regression suite.
- The user interface uses Django templates with inline JavaScript and no compiled frontend bundle. Lucide icons load from a deferred CDN script.

## Roadmap, in priority order

### Before inviting multiple users

1. Add account lifecycle controls, password reset, session management, privacy export/deletion, and an administrator audit trail.
2. Expand regression coverage for every parser, partial downloads, pagination, and concurrent background-task failures.
3. Add a deployment restore drill for the database, user settings, reading progress, and downloaded files.

### Reader and library quality

4. Add image fit options, touch/swipe navigation, and optional two-page spreads; keep reader preferences per account as well as per browser.
5. Add user-managed reading lists, favorites, and bulk actions; current reading statuses and personal labels are implemented.
6. Add pagination and incremental loading to large libraries and chapter lists; expose source health and cache status.
7. Add backup/restore for the database, user settings, reading progress, and downloaded files.

### Scale and interoperability

8. Add OPDS after defining account-safe authorization, pagination, metadata mapping, and reading-progress semantics.
9. Configure PostgreSQL, Redis, mounted durable files, and supervised Celery workers for hosted deployments; add retries and cancellation controls to background tasks.
10. Add per-source cache, timeout, and request budgets, plus monitoring and an explicit host allowlist for outbound fetches.
11. Evaluate additional sources one at a time. Prefer official APIs and explicit permissions, and verify actual chapter-reading support before advertising a source as readable.

## Maintenance commands

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py collectstatic
```

Use `python manage.py check --deploy` with production environment settings before deployment. Run the project's tests when changing scraper parsing, access control, downloads, or progress behavior. Check `codex.md` for the latest implementation handoff and unfinished work.
