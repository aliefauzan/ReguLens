"""A malformed CORS_ORIGINS must not silently kill the deployed site.

A deploy step read the current value back through gcloud, got a Python-style
list, and stripped the brackets but not the quotes. The resulting origin
`https://host'` matches no browser Origin header, so the web app died with a
CORS error and the API looked perfectly healthy.
"""

from __future__ import annotations

from app.settings import Settings


def _origins(raw: str) -> list[str]:
    return Settings(cors_origins=raw).cors_origin_list


def test_plain_list():
    assert _origins("https://a.example,https://b.example") == [
        "https://a.example",
        "https://b.example",
    ]


def test_whitespace_is_ignored():
    assert _origins(" https://a.example , https://b.example ") == [
        "https://a.example",
        "https://b.example",
    ]


def test_quotes_and_brackets_from_a_shell_round_trip_are_stripped():
    raw = "['http://localhost:3000,https://web.example'],https://legacy.example"
    assert _origins(raw) == [
        "http://localhost:3000",
        "https://web.example",
        "https://legacy.example",
    ]


def test_empty_entries_are_dropped():
    assert _origins("https://a.example,,  ,") == ["https://a.example"]
