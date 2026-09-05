# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import uuid as uuid_mod

# QGIS (and similar) put themselves on PYTHONPATH and confuse Analysis.
os.environ.pop("PYTHONPATH", None)
sys.path[:] = [p for p in sys.path if "QGIS" not in p]

from PyInstaller.utils.hooks import collect_all, collect_data_files, get_package_paths

datas = [
    ("sck_map.html", "."),
    ("logo.png", "."),
]
if os.path.isfile("SensorApp.json"):
    datas.append(("SensorApp.json", "."))
if os.path.isfile("SensorApp.json_"):
    datas.append(("SensorApp.json_", "."))
if os.path.isdir("vendor/leaflet"):
    datas.append(("vendor/leaflet", "vendor/leaflet"))
_locate_app = os.path.join("vendor", "sck-locate", "sck-locate.app")
if sys.platform == "darwin" and os.path.isdir(_locate_app):
    datas.append((_locate_app, "sck-locate.app"))
datas += collect_data_files("orderedmultidict", include_py_files=True)
try:
    import certifi
    datas.append((certifi.where(), "."))
except Exception:
    pass
binaries = []
hiddenimports = [
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebChannel",
    "PyQt6.QtPositioning",
    "uuid",
    "_uuid",
    "copy",
    "pathlib",
    "secrets",
    "webbrowser",
    "csv",
    "decimal",
    "queue",
    "tempfile",
    "subprocess",
    "calendar",
    "hmac",
    "base64",
    "logging",
    "html",
    "http",
    "email",
    "xml",
    "xml.etree",
    "xml.etree.ElementTree",
    "numbers",
    "ipaddress",
    "pickle",
    "gzip",
    "zipfile",
    "ssl",
    "socket",
    "random",
    "hashlib",
    "string",
    "dataclasses",
    "jsonpatch",
    "jsonpointer",
    "six",
    "ujson",
    "demjson3",
    "orderedmultidict",
    "frost_sta_client",
    "furl",
    "geojson",
    "h3",
    "jwt",
    "requests",
    "certifi",
    "serial",
    "paho",
    "paho.mqtt",
    "paho.mqtt.client",
    "cryptography",
]
pathex = []
# Editable installs and lazy imports are often invisible to Analysis.
for pkg in (
    "sta_dggs_client",
    "staplus_client",
    "frost_sta_client",
    "jsonpickle",
    "demjson3",
    "furl",
    "geojson",
    "h3",
    "jwt",
    "requests",
    "serial",
    "paho",
    "cryptography",
    "PyQt6.QtPositioning",
):
    try:
        extra_datas, extra_binaries, extra_hidden = collect_all(pkg)
    except Exception:
        continue
    datas += extra_datas
    binaries += extra_binaries
    hiddenimports += extra_hidden
    try:
        pkg_root, _pkg_dir = get_package_paths(pkg)
    except Exception:
        continue
    if pkg_root and pkg_root not in pathex:
        pathex.append(pkg_root)
tmp_ret = collect_all("PyQt6")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]
icon = "logo.ico" if sys.platform == "win32" and os.path.isfile("logo.ico") else (
    "logo.icns" if sys.platform == "darwin" and os.path.isfile("logo.icns") else None
)


a = Analysis(
    ["SCK-App.py"],
    pathex=pathex,
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=["packaging/hooks"],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Analysis drops .py datas that are also imported modules. orderedmultidict
# opens __version__.py from disk, so put that file back into the bundle.
_omd_version = os.path.join(get_package_paths("orderedmultidict")[1], "__version__.py")
a.datas.append(("orderedmultidict/__version__.py", _omd_version, "DATA"))
# If the PyPI Python-2 `uuid` package still poisoned Analysis, force stdlib in.
if not any(name == "uuid" for name, _, _ in a.pure):
    a.pure.append(("uuid", uuid_mod.__file__, "PYMODULE"))
a.datas.append(("uuid.py", uuid_mod.__file__, "DATA"))
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="STAplus SCK",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="STAplus SCK",
)
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="STAplus SCK.app",
        icon=icon,
        bundle_identifier="de.secure-dimensions.staplus.sck",
        info_plist={
            "NSLocationUsageDescription": (
                "STAplus SCK uses your location to place the Thing marker on the map."
            ),
            "NSLocationWhenInUseUsageDescription": (
                "STAplus SCK uses your location to place the Thing marker on the map."
            ),
        },
    )
