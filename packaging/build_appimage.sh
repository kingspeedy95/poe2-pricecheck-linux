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
# Pinned, no --upgrade, so the build tool can't change underneath us.
PYINSTALLER_VERSION="6.20.0"
python3 -m pip install --quiet "pyinstaller==$PYINSTALLER_VERSION"
rm -rf build dist/"$APP_ID" "$APP_ID.spec"
pyinstaller --noconfirm --clean \
    --name "$APP_ID" \
    --paths "$REPO_DIR" \
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
# Pinned to a tagged release (not the rolling "continuous" build) and verified
# against a known SHA-256 before we make it executable.
APPIMAGETOOL_VERSION="1.9.1"
APPIMAGETOOL_SHA256_x86_64="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"

TOOL="build/appimagetool-$ARCH.AppImage"
if [[ ! -x "$TOOL" ]]; then
    echo ">> Fetching appimagetool $APPIMAGETOOL_VERSION"
    curl -fsSL -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/$APPIMAGETOOL_VERSION/appimagetool-$ARCH.AppImage"
    expected_var="APPIMAGETOOL_SHA256_${ARCH}"
    expected="${!expected_var:-}"
    if [[ -z "$expected" ]]; then
        echo "ERROR: no pinned SHA-256 for arch '$ARCH'; refusing to run unverified appimagetool." >&2
        rm -f "$TOOL"
        exit 1
    fi
    echo "$expected  $TOOL" | sha256sum -c - \
        || { echo "ERROR: appimagetool checksum mismatch" >&2; rm -f "$TOOL"; exit 1; }
    chmod +x "$TOOL"
fi

mkdir -p dist
OUT="dist/$APP_ID-$VERSION-$ARCH.AppImage"
# --appimage-extract-and-run avoids needing FUSE (e.g. in CI containers).
ARCH="$ARCH" "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"

echo ">> Built $OUT"
