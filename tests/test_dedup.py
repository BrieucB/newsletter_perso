from __future__ import annotations

from pathlib import Path

from app.db import connect, init_db
from app.models import NormalizedItem
from app.repositories.items import ItemsRepository
from app.utils.hashing import stable_hash
from app.utils.text import normalize_title


def test_upsert_normalized_item_deduplicates_by_normalized_title(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)
    connection = connect(db_path)
    repo = ItemsRepository(connection)
    source_id = repo.ensure_source(
        kind="rss", name="OpenAI News", config={"url": "https://example.com"}
    )

    item_a = NormalizedItem(
        topic="llm",
        source_kind="rss",
        source_name="OpenAI News",
        external_id="1",
        title="OpenAI ships new evaluation tooling",
        url="https://example.com/a",
        authors=[],
        raw_summary="Summary A",
        raw_payload={"a": 1},
        tags=[],
    )
    item_b = item_a.model_copy(update={"external_id": "2", "url": "https://example.com/b"})

    first_id = repo.upsert_normalized_item(
        source_id=source_id,
        normalized_item=item_a,
        normalized_title=normalize_title(item_a.title),
        content_hash=stable_hash([item_a.title, item_a.raw_summary or "", item_a.url]),
    )
    second_id = repo.upsert_normalized_item(
        source_id=source_id,
        normalized_item=item_b,
        normalized_title=normalize_title(item_b.title),
        content_hash=stable_hash([item_b.title, item_b.raw_summary or "", item_b.url]),
    )

    assert first_id == second_id
    count = connection.execute("SELECT COUNT(*) AS count FROM items").fetchone()["count"]
    assert count == 1
