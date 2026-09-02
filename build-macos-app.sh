#!/bin/sh
set -e
cd "$(dirname "$0")"
if [ ! -x ./venv/bin/python ]; then
  echo "Missing ./venv/bin/python — create the venv and install requirements first."
  exit 1
fi
./venv/bin/python -m pip install -q pyinstaller PyQt6 PyQt6-WebEngine
./vendor/sck-locate/build.sh
./venv/bin/python -c "import PyQt6, PyQt6.QtWebEngineWidgets; print('bundling with', PyQt6.__file__)"
./venv/bin/python make_app_icon.py
# QGIS sets PYTHONPATH in this shell; it breaks PyInstaller's module collection.
unset PYTHONPATH
./venv/bin/python -m PyInstaller --noconfirm --clean "STAplus SCK.spec"
OMD_VER="dist/STAplus SCK/_internal/orderedmultidict/__version__.py"
if [ ! -f "$OMD_VER" ]; then
  echo "Bundle is missing $OMD_VER"
  exit 1
fi
UUID_PY="dist/STAplus SCK/_internal/uuid.py"
if [ ! -f "$UUID_PY" ]; then
  echo "Bundle is missing $UUID_PY"
  exit 1
fi
APP="dist/STAplus SCK.app"
HELPER_SRC="vendor/sck-locate/sck-locate.app"
HELPER_DST="$APP/Contents/Resources/sck-locate.app"
if [ ! -x "$HELPER_SRC/Contents/MacOS/sck-locate" ]; then
  echo "Missing $HELPER_SRC — run ./vendor/sck-locate/build.sh first."
  exit 1
fi
# Copy a real .app into Resources. PyInstaller only symlinks datas into
# Frameworks, and Chromium will not follow those for file:// or helpers.
rm -rf "$HELPER_DST"
cp -R "$HELPER_SRC" "$HELPER_DST"
chmod +x "$HELPER_DST/Contents/MacOS/sck-locate"
codesign --force --sign - --identifier de.secure-dimensions.staplus.sck.locate "$HELPER_DST" >/dev/null
codesign --force --sign - --identifier de.secure-dimensions.staplus.sck "$APP" >/dev/null
if [ ! -x "$HELPER_DST/Contents/MacOS/sck-locate" ]; then
  echo "Bundle is missing the location helper at $HELPER_DST"
  exit 1
fi
if [ ! -f "$APP/Contents/Resources/sck_map.html" ]; then
  echo "Bundle is missing sck_map.html"
  exit 1
fi
echo "Built: $(pwd)/$APP"
