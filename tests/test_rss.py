from __future__ import annotations

from app.collectors.rss import parse_rss_feed


def test_parse_rss_feed_extracts_item() -> None:
    feed = """<?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <title>Example Feed</title>
        <item>
          <guid>abc-123</guid>
          <title>OpenAI released a new Responses API capability</title>
          <link>https://example.com/openai-responses</link>
          <pubDate>Tue, 17 Mar 2026 10:00:00 GMT</pubDate>
          <description>Short release note summary.</description>
        </item>
      </channel>
    </rss>
    """

    items = parse_rss_feed(feed, source_name="OpenAI News", topic="llm")

    assert len(items) == 1
    item = items[0]
    assert item.topic == "llm"
    assert item.source_name == "OpenAI News"
    assert item.url == "https://example.com/openai-responses"
    assert item.raw_summary == "Short release note summary."
