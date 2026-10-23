# MangaVault

MangaVault is a Django web application for searching manga, importing series from supported sources, reading chapters in the browser, and downloading chapters or volumes as CBZ archives.

## Features

- Search MangaDex, Comick, MangaPill, MangaHere/FanFox, MangaReader, and legacy MangaKakalot from one interface.
- Import a series from search results or a supported URL.
- Read chapter pages through the built-in image proxy.
- Download individual chapters, volumes, or multiple chapters as CBZ files.
- Track download progress through the REST API.
- Resume chapters from saved page progress and filter/sort the library by format, source, and title.
- Use Celery and Redis for background downloads, with a local threaded fallback for development.

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

Open <http://127.0.0.1:8000/>. The main workflow is available at `/search/`; the admin site is available at `/admin/` after creating a superuser:

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
| `DJANGO_DB_PATH` | SQLite database path. |
| `CORS_ALLOWED_ORIGINS` | Comma-separated trusted browser origins. |
| `CELERY_BROKER_URL` | Redis or another Celery broker URL. |
| `CELERY_RESULT_BACKEND` | Celery result backend URL. |

When `DJANGO_DEBUG=false`, the app requires a non-default secret key and a configured host, enables HTTPS redirects, secure cookies, and HSTS, and requires an authenticated account to access the app and API. Sign-in is limited to 10 failed attempts per client IP per 15-minute window. Create the first account with `python manage.py createsuperuser`, then sign in at `/accounts/login/`. Accounts are created through Django admin; there is no public registration. The library is currently shared across authenticated accounts. Run `python manage.py collectstatic` during deployment and configure the web server or hosting platform to serve `staticfiles/` and uploaded media. MangaVault renders its page shells and manga details on the server; search results and the personal library are loaded dynamically because they are interactive/local data.

### Custom domain and indexing

The application cannot register a domain for you. Purchase a domain from a registrar, point its DNS records to your hosting provider, configure HTTPS there, then set `DJANGO_SITE_URL` to the exact public origin and include the domain in `DJANGO_ALLOWED_HOSTS`. Canonical tags are emitted only when `DJANGO_SITE_URL` is set. `/robots.txt` permits public pages and excludes the API, admin, reader, library, and download paths from crawlers. Search, library, reader, and error pages are marked `noindex`; manga detail pages can be indexed.

The site uses one heading per primary page, unique page titles and descriptions, semantic breadcrumbs, and descriptive image alternatives where images convey content. It has no compiled JavaScript bundle or source-map output; its interactive search and reader code is currently inline, and Lucide is loaded from a deferred CDN script. Scraper requests reject non-public IPs and revalidate redirect targets; API requests have per-IP/user rate limits. These are application safeguards, not a replacement for a firewall, reverse-proxy limits, or production monitoring.

## API endpoints

- `GET /api/sources/`: list scraper sources
- `GET /api/search/?q=<title>&source=all`: search sources
- `POST /api/import/`: import or refresh a manga
- `GET /api/manga/<id>/chapters/`: list chapters and volumes
- `POST /api/chapter/<id>/download/`: start a chapter download
- `POST /api/download/chapters/`: start a multi-chapter download
- `POST /api/download/volume/<id>/`: start a volume download
- `GET /api/task/<id>/`: inspect task progress

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
