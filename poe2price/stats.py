"""Map parsed item modifiers to trade2 stat IDs.

The trade site searches rares/magics by *stat filters*: each modifier becomes a
``{"id": "explicit.stat_1234", "value": {"min": N}}`` entry. To build those we
need the catalog from ``/api/trade2/data/stats``, which lists every stat's
``#``-templated text and its type-prefixed id.

Two wrinkles handled here:

* The catalog drops a leading ``+`` that the parser keeps (``# to maximum Mana``
  vs ``+# to maximum Mana``), so both sides are canonicalised by collapsing
  ``+#`` → ``#``.
* The same stat text exists under several types (``explicit``/``implicit``/…)
  sharing one stat number; we pick the id whose type best matches the modifier.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections import defaultdict

STATS_URL = "https://www.pathofexile.com/api/trade2/data/stats"
STATIC_URL = "https://www.pathofexile.com/api/trade2/data/static"

_CACHE_DIR = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
    "poe2-pricecheck",
)
_CACHE_PATH = os.path.join(_CACHE_DIR, "stats.json")
_CURRENCY_CACHE_PATH = os.path.join(_CACHE_DIR, "currency.json")
_MAX_AGE_SECONDS = 7 * 24 * 3600  # refresh weekly

# How far below the actual roll to set a filter's min, so we find
# comparable-or-slightly-worse listings instead of over-constraining to the
# exact roll (mirrors Exiled Exchange 2's default behaviour).
_ROLL_RELAX = 0.9

# Canonical pseudo-stat texts (post-:func:`canon`), keyed by a short name.
_PSEUDO_TEXT = {
    "fire": "#% total to Fire Resistance",
    "cold": "#% total to Cold Resistance",
    "lightning": "#% total to Lightning Resistance",
    "chaos": "#% total to Chaos Resistance",
    "elemental": "#% total Elemental Resistance",
    "life": "# total maximum Life",
    "mana": "# total maximum Mana",
    "es": "# total maximum Energy Shield",
    "str": "# total to Strength",
    "dex": "# total to Dexterity",
    "int": "# total to Intelligence",
}

# Which pseudo totals a given (canonical) modifier text contributes to. Folding
# these into pseudo-stats is how the trade site actually prices rares: an exact
# mod combo is rare, but the *totals* are comparable across items.
_PSEUDO_CONTRIB = {
    "#% to Fire Resistance": [("fire", 1)],
    "#% to Cold Resistance": [("cold", 1)],
    "#% to Lightning Resistance": [("lightning", 1)],
    "#% to Chaos Resistance": [("chaos", 1)],
    "#% to all Elemental Resistances": [("fire", 1), ("cold", 1), ("lightning", 1)],
    "# to maximum Life": [("life", 1)],
    "# to maximum Mana": [("mana", 1)],
    "# to maximum Energy Shield": [("es", 1)],
    "# to Strength": [("str", 1)],
    "# to Dexterity": [("dex", 1)],
    "# to Intelligence": [("int", 1)],
    "# to all Attributes": [("str", 1), ("dex", 1), ("int", 1)],
}

# For a modifier of a given kind, which catalog types to prefer (first match
# wins). Rune mods live under the catalog's "augment" type.
_TYPE_PREFERENCE = {
    "explicit": ["explicit", "fractured", "crafted", "desecrated", "implicit"],
    "implicit": ["implicit", "explicit"],
    "enchant": ["enchant", "explicit"],
    "rune": ["augment", "enchant", "explicit"],
    "crafted": ["crafted", "explicit"],
    "fractured": ["fractured", "explicit"],
}
_DEFAULT_PREFERENCE = ["explicit", "implicit", "fractured", "crafted"]


def canon(text: str) -> str:
    """Canonical form so parser text and catalog text compare equal."""
    return text.replace("+#", "#").strip()


class StatsIndex:
    """Looks up trade2 stat IDs for parsed :class:`~poe2price.parser.Modifier`."""

    def __init__(self, data: dict) -> None:
        # canonical text -> {catalog type: stat id}
        self._by_text: dict[str, dict[str, str]] = defaultdict(dict)
        for group in data.get("result", []):
            for entry in group.get("entries", []):
                text = entry.get("text")
                stat_id = entry.get("id")
                stat_type = entry.get("type")
                if not (text and stat_id and stat_type):
                    continue
                self._by_text[canon(text)].setdefault(stat_type, stat_id)

    def __len__(self) -> int:
        return len(self._by_text)

    def match(self, mod) -> str | None:
        """Return the best stat id for *mod*, or None if it isn't in the catalog."""
        ids = self._by_text.get(canon(mod.text))
        if not ids:
            return None
        for stat_type in _TYPE_PREFERENCE.get(mod.kind, _DEFAULT_PREFERENCE):
            if stat_type in ids:
                return ids[stat_type]
        return next(iter(ids.values()))

    def pseudo(self, canon_text: str) -> str | None:
        """Return the pseudo-stat id for an already-canonicalised text."""
        ids = self._by_text.get(canon_text)
        return ids.get("pseudo") if ids else None


def _relax(value: float, factor: float = _ROLL_RELAX) -> float:
    """A slightly-lowered min so searches aren't pinned to the exact roll."""
    if value <= 0:
        return int(value) if value == int(value) else value
    return max(math.floor(value * factor), 1)


def build_stat_filters(item, index: StatsIndex) -> list[dict]:
    """Build trade2 stat filters for *item*, EE2-style.

    Resistances/life/attributes are folded into pseudo-totals (when the catalog
    has the pseudo); the contributing mods are then dropped in favour of the
    total. Remaining mods become individual stat filters. Single-number mods get
    a relaxed min roll so the search isn't pinned to the exact value.
    """
    mods = [*item.implicits, *item.enchants, *item.explicits]

    totals: dict[str, float] = defaultdict(float)
    contributors: dict[str, list] = defaultdict(list)
    for mod in mods:
        contrib = _PSEUDO_CONTRIB.get(canon(mod.text)) if len(mod.values) == 1 else None
        if contrib:
            for key, mult in contrib:
                totals[key] += mod.values[0] * mult
                contributors[key].append(mod)

    filters: list[dict] = []
    consumed: set[int] = set()

    def emit_pseudo(key: str, amount: float, source_keys: list[str]) -> None:
        if amount <= 0:
            return
        pseudo_id = index.pseudo(_PSEUDO_TEXT[key])
        if not pseudo_id:
            return  # catalog lacks it; leave the mods as individual filters
        filters.append({
            "id": pseudo_id,
            "value": {"min": _relax(amount)},
            "disabled": False,
        })
        for src in source_keys:
            for mod in contributors[src]:
                consumed.add(id(mod))

    # The three elemental resists combine into one total (the standard pseudo).
    elemental = totals["fire"] + totals["cold"] + totals["lightning"]
    emit_pseudo("elemental", elemental, ["fire", "cold", "lightning"])
    emit_pseudo("chaos", totals["chaos"], ["chaos"])
    emit_pseudo("life", totals["life"], ["life"])
    emit_pseudo("es", totals["es"], ["es"])
    emit_pseudo("mana", totals["mana"], ["mana"])
    for attr in ("str", "dex", "int"):
        emit_pseudo(attr, totals[attr], [attr])

    # Everything not folded into a pseudo becomes an individual stat filter.
    for mod in mods:
        if id(mod) in consumed:
            continue
        stat_id = index.match(mod)
        if not stat_id:
            continue
        entry: dict = {"id": stat_id, "disabled": False}
        if len(mod.values) == 1:
            entry["value"] = {"min": _relax(mod.values[0])}
        filters.append(entry)

    return filters


def load_currency_map(session, *, max_age_seconds: int = _MAX_AGE_SECONDS) -> dict[str, str]:
    """Return a {currency display name: exchange id} map, cached on disk."""
    data = _read_json_cache(_CURRENCY_CACHE_PATH, max_age_seconds)
    if data is None:
        resp = session.get(STATIC_URL, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        _write_json_cache(_CURRENCY_CACHE_PATH, data)
    mapping: dict[str, str] = {}
    for group in data.get("result", []):
        if group.get("label") != "Currency":
            continue
        for entry in group.get("entries", []):
            text, cid = entry.get("text"), entry.get("id")
            if text and cid:
                mapping[text] = cid
    return mapping


def load_stats_index(session, *, max_age_seconds: int = _MAX_AGE_SECONDS) -> StatsIndex:
    """Load the stat catalog from the local cache, fetching it if stale.

    *session* is a ``requests.Session`` (e.g. ``TradeClient.session``). On a
    network failure a usable cache is still returned if one exists.
    """
    data = _read_json_cache(_CACHE_PATH, max_age_seconds)
    if data is None:
        resp = session.get(STATS_URL, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        _write_json_cache(_CACHE_PATH, data)
    return StatsIndex(data)


def _read_json_cache(path: str, max_age_seconds: int) -> dict | None:
    try:
        age = time.time() - os.path.getmtime(path)
    except OSError:
        return None
    if age > max_age_seconds:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write_json_cache(path: str, data: dict) -> None:
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError:
        pass  # caching is best-effort
