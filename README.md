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

- An **X11** session (the key injection uses XTEST) — required for every
  install method.
- The **AppImage** needs nothing else.
- **From source:** **Python ≥ 3.10** and `libxcb-cursor0` (Qt 6.5+ needs it at
  runtime; it can't be installed via `pip`). No external command-line tools are
  used — key injection is `pynput`, the clipboard is Qt.

## Install

### AppImage (recommended)

Grab the latest `.AppImage` from the
[Releases](https://github.com/kingspeedy95/poe2-pricecheck-linux/releases) page —
it bundles Python, Qt, and all dependencies, so **no system packages are
needed**:

```bash
chmod +x poe2-pricecheck-*.AppImage
./poe2-pricecheck-*.AppImage
```

(Requires an X11 session; the key injection uses XTEST.)

### From source

```bash
git clone git@github.com:kingspeedy95/poe2-pricecheck-linux.git
cd poe2-pricecheck-linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo apt install libxcb-cursor0   # the one OS package Qt needs at runtime
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

Preview the popup layout without the game:

```bash
QT_QPA_PLATFORM=offscreen python tools/render_popup.py   # writes PNGs to /tmp/poe2popup
```

### Contributing & releases

- Development happens on **branches via pull requests**; `main` stays
  releasable and CI must be green to merge.
- To cut a release, tag a version on `main`:

  ```bash
  git tag v0.2.0 && git push origin v0.2.0
  ```

  `.github/workflows/release.yml` then builds the AppImage and publishes a
  GitHub Release with an auto-generated changelog.

## License

MIT — see [LICENSE](LICENSE).
