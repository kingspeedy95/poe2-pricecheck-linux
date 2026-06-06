"""Parse Path of Exile 2 item text copied from the game clipboard.

The game writes a block of text split into *sections* by lines of dashes
(``--------``).  The first section is the header (item class, rarity, name,
base type).  Later sections hold properties, requirements, the item level,
and the modifiers.

With **Advanced Item Descriptions** enabled (which this user has), each
modifier is introduced by an annotation line, e.g.::

    { Prefix Modifier "Marking" (Tier: 1) }
    4(4-8)% increased Effect of your Mark Skills

The annotation gives us the affix kind and tier; the stat line gives us the
text and the rolled value (the ``4`` in ``4(4-8)%``).  We normalise stat
text by replacing every number with ``#`` so it can be matched against the
trade API's stat templates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# A section separator is a line of three or more dashes (the game uses 8).
_SECTION_SEP = re.compile(r"^-{3,}$")

# "4(4-8)" / "17(10-20)" / "1.5(1-2)" -> rolled value + (min-max range).
# Group 1 = rolled value, group 2 = range min, group 3 = range max.
_ROLL_RE = re.compile(
    r"(-?\d+(?:\.\d+)?)\((-?\d+(?:\.\d+)?)-(-?\d+(?:\.\d+)?)\)"
)

# A plain signed/decimal number.
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")

# "{ Prefix Modifier "Beryl" (Tier: 11) - Mana }" and friends.
_MOD_ANNOT_RE = re.compile(
    r"^\{\s*(?P<affix>[A-Za-z]+)\s+Modifier"
    r'(?:\s+"(?P<name>[^"]*)")?'
    r"(?:\s*\(Tier:\s*(?P<tier>\d+)\))?"
    r".*\}\s*$"
)

# Item classes whose price is looked up purely by name/base (no stat filters).
NAME_SEARCH_CLASSES = {
    "stackable currency",
    "currency",
    "skill gems",
    "support gems",
    "uncut skill gems",
    "uncut support gems",
    "uncut spirit gems",
    "waystones",
    "jewels",  # abyss/regular jewels are commonly searched by base + a stat
}


@dataclass
class Modifier:
    """A single modifier line on an item."""

    text: str                       # normalised template, numbers -> '#'
    values: list[float] = field(default_factory=list)
    kind: str = "explicit"          # explicit | implicit | enchant | rune | crafted | fractured
    affix: str | None = None        # "prefix" | "suffix" | None
    tier: int | None = None
    name: str | None = None         # affix name, e.g. "Marking"
    raw: str = ""                   # the original stat line
    # Per-value (min, max) tier range from Advanced Item Descriptions; an entry
    # is None for plain numbers that carried no range.
    ranges: list[tuple[float, float] | None] = field(default_factory=list)

    @property
    def roll_quality(self) -> float | None:
        """Average roll position within the tier range, 0..1 (None if unknown).

        e.g. a 4 rolled on a 4–8 range -> 0.0; 8 -> 1.0; 6 -> 0.5.
        """
        qualities: list[float] = []
        for value, rng in zip(self.values, self.ranges, strict=False):
            if rng is None:
                continue
            low, high = rng
            if high == low:
                continue
            qualities.append(max(0.0, min(1.0, (value - low) / (high - low))))
        return sum(qualities) / len(qualities) if qualities else None


@dataclass
class Item:
    """A parsed Path of Exile 2 item."""

    raw: str = ""
    item_class: str | None = None
    rarity: str | None = None
    name: str | None = None         # given/affixed name (rare, unique, magic)
    base_type: str | None = None    # base item type
    item_level: int | None = None
    quality: int | None = None
    identified: bool = True
    corrupted: bool = False
    requirements: dict = field(default_factory=dict)
    properties: dict = field(default_factory=dict)
    implicits: list[Modifier] = field(default_factory=list)
    explicits: list[Modifier] = field(default_factory=list)
    enchants: list[Modifier] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        if self.name and self.base_type and self.name != self.base_type:
            return f"{self.name} ({self.base_type})"
        return self.name or self.base_type or "Unknown item"

    @property
    def name_searchable(self) -> bool:
        """True when we can price the item by name/base alone (no stat matching)."""
        if self.rarity in {"Unique", "Currency"}:
            return True
        return (self.item_class or "").strip().lower() in NAME_SEARCH_CLASSES


def normalize_stat(line: str) -> tuple[str, list[float], list[tuple[float, float] | None]]:
    """Replace numbers in a stat line with ``#``; return values and ranges.

    Advanced-mode rolls like ``4(4-8)%`` collapse to ``#`` with value ``4`` and
    range ``(4.0, 8.0)``. Remaining bare numbers (e.g. ``+1``) are captured as
    values with a ``None`` range. ``values`` and ``ranges`` are aligned.
    """
    values: list[float] = []
    ranges: list[tuple[float, float] | None] = []

    def _take_roll(m: re.Match) -> str:
        values.append(float(m.group(1)))
        ranges.append((float(m.group(2)), float(m.group(3))))
        return "#"

    text = _ROLL_RE.sub(_take_roll, line)

    def _take_num(m: re.Match) -> str:
        values.append(float(m.group(0)))
        ranges.append(None)
        return "#"

    text = _NUM_RE.sub(_take_num, text)
    return text, values, ranges


def parse(text: str) -> Item:
    """Parse clipboard *text* into an :class:`Item`."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    item = Item(raw=text)

    sections: list[list[str]] = [[]]
    for line in text.split("\n"):
        if _SECTION_SEP.match(line.strip()):
            sections.append([])
        else:
            sections[-1].append(line.rstrip())
    sections = [s for s in sections if any(line.strip() for line in s)]
    if not sections:
        return item

    _parse_header(item, sections[0])
    for sec in sections[1:]:
        _parse_section(item, sec)
    return item


def _parse_header(item: Item, sec: list[str]) -> None:
    name_lines: list[str] = []
    for line in sec:
        s = line.strip()
        if s.startswith("Item Class:"):
            item.item_class = s.split(":", 1)[1].strip()
        elif s.startswith("Rarity:"):
            item.rarity = s.split(":", 1)[1].strip()
        elif s:
            name_lines.append(s)

    if item.rarity in ("Rare", "Unique"):
        item.name = name_lines[0] if name_lines else None
        item.base_type = name_lines[1] if len(name_lines) > 1 else None
    elif item.rarity == "Magic":
        # Magic items are "<prefix> <base> <suffix>" on one line.  The base
        # cannot be split out reliably without a base-type database, so we
        # keep the full line as the name and leave base_type for phase 2.
        item.name = name_lines[0] if name_lines else None
        item.base_type = None
    else:  # Normal, Currency, Gems, ...
        item.base_type = name_lines[0] if name_lines else None
        item.name = item.base_type


def _parse_section(item: Item, sec: list[str]) -> None:
    if any(line.lstrip().startswith("{") for line in sec):
        _parse_mod_section(item, sec)
        return

    for line in sec:
        s = line.strip()
        if not s:
            continue
        if s == "Corrupted":
            item.corrupted = True
        elif s == "Unidentified":
            item.identified = False
        elif s.startswith("Item Level:"):
            item.item_level = _first_int(s)
        elif s.startswith("Quality:"):
            item.quality = _first_int(s)
        elif s.startswith("Requires:"):
            item.requirements = _parse_requires(s)
        elif ":" in s:
            key, val = s.split(":", 1)
            item.properties[key.strip()] = val.strip()


def _parse_mod_section(item: Item, sec: list[str]) -> None:
    current: dict | None = None
    for line in sec:
        s = line.strip()
        if not s:
            continue
        annot = _MOD_ANNOT_RE.match(s)
        if annot:
            current = annot.groupdict()
            continue
        template, values, ranges = normalize_stat(s)
        kind, affix = _classify(current)
        mod = Modifier(
            text=template,
            values=values,
            kind=kind,
            affix=affix,
            tier=int(current["tier"]) if current and current.get("tier") else None,
            name=current.get("name") if current else None,
            raw=s,
            ranges=ranges,
        )
        _add_mod(item, mod)


def _classify(annot: dict | None) -> tuple[str, str | None]:
    if not annot:
        return "explicit", None
    affix = (annot.get("affix") or "").lower()
    if affix in ("prefix", "suffix"):
        return "explicit", affix
    if affix in ("implicit", "enchant", "rune", "crafted", "fractured"):
        return affix, None
    return "explicit", None


def _add_mod(item: Item, mod: Modifier) -> None:
    if mod.kind == "implicit":
        item.implicits.append(mod)
    elif mod.kind == "enchant":
        item.enchants.append(mod)
    else:
        item.explicits.append(mod)


def _parse_requires(s: str) -> dict:
    req: dict[str, int] = {}
    body = s.split(":", 1)[1]
    for part in body.split(","):
        part = part.strip()
        m = re.match(r"Level\s+(\d+)", part)
        if m:
            req["Level"] = int(m.group(1))
            continue
        m = re.match(r"(\d+)\s+([A-Za-z]+)", part)  # e.g. "9 Int"
        if m:
            req[m.group(2)] = int(m.group(1))
    return req


def _first_int(s: str) -> int | None:
    m = _NUM_RE.search(s)
    return int(float(m.group(0))) if m else None
