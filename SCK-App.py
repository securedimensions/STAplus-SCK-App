# Copyright (C) 2023 Secure Dimensions GmbH, Munich, Germany.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""PyQt6 desktop app for the Smart Citizen Kit STAplus publisher."""

import json
import os
import shutil
import sys
import threading
import time
import traceback
from urllib.parse import unquote

# Chromium flags must be set before QtWebEngine is imported.
def _ensure_webengine_flags():
    if sys.platform != "win32":
        return
    current = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if "CalculateNativeWinOcclusion" in current:
        return
    extra = "--disable-features=CalculateNativeWinOcclusion"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (current + " " + extra).strip()


_ensure_webengine_flags()

# Keep a top-level PyQt6 import so PyInstaller always bundles Qt.
import PyQt6  # noqa: F401
from PyQt6.QtCore import (
    QBuffer,
    QByteArray,
    QCoreApplication,
    QIODevice,
    QObject,
    QProcess,
    Qt,
    QThread,
    QTimer,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)

# WebEngine binds its cookie directory at import time. Set the app name first
# so AUTHENIX cookies land under STAplus-SCK, not Python/QtWebEngine.
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
QCoreApplication.setApplicationName("STAplus-SCK")

from PyQt6.QtGui import QCloseEvent, QIcon
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from geojson import Point
from serial import Serial
from serial.tools import list_ports
from staplus_client.service import auth_handler
import staplus_client as staPlus
import sta_dggs_client as dggs

import SensorApp as sckapp

def _macos_resources_dir():
    """Real Contents/Resources in a frozen .app (not the Frameworks symlink tree)."""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return None
    resources = os.path.abspath(
        os.path.join(os.path.dirname(sys.executable), "..", "Resources")
    )
    if os.path.isfile(os.path.join(resources, "sck_map.html")):
        return resources
    return None


def _bundle_dir():
    resources = _macos_resources_dir()
    if resources:
        return resources
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _data_path(*parts):
    path = os.path.join(_bundle_dir(), *parts)
    real = os.path.realpath(path)
    return real if os.path.exists(real) else path


def _app_support_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(base, "STAplus-SCK")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "STAplus-SCK")
    return os.path.join(os.path.expanduser("~"), ".local", "share", "STAplus-SCK")


def _oauth_json_usable(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return sckapp._valid_client_metadata(data)
    except (OSError, json.JSONDecodeError, TypeError):
        return False


def _prepare_frozen_workdir():
    """OAuth client metadata is read as ./SensorApp.json; keep a writable copy for the frozen app."""
    if not getattr(sys, "frozen", False):
        return
    support = _app_support_dir()
    os.makedirs(support, exist_ok=True)
    bundled = os.path.join(_bundle_dir(), "SensorApp.json")
    dest = os.path.join(support, "SensorApp.json")
    if os.path.isfile(bundled) and (not os.path.isfile(dest) or not _oauth_json_usable(dest)):
        shutil.copy2(bundled, dest)
    os.chdir(support)


APP_DIR = _bundle_dir()
MAP_HTML = _data_path("sck_map.html")
MAP_SCHEME = "sckmap"
MAP_PAGE_HREF = MAP_SCHEME + "://bundle/sck_map.html"
APP_ICON = _data_path("logo.png")
_MAP_SCHEME_REGISTERED = False
_MAP_MIME = {
    ".css": b"text/css;charset=utf-8",
    ".gif": b"image/gif",
    ".htm": b"text/html;charset=utf-8",
    ".html": b"text/html;charset=utf-8",
    ".ico": b"image/x-icon",
    ".jpeg": b"image/jpeg",
    ".jpg": b"image/jpeg",
    ".js": b"text/javascript;charset=utf-8",
    ".json": b"application/json",
    ".png": b"image/png",
    ".svg": b"image/svg+xml",
}


def _register_map_scheme():
    """Serve the Leaflet page over a secure custom origin instead of file://."""
    global _MAP_SCHEME_REGISTERED
    if _MAP_SCHEME_REGISTERED:
        return
    scheme = QWebEngineUrlScheme(MAP_SCHEME.encode("ascii"))
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.CorsEnabled
        | QWebEngineUrlScheme.Flag.ContentSecurityPolicyIgnored
        | QWebEngineUrlScheme.Flag.FetchApiAllowed
    )
    QWebEngineUrlScheme.registerScheme(scheme)
    _MAP_SCHEME_REGISTERED = True


def _map_mime(path):
    return _MAP_MIME.get(os.path.splitext(path)[1].lower(), b"application/octet-stream")


class MapSchemeHandler(QWebEngineUrlSchemeHandler):
    def __init__(self, root_dir, parent=None):
        super().__init__(parent)
        self._root = os.path.realpath(root_dir)

    def requestStarted(self, job):
        rel = unquote(job.requestUrl().path() or "").replace("\\", "/").lstrip("/")
        if not rel or rel.endswith("/"):
            rel = (rel + "sck_map.html") if rel else "sck_map.html"
        if any(part == ".." for part in rel.split("/")):
            job.fail(QWebEngineUrlRequestJob.Error.UrlInvalid)
            return
        full = os.path.realpath(os.path.join(self._root, *rel.split("/")))
        try:
            if os.path.commonpath([self._root, full]) != self._root:
                job.fail(QWebEngineUrlRequestJob.Error.UrlInvalid)
                return
        except ValueError:
            job.fail(QWebEngineUrlRequestJob.Error.UrlInvalid)
            return
        if not os.path.isfile(full):
            print("map scheme 404:", rel)
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return
        try:
            with open(full, "rb") as handle:
                data = handle.read()
        except OSError:
            job.fail(QWebEngineUrlRequestJob.Error.RequestFailed)
            return
        buf = QBuffer(job)
        buf.setData(QByteArray(data))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(_map_mime(full), buf)


APP_SUPPORT_DIR = _app_support_dir()
_DATA_DIR = APP_SUPPORT_DIR if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
LOCATION_CACHE = os.path.join(_DATA_DIR, "sck_location.json")
AUTHENIX_PROFILE_DIR = os.path.join(APP_SUPPORT_DIR, "QtWebEngine", "sck-authenix")
READING_ROWS = [
    ("phenomenon_time", "Time"),
    ("temperature", "Temperature C"),
    ("humidity", "Humidity %"),
    ("light", "Light lux"),
    ("noise", "Noise dBA"),
    ("pressure", "Pressure kPa"),
    ("pm1", "PM1"),
    ("pm25", "PM2.5"),
    ("pm10", "PM10"),
]
CHART_KEYS = [key for key, _label in READING_ROWS if key != "phenomenon_time"]
CHART_WINDOW_S = 30 * 60


def load_location_cache():
    try:
        with open(LOCATION_CACHE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return {
            "lat": float(data["lat"]),
            "lon": float(data["lon"]),
            "name": data.get("name") or "",
        }
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def save_location_cache(lat, lon, name):
    with open(LOCATION_CACHE, "w", encoding="utf-8") as handle:
        json.dump({"lat": lat, "lon": lon, "name": name}, handle)


def locate_helper_path():
    names = []
    resources = _macos_resources_dir()
    if resources:
        names.append(
            os.path.join(resources, "sck-locate.app", "Contents", "MacOS", "sck-locate")
        )
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        names.extend(
            (
                os.path.join(exe_dir, "sck-locate.app", "Contents", "MacOS", "sck-locate"),
                os.path.join(exe_dir, "sck-locate"),
            )
        )
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            names.extend(
                (
                    os.path.join(meipass, "sck-locate.app", "Contents", "MacOS", "sck-locate"),
                    os.path.join(meipass, "sck-locate"),
                )
            )
    names.append(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "vendor",
            "sck-locate",
            "sck-locate.app",
            "Contents",
            "MacOS",
            "sck-locate",
        )
    )
    seen = set()
    for path in names:
        if path in seen:
            continue
        seen.add(path)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def _location_settings_help():
    if sys.platform == "win32":
        return (
            "Could not get the computer location. In Windows Settings, turn on Location "
            "and allow desktop apps to access it, then try Use my location again. "
            "You can also click the map."
        )
    if sys.platform == "darwin":
        return (
            "Could not get the computer location. Allow STAplus SCK in System Settings → "
            "Privacy & Security → Location Services if macOS asked."
        )
    return "Could not get the computer location. Click the map to place the marker."


def list_serial_ports():
    ports = []
    for info in list_ports.comports():
        label = info.device
        if info.description and info.description != "n/a":
            label = f"{info.device} ({info.description})"
        ports.append((info.device, label))
    return ports


class MapBridge(QObject):
    markerMoved = pyqtSignal(float, float)
    locationRequested = pyqtSignal()

    def __init__(self, lat, lon, parent=None):
        super().__init__(parent)
        self.lat = lat
        self.lon = lon

    @pyqtSlot(result=str)
    def initialPosition(self):
        return json.dumps({"lat": self.lat, "lon": self.lon})

    @pyqtSlot(float, float)
    def markerMovedTo(self, lat, lon):
        self.lat = float(lat)
        self.lon = float(lon)
        self.markerMoved.emit(self.lat, self.lon)

    @pyqtSlot()
    def requestLocation(self):
        self.locationRequested.emit()


class AuthCodeWorker(QThread):
    needs_browser = pyqtSignal(str)
    succeeded = pyqtSignal(str, str, object, str)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop = False
        self._redirect = None
        self._got_redirect = threading.Event()

    def stop(self):
        self._stop = True
        self._got_redirect.set()

    def set_redirect(self, url):
        if self._redirect:
            return
        self._redirect = url
        self._got_redirect.set()

    def run(self):
        try:
            started = sckapp.start_authorization()
            if self._stop:
                return
            self.needs_browser.emit(started["url"])
            deadline = time.time() + 600
            while not self._got_redirect.wait(0.25):
                if self._stop:
                    raise sckapp.DeviceAuthCancelled()
                if time.time() >= deadline:
                    raise RuntimeError("Timed out waiting for AUTHENIX sign-in.")
            if self._stop or not self._redirect:
                raise sckapp.DeviceAuthCancelled()
            access_token, refresh_token, user, id_token = sckapp.finish_authorization(
                started, self._redirect
            )
            self.succeeded.emit(access_token, refresh_token, user, id_token)
        except sckapp.DeviceAuthCancelled:
            return
        except Exception:
            self.failed.emit(traceback.format_exc())


class SetupWorker(QThread):
    succeeded = pyqtSignal(object, object, object)
    failed = pyqtSignal(str)

    def __init__(self, access_token, user, location, parent=None):
        super().__init__(parent)
        self.access_token = access_token
        self.user = user
        self.location = location

    def run(self):
        try:
            auth = auth_handler.AuthHandler(self.access_token)
            service = dggs.compose(sckapp.url, auth_handler=auth)
            config = sckapp.setup(service, self.user, self.location)
            party = service.parties().find(self.user["sub"])
            self.succeeded.emit(service, config, party)
        except Exception:
            self.failed.emit(traceback.format_exc())


class SerialWorker(QThread):
    sample = pyqtSignal(dict)
    failed = pyqtSignal(str)
    connected = pyqtSignal(str)
    finished_ok = pyqtSignal()

    def __init__(self, port, parent=None):
        super().__init__(parent)
        self.port = port
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        sck = None
        try:
            sck = Serial(self.port, sckapp.SCK_BAUD, timeout=1)
            sckapp.start_sck_monitor(sck)
            self.connected.emit(self.port)
            next_due = 0.0
            latest = None
            while not self._stop:
                line = sck.readline()
                if line:
                    parsed = sckapp.parse_sck_line(line)
                    if parsed is not None:
                        latest = parsed
                now = time.time()
                if latest is not None and now >= next_due:
                    self.sample.emit(latest)
                    latest = None
                    next_due = now + sckapp.SCK_SAMPLE_INTERVAL
        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            if sck is not None:
                try:
                    sck.close()
                except Exception:
                    pass
            self.finished_ok.emit()


def _qurl_is_logout_redirect(url):
    href = url.toString()
    if sckapp.is_oauth_logout_redirect(href):
        return True
    if url.host().lower() not in ("127.0.0.1", "localhost"):
        return False
    if url.port() not in (4711,):
        return False
    return url.path().rstrip("/").lower() == "/sensorapp/logout"


def _qurl_is_oauth_redirect(url):
    if _qurl_is_logout_redirect(url):
        return False
    href = url.toString()
    if sckapp.is_oauth_redirect(href):
        return True
    if url.host().lower() not in ("127.0.0.1", "localhost"):
        return False
    if url.port() not in (4711,):
        return False
    return url.path().rstrip("/").lower() == "/sensorapp"


def _qurl_is_loopback_handoff(url):
    return _qurl_is_oauth_redirect(url) or _qurl_is_logout_redirect(url)


class MapPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        print(f"map js[{line_number}]: {message}")

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if not is_main_frame:
            return True
        return url.scheme().lower() in ("file", "qrc", "data", "about", MAP_SCHEME)


class LoginPage(QWebEnginePage):
    oauthRedirect = pyqtSignal(str)

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self._captured = False

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if _qurl_is_loopback_handoff(url):
            if not self._captured:
                self._captured = True
                self.oauthRedirect.emit(url.toString())
            return False
        return True


def _make_login_profile(parent):
    """Named disk profile under AUTHENIX_PROFILE_DIR (set via app name before QtWebEngine import)."""
    profile = QWebEngineProfile("sck-authenix", parent)
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
    )
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
    profile.setPersistentPermissionsPolicy(
        QWebEngineProfile.PersistentPermissionsPolicy.StoreOnDisk
    )
    profile.settings().setAttribute(
        QWebEngineSettings.WebAttribute.LocalStorageEnabled, True
    )
    return profile


class OauthRedirectInterceptor(QWebEngineUrlRequestInterceptor):
    captured = pyqtSignal(str)

    def interceptRequest(self, info):
        url = info.requestUrl()
        if _qurl_is_loopback_handoff(url):
            info.block(True)
            self.captured.emit(url.toString())


class CollapsibleCard(QWidget):
    """Titled panel whose body can be folded to free vertical space."""

    toggled = pyqtSignal(bool)

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self._toggle = QToolButton()
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(True)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow)
        self._toggle.setAutoRaise(True)
        font = self._toggle.font()
        font.setBold(True)
        self._toggle.setFont(font)
        self._toggle.toggled.connect(self._on_toggled)

        header = QFrame()
        header.setFrameShape(QFrame.Shape.StyledPanel)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(6, 4, 6, 4)
        header_layout.addWidget(self._toggle, 1)

        self.body = QWidget()
        self._body_frame = QFrame()
        self._body_frame.setFrameShape(QFrame.Shape.StyledPanel)
        body_holder = QVBoxLayout(self._body_frame)
        body_holder.setContentsMargins(8, 6, 8, 8)
        body_holder.addWidget(self.body)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self._body_frame)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

    def _on_toggled(self, expanded):
        self._body_frame.setVisible(expanded)
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.toggled.emit(expanded)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("STAplus Smart Citizen Kit")
        self.resize(1200, 760)
        if os.path.isfile(APP_ICON):
            self.setWindowIcon(QIcon(APP_ICON))

        self.access_token = None
        self.refresh_token = None
        self.id_token = None
        self.user = None
        self.service = None
        self.config = None
        self.party = None
        self.publish_ctx = None
        self.mqtt_client = None
        self.publishing = False
        self.marker_confirmed = False
        self.serial_connected = False
        self.lat = None
        self.lon = None
        self._chart_history = []
        self._browser_mode = "map"
        self._authorize_url = ""
        self._consent_retry = False
        self._logout_pending = False

        self.auth_worker = None
        self.setup_worker = None
        self.serial_worker = None

        self.sign_in_btn = QPushButton("Sign in")
        self.cancel_sign_in_btn = QPushButton("Cancel sign-in")
        self.cancel_sign_in_btn.setVisible(False)
        self.logout_btn = QPushButton("Log out")
        self.logout_btn.setVisible(False)
        self.auth_status = QLabel("Not signed in")
        self.auth_status.setWordWrap(True)

        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(280)
        self.refresh_ports_btn = QPushButton("Refresh")
        self.connect_serial_btn = QPushButton("Connect kit")
        self.serial_status = QLabel("Kit not connected")

        self.name_edit = QLineEdit("")
        self.name_edit.clear()
        self.coord_label = QLabel("")
        self.coord_label.setWordWrap(True)
        self.coord_label.setMinimumWidth(160)
        self.coord_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.confirm_location_btn = QPushButton("Use this marker")

        self.start_btn = QPushButton("Start publishing")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)

        self.readings = QTableWidget(len(READING_ROWS), 2)
        self.readings.setHorizontalHeaderLabels(["Quantity", "Value"])
        self.readings.verticalHeader().setVisible(False)
        self.readings.horizontalHeader().setStretchLastSection(True)
        self.readings.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, (_key, label) in enumerate(READING_ROWS):
            self.readings.setItem(row, 0, QTableWidgetItem(label))
            self.readings.setItem(row, 1, QTableWidgetItem("—"))

        serial_card = CollapsibleCard("Smart Citizen Kit")
        serial_layout = QVBoxLayout(serial_card.body)
        serial_layout.setContentsMargins(0, 0, 0, 0)
        port_row = QHBoxLayout()
        port_row.addWidget(self.port_combo, 1)
        port_row.addWidget(self.refresh_ports_btn)
        serial_layout.addLayout(port_row)
        serial_layout.addWidget(self.connect_serial_btn)
        serial_layout.addWidget(self.serial_status)

        loc_card = CollapsibleCard("Location")
        loc_layout = QFormLayout(loc_card.body)
        loc_layout.setContentsMargins(0, 0, 0, 0)
        loc_layout.addRow("Name", self.name_edit)
        loc_layout.addRow("Marker", self.coord_label)
        loc_layout.addRow(self.confirm_location_btn)

        auth_card = CollapsibleCard("Account")
        auth_layout = QVBoxLayout(auth_card.body)
        auth_layout.setContentsMargins(0, 0, 0, 0)
        auth_layout.addWidget(self.sign_in_btn)
        auth_layout.addWidget(self.cancel_sign_in_btn)
        auth_layout.addWidget(self.logout_btn)
        auth_layout.addWidget(self.auth_status)

        publish_card = CollapsibleCard("STAplus")
        publish_layout = QVBoxLayout(publish_card.body)
        publish_layout.setContentsMargins(0, 0, 0, 0)
        publish_layout.addWidget(self.start_btn)
        self.publish_hint = QLabel("Login required")
        self.publish_hint.setWordWrap(True)
        publish_layout.addWidget(self.publish_hint)
        publish_layout.addWidget(self.stop_btn)

        readings_card = CollapsibleCard("Live readings")
        readings_layout = QVBoxLayout(readings_card.body)
        readings_layout.setContentsMargins(0, 0, 0, 0)
        readings_layout.addWidget(self.readings)
        readings_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(serial_card)
        left_layout.addWidget(loc_card)
        left_layout.addWidget(auth_card)
        left_layout.addWidget(publish_card)
        left_layout.addWidget(readings_card, 1)
        self._left_layout = left_layout
        self._readings_card = readings_card
        readings_card.toggled.connect(self._on_readings_card_toggled)

        self.bridge = MapBridge(self.lat, self.lon, self)
        self.map_view = QWebEngineView()
        self.map_page = MapPage(self.map_view)
        self.map_view.setPage(self.map_page)
        settings = self.map_page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self._grant_geolocation()
        self._map_file_fallback = False
        self._geo_source = None
        self._map_scheme_handler = MapSchemeHandler(_bundle_dir(), self)
        self.map_page.profile().installUrlSchemeHandler(
            MAP_SCHEME.encode("ascii"), self._map_scheme_handler
        )
        self.channel = QWebChannel(self.map_page)
        self.channel.registerObject("bridge", self.bridge)
        self.map_page.setWebChannel(self.channel)
        self.login_view = QWebEngineView()
        self._login_profile = _make_login_profile(self)
        self._login_profile.cookieStore().cookieAdded.connect(self._on_login_cookie_added)
        self._oauth_interceptor = OauthRedirectInterceptor(self)
        self._login_profile.setUrlRequestInterceptor(self._oauth_interceptor)
        self.login_page = LoginPage(self._login_profile, self.login_view)
        self.login_view.setPage(self.login_page)
        self.login_page.oauthRedirect.connect(self._on_oauth_redirect)
        self._oauth_interceptor.captured.connect(self._on_oauth_redirect)
        self.login_view.urlChanged.connect(self._on_login_url_changed)
        self.login_view.loadFinished.connect(self._on_login_load_finished)
        self.browser_stack = QStackedWidget()
        self.browser_stack.addWidget(self.map_view)
        self.browser_stack.addWidget(self.login_view)
        self._locate_proc = None
        self._locate_interactive = True
        self._locate_timeout = QTimer(self)
        self._locate_timeout.setSingleShot(True)
        self._locate_timeout.timeout.connect(self._on_locate_timeout)
        self._coord_flash_timer = QTimer(self)
        self._coord_flash_timer.setSingleShot(True)
        self._coord_flash_timer.timeout.connect(self._clear_coord_flash)
        self.bridge.markerMoved.connect(self.on_marker_moved)
        self.bridge.locationRequested.connect(self.request_os_location)
        self.map_view.loadFinished.connect(self._on_map_loaded)
        self.map_view.load(QUrl(MAP_PAGE_HREF))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.browser_stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 820])
        self.setCentralWidget(splitter)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Finding current location…")

        self.sign_in_btn.clicked.connect(self.start_sign_in)
        self.cancel_sign_in_btn.clicked.connect(self.cancel_sign_in)
        self.logout_btn.clicked.connect(self.start_logout)
        self.refresh_ports_btn.clicked.connect(self.reload_ports)
        self.connect_serial_btn.clicked.connect(self.toggle_serial)
        self.confirm_location_btn.clicked.connect(self.confirm_location)
        self.start_btn.clicked.connect(self.start_publishing)
        self.stop_btn.clicked.connect(self.stop_publishing)

        self.token_timer = QTimer(self)
        self.token_timer.setInterval(sckapp.TOKEN_REFRESH_INTERVAL * 1000)
        self.token_timer.timeout.connect(self.refresh_mqtt_token)

        self.reload_ports()
        self._update_start_enabled()

    def _coord_text(self):
        if not self.marker_confirmed or self.lat is None or self.lon is None:
            return ""
        return f"{self.lat:.6f}, {self.lon:.6f}"

    def _clear_coord_flash(self):
        self.coord_label.setStyleSheet("")

    def _flash_coords(self):
        self.coord_label.setStyleSheet(
            "QLabel { background-color: #ffe566; color: #111111; padding: 2px 6px; border-radius: 3px; }"
        )
        self._coord_flash_timer.start(1200)

    def _set_coords(self, lat, lon, confirmed=False):
        self.lat = float(lat)
        self.lon = float(lon)
        self.bridge.lat = self.lat
        self.bridge.lon = self.lon
        self.marker_confirmed = bool(confirmed)
        self.coord_label.setText(self._coord_text())
        self.confirm_location_btn.setText("Use this marker")
        if confirmed:
            self._flash_coords()
        else:
            self._coord_flash_timer.stop()
            self._clear_coord_flash()
        self._update_start_enabled()

    def _grant_geolocation(self):
        page = self.map_page
        if hasattr(page, "permissionRequested"):
            page.permissionRequested.connect(self._on_permission_requested)
        elif hasattr(page, "featurePermissionRequested"):
            page.featurePermissionRequested.connect(self._on_feature_permission)

    def _on_permission_requested(self, permission):
        try:
            from PyQt6.QtWebEngineCore import QWebEnginePermission
            if permission.permissionType() == QWebEnginePermission.PermissionType.Geolocation:
                permission.grant()
        except Exception:
            try:
                permission.grant()
            except Exception:
                pass

    def _on_feature_permission(self, origin, feature):
        granted = QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
        self.map_page.setFeaturePermission(origin, feature, granted)

    def _is_map_document(self, url):
        scheme = url.scheme().lower()
        return scheme == MAP_SCHEME or url.isLocalFile()

    def _on_map_loaded(self, ok):
        url = self.map_view.url()
        if not ok:
            if not self._map_file_fallback and url.scheme().lower() == MAP_SCHEME:
                self._map_file_fallback = True
                print("sckmap load failed, falling back to file://")
                self.map_view.load(QUrl.fromLocalFile(MAP_HTML))
            return
        if self._browser_mode != "map" or not self._is_map_document(url):
            return
        QTimer.singleShot(250, self._refit_map)
        if self.lat is not None and self.lon is not None:
            self._place_map_marker(self.lat, self.lon)
        else:
            self._request_os_location(interactive=False)
        self._sync_map_kit()

    def _sync_map_kit(self):
        connected = "true" if self.serial_connected else "false"
        self.map_view.page().runJavaScript(
            "window.sckKit && window.sckKit(%s);" % connected
        )

    def _place_map_marker(self, lat, lon):
        self.map_view.page().runJavaScript(
            "window.sckBoot && window.sckBoot(%s, %s);" % (lat, lon)
        )

    def _refit_map(self):
        if self._browser_mode != "map":
            return
        lat, lon = self.lat, self.lon
        restore = ""
        if lat is not None and lon is not None:
            restore = (
                "var c = window.sckMarkerCoords ? window.sckMarkerCoords() : '';"
                "if (!c) { window.sckBoot && window.sckBoot(%s, %s); }"
                "else if (window.map) { var p = c.split(',');"
                " window.map.setView([+p[0], +p[1]], Math.max(window.map.getZoom(), 13)); }"
            ) % (lat, lon)
        self.map_view.page().runJavaScript(
            "if (window.map && window.map.invalidateSize) { window.map.invalidateSize(); }"
            + restore
        )

    def _on_readings_card_toggled(self, expanded):
        self._left_layout.setStretchFactor(self._readings_card, 1 if expanded else 0)
        vertical = QSizePolicy.Policy.Expanding if expanded else QSizePolicy.Policy.Maximum
        self._readings_card.setSizePolicy(QSizePolicy.Policy.Preferred, vertical)

    def _show_map_page(self):
        self._browser_mode = "map"
        self._authorize_url = ""
        self._consent_retry = False
        self.browser_stack.setCurrentWidget(self.map_view)
        self.login_view.stop()
        self.login_view.setUrl(QUrl("about:blank"))
        QTimer.singleShot(50, self._refit_map)
        QTimer.singleShot(300, self._refit_map)

    def _show_authenix_page(self, url, mode="login"):
        self._browser_mode = mode
        self._authorize_url = url if mode == "login" else ""
        self._consent_retry = False
        self.login_page._captured = False
        self.login_view.load(QUrl(url))
        self.browser_stack.setCurrentWidget(self.login_view)

    def _on_login_cookie_added(self, cookie):
        # AUTHENIX reloads the consent page before Qt has committed
        # ASCookieConsent. Once the store has it, retry /oauth/authorize.
        name = bytes(cookie.name()).decode("ascii", "replace")
        domain = (cookie.domain() or "").lower()
        if name != "ASCookieConsent" or "authenix" not in domain:
            return
        if self._browser_mode != "login" or self._consent_retry or not self._authorize_url:
            return
        self._consent_retry = True
        QTimer.singleShot(150, self._continue_after_consent)

    def _continue_after_consent(self):
        if self._browser_mode != "login" or not self._authorize_url:
            return
        self.login_view.load(QUrl(self._authorize_url))

    def _on_login_url_changed(self, qurl):
        if self._browser_mode == "login" and _qurl_is_oauth_redirect(qurl):
            self._on_oauth_redirect(qurl.toString())
            return
        if self._browser_mode == "logout" and _qurl_is_logout_redirect(qurl):
            self._finish_logout()

    def _on_login_load_finished(self, _ok):
        if self._browser_mode != "logout" or not self._logout_pending:
            return
        href = self.login_view.url().toString().lower()
        if "/openid/logout" in href or "/oauth/logout" in href:
            QTimer.singleShot(400, self._finish_logout)

    def _on_oauth_redirect(self, url):
        if self._browser_mode == "logout" and (
            _qurl_is_logout_redirect(QUrl(url)) or sckapp.is_oauth_logout_redirect(url)
        ):
            self._finish_logout()
            return
        if self._browser_mode != "login":
            return
        self.auth_status.setText("Completing sign-in…")
        self.statusBar().showMessage("AUTHENIX returned. Completing sign-in…")
        if self.auth_worker is not None:
            self.auth_worker.set_redirect(url)

    def _update_account_ui(self):
        signed_in = bool(self.user)
        busy = self.cancel_sign_in_btn.isVisible()
        self.sign_in_btn.setVisible(not signed_in)
        self.sign_in_btn.setEnabled(not busy)
        self.logout_btn.setVisible(signed_in and not busy)

    def _set_sign_in_busy(self, busy):
        self.cancel_sign_in_btn.setVisible(busy)
        self.sign_in_btn.setEnabled(not busy)
        self.logout_btn.setEnabled(not busy)
        self._update_account_ui()

    def _clear_local_session(self):
        self.access_token = None
        self.refresh_token = None
        self.id_token = None
        self.user = None
        self.service = None
        self.config = None
        self.party = None
        self.sign_in_btn.setText("Sign in")

    def start_logout(self):
        if self.publishing:
            self.stop_publishing()
        if self.auth_worker is not None and self.auth_worker.isRunning():
            self.auth_worker.stop()
            self._set_sign_in_busy(False)
        self._logout_pending = True
        self.logout_btn.setEnabled(False)
        self.auth_status.setText("Signing out of AUTHENIX…")
        self.statusBar().showMessage("Signing out of AUTHENIX…")
        self._show_authenix_page(sckapp.logout_url(self.id_token or ""), mode="logout")

    def _finish_logout(self):
        if not self._logout_pending:
            return
        self._logout_pending = False
        self._clear_local_session()
        self._set_sign_in_busy(False)
        self.auth_status.setText("Signed out")
        self.statusBar().showMessage("Signed out. Sign in again to use a different account.")
        self._update_start_enabled()
        self._update_account_ui()
        # stop()/setUrl must not run inside acceptNavigationRequest or
        # the URL interceptor — Qt WebEngine aborts with SIGTRAP.
        QTimer.singleShot(0, self._after_logout_view)

    def _after_logout_view(self):
        try:
            self._login_profile.cookieStore().deleteSessionCookies()
        except Exception:
            pass
        self._show_map_page()

    def reload_ports(self):
        current = self.port_combo.currentData()
        self.port_combo.clear()
        ports = list_serial_ports()
        if not ports:
            self.port_combo.addItem("No serial ports found", "")
            return
        preferred = None
        for device, label in ports:
            self.port_combo.addItem(label, device)
            if preferred is None and any(token in device for token in ("usbmodem", "ttyACM", "ttyUSB", "COM")):
                preferred = device
        target = current or sckapp.DEFAULT_SCK_PORT
        index = self.port_combo.findData(target)
        if index < 0 and preferred:
            index = self.port_combo.findData(preferred)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)

    def request_os_location(self):
        self._request_os_location(interactive=True)

    def _request_os_location(self, interactive=True):
        helper = locate_helper_path()
        if helper:
            self._start_locate_helper(helper, interactive)
            return
        if self._start_qt_location(interactive):
            return
        self._request_browser_geolocation(interactive)

    def _start_locate_helper(self, helper, interactive):
        self._locate_interactive = interactive
        if self._locate_proc is not None:
            self._stop_locate_proc()
        self.statusBar().showMessage("Finding current location…")
        proc = QProcess(self)
        self._locate_proc = proc
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.finished.connect(self._on_locate_finished)
        proc.errorOccurred.connect(self._on_locate_process_error)
        self._locate_timeout.start(22000)
        proc.start(helper, [])

    def _start_qt_location(self, interactive=True):
        try:
            from PyQt6.QtPositioning import QGeoPositionInfoSource
        except ImportError:
            return False
        if self._geo_source is None:
            self._geo_source = QGeoPositionInfoSource.createDefaultSource(self)
            if self._geo_source is None:
                return False
            self._geo_source.positionUpdated.connect(self._on_qt_position)
            if hasattr(self._geo_source, "errorOccurred"):
                self._geo_source.errorOccurred.connect(self._on_qt_position_error)
        self._locate_interactive = interactive
        self.statusBar().showMessage("Finding current location…")
        self._locate_timeout.start(22000)
        try:
            self._geo_source.requestUpdate(20000)
        except Exception:
            self._locate_timeout.stop()
            return False
        return True

    def _on_qt_position(self, info):
        self._locate_timeout.stop()
        try:
            coord = info.coordinate()
        except Exception:
            coord = None
        if coord is None or not coord.isValid():
            self._on_location_unavailable()
            return
        self._apply_computer_location(coord.latitude(), coord.longitude())

    def _on_qt_position_error(self, error):
        try:
            from PyQt6.QtPositioning import QGeoPositionInfoSource
            access = QGeoPositionInfoSource.Error.AccessError
        except Exception:
            access = None
        if access is not None and error == access:
            self._locate_timeout.stop()
            self._on_location_denied()
            return
        # Timeout and other errors fall through to _on_locate_timeout if still pending.

    def _request_browser_geolocation(self, interactive=True):
        self._locate_interactive = interactive
        self.statusBar().showMessage("Finding current location…")
        self._locate_timeout.start(20000)
        self.map_view.page().runJavaScript(
            """
            (function () {
              if (!navigator.geolocation) return "unsupported";
              navigator.geolocation.getCurrentPosition(
                function (pos) {
                  window.sckBoot && window.sckBoot(pos.coords.latitude, pos.coords.longitude);
                },
                function (err) {
                  console.log("geolocation error " + err.code + " " + err.message);
                },
                { enableHighAccuracy: true, timeout: 18000, maximumAge: 60000 }
              );
              return "ok";
            })();
            """,
            0,
            self._on_browser_geo_started,
        )

    def _on_browser_geo_started(self, result):
        if result == "unsupported":
            self._locate_timeout.stop()
            self._on_location_unavailable()

    def _on_location_denied(self):
        self.statusBar().showMessage("Location permission denied. Click the map or “Use my location”.")
        if self._locate_interactive:
            QMessageBox.warning(self, "Location", _location_settings_help())

    def _on_location_unavailable(self):
        self.statusBar().showMessage("Could not get the current location. Click the map or “Use my location”.")
        if self._locate_interactive:
            QMessageBox.warning(self, "Location", _location_settings_help())

    def _stop_locate_proc(self):
        proc = self._locate_proc
        self._locate_proc = None
        self._locate_timeout.stop()
        if proc is None:
            return
        try:
            proc.finished.disconnect(self._on_locate_finished)
        except TypeError:
            pass
        try:
            proc.errorOccurred.disconnect(self._on_locate_process_error)
        except TypeError:
            pass
        if proc.state() != QProcess.ProcessState.NotRunning:
            proc.kill()
        proc.deleteLater()

    def _on_locate_timeout(self):
        self._stop_locate_proc()
        if self._geo_source is not None:
            try:
                self._geo_source.stopUpdates()
            except Exception:
                pass
        self._on_location_unavailable()

    def _on_locate_process_error(self, error):
        if error == QProcess.ProcessError.Crashed:
            return
        self._locate_timeout.stop()
        self.statusBar().showMessage("Could not start the location helper.")
        if self._locate_interactive:
            QMessageBox.warning(
                self,
                "Location",
                "Could not start the location helper.",
            )

    def _on_locate_finished(self, code, _status):
        self._locate_timeout.stop()
        proc = self._locate_proc
        output = ""
        if proc is not None:
            output = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace").strip()
            proc.deleteLater()
            self._locate_proc = None
        if code == 0:
            lat = lon = None
            for line in reversed(output.splitlines()):
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    data = json.loads(line)
                    lat = float(data["lat"])
                    lon = float(data["lon"])
                    break
                except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                    continue
            if lat is not None and lon is not None:
                self._apply_computer_location(lat, lon)
                return
        if code == 2 or "permission denied" in output.lower():
            self._on_location_denied()
            return
        self._on_location_unavailable()

    def _apply_computer_location(self, lat, lon):
        self._locate_timeout.stop()
        self._set_coords(lat, lon, confirmed=False)
        self.map_view.page().runJavaScript(
            "window.sckBoot && window.sckBoot(%s, %s);" % (self.lat, self.lon)
        )
        self.statusBar().showMessage(
            "Marker moved to computer location. Click “Use this marker” to confirm."
        )

    def on_marker_moved(self, lat, lon):
        if self._locate_timeout.isActive():
            self._locate_timeout.stop()
        self._set_coords(lat, lon, confirmed=False)

    def confirm_location(self):
        if self.bridge.lat is not None and self.bridge.lon is not None:
            self._apply_confirmed_coords(self.bridge.lat, self.bridge.lon)
        self.map_view.page().runJavaScript(
            "window.sckMarkerCoords ? window.sckMarkerCoords() : ''",
            0,
            self._finish_confirm_location,
        )

    def _parse_marker_coords(self, raw):
        if raw is None or raw == "" or raw == "null":
            return None, None
        if isinstance(raw, dict):
            try:
                return float(raw.get("lat")), float(raw.get("lon"))
            except (TypeError, ValueError):
                return None, None
        text = str(raw).strip()
        if "," in text and not text.startswith("{"):
            left, right = text.split(",", 1)
            try:
                return float(left), float(right)
            except ValueError:
                return None, None
        if text.startswith("{"):
            try:
                data = json.loads(text)
                return float(data["lat"]), float(data["lon"])
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                return None, None
        return None, None

    def _apply_confirmed_coords(self, lat, lon):
        self._set_coords(lat, lon, confirmed=True)
        save_location_cache(self.lat, self.lon, self.name_edit.text().strip())
        self.statusBar().showMessage(f"Using marker {self.lat:.6f}, {self.lon:.6f}")

    def _finish_confirm_location(self, raw):
        lat, lon = self._parse_marker_coords(raw)
        if lat is None or lon is None:
            lat, lon = self.bridge.lat, self.bridge.lon
        if lat is None or lon is None:
            lat, lon = self.lat, self.lon
        if lat is None or lon is None:
            QMessageBox.warning(
                self,
                "No location",
                "Wait for the current location, click the map, or use “Use my location”.",
            )
            return
        self._apply_confirmed_coords(lat, lon)

    def start_sign_in(self):
        if self.auth_worker is not None and self.auth_worker.isRunning():
            return
        self._set_sign_in_busy(True)
        self.auth_status.setText("Starting Authenix sign-in…")
        self.statusBar().showMessage("Opening Authenix in the map view.")
        self.auth_worker = AuthCodeWorker(self)
        self.auth_worker.needs_browser.connect(self.on_auth_url_ready)
        self.auth_worker.succeeded.connect(self.on_signed_in)
        self.auth_worker.failed.connect(self.on_sign_in_failed)
        self.auth_worker.start()

    def on_auth_url_ready(self, authorize_url):
        self.auth_status.setText("Complete sign-in in the Authenix page on the right.")
        self.statusBar().showMessage("Complete sign-in in the Authenix page.")
        self._show_authenix_page(authorize_url)

    def cancel_sign_in(self):
        if self.auth_worker is not None:
            self.auth_worker.stop()
        self._set_sign_in_busy(False)
        self.auth_status.setText("Sign-in cancelled")
        self.statusBar().showMessage("Sign-in cancelled.")
        self._show_map_page()

    def on_signed_in(self, access_token, refresh_token, user, id_token=""):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.id_token = id_token or ""
        self.user = user
        name = user.get("preferred_username") or user.get("sub") or "signed in"
        self._set_sign_in_busy(False)
        self.auth_status.setText(f"Signed in as {name}")
        self.statusBar().showMessage("Signed in.")
        self._show_map_page()
        self._update_start_enabled()
        self._update_account_ui()

    def on_sign_in_failed(self, error):
        self._set_sign_in_busy(False)
        self.auth_status.setText("Sign-in failed")
        self._show_map_page()
        QMessageBox.critical(self, "Sign-in failed", error)

    def toggle_serial(self):
        if self.serial_worker is not None and self.serial_worker.isRunning():
            self.serial_worker.stop()
            self.connect_serial_btn.setEnabled(False)
            self.serial_status.setText("Disconnecting…")
            return
        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "No serial port", "Plug in the Smart Citizen Kit and click Refresh.")
            return
        self.connect_serial_btn.setEnabled(False)
        self.serial_status.setText(f"Opening {port}…")
        self.serial_worker = SerialWorker(port, self)
        self.serial_worker.connected.connect(self.on_serial_connected)
        self.serial_worker.sample.connect(self.on_sample)
        self.serial_worker.failed.connect(self.on_serial_failed)
        self.serial_worker.finished_ok.connect(self.on_serial_finished)
        self.serial_worker.start()

    def on_serial_connected(self, port):
        self.serial_connected = True
        self.connect_serial_btn.setEnabled(True)
        self.connect_serial_btn.setText("Disconnect kit")
        self.serial_status.setText(f"Connected: {port}")
        self.statusBar().showMessage("Kit connected.")
        self._chart_history = []
        self._sync_map_kit()
        self.map_view.page().runJavaScript("window.sckCharts && window.sckCharts([]);")
        self._update_start_enabled()

    def on_serial_failed(self, error):
        self.serial_connected = False
        self.connect_serial_btn.setEnabled(True)
        self.connect_serial_btn.setText("Connect kit")
        self.serial_status.setText("Connection failed")
        self._sync_map_kit()
        self._update_start_enabled()
        QMessageBox.critical(self, "Serial error", error)

    def on_serial_finished(self):
        self.serial_connected = False
        self.connect_serial_btn.setEnabled(True)
        self.connect_serial_btn.setText("Connect kit")
        if "fail" not in self.serial_status.text().lower():
            self.serial_status.setText("Kit not connected")
        self._sync_map_kit()
        self._update_start_enabled()

    def on_sample(self, sample):
        if self.publishing and self.config is not None and self.publish_ctx is not None:
            try:
                values = sckapp.apply_sample(self.config, self.publish_ctx, sample)
                self._show_readings(values)
                if self.mqtt_client is not None:
                    userdata = self.mqtt_client.user_data_get()
                    if time.time() - userdata.get("last_refresh", 0) >= sckapp.TOKEN_REFRESH_INTERVAL:
                        self.refresh_mqtt_token()
                    sckapp.publish_sample(self.mqtt_client, self.party, self.publish_ctx, values)
            except Exception:
                self.statusBar().showMessage("Publish failed; see console.")
                traceback.print_exc()
            return
        self._show_readings({
            "phenomenon_time": sample["phenomenon_time"],
            "temperature": sample["temperature"],
            "humidity": sample["humidity"],
            "light": sample["light"],
            "noise": sample["noise"],
            "pressure": sample["pressure"],
            "pm1": sample["pm1"],
            "pm25": sample["pm25"],
            "pm10": sample["pm10"],
        })

    def _show_readings(self, values):
        for row, (key, _label) in enumerate(READING_ROWS):
            value = values.get(key, "—")
            self.readings.setItem(row, 1, QTableWidgetItem(str(value)))
        now = time.time()
        point = {"ts": now, "t": str(values.get("phenomenon_time") or "")}
        for key in CHART_KEYS:
            try:
                point[key] = float(values[key])
            except (TypeError, ValueError, KeyError):
                continue
        self._chart_history.append(point)
        cutoff = now - CHART_WINDOW_S
        while self._chart_history and float(self._chart_history[0].get("ts") or 0) < cutoff:
            del self._chart_history[0]
        self.map_view.page().runJavaScript(
            "window.sckCharts && window.sckCharts([" + json.dumps(point) + "]);"
        )

    def _update_start_enabled(self):
        ready = bool(self.user) and self.serial_connected and self.marker_confirmed and not self.publishing
        self.start_btn.setEnabled(ready)
        need_login = not bool(self.user) and not self.publishing
        self.publish_hint.setText("Login required")
        self.publish_hint.setVisible(need_login)
        self.start_btn.setToolTip("Login required" if need_login else "")

    def start_publishing(self):
        if not self.user or not self.access_token:
            QMessageBox.warning(self, "Not signed in", "Sign in before publishing.")
            return
        if not self.marker_confirmed:
            QMessageBox.warning(self, "No location", "Place a marker and click “Use this marker”.")
            return
        if not self.serial_connected:
            QMessageBox.warning(self, "No kit", "Connect the Smart Citizen Kit first.")
            return
        name = self.name_edit.text().strip() or "SCK location"
        save_location_cache(self.lat, self.lon, name)
        loc = staPlus.Location(
            name=name,
            description="Location chosen in the SCK desktop app",
            location=Point((self.lon, self.lat)),
            encoding_type="application/geo+json",
        )
        self.start_btn.setEnabled(False)
        self.statusBar().showMessage("Creating Datastreams on STAplus…")
        self.setup_worker = SetupWorker(self.access_token, self.user, loc, self)
        self.setup_worker.succeeded.connect(self.on_setup_ready)
        self.setup_worker.failed.connect(self.on_setup_failed)
        self.setup_worker.start()

    def on_setup_ready(self, service, config, party):
        self.service = service
        self.config = config
        self.party = party
        try:
            self.publish_ctx = sckapp.prepare_publish(service, config)
            self.mqtt_client = sckapp.connect_mqtt(self.access_token, self.refresh_token)
        except Exception:
            self.start_btn.setEnabled(True)
            QMessageBox.critical(self, "MQTT failed", traceback.format_exc())
            return
        self.publishing = True
        self.stop_btn.setEnabled(True)
        self.token_timer.start()
        self.statusBar().showMessage(
            f"Publishing to Thing {config.get('thing_id')} (new Datastreams this session)."
        )
        self._update_start_enabled()

    def on_setup_failed(self, error):
        self.start_btn.setEnabled(True)
        QMessageBox.critical(self, "STAplus setup failed", error)
        self._update_start_enabled()

    def refresh_mqtt_token(self):
        if self.mqtt_client is None:
            return
        try:
            sckapp.refresh_mqtt_auth(self.mqtt_client)
            userdata = self.mqtt_client.user_data_get()
            self.access_token = userdata.get("access_token", self.access_token)
            self.refresh_token = userdata.get("refresh_token", self.refresh_token)
        except Exception as err:
            self.statusBar().showMessage(f"Token refresh failed: {err}")

    def stop_publishing(self):
        self.publishing = False
        self.token_timer.stop()
        self.stop_btn.setEnabled(False)
        if self.mqtt_client is not None:
            try:
                self.mqtt_client.user_data_get()["shutting_down"] = True
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except Exception:
                pass
            self.mqtt_client = None
        self.publish_ctx = None
        self.statusBar().showMessage("Publishing stopped. The kit can stay connected.")
        self._update_start_enabled()

    def closeEvent(self, event: QCloseEvent):
        self._stop_locate_proc()
        if self.auth_worker is not None and self.auth_worker.isRunning():
            self.auth_worker.stop()
            self.auth_worker.wait(2000)
        self.stop_publishing()
        if self.serial_worker is not None and self.serial_worker.isRunning():
            self.serial_worker.stop()
            self.serial_worker.wait(2000)
        # Detach the login page before the profile is destroyed so Chromium
        # can flush ASCookieConsent and localStorage to disk.
        if getattr(self, "login_view", None) is not None:
            self.login_view.stop()
            spare = QWebEnginePage(self.login_view)
            old_page = getattr(self, "login_page", None)
            self.login_page = None
            self.login_view.setPage(spare)
            if old_page is not None:
                old_page.deleteLater()
        event.accept()


def main():
    _prepare_frozen_workdir()
    _register_map_scheme()
    app = QApplication(sys.argv)
    if os.path.isfile(APP_ICON):
        app.setWindowIcon(QIcon(APP_ICON))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
