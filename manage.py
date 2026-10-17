#!/usr/bin/env python3
"""Django's command-line utility for administrative tasks."""

import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _rerun_with_venv_python() -> None:
    venv_python = BASE_DIR / ".venv" / "bin" / "python"
    if not venv_python.exists() or Path(sys.executable).resolve() == venv_python.resolve():
        return

    os.execv(str(venv_python), [str(venv_python), *sys.argv])


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "manga_downloader.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        _rerun_with_venv_python()
        raise ImportError(
            "Couldn't import Django. Activate the virtual environment with "
            "`source .venv/bin/activate`, or install dependencies with "
            "`python3 -m pip install -r requirements.txt`."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
