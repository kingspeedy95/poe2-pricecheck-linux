"""Build external reference URLs for an item (poe2db, wiki).

poe2db.tw covers PoE2 bases and uniques reliably; the community wiki mainly has
named/unique pages. Both are best-effort deep links opened from the popup.
"""

from __future__ import annotations

import urllib.parse

from .parser import Item

POE2DB = "https://poe2db.tw/us"
WIKI = "https://www.poewiki.net/wiki"


def lookup_term(item: Item) -> str | None:
    """The most useful term to look an item up by: unique name, else base."""
    if item.rarity == "Unique" and item.name:
        return item.name
    return item.base_type or item.name


def _slug(term: str) -> str:
    return urllib.parse.quote(term.replace(" ", "_"))


def poe2db_url(item: Item) -> str | None:
    term = lookup_term(item)
    return f"{POE2DB}/{_slug(term)}" if term else None


def wiki_url(item: Item) -> str | None:
    term = lookup_term(item)
    return f"{WIKI}/{_slug(term)}" if term else None
