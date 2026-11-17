# MangaVault

MangaVault is a Django web application for searching manga, importing series from supported sources, reading chapters in the browser, and downloading chapters or volumes as CBZ archives.

## Features

- Search MangaDex, Comick, MangaPill, MangaHere/FanFox, MangaReader, and MangaUpdates from one interface. Legacy MangaKakalot links remain importable, but its unavailable search endpoint is excluded from results.
- Import a series from search results or a supported URL.
- Read chapter pages through the built-in image proxy.
- Download individual chapters, volumes, or multiple chapters as CBZ files.
- Track download progress through the REST API.
- Resume chapters from saved page progress and filter/sort the library by format, source, and title.
- Continue reading from the personalized home page, with chapter and page progress at a glance.
- Keep separate private libraries per account, with reading status and personal labels for organizing titles.
- Choose continuous-scroll or single-page reading, set left-to-right or right-to-left navigation, and resume saved progress.
- Reject empty chapter imports, filter weak search matches, and avoid marking partial CBZ files as successful downloads.
- Use Celery and Redis for background downloads, with a local threaded fallback for development.
- Use the custom MangaVault SVG identity and public About, Privacy, Terms, and Content Policy pages.
- Search results show whether a source supports in-app import and reading or is a catalog-only outbound link.
- Search fans out to all enabled providers concurrently, caches successful per-source results briefly, and renders large result sets in batches to keep repeat searches and the initial page responsive.
- All-source searches stream each provider's results as it finishes and show per-source response time/cache status, so one slow provider no longer hides the faster matches.

## Requirements

- Python 3.10 or newer
- Django 5.2 LTS (`requirements.txt` keeps the project on this supported series)
- `pip`
- Redis and a Celery worker for production/background processing

## Quick start

```bash
git clone <your-repository-url>
cd manga-vault
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. Create an account before importing or using the private library. The main workflow is available at `/search/`; the admin site is available at `/admin/` after creating a superuser:

```bash
python manage.py createsuperuser
```

The development defaults use SQLite and do not require Redis for the web server to start. If Redis is not running, download tasks use the local fallback. For queued background jobs, run:

```bash
redis-server
celery -A manga_downloader worker --loglevel=info
```

Django 5.2 is selected because it supports Python 3.10 and remains in security support through April 2028. `requirements.txt` constrains installation to the 5.2 series; review Django's release notes before changing that range.

## Configuration

Copy `.env.example` to `.env` and set at least `DJANGO_SECRET_KEY` before deployment. Useful settings include:

| Variable | Purpose |
| --- | --- |
| `DJANGO_DEBUG` | Enables development behavior; use `false` in production. |
| `DJANGO_SECRET_KEY` | Django signing key; keep it private and stable. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames accepted by Django. |
| `DJANGO_SITE_URL` | Public HTTPS origin used to generate canonical page URLs, for example `https://manga.example.com`. Leave blank for local development. |
| `SITE_CONTACT_EMAIL` | Instance operator contact shown on privacy, terms, and content policy pages. |
| `DJANGO_DB_PATH` | SQLite database path. |
| `CORS_ALLOWED_ORIGINS` | Comma-separated trusted browser origins. |
| `CELERY_BROKER_URL` | Redis or another Celery broker URL. |
| `CELERY_RESULT_BACKEND` | Celery result backend URL. |

When `DJANGO_DEBUG=false`, the app requires a non-default secret key and a configured host, enables HTTPS redirects, secure cookies, and HSTS, and requires an authenticated account to access the app and API. Sign-in is limited to 10 failed attempts per client IP per 15-minute window. Create accounts through Django admin; there is no public registration. Manga, chapters, downloads, reading progress, and library organization are scoped to the account owner. Legacy rows from before ownership was added remain unclaimed until an administrator assigns them with `python manage.py claim_legacy_library <username>`.

For production, configure PostgreSQL with `DATABASE_URL`, Redis with `REDIS_URL` and the Celery broker/result URLs, and mount durable volumes at `MEDIA_ROOT` and `DOWNLOADS_DIR`. The local cache and threaded download fallback are development defaults; background execution falls back to a local thread only when `DEBUG=true` (or `ALLOW_LOCAL_TASK_FALLBACK=true` is explicitly set). Run a Celery worker under a process supervisor. `/healthz/` checks database and cache availability. Configure database and file backups, run `python manage.py check --deploy`, and serve collected static files and media through the hosting stack. MangaVault renders page shells and manga details on the server; search results and the personal library load dynamically.

### Custom domain and indexing

The application cannot register a domain for you. Purchase a domain from a registrar, point its DNS records to your hosting provider, configure HTTPS there, then set `DJANGO_SITE_URL` to the exact public origin and include the domain in `DJANGO_ALLOWED_HOSTS`. Canonical tags are emitted only when `DJANGO_SITE_URL` is set. `/robots.txt` permits public pages and excludes the API, admin, reader, library, and download paths from crawlers. Search, library, reader, and error pages are marked `noindex`; manga detail pages can be indexed.

The site uses one heading per primary page, unique page titles and descriptions, semantic breadcrumbs, and descriptive image alternatives where images convey content. It has no compiled JavaScript bundle or source-map output; its interactive search and reader code is currently inline, and Lucide is loaded from a deferred CDN script. Scraper requests reject non-public IPs and revalidate redirect targets; API requests have per-IP/user rate limits. These are application safeguards, not a replacement for a firewall, reverse-proxy limits, or production monitoring.

MangaUpdates is a metadata-only discovery source: its result links open on MangaUpdates and cannot be imported or read inside MangaVault. Results visibly credit the provider, and searches are cached for six hours in accordance with its API guidance on attribution, spacing, and caching. See the [MangaUpdates API documentation](https://mangaupdates.apidocumentation.com/) for its current usage requirements.

Other source searches use a short three-minute cache. A failed provider response is not cached, so retrying can recover as soon as that source is available. Search requests use a bounded timeout and one attempt; imports and chapter extraction retain their normal retry behavior. The home page aggregates chapter counts with its manga query instead of issuing a separate count query for every card.

All-source discovery uses `GET /api/search/stream/?q=<title>` and returns newline-delimited JSON events. Deployments should preserve streaming responses and disable reverse-proxy buffering for that route; the endpoint sends `X-Accel-Buffering: no` for Nginx. Per-source timing is also logged to help identify slow or unhealthy providers. CI runs Django checks, verifies migrations, and runs the fixture/API regression suite on pushes and pull requests.

## Product guide and policies

See [PRODUCT_WALKTHROUGH.md](PRODUCT_WALKTHROUGH.md) for the user and operator walkthrough, product comparison, current limitations, and prioritized roadmap. The app includes `/about/`, `/privacy/`, `/terms/`, and `/content-policy/`; operators should set `SITE_CONTACT_EMAIL` and adapt the starter policy text before public deployment. Policy pages are software documentation and do not replace legal review.

The reader remembers mode and reading direction in browser storage. Chapter progress is stored server-side per account. Each account can assign a reading status and up to 12 personal labels to a title, then filter its library by status or label.

## API endpoints

- `GET /api/sources/`: list scraper sources
- `GET /api/search/?q=<title>&source=all`: search sources
- `GET /api/search/stream/?q=<title>`: receive all-source results as NDJSON events
- `GET /healthz/`: check database and cache readiness
- `POST /api/import/`: import or refresh a manga
- `GET /api/manga/<id>/chapters/`: list chapters and volumes
- `POST /api/chapter/<id>/download/`: start a chapter download
- `POST /api/download/chapters/`: start a multi-chapter download
- `POST /api/download/volume/<id>/`: start a volume download
- `GET /api/task/<id>/`: inspect task progress

Private catalog APIs and chapter files require an authenticated owner. Use the Django admin to create accounts; public registration is disabled.

## Project layout

```text
api/                 REST API views and routes
core/                Models, pages, scrapers, tasks, and download services
manga_downloader/    Django settings, WSGI, ASGI, and Celery config
templates/           Server-rendered web interface
manage.py            Django management entry point
```

## Checks

```bash
python manage.py check
python manage.py check --deploy
```

The second command is intended for a deployment configuration with `DJANGO_DEBUG=false` and a real secret key. Manga sources and their availability can change independently of this project; use the app only with content you are allowed to access and download. Site parsers are best-effort integrations: some sites may block automated requests, change markup, limit chapters, or require browser-specific JavaScript.
