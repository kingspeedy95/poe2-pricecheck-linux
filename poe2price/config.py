"""User configuration, stored as JSON under ``~/.config/poe2-pricecheck``."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

CONFIG_DIR = os.path.expanduser("~/.config/poe2-pricecheck")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


@dataclass
class Config:
    # Defaults seeded from the user's Exiled Exchange 2 install.
    league: str = "Runes of Aldur"
    language: str = "en"

    # pynput hotkey spec. Pressed while hovering an item in-game.
    hotkey: str = "<ctrl>+d"

    # Listing status to search: "online" (default) or "any" (include offline).
    status: str = "online"

    # The trade API sits behind Cloudflare. A logged-in session cookie makes
    # requests reliable. Copy POESESSID from your browser cookies for
    # pathofexile.com (DevTools -> Application -> Cookies).
    poesessid: str = ""

    # GGG asks for a descriptive, contactable User-Agent.
    user_agent: str = (
        "poe2-pricecheck-linux/0.1 "
        "(+https://github.com/kingspeedy95/poe2-pricecheck-linux)"
    )
    contact_email: str = ""

    # How many of the cheapest listings to fetch/show.
    max_listings: int = 10

    @classmethod
    def load(cls) -> Config:
        """Load config, creating a default file on first run."""
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            cfg = cls(**known)
        else:
            cfg = cls()
        cfg.save()  # rewrite to add any newly-introduced fields
        return cfg

    def save(self) -> None:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        os.chmod(CONFIG_PATH, 0o600)  # POESESSID is a secret
