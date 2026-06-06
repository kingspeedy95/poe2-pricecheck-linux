#!/usr/bin/env bash
#
# Build a self-contained AppImage of poe2-pricecheck.
#
# Bundles Python, PyQt6 (+ Qt plugins), and the app via PyInstaller, then packs
# the result into an AppImage with appimagetool. The result needs no system
# packages on the end user's machine.
#
# Usage:  packaging/build_appimage.sh [version]
# Output: dist/poe2-pricecheck-<version>-x86_64.AppImage
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

APP_ID="poe2-pricecheck"
ARCH="${ARCH:-x86_64}"

# Version: explicit arg, else from pyproject.toml.
VERSION="${1:-$(python3 -c '
import tomllib
with open("pyproject.toml","rb") as f:
    print(tomllib.load(f)["project"]["version"])
')}"
echo ">> Building $APP_ID $VERSION ($ARCH)"

# -- 1. PyInstaller (onedir) ------------------------------------------------
python3 -m pip install --quiet --upgrade pyinstaller
rm -rf build dist/"$APP_ID" "$APP_ID.spec"
pyinstaller --noconfirm --clean \
    --name "$APP_ID" \
    --add-data "assets:assets" \
    --hidden-import "pynput.keyboard._xorg" \
    --hidden-import "pynput.mouse._xorg" \
    packaging/entry.py

# -- 2. Assemble the AppDir -------------------------------------------------
APPDIR="build/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -r "dist/$APP_ID/." "$APPDIR/usr/bin/"

# Icon at the AppDir root (name must match the .desktop Icon= key).
cp "assets/png/icon-256.png" "$APPDIR/$APP_ID.png"

cat > "$APPDIR/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PoE2 Price Check
GenericName=Path of Exile 2 Price Checker
Comment=Check Path of Exile 2 item prices with a global hotkey
Exec=$APP_ID
Icon=$APP_ID
Categories=Utility;
Terminal=false
EOF

cat > "$APPDIR/AppRun" <<EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\$0")")"
exec "\$HERE/usr/bin/$APP_ID" "\$@"
EOF
chmod +x "$APPDIR/AppRun"

# -- 3. Pack with appimagetool ---------------------------------------------
TOOL="build/appimagetool-$ARCH.AppImage"
if [[ ! -x "$TOOL" ]]; then
    echo ">> Fetching appimagetool"
    curl -fsSL -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
    chmod +x "$TOOL"
fi

mkdir -p dist
OUT="dist/$APP_ID-$VERSION-$ARCH.AppImage"
# --appimage-extract-and-run avoids needing FUSE (e.g. in CI containers).
ARCH="$ARCH" "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"

echo ">> Built $OUT"
