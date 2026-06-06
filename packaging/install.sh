#!/usr/bin/env bash
#
# Install a desktop launcher + icons for poe2-pricecheck so it shows up in the
# application menu and can be pinned to the taskbar. Per-user, no root needed.
#
# Usage:
#   packaging/install.sh                 # install the menu launcher
#   packaging/install.sh --autostart     # also launch automatically on login
#   packaging/install.sh --no-autostart  # remove only the autostart entry
#   packaging/install.sh --uninstall     # remove everything
#
set -euo pipefail

# Repo root = parent of this script's directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_ID="poe2-pricecheck"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_BASE="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
DESKTOP_FILE="$DESKTOP_DIR/$APP_ID.desktop"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/$APP_ID.desktop"

AUTOSTART=0  # set by --autostart

refresh_caches() {
    command -v update-desktop-database >/dev/null 2>&1 && \
        update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && \
        gtk-update-icon-cache -f -t "$ICON_BASE" >/dev/null 2>&1 || true
}

case "${1:-}" in
    --uninstall)
        rm -f "$DESKTOP_FILE" "$AUTOSTART_FILE"
        for size in 16 32 48 64 128 256 512; do
            rm -f "$ICON_BASE/${size}x${size}/apps/$APP_ID.png"
        done
        rm -f "$ICON_BASE/scalable/apps/$APP_ID.svg"
        refresh_caches
        echo "Removed $APP_ID launcher, icons, and autostart entry."
        exit 0
        ;;
    --no-autostart)
        rm -f "$AUTOSTART_FILE"
        echo "Removed autostart entry: $AUTOSTART_FILE"
        exit 0
        ;;
    --autostart)
        AUTOSTART=1
        ;;
    "")
        ;;
    *)
        echo "Unknown option: $1" >&2
        echo "Use --autostart, --no-autostart, or --uninstall." >&2
        exit 2
        ;;
esac

# Pick the launch command: prefer the venv console script, then a venv python
# running the module, then the system python. Whichever exists wins.
if [[ -x "$REPO_DIR/.venv/bin/poe2-pricecheck" ]]; then
    EXEC_CMD="$REPO_DIR/.venv/bin/poe2-pricecheck"
elif [[ -x "$REPO_DIR/.venv/bin/python" ]]; then
    EXEC_CMD="$REPO_DIR/.venv/bin/python -m poe2price"
else
    EXEC_CMD="python3 -m poe2price"
fi

# Install icons into the hicolor theme so they render crisply at any size.
for size in 16 32 48 64 128 256 512; do
    src="$REPO_DIR/assets/png/icon-$size.png"
    [[ -f "$src" ]] || continue
    dest_dir="$ICON_BASE/${size}x${size}/apps"
    mkdir -p "$dest_dir"
    cp "$src" "$dest_dir/$APP_ID.png"
done
if [[ -f "$REPO_DIR/assets/icon.svg" ]]; then
    mkdir -p "$ICON_BASE/scalable/apps"
    cp "$REPO_DIR/assets/icon.svg" "$ICON_BASE/scalable/apps/$APP_ID.svg"
fi

# Write the .desktop entry with absolute paths for this clone.
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=PoE2 Price Check
GenericName=Path of Exile 2 Price Checker
Comment=Check Path of Exile 2 item prices with a global hotkey
Exec=$EXEC_CMD
Path=$REPO_DIR
Icon=$APP_ID
Terminal=false
Categories=Utility;
Keywords=poe;poe2;trade;price;exile;
StartupNotify=false
EOF
chmod +x "$DESKTOP_FILE"

refresh_caches

echo "Installed launcher: $DESKTOP_FILE"
echo "  Exec: $EXEC_CMD"
echo "It should now appear in your app menu as \"PoE2 Price Check\"."
echo "Right-click it there to pin it to the taskbar/favorites."

# Optionally start automatically on login (a copy in the autostart dir).
if [[ "$AUTOSTART" == "1" ]]; then
    mkdir -p "$AUTOSTART_DIR"
    cp "$DESKTOP_FILE" "$AUTOSTART_FILE"
    echo "Autostart enabled: $AUTOSTART_FILE"
    echo "  (disable with: packaging/install.sh --no-autostart)"
fi
