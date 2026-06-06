"""Visual theme for the price popup — a dark, PoE2-exile palette with gold.

Centralises colours and a few stylesheet snippets so the UI stays consistent
and is easy to retheme. Item-text colours follow Path of Exile's conventions
(magic blue, rare yellow, unique brown) so the popup reads like the game.
"""

from __future__ import annotations

# -- palette ----------------------------------------------------------------
BG = "#16151a"            # window background (near-black, warm)
BG_PANEL = "#201e26"      # raised panel / price band
BORDER = "#3a3550"        # subtle violet-grey border
GOLD = "#e8c87a"          # primary accent (prices, highlights)
GOLD_DIM = "#b9974d"
TEXT = "#d8d4cc"          # body text (parchment)
TEXT_DIM = "#8a8580"      # secondary text
TEXT_FAINT = "#5f5b55"    # hints / row numbers
DANGER = "#cc6666"        # errors / no results
GOOD = "#7bbf6a"          # positive (high roll)
MOD = "#8c9ed6"           # item modifier text (PoE affix blue)

# Path of Exile item-rarity text colours.
RARITY_COLORS = {
    "Normal": "#c8c8c8",
    "Magic": "#8888ff",
    "Rare": "#f3e463",
    "Unique": "#cf8c4f",
    "Currency": "#caa46a",
    "Gem": "#1ba29b",
    "Quest": "#4ae63a",
}
_DEFAULT_RARITY_COLOR = TEXT


def rarity_color(rarity: str | None) -> str:
    """Return the item-text colour for *rarity* (falls back to body text)."""
    return RARITY_COLORS.get(rarity or "", _DEFAULT_RARITY_COLOR)


def roll_quality_color(quality: float) -> str:
    """Colour for a roll-quality fraction (0..1): red → yellow → green."""
    quality = max(0.0, min(1.0, quality))
    if quality >= 0.75:
        return GOOD
    if quality >= 0.4:
        return GOLD
    return "#c98a55" if quality >= 0.2 else DANGER


# -- stylesheet --------------------------------------------------------------
def window_stylesheet() -> str:
    """The top-level stylesheet for the price window."""
    return (
        f"PriceWindow {{ background: {BG}; border: 1px solid {BORDER}; "
        f"border-radius: 10px; }} "
        f"QLabel {{ color: {TEXT}; }}"
    )
