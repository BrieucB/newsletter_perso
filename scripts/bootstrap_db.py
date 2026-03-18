from __future__ import annotations

from app.db import init_db
from app.settings import load_settings


def main() -> None:
    settings = load_settings()
    init_db(settings.db_path)
    print(f"Initialized {settings.db_path}")


if __name__ == "__main__":
    main()
