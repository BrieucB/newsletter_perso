from __future__ import annotations

from app.collectors.arxiv import parse_arxiv_feed


def test_parse_arxiv_feed_extracts_expected_fields() -> None:
    feed = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/1234.5678v1</id>
        <updated>2026-03-17T12:00:00Z</updated>
        <published>2026-03-17T12:00:00Z</published>
        <title>Simulation-based inference for inverse problems</title>
        <summary>We study surrogate-assisted inference.</summary>
        <author><name>Alice Example</name></author>
        <author><name>Bob Example</name></author>
        <link href="http://arxiv.org/abs/1234.5678v1" rel="alternate" type="text/html" />
      </entry>
    </feed>
    """

    items = parse_arxiv_feed(feed, source_name="arXiv: uq", query="simulation-based inference")

    assert len(items) == 1
    item = items[0]
    assert item.topic == "uq_hpc"
    assert item.source_kind == "arxiv"
    assert item.title == "Simulation-based inference for inverse problems"
    assert item.authors == ["Alice Example", "Bob Example"]
    assert item.url == "http://arxiv.org/abs/1234.5678v1"
