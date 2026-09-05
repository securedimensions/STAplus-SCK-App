@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
  echo Missing venv\Scripts\python.exe — create the venv and install requirements first.
  exit /b 1
)

venv\Scripts\python.exe -m pip install -q pyinstaller PyQt6 PyQt6-WebEngine pillow
venv\Scripts\python.exe -c "import PyQt6, PyQt6.QtWebEngineWidgets; print('bundling with', PyQt6.__file__)"
venv\Scripts\python.exe make_app_icon.py
set PYTHONPATH=
venv\Scripts\python.exe -m PyInstaller --noconfirm --clean "STAplus SCK.spec"
if not exist "dist\STAplus SCK\_internal\orderedmultidict\__version__.py" (
  echo Bundle is missing orderedmultidict\__version__.py
  exit /b 1
)
if not exist "dist\STAplus SCK\_internal\uuid.py" (
  echo Bundle is missing uuid.py
  exit /b 1
)
if not exist "dist\STAplus SCK\_internal\sck_map.html" (
  echo Bundle is missing sck_map.html
  exit /b 1
)
if not exist "dist\STAplus SCK\_internal\vendor\leaflet\leaflet.js" (
  echo Bundle is missing vendor\leaflet\leaflet.js
  exit /b 1
)
echo Built: %CD%\dist\STAplus SCK\STAplus SCK.exe
