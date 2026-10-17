# MangaVault

MangaVault is a Django web application for searching manga, importing series from supported sources, reading chapters in the browser, and downloading chapters or volumes as CBZ archives.

## Features

- Search MangaDex, Comick, MangaPill, and MangaKakalot from one interface.
- Import a series from search results or a supported URL.
- Read chapter pages through the built-in image proxy.
- Download individual chapters, volumes, or multiple chapters as CBZ files.
- Track download progress through the REST API.
- Use Celery and Redis for background downloads, with a local threaded fallback for development.

## Requirements

- Python 3.10 or newer
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

## Configuration

Copy `.env.example` to `.env` and set at least `DJANGO_SECRET_KEY` before deployment. Useful settings include:

| Variable | Purpose |
| --- | --- |
| `DJANGO_DEBUG` | Enables development behavior; use `false` in production. |
| `DJANGO_SECRET_KEY` | Django signing key; keep it private and stable. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames accepted by Django. |
| `DJANGO_DB_PATH` | SQLite database path. |
| `CORS_ALLOWED_ORIGINS` | Comma-separated trusted browser origins. |
| `CELERY_BROKER_URL` | Redis or another Celery broker URL. |
| `CELERY_RESULT_BACKEND` | Celery result backend URL. |

When `DJANGO_DEBUG=false`, HTTPS redirects, secure cookies, HSTS, and production static/media behavior are enabled. Configure the reverse proxy and static file serving accordingly.

## API endpoints

- `GET /api/sources/` — list scraper sources
- `GET /api/search/?q=<title>&source=all` — search sources
- `POST /api/import/` — import or refresh a manga
- `GET /api/manga/<id>/chapters/` — list chapters and volumes
- `POST /api/chapter/<id>/download/` — start a chapter download
- `POST /api/download/chapters/` — start a multi-chapter download
- `POST /api/download/volume/<id>/` — start a volume download
- `GET /api/task/<id>/` — inspect task progress

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

The second command is intended for a deployment configuration with `DJANGO_DEBUG=false` and a real secret key. Manga sources and their availability can change independently of this project; use the app only with content you are allowed to access and download.
