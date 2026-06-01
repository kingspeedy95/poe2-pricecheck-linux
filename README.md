# poe2-pricecheck-linux

A small, Linux-first price checker for **Path of Exile 2**.

Press a hotkey while hovering an item in-game; the tool copies the item,
parses it, queries the official trade API, and shows prices in a popup next
to your cursor.

> **Why this exists.** Exiled Exchange 2 relies on `uiohook-napi` to inject
> the copy keystroke. On some Linux/X11 setups that injection silently fails
> ("No item text found in clipboard") even though the game accepts synthetic
> input from `xdotool`. This tool uses `xdotool` for the copy, which works.

## Status

- ✅ **Phase 1** — clipboard copy, item parser (handles *Advanced Item
  Descriptions*), PyQt popup, and name/base price lookups (currency,
  uniques, gems, waystones).
- 🚧 **Phase 2** — stat-ID matching so rare/magic items can be priced by
  their modifiers.

## Requirements

System tools (X11):

```bash
sudo apt install xdotool xclip libnotify-bin
```

Python ≥ 3.10.

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
  "poesessid": "",
  "max_listings": 10
}
```

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
the search on the trade site; **Esc** closes it.

## Develop

```bash
pip install -e ".[dev]"
pytest
```

The parser is covered by tests built from real clipboard captures in
`tests/fixtures/`.

## License

MIT — see [LICENSE](LICENSE).
