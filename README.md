# poe2-pricecheck-linux

<img src="assets/icon.svg" alt="icon" width="128" align="right"/>

A small, Linux-first price checker for **Path of Exile 2**.

Press a hotkey while hovering an item in-game; the tool copies the item,
parses it, queries the official trade API, and shows prices in a popup next
to your cursor.

> **Why this exists.** On some Linux/X11 setups, the synthetic copy keystroke
> from existing overlays never reaches the focused game window, so the item
> text never lands on the clipboard. This tool injects the copy with `pynput`
> via XTEST, which does reach the Wine/Proton game window — and uses no external
> command-line tools.

## Features

- **Whole-item search**, not just the base: rares/magics are priced by their
  modifiers via trade stat-IDs, with **pseudo-stats** (total elemental
  resistance, life, mana, ES, attributes) and **relaxed (~90%) min rolls**, so
  prices reflect the item's actual rolls.
- **Currency** priced through the bulk **exchange** endpoint (proper ratios).
- **Price summary** — median price (robust to lowball listings) + listing
  count, with a "few data points" warning when the sample is thin.
- **Search transparency** — the popup shows *what* it searched by
  (e.g. `Sapphire Ring + 2 stat filters`, or `base only — no mods matched`).
- **Rate-limit aware** — adaptive per-endpoint throttling + retry/back-off.
- **Draggable popup** that remembers its position, with an ✕ button.
- **System-tray icon** (quit), a status toast (waiting for / detected PoE2),
  and a **single-instance** guard.
- **Taskbar launcher** + optional autostart (`packaging/install.sh`).

## Requirements

- An **X11** session (the key injection uses XTEST).
- **Python ≥ 3.10**.
- One system library for the Qt GUI:

  ```bash
  sudo apt install libxcb-cursor0
  ```

  This is the only OS package needed. It cannot be installed via `pip`
  (Qt 6.5+ requires it at runtime). No external command-line tools are
  used — key injection is `pynput`, the clipboard is Qt.

> **Planned:** an AppImage build that bundles `libxcb-cursor0`, the Qt
> plugins, and Python, so end users need nothing installed at all.

## Install

```bash
git clone git@github.com:kingspeedy95/poe2-pricecheck-linux.git
cd poe2-pricecheck-linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure

A config file is created on first run at
`~/.config/poe2-pricecheck/config.json`:

```json
{
  "league": "Runes of Aldur",
  "hotkey": "<ctrl>+d",
  "status": "online",
  "poesessid": "",
  "max_listings": 10
}
```

- `status` — `"online"` (default) or `"any"` to include offline listings.
- `max_listings` — how many of the cheapest listings to fetch/show.

The trade API is behind Cloudflare. For reliable requests, paste your
**POESESSID** cookie:

1. Log in at <https://www.pathofexile.com> in your browser.
2. DevTools → Application → Cookies → `pathofexile.com` → copy `POESESSID`.
3. Put it in `config.json` (the file is chmod `600`; it is git-ignored).

Hotkey strings use [pynput syntax](https://pynput.readthedocs.io/en/latest/keyboard.html#monitoring-the-keyboard)
(e.g. `<ctrl>+d`, `<alt>+d`).

## Run

```bash
python -m poe2price
```

Then hover an item in PoE2 and press your hotkey. **Enter** in the popup opens
the search on the trade site; **drag** to move it; **Esc** or **✕** closes it.
The app lives in the background with a system-tray icon (right-click → Quit).

A log is written to `~/.local/state/poe2-pricecheck/poe2price.log`.

### Taskbar launcher / autostart

```bash
packaging/install.sh              # add a menu launcher (pin it to the taskbar)
packaging/install.sh --autostart  # also start automatically on login
packaging/install.sh --uninstall  # remove everything
```

## Develop

```bash
pip install -e ".[dev]"
pytest          # 100+ tests
ruff check .    # lint
```

Tests run headless (Qt uses the offscreen platform via `tests/conftest.py`) and
are built from real clipboard captures and live API responses in
`tests/fixtures/`. CI runs `pytest` + `ruff` on push (see
`.github/workflows/ci.yml`).

## License

MIT — see [LICENSE](LICENSE).
