"""Render an item's modifiers as HTML for the popup (with roll-quality bars).

Kept separate from the Qt widget so the HTML building is pure and unit-testable.
"""

from __future__ import annotations

from . import theme
from .parser import Item, Modifier

_BAR_SEGMENTS = 5
_FILLED = "▰"
_EMPTY = "▱"


def _fmt(value: float) -> str:
    return str(int(value)) if value == int(value) else str(round(value, 2))


def mod_display(mod: Modifier) -> str:
    """The human text for a mod: its raw line, or values folded into the template."""
    if mod.raw:
        return mod.raw
    text = mod.text
    for value in mod.values:
        text = text.replace("#", _fmt(value), 1)
    return text


def mod_tag(mod: Modifier) -> str:
    """A short, dim affix/kind tag: P/S (+tier) for affixes, else the kind."""
    if mod.kind in ("implicit", "enchant", "rune", "crafted", "fractured"):
        label = mod.kind[:4]
    elif mod.affix == "prefix":
        label = f"P{mod.tier}" if mod.tier is not None else "P"
    elif mod.affix == "suffix":
        label = f"S{mod.tier}" if mod.tier is not None else "S"
    elif mod.tier is not None:
        label = f"T{mod.tier}"
    else:
        return ""
    return f"<span style='color:{theme.TEXT_FAINT}'>{label}</span> "


def quality_bar_html(quality: float) -> str:
    """A coloured segmented bar + percentage for a roll-quality fraction 0..1."""
    quality = max(0.0, min(1.0, quality))
    filled = round(quality * _BAR_SEGMENTS)
    color = theme.roll_quality_color(quality)
    bar = (
        f"<span style='color:{color}'>{_FILLED * filled}</span>"
        f"<span style='color:{theme.TEXT_FAINT}'>{_EMPTY * (_BAR_SEGMENTS - filled)}</span>"
    )
    return f"{bar} <span style='color:{color}'>{round(quality * 100)}%</span>"


def mods_html(item: Item) -> str:
    """An HTML table of the item's mods, or '' when there are none worth showing."""
    mods = [*item.implicits, *item.enchants, *item.explicits]
    if not mods:
        return ""
    rows = []
    for mod in mods:
        # Implicit/enchant lines read as innate (dimmer) vs affix blue.
        is_affix = mod.kind in ("explicit", "crafted", "fractured")
        color = theme.MOD if is_affix else theme.TEXT_DIM
        left = f"{mod_tag(mod)}<span style='color:{color}'>{mod_display(mod)}</span>"
        quality = mod.roll_quality
        right = quality_bar_html(quality) if quality is not None else ""
        rows.append(
            f"<tr><td>{left}</td>"
            f"<td align='right' style='white-space:nowrap'>{right}</td></tr>"
        )
    return f"<table width='100%' cellspacing='0' cellpadding='1'>{''.join(rows)}</table>"
