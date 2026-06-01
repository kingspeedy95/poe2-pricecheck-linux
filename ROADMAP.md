# Roadmap

Development plan for **poe2-pricecheck-linux**. Milestones are roughly in
priority order; check items off as they land. See `PROGRESS.md` (local, not in
git) for the day-to-day handoff notes.

**Legend:** ✅ done · 🚧 in progress · ⬜ todo

---

## Current status
- ✅ Item parser (handles Advanced Item Descriptions), 13 tests passing.
- ✅ Clipboard copy via pynput (XTEST) + Qt clipboard — no external tools.
- ✅ Trade client: search + fetch, rate-limit aware, `check_session()`.
- ✅ PyQt6 popup near cursor; startup POESESSID warning.
- ✅ PoE2-themed icon (SVG + PNGs).
- 🚧 Live trade API never exercised — query schema unverified.

---

## ▶ Start here tomorrow — Milestone 0: Verify Phase 1 live
Goal: a real price comes back end-to-end for at least one item.

- ⬜ Put a valid **POESESSID** in `~/.config/poe2-pricecheck/config.json`.
- ⬜ `python -m poe2price`; confirm startup prints `POESESSID OK: …`.
- ⬜ Hover a **currency** item, press Ctrl+D → confirms pynput copy reaches the
  game (the one thing untested). If nothing copies, fall back to xdotool path.
- ⬜ Hover a **unique** → confirm a search + listings come back.
- ⬜ Capture a real API response; fix `trade.build_query` / `_post_search` /
  `_fetch` to match the live `trade2` schema. Save sample JSON to
  `tests/fixtures/` for regression tests.
- **Done when:** a unique and a currency both return prices in the popup.

---

## Milestone 1: Solid name-based pricing
Goal: reliable prices for everything searchable by name/base.

- ⬜ **Currency** via the bulk **exchange** endpoint
  (`/api/trade2/exchange/...`) rather than `search` — different schema.
- ⬜ Price **summary stats**: show min / median + listing count, not just a
  raw list.
- ⬜ Handle "online but offline-friendly" status options; let config choose
  `online` vs `any`.
- ⬜ Gems (incl. level/quality awareness), waystones (tier), runes.
- ⬜ Graceful empty-result and "not enough data" messaging.
- ⬜ **poe.ninja integration** for currency/unique baselines — fast, no
  Cloudflare/rate-limit pain; use as a fallback when the trade API throttles. *(requested)*
- **Done when:** currency, uniques, gems, waystones all price sanely.

---

## Milestone 2: Stat-ID matching (rares & magics)
Goal: price items by their modifiers, like the real trade site.

- ⬜ Fetch `/api/trade2/data/stats`; cache locally, refresh per league/patch.
- ⬜ Map each parsed `Modifier.text` (already `#`-normalised) → stat id.
  Handle implicit/explicit/rune variants of the same text.
- ⬜ Build `query.stats[].filters[]` with `min` from `Modifier.values`.
- ⬜ UI to toggle which mods/filters are active and set min rolls.
- ⬜ Pseudo-stats (e.g. total resistances) — stretch.
- ⬜ **Roll-quality indicator** — show each mod's roll as a % of its tier
  range with a color bar (e.g. `4 of 4–8 → 25%`). Cheap: the min–max is
  already parsed from Advanced Item Descriptions. *(requested)*
- **Done when:** a rare with 3–4 mods returns a relevant search.

---

## Milestone 3: Parser hardening & item coverage
- ⬜ Magic-item **base-type extraction** (needs a base-item list;
  currently `base_type=None` for Magic).
- ⬜ Sockets / socketed runes, corrupted, mirrored, quality, influence-likes.
- ⬜ Item categories: maps/waystones, jewels, flasks, charms, relics,
  sanctum/relic-likes, uncut gems.
- ⬜ Grow `tests/fixtures/` with a capture per category.
- **Done when:** parser round-trips a representative sample of each class.

---

## Milestone 4: UX / UI polish
- ⬜ Set the app/window/taskbar icon (`QApplication.setWindowIcon`).
- ⬜ System-tray icon with quit + settings.
- ⬜ **Options UI** to edit the **hotkey** and **POESESSID** (and league),
  with a "Test session" button — no hand-editing JSON. *(requested, priority)*
- ⬜ **Copy-whisper** hotkey/button + **Open on trade site** button. *(requested)*
- ⬜ **Quick links** — hotkeys to open the hovered item on wiki / poedb /
  craftofexile. *(requested)*
- ⬜ Better result layout (currency icons, price ranges, age of listing).
- ⬜ Configurable popup position / auto-hide on focus loss.
- **Done when:** a new user can configure and use it without touching JSON.

---

## Milestone 5: Distribution
- ⬜ **AppImage** build (PyInstaller + linuxdeploy) bundling Python, Qt
  plugins, and `libxcb-cursor0` → zero system deps for end users.
- ⬜ `.desktop` launcher + install script.
- ⬜ Optional autostart entry.
- ⬜ Tagged GitHub Releases with the AppImage attached.
- **Done when:** a user downloads one file, makes it executable, and it runs.

---

## Milestone 6: Quality & infrastructure
- ⬜ GitHub Actions CI: run `pytest` + lint on push.
- ⬜ Formatter/linter (ruff/black) config.
- ⬜ Logging to `~/.local/state/poe2-pricecheck/log` for debugging.
- ⬜ Robust rate-limit compliance (parse `X-Rate-Limit-*` properly, backoff).
- ⬜ Wayland note / fallback (currently X11-only via XTEST).

---

## Known risks / open questions
- pynput Ctrl+C reaching the Wine game window (verify in M0).
- Exact `trade2` query + exchange schemas (discover from live responses in M0/M1).
- Cloudflare/rate limits on the trade API; POESESSID expiry handling.
- Stat-text → stat-id mapping ambiguity for similar mods (M2).
