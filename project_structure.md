manga_downloader/
├── manage.py
├── requirements.txt
├── manga_downloader/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── core/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── mangadex.py
│   └── utils/
│       ├── __init__.py
│       └── packager.py
├── api/
│   ├── __init__.py
│   ├── urls.py
│   └── views.py
└── templates/
    └── core/
        ├── base.html
        ├── index.html
        ├── manga_detail.html
        └── search.html
