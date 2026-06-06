"""Dev tool: render the price popup to PNG files (offscreen) for eyeballing.

Run headless:  QT_QPA_PLATFORM=offscreen python tools/render_popup.py [outdir]

Produces <outdir>/popup_<state>.png for a few representative states so the
layout/theme can be reviewed without launching the live GUI.
"""

from __future__ import annotations

import os
import sys

from PyQt6 import QtWidgets

from poe2price.parser import Item, Modifier
from poe2price.trade import Listing
from poe2price.ui import PriceWindow


def _grab(window: PriceWindow, path: str) -> None:
    window.adjustSize()
    window.grab().save(path)
    print("wrote", path, f"({window.width()}x{window.height()})")


def main(outdir: str = "/tmp/poe2popup") -> int:
    os.makedirs(outdir, exist_ok=True)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    assert app is not None  # keep a reference so it isn't garbage-collected

    listings = [
        Listing(80, "exalted", "SellerOne#1234", "@SellerOne hi"),
        Listing(81, "exalted", "Trader_Two#5678", "@Trader_Two hi"),
        Listing(82, "exalted", "buyer#9012", "@buyer hi"),
        Listing(85, "exalted", "merchant#3456", "@merchant hi"),
        Listing(88, "exalted", "vendor#7777", "@vendor hi"),
        Listing(90, "exalted", "exile#2468", "@exile hi"),
    ]
    many = listings + [Listing(90 + i, "exalted", f"more#{i}", f"@m{i}") for i in range(6)]

    rare = Item(
        rarity="Rare", name="Doom Coil", base_type="Sapphire Ring", item_level=82,
        implicits=[
            Modifier(text="+#% to Fire Resistance", values=[18.0], ranges=[(10.0, 20.0)],
                     kind="implicit", raw="+18% to Fire Resistance"),
        ],
        explicits=[
            Modifier(text="+# to maximum Life", values=[95.0], ranges=[(80.0, 99.0)],
                     kind="explicit", affix="prefix", tier=1, raw="+95 to maximum Life"),
            Modifier(text="+#% to Cold Resistance", values=[40.0], ranges=[(36.0, 45.0)],
                     kind="explicit", affix="suffix", tier=2, raw="+40% to Cold Resistance"),
            Modifier(text="+# to Spirit", values=[22.0], ranges=[(20.0, 30.0)],
                     kind="explicit", affix="prefix", tier=3, raw="+22 to Spirit"),
        ],
    )
    unique = Item(rarity="Unique", name="Astramentis", base_type="Stellar Amulet",
                  item_level=84)

    w = PriceWindow()
    w.show_result(rare, many, "https://example/trade", "Sapphire Ring + 2 stat filters")
    _grab(w, f"{outdir}/popup_rare.png")

    w.show_result(unique, listings, "https://example/trade", "by name: Astramentis")
    _grab(w, f"{outdir}/popup_unique.png")

    w.show_error("Rate limited by the trade API. Try again in about 12s.")
    _grab(w, f"{outdir}/popup_error.png")

    w.show_loading(rare)
    _grab(w, f"{outdir}/popup_loading.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
