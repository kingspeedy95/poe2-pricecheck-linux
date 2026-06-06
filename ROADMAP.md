# Roadmap

Development plan for **poe2-pricecheck-linux**. Milestones are roughly in
priority order; check items off as they land. See `PROGRESS.md` (local, not in
git) for the day-to-day handoff notes.

**Legend:** ✅ done · 🚧 in progress · ⬜ todo

---

## Current status (updated 2026-06-06)
- ✅ Item parser (handles Advanced Item Descriptions).
- ✅ Clipboard copy via pynput (XTEST) + Qt clipboard — no external tools.
- ✅ **Live trade API verified end-to-end** (auth, search, fetch, exchange);
  real-response fixtures in `tests/fixtures/`. Pynput Ctrl+C reaches the game.
- ✅ Trade client: adaptive per-endpoint rate-limit throttling, 5xx retry,
  429 `Retry-After` handling.
- ✅ **Stat-ID matching** for rares/magics: `data/stats` cached, mods → stat
  ids, **pseudo-stat folding** (resist/life/attrs), relaxed (~90%) min rolls.
- ✅ **Currency via bulk exchange** endpoint.
- ✅ Search-summary shown in popup ("base + N filters" / "base only").
- ✅ Popup: draggable, remembers position, ✕ button, multi-monitor clamp.
- ✅ System-tray icon (quit) + bottom-centre status toast + PoE2 detection.
- ✅ Single-instance guard; `.desktop` launcher + installer.
- ✅ PoE2-themed icon (SVG + PNGs); 90 tests passing.
- ⬜ Next up: the two requested UI features below (M4) + price summary (M1).

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

- ✅ **Currency** via the bulk **exchange** endpoint
  (`/api/trade2/exchange/...`) rather than `search`.
- ✅ Price **summary stats**: median + low + listing count (median denoises the
  exchange "lowball bait" listings).
- ✅ Config `status`: choose `online` vs `any`.
- ⬜ Gems (incl. level/quality awareness), waystones (tier), runes.
- ✅ Graceful empty-result + "few data points" low-confidence messaging.
- ⬜ **poe.ninja integration** for currency/unique baselines — fast, no
  Cloudflare/rate-limit pain; use as a fallback when the trade API throttles. *(requested)*
- ⬜ **"Worth picking up?" verdict** — derive a trash / decent / valuable
  color from the price + a configurable threshold, for fast loot calls. *(requested)*
- **Done when:** currency, uniques, gems, waystones all price sanely.

---

## Milestone 2: Stat-ID matching (rares & magics)
Goal: price items by their modifiers, like the real trade site.

- ✅ Fetch `/api/trade2/data/stats`; cached locally (weekly refresh).
- ✅ Map each parsed `Modifier.text` (already `#`-normalised) → stat id.
  Handles implicit/explicit/rune variants of the same text.
- ✅ Build `query.stats[].filters[]` with relaxed `min` from `Modifier.values`.
- ➡️ UI to toggle which mods/filters are active and set min rolls — promoted to
  the M4 **"Modify the search" panel**.
- ✅ Pseudo-stats (total elemental resistance, life, mana, ES, attributes).
- 🚧 **Roll-quality indicator** — `Modifier.ranges` + `roll_quality` (0..1) are
  now parsed from Advanced Item Descriptions; the colour-bar display lands with
  the rich UI. *(requested)*
- **Done when:** a rare with 3–4 mods returns a relevant search.

---

## Milestone 3: Parser hardening & item coverage
- ⬜ Magic-item **base-type extraction** (needs a base-item list;
  currently `base_type=None` for Magic).
- ⬜ Sockets / socketed runes, corrupted, mirrored, quality, influence-likes.
- ⬜ Item categories: maps/waystones, jewels, flasks, charms, relics,
  sanctum/relic-likes, uncut gems.
- ⬜ Grow `tests/fixtures/` with a capture per category.
- ⬜ **Multi-language parsing** — support the German client (and others);
  map localized labels/mods back to canonical ids. *(requested)*
- **Done when:** parser round-trips a representative sample of each class.

---

## Milestone 4: UX / UI polish
- 🚧 **Rich trade-tool UI** — themed popup (dark + gold) shipped: rarity-coloured
  name, base·rarity·ilvl meta, gold **price band** (median + count), **mods
  section** with affix/tier tags and **roll-quality colour bars**, divider,
  numbered listings, "+N more". Remaining: item/currency **icons** (needs async
  image fetch + cache). `poe2price/theme.py` + `modview.py`; preview via
  `tools/render_popup.py`. *(requested, priority)*
- ⬜ **"Modify the search" panel** — an interactive filter editor like EE2: per
  mod/pseudo toggle on/off, set min/max per filter (spin/slider), choose
  base-type on/off, item level, rarity, corrupted, `online` vs `any`, then a
  **re-run search** button. Builds on the M2 stat filters + the search-summary
  we already surface. *(requested, priority)*
- ⬜ Set the app/window/taskbar icon (`QApplication.setWindowIcon`).
- ⬜ System-tray icon with quit + settings.
- ⬜ **Options UI** to edit the **hotkey** and **POESESSID** (and league),
  with a "Test session" button — no hand-editing JSON. *(requested, priority)*
- ✅ **Copy-whisper** (popup keys 1–9) + **Open on trade site** (Enter). *(requested)*
- ✅ **Quick links** — popup keys: **W** = community wiki, **B** = poe2db.
  (craftofexile still todo.) *(requested)*
- ✅ **Numbered listings** — popup shows 1–9; press the number to copy that
  seller's whisper to the clipboard. *(requested)*
- ⬜ **Stash search generator** — click a mod to build an in-game stash
  search/regex string to paste into the search box. *(requested)*
- ⬜ Better result layout (currency icons, price ranges, age of listing).
- ⬜ Configurable popup position / auto-hide on focus loss.
- **Done when:** a new user can configure and use it without touching JSON.

---

## Milestone 5: Distribution
- ⬜ **AppImage** build (PyInstaller + linuxdeploy) bundling Python, Qt
  plugins, and `libxcb-cursor0` → zero system deps for end users.
- ✅ `.desktop` launcher + install script (`packaging/install.sh`).
- ✅ Optional autostart entry (`install.sh --autostart`).
- ⬜ Tagged GitHub Releases with the AppImage attached.
- **Done when:** a user downloads one file, makes it executable, and it runs.

---

## Milestone 6: Quality & infrastructure
- ✅ GitHub Actions CI: `pytest` + ruff on push (`.github/workflows/ci.yml`).
- ✅ Linter (ruff) config in `pyproject.toml`.
- ✅ Logging to `~/.local/state/poe2-pricecheck/poe2price.log`.
- ✅ Robust rate-limit compliance (adaptive `X-Rate-Limit-*` throttle, backoff).
- ⬜ Wayland note / fallback (currently X11-only via XTEST).

---

## Known risks / open questions
- ✅ pynput Ctrl+C reaching the Wine game window — confirmed working.
- ✅ `trade2` search/exchange/stats schemas — verified live, fixtures saved.
- ✅ Rate limits — adaptive throttle + 429 handling in place.
- ⬜ POESESSID expiry — startup check warns; no auto-refresh.
- ⬜ poe.ninja PoE2 API — endpoints unverified (guessed URLs 404); needs
  investigation before the baseline-price fallback can be built.
- ⬜ Over-constrained rare searches (many high min-rolls → few results); the
  M4 "modify the search" panel will let users relax filters.
- ⬜ Magic items have no base type (parser limitation) → stat-only search.
