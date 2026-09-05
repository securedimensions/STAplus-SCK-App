# Copyright (C) 2023 Secure Dimensions GmbH, Munich, Germany.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import datetime
import json
import os
import random
import time
import traceback
import string
import requests
import math

import staplus_client.model.feature_of_interest
from staplus_client.utils import transform_entity_to_json_dict
from geojson import Point, Feature
from staplus_client.service import auth_handler
from paho.mqtt import client as mqtt_client
from paho.mqtt.enums import MQTTErrorCode  # For paho-mqtt v2.x readability
from datetime import datetime, timezone
from serial import Serial

import h3
import base64
import hashlib
import logging
import secrets
import sys
import webbrowser
import jwt
from jwt import PyJWKClient
from typing import Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit
from requests.auth import HTTPBasicAuth
import staplus_client as staPlus
import sta_dggs_client as dggs

FIRST_RECONNECT_DELAY = 1
MAX_RECONNECT_DELAY = 60
# Refresh MQTT bearer token before the typical 30-minute expiry
TOKEN_REFRESH_INTERVAL = 25 * 60
OAUTH_SCOPES = [
    "openid",
    "profile",
    "idp",
    "offline_access",
    "citiobs.secd.eu#create",
    "citiobs.secd.eu#update",
]
# STAplus demo API audience registered with AUTHENIX.
STA_AUDIENCE = "3042e50b-dc09-4817-b34c-1b06c709da78"
AUTHENIX_ORIGIN = "https://authenix.eu"
AUTHENIX_AUTHORIZE = AUTHENIX_ORIGIN + "/oauth/authorize"
AUTHENIX_TOKEN = AUTHENIX_ORIGIN + "/oauth/token"
AUTHENIX_JWKS = AUTHENIX_ORIGIN + "/.well-known/jwks.json"
AUTHENIX_REGISTER = AUTHENIX_ORIGIN + "/oauth/register"
AUTHENIX_LOGOUT = AUTHENIX_ORIGIN + "/openid/logout"
OAUTH_REDIRECT_URI = "http://127.0.0.1:4711/SensorApp"
OAUTH_LOGOUT_REDIRECT_URI = "http://127.0.0.1:4711/SensorApp/logout"
AUTHENIX_REGISTER_LOGO_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4"
    "//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg=="
)

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
_logger = logging.getLogger()

url = "https://citiobs.demo.secure-dimensions.de/stapluscelltest/v1.1"
#url = "http://localhost:8080/FROST-Server/v1.1"
broker = 'citiobs.demo.secure-dimensions.de'
#broker = '127.0.0.1'
port = 3883
#port = 1883
topic = "v1.1/Observations"
client_id = f'python-mqtt-{random.randint(0, 1000)}'
kit_id = '16526'
#location = staPlus.Location(name="Spitzingsee", description="A nice place on Earth", location=Point((11.885329792,47.659664028)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Munich", description="A nice place on Earth", location=Point((11.509234,48.1107284)), encoding_type='application/geo+json')
#location = staPlus.Location(name="London", description="Geovation Hub", location=Point((-0.0996240,51.5244167)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Cape Town", description="A diverse place on Earth", location=Point((18.423300,-33.918861)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Dublin", description="A rainy place on Earth", location=Point((-6.222995, 53.306816)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Montreal", description="A pretty place on Earth", location=Point((-73.561668, 45.508888)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Montreal", description="Mont Royal Center", location=Point((-73.643059, 45.516109)), encoding_type='application/geo+json')
location = staPlus.Location(name="Schliersee", description="A nice place on Earth", location=Point((11.860125651759835,47.73457097754226)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Thessaloniki", description="A sunny place on Earth", location=Point((22.951011263177264, 40.59529301861192)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Rome", description="A sunny and nice place on Earth", location=Point((12.4634654,41.8358714)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Oslo", description="At Deichman Library, a nice place on Earth", location=Point((10.752602603269894,59.908823365033165)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Oslo", description="At Nedre Lokka Cocktail Bar :)", location=Point((10.759240260213346,59.91896661895605)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Aix-en-Provence", description="A nice but very hot place on Earth", location=Point((5.4398124,43.5289402)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Rotterdam", description="VONK is a nice place on Earth", location=Point((4.4818404, 51.9219658)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Oulu", description="The University of Oulu is a very nice place", location=Point((25.4663717,65.0589239)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Oslo", description="NILU", location=Point((11.0505295,59.9753226)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Helsinki", description="Cumpula Campus", location=Point((24.9624645,60.2038549)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Timisoara", description="University West", location=Point((21.2168783,45.7428234)), encoding_type='application/geo+json')
#location = staPlus.Location(name="Budapest", description="Hotel Continental", location=Point((19.0645204,47.4970053)), encoding_type='application/geo+json')

# Cell resolution
resolution = 9

# USB connection to the SCK (opened by the CLI or the Qt app, not at import)
DEFAULT_SCK_PORT = '/dev/tty.usbmodem14101'
SCK_BAUD = 115200
SCK_SAMPLE_INTERVAL = 10
SCK_MONITOR_CMD = (
    'shell -on\n'
    'monitor -noms Temperature,Humidity,Light,Noise dBA,Barometric pressure,PM 1.0,PM 2.5,PM 10.0\n'
)

def get_elevation(lat: float, lon: float, timeout: float = 10.0) -> float:
    """
    Look up ground elevation (meters above sea level) for a GPS coordinate
    using the free Open-Elevation API.
 
    Raises requests.RequestException on network/API failure.
    """
    _ELEVATION_API_URL = "https://api.open-elevation.com/api/v1/lookup"
    resp = requests.get(
        _ELEVATION_API_URL,
        params={"locations": f"{lat},{lon}"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return float(data["results"][0]["elevation"])

def pressure_normalization_factor(
    temperature: float = 15.0,
    elevation: float = 0.0,
) -> float:
    """
    Compute the multiplicative factor to normalize a raw barometric pressure
    reading taken at elevation to its sea-level equivalent.
 
    Usage:
        factor = pressure_normalization_factor(20, 521)
        p_sea_level = p_raw * factor
 
    Parameters
    ----------
    temperature : float, optional
        Local air temperature in Celsius. Defaults to 15degC (ICAO standard
        atmosphere at sea level). Pass the sensor's own temperature reading
        for better accuracy if available.
    elevation : float, optional
        Altitude above sea level in meters. If omitted, it is looked up
        automatically from lat/lon (requires network access). Pass this
        directly if you already have a GPS altitude fix (and have corrected
        it from the WGS84 ellipsoid to orthometric/MSL height), to skip the
        lookup and avoid its accuracy limitations.
 
    Returns
    -------
    float
        Multiplicative correction factor (>= 1.0 for elevation >= 0).
    """
    _G = 9.80665        # gravity, m/s^2
    _M = 0.0289644      # molar mass of dry air, kg/mol
    _R = 8.31447        # universal gas constant, J/(mol*K)
    
    t_kelvin = temperature + 273.15
    factor = math.exp((_G * _M * elevation) / (_R * t_kelvin))
    return factor

def generate_sha256_pkce(length: int) -> Tuple[str, str]:
    if not (43 <= length <= 128):
        raise Exception("Invalid length: " % str(length))
    verifier = secrets.token_urlsafe(length)
    encoded = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest())
    challenge = encoded.decode('ascii')[:-1]
    return verifier, challenge

def _as_string_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [part for part in value.split() if part]
    if isinstance(value, (list, tuple)):
        return [str(part) for part in value if part]
    return []


def _valid_client_metadata(meta):
    if not isinstance(meta, dict) or "error" in meta or not meta.get("client_id"):
        return False
    if not meta.get("client_secret"):
        return False
    grants = _as_string_list(meta.get("grant_types"))
    if "authorization_code" not in grants:
        return False
    audiences = _as_string_list(meta.get("audiences"))
    return STA_AUDIENCE in audiences


def _oauth_form_post(url, form, client_id, client_secret=""):
    data = dict(form)
    data["client_id"] = client_id
    kwargs = {
        "data": data,
        "headers": {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        "timeout": 30,
    }
    if client_secret:
        data["client_secret"] = client_secret
        kwargs["auth"] = HTTPBasicAuth(client_id, client_secret)
    return requests.post(url, **kwargs)


def _load_sensor_app_json():
    candidates = [os.path.join(os.getcwd(), "SensorApp.json")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "SensorApp.json"))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, "SensorApp.json"))
    candidates.append(os.path.join(here, "SensorApp.json_"))
    seen = set()
    for path in candidates:
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if _valid_client_metadata(data):
            return data, path
    return {}, None


def _register_web_client():
    request = {
        "application_type": "web",
        "redirect_uris": [OAUTH_REDIRECT_URI],
        "post_logout_redirect_uris": [OAUTH_LOGOUT_REDIRECT_URI],
        "logout_uri": OAUTH_LOGOUT_REDIRECT_URI,
        "audiences": [STA_AUDIENCE],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code", "code id_token"],
        "client_name": "STAplus SCK App",
        "logo_uri": AUTHENIX_REGISTER_LOGO_URI,
        "scope": " ".join(OAUTH_SCOPES),
        "contacts": [
            "Secure Dimensions GmbH",
            "https://www.secure-dimensions.de",
            "W 28",
            "DE",
            "https://www.secure-dimensions.de/legal",
        ],
        "operator_country": "de",
        "tos_uri": "https://www.secure-dimensions.de/terms",
        "policy_uri": "https://www.secure-dimensions.de/privacy",
        "software_id": "b8815b0ff48b66ed3adbecb5d405fb15d941dbdb",
        "software_version": "1.2",
        "token_endpoint_auth_method": "client_secret_basic",
    }
    last_detail = "unknown error"
    for attempt in range(2):
        if attempt:
            time.sleep(11)
        response = requests.post(
            AUTHENIX_REGISTER,
            json=request,
            headers={"Accept": "application/json"},
            timeout=30,
        )
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code == 200 and _valid_client_metadata(body):
            return body
        if response.status_code == 429:
            last_detail = "AUTHENIX registration rate-limited"
            continue
        last_detail = body.get("error_description") or body.get("error") or response.text[:300]
    raise RuntimeError("App registration failed: %s" % last_detail)


def registerApp() -> Tuple[str, str]:
    dest = os.path.join(os.getcwd(), "SensorApp.json")
    app_metadata, loaded_from = _load_sensor_app_json()
    register = not _valid_client_metadata(app_metadata)
    if _valid_client_metadata(app_metadata):
        expires = app_metadata.get("expires")
        if expires is not None:
            try:
                if int(time.time()) >= int(expires):
                    register = True
            except (TypeError, ValueError):
                pass

    if register:
        app_metadata = _register_web_client()
        with open(dest, "w", encoding="utf-8") as handle:
            json.dump(app_metadata, handle)
    elif loaded_from and os.path.abspath(loaded_from) != os.path.abspath(dest):
        if os.path.basename(loaded_from) != "SensorApp.json_":
            with open(dest, "w", encoding="utf-8") as handle:
                json.dump(app_metadata, handle)

    client_id = app_metadata["client_id"]
    client_secret = app_metadata.get("client_secret") or ""
    _logger.info("client_id :%s", client_id)
    return client_id, client_secret


def updateTokens(refresh_token):
    client_id, client_secret = registerApp()
    response = _oauth_form_post(
        AUTHENIX_TOKEN,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "audience": STA_AUDIENCE,
        },
        client_id,
        client_secret,
    )
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200 or not body.get("access_token"):
        detail = body.get("error_description") or body.get("error") or response.text[:300]
        raise RuntimeError("Token refresh failed: %s" % detail)
    return body["access_token"], body.get("refresh_token") or refresh_token


class DeviceAuthCancelled(Exception):
    """Sign-in stopped because the user cancelled."""


def _id_token_claims(id_token, client_id):
    jwks_client = PyJWKClient(AUTHENIX_JWKS)
    signing_key = jwks_client.get_signing_key_from_jwt(id_token)
    return jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=client_id,
        options={"verify_exp": False, "verify_iat": False},
    )


def _oauth_loopback_path(url):
    parts = urlsplit(url)
    if parts.hostname not in ("127.0.0.1", "localhost"):
        return None
    if parts.port not in (4711,):
        return None
    return (parts.path or "").rstrip("/")


def is_oauth_redirect(url):
    return _oauth_loopback_path(url) == "/SensorApp"


def is_oauth_logout_redirect(url):
    return _oauth_loopback_path(url) == "/SensorApp/logout"


def logout_url(id_token=""):
    """AUTHENIX RP-initiated logout (end_session / logout_uri)."""
    params = {"post_logout_redirect_uri": OAUTH_LOGOUT_REDIRECT_URI}
    if id_token:
        params["id_token_hint"] = id_token
    return AUTHENIX_LOGOUT + "?" + urlencode(params)


def _parse_oauth_redirect(url):
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params.update(dict(parse_qsl(parts.fragment, keep_blank_values=True)))
    return params


def start_authorization():
    """Build an AUTHENIX authorization-code URL for the embedded or system browser."""
    client_id, client_secret = registerApp()
    verifier, challenge = generate_sha256_pkce(64)
    state = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "response_type": "code",
            "response_mode": "query",
            "scope": " ".join(OAUTH_SCOPES),
            "audience": STA_AUDIENCE,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": verifier,
        "state": state,
        "nonce": nonce,
        "url": AUTHENIX_AUTHORIZE + "?" + query,
    }


def finish_authorization(started, redirect_url):
    """Exchange the AUTHENIX authorization code for tokens."""
    params = _parse_oauth_redirect(redirect_url)
    if params.get("error"):
        raise RuntimeError(
            "Authorization failed: %s" % (params.get("error_description") or params.get("error"))
        )
    if params.get("state") != started["state"]:
        raise RuntimeError("Authorization state mismatch.")
    code = params.get("code")
    if not code:
        raise RuntimeError("AUTHENIX redirect did not include an authorization code.")
    response = _oauth_form_post(
        AUTHENIX_TOKEN,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "code_verifier": started["code_verifier"],
            "audience": STA_AUDIENCE,
        },
        started["client_id"],
        started["client_secret"],
    )
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200 or not body.get("access_token"):
        detail = body.get("error_description") or body.get("error") or response.text[:300]
        raise RuntimeError("Token exchange failed: %s" % detail)
    id_token = body.get("id_token")
    if not id_token:
        raise RuntimeError("Token response did not include an id_token.")
    user = _id_token_claims(id_token, started["client_id"])
    return body["access_token"], body.get("refresh_token") or "", user, id_token


def authorize():
    started = start_authorization()
    _logger.info("Open this url in your browser\n%s", started["url"])
    webbrowser.open(started["url"], new=0, autoraise=True)
    from http.server import BaseHTTPRequestHandler, HTTPServer

    result = {"url": None}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            result["url"] = "http://127.0.0.1:4711" + self.path
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"You can close this window and return to the app.")

        def log_message(self, *_args):
            return

    httpd = HTTPServer(("127.0.0.1", 4711), Handler)
    httpd.timeout = 1
    deadline = time.time() + 600
    while result["url"] is None and time.time() < deadline:
        httpd.handle_request()
    httpd.server_close()
    if not result["url"]:
        raise RuntimeError("Timed out waiting for AUTHENIX sign-in.")
    access_token, refresh_token, user, _id_token = finish_authorization(started, result["url"])
    _logger.info(user)
    return access_token, refresh_token, user

def refresh_mqtt_auth(client):
    """Refresh OAuth tokens and update MQTT username/password for the next connect."""
    userdata = client.user_data_get()
    access_token, refresh_token = updateTokens(userdata['refresh_token'])
    userdata['access_token'] = access_token
    userdata['refresh_token'] = refresh_token
    userdata['last_refresh'] = time.time()
    client.username_pw_set('Bearer', access_token)
    _logger.debug('MQTT credentials refreshed')
    return access_token, refresh_token

def connect_mqtt(token, refresh_token):
    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print("Connected to MQTT Broker!")
        else:
            print("Failed to connect, return code %s" % reason_code)

    def on_disconnect(client, userdata, flags, reason_code, properties):
        print("Disconnected with result code: %s" % reason_code)
        if userdata.get('shutting_down'):
            return
        # Refresh credentials so paho's automatic reconnect uses a valid token.
        # Do not sleep or call reconnect() here — that blocks the network loop.
        try:
            refresh_mqtt_auth(client)
        except Exception as err:
            print("Failed to refresh MQTT token before reconnect: %s" % err)

    userdata = {
        'access_token': token,
        'refresh_token': refresh_token,
        'last_refresh': time.time(),
        'shutting_down': False,
    }
    client = mqtt_client.Client(
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2,
        protocol=mqtt_client.MQTTv5,
        client_id=client_id,
        userdata=userdata,
        reconnect_on_failure=True,
    )
    client.reconnect_delay_set(min_delay=FIRST_RECONNECT_DELAY, max_delay=MAX_RECONNECT_DELAY)
    client.username_pw_set('Bearer', token)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.connect(broker, port)
    #client.connect('localhost', port)
    client.loop_start()
    return client


def start_sck_monitor(sck):
    sck.write(SCK_MONITOR_CMD.encode('ASCII'))


def _utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _phenomenon_time(raw):
    """SCK reports Time 0 when its clock is unset; use the host UTC time instead."""
    text = str(raw).strip()
    if not text:
        return _utc_now_iso()
    try:
        if float(text) == 0:
            return _utc_now_iso()
    except ValueError:
        pass
    return text


def parse_sck_line(data):
    """Parse one SCK monitor line into a sample dict, or None if it is not a reading."""
    if data is None:
        return None
    if isinstance(data, bytes):
        data = data.decode('utf-8', errors='replace')
    data = data.strip()
    if not data or data.startswith('SCK'):
        return None
    obs = list(filter(None, data.split()))
    if len(obs) != 9:
        return None
    d, t, h, l, n, p, v_pm1, v_pm25, v_pm10 = obs
    return {
        'phenomenon_time': _phenomenon_time(d),
        'temperature': float(t),
        'humidity': float(h),
        'light': float(l),
        'noise': float(n),
        'pressure': float(p),
        'pm1': float(v_pm1),
        'pm25': float(v_pm25),
        'pm10': float(v_pm10),
        'raw': data,
    }


def prepare_publish(service, config):
    """Resolve FoI, Observation templates and license used for each MQTT publish."""
    foi = None
    fois = service.features_of_interest().query().filter("substringof('World',name)").list()
    if fois.entities:
        for f in fois.entities:
            foi = f
            break
    if foi is None:
        f = Feature(geometry=None)
        foi = staplus_client.model.feature_of_interest.FeatureOfInterest(
            name="The World",
            description="somewhere on this planet",
            encoding_type='application/geo+json',
            feature=f,
        )
        service.create(foi)

    print("foi: ", vars(foi))

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    temperature = staPlus.Observation(None, None, now)
    temperature.feature_of_interest = foi.clone()
    temperature.datastream = service.datastreams().find(config.get('temp_id')).clone()

    humidity = staPlus.Observation(None, None, now)
    humidity.feature_of_interest = foi.clone()
    humidity.datastream = service.datastreams().find(config.get('humidity_id')).clone()

    light = staPlus.Observation(None, None, now)
    light.feature_of_interest = foi.clone()
    light.datastream = service.datastreams().find(config.get('light_id')).clone()

    noise = staPlus.Observation(None, None, now)
    noise.feature_of_interest = foi.clone()
    noise.datastream = service.datastreams().find(config.get('noise_id')).clone()

    pressure = staPlus.Observation(None, None, now)
    pressure.feature_of_interest = foi.clone()
    pressure.datastream = service.datastreams().find(config.get('pressure_id')).clone()

    pm1 = staPlus.Observation(None, None, now)
    pm1.feature_of_interest = foi.clone()
    pm1.datastream = service.datastreams().find(config.get('pm1_id')).clone()

    pm25 = staPlus.Observation(None, None, now)
    pm25.feature_of_interest = foi.clone()
    pm25.datastream = service.datastreams().find(config.get('pm25_id')).clone()

    pm10 = staPlus.Observation(None, None, now)
    pm10.feature_of_interest = foi.clone()
    pm10.datastream = service.datastreams().find(config.get('pm10_id')).clone()

    cc_by = service.licenses().find(config['license_id'])
    return {
        'temperature': temperature,
        'humidity': humidity,
        'light': light,
        'noise': noise,
        'pressure': pressure,
        'pm1': pm1,
        'pm25': pm25,
        'pm10': pm10,
        'cc_by': cc_by,
    }


def apply_sample(config, ctx, sample):
    """Fill Observation templates from a parsed SCK sample. Returns values for display."""
    now = _utc_now_iso()
    d = _phenomenon_time(sample['phenomenon_time'])

    temperature = ctx['temperature']
    humidity = ctx['humidity']
    light = ctx['light']
    noise = ctx['noise']
    pressure = ctx['pressure']
    pm1 = ctx['pm1']
    pm25 = ctx['pm25']
    pm10 = ctx['pm10']

    temperature.phenomenon_time = d
    temperature.result_time = now
    temperature.result = sample['temperature']

    humidity.phenomenon_time = d
    humidity.result_time = now
    humidity.result = sample['humidity']

    light.phenomenon_time = d
    light.result_time = now
    light.result = sample['light']

    noise.phenomenon_time = d
    noise.result_time = now
    noise.result = sample['noise']

    pressure_factor = pressure_normalization_factor(temperature.result, config['elevation'])
    pressure.phenomenon_time = d
    pressure.result_time = now
    pressure.result = round(sample['pressure'] * pressure_factor, 2)

    pm1.phenomenon_time = d
    pm1.result_time = now
    pm1.result = sample['pm1']

    pm25.phenomenon_time = d
    pm25.result_time = now
    pm25.result = sample['pm25']

    pm10.phenomenon_time = d
    pm10.result_time = now
    pm10.result = sample['pm10']

    return {
        'phenomenon_time': d,
        'result_time': now,
        'temperature': temperature.result,
        'humidity': humidity.result,
        'light': light.result,
        'noise': noise.result,
        'pressure': pressure.result,
        'pm1': pm1.result,
        'pm25': pm25.result,
        'pm10': pm10.result,
        'pressure_factor': pressure_factor,
    }


def publish_sample(client, party, ctx, values):
    """Publish the current Observation templates as one ObservationGroup."""
    now = values['result_time']
    temperature = ctx['temperature']
    humidity = ctx['humidity']
    light = ctx['light']
    noise = ctx['noise']
    pressure = ctx['pressure']
    pm1 = ctx['pm1']
    pm25 = ctx['pm25']
    pm10 = ctx['pm10']
    cc_by = ctx['cc_by']

    print('publishing at ' + values['phenomenon_time'])
    print("pressure factor: ", values['pressure_factor'])
    print('Temperature   Humidity   Light  Pressure  Noise   PM1   PM2.5   PM10')
    print(f"{temperature.result}         {humidity.result}      {light.result}  {pressure.result}    {noise.result}   {pm1.result}  {pm25.result}    {pm10.result}")
    print(f"{temperature.datastream.id}         {humidity.datastream.id}      {light.datastream.id}  {pressure.datastream.id}    {noise.datastream.id}   {pm1.datastream.id}  {pm25.datastream.id}    {pm10.datastream.id}")

    group = staPlus.ObservationGroup(
        "OG {}".format(now),
        description=" ",
        creation_time=now,
        end_time=now,
        party=party.clone(),
        license=cc_by.clone(),
    )
    group.observations = [temperature, humidity, light, pressure, noise, pm1, pm25, pm10]
    payload = json.dumps(transform_entity_to_json_dict(group))
    print(payload)
    msg_info = client.publish("v1.1/ObservationGroups", payload)
    try:
        msg_info.wait_for_publish(timeout=5)
    except RuntimeError as e:
        print(f"Publish timeout error: {e}")

    print("--- MQTTMessageInfo Details ---")
    print(f"Message ID (mid)    : {msg_info.mid}")
    print(f"Result Code (rc)    : {msg_info.rc}")
    print(f"Is Fully Delivered? : {msg_info.is_published()}")
    return msg_info


def publish(service, client, config, party, sck, loc=None):
    loc = loc if loc is not None else location
    thing = service.things().query().filter("id eq '" + config.get('thing_id') + "'") #.expand("Locations").list().get(0)
    thing.locations = [loc]

    ctx = prepare_publish(service, config)
    start_sck_monitor(sck)
    while True:
        userdata = client.user_data_get()
        if time.time() - userdata.get('last_refresh', 0) >= TOKEN_REFRESH_INTERVAL:
            try:
                refresh_mqtt_auth(client)
            except Exception as err:
                print("Proactive MQTT token refresh failed: %s" % err)

        data = None
        while sck.in_waiting:
            data = sck.readline().decode('utf-8')
        sample = parse_sck_line(data)
        if sample is not None:
            values = apply_sample(config, ctx, sample)
            publish_sample(client, party, ctx, values)

        time.sleep(SCK_SAMPLE_INTERVAL)

def configure_ssl_certs():
    """Point requests/OpenSSL at a CA bundle (needed in the frozen Windows exe)."""
    try:
        import certifi
    except ImportError:
        return
    path = certifi.where()
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        bundled = os.path.join(meipass or os.path.dirname(sys.executable), "cacert.pem")
        if os.path.isfile(bundled):
            path = bundled
    if os.path.isfile(path):
        os.environ.setdefault("SSL_CERT_FILE", path)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", path)


def _odata_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def _format_sta_http_error(exc, href=""):
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    body = ""
    if response is not None:
        text = (response.text or "").strip()
        try:
            data = response.json()
            if isinstance(data, dict):
                body = str(
                    data.get("message") or data.get("error") or data.get("detail") or text
                )
            else:
                body = text
        except Exception:
            body = text
    parts = ["STAplus request failed"]
    if status:
        parts.append("(HTTP %s)" % status)
    if href:
        parts.append("for %s" % href)
    msg = " ".join(parts) + "."
    if body:
        msg += "\n\n" + body[:1500]
    else:
        msg += "\n\nThe server returned an empty error body."
    if status in (401, 403):
        msg += "\n\nSign in again, then retry Start publishing."
    return msg


def format_setup_error(err):
    """User-facing text for setup failures; keep HTTP status when the client hid it."""
    if isinstance(err, RuntimeError) and str(err).startswith("STAplus request failed"):
        return str(err)
    http = err if isinstance(err, requests.exceptions.HTTPError) else getattr(err, "__context__", None)
    if isinstance(http, requests.exceptions.HTTPError):
        href = ""
        if http.response is not None:
            href = http.response.url or ""
        return _format_sta_http_error(http, href)
    return "".join(traceback.format_exception(type(err), err, err.__traceback__))


def attach_sta_http_errors(service):
    """Turn empty/non-JSON HTTP error bodies into a readable RuntimeError."""
    original = service.execute

    def execute(method, url, **kwargs):
        href = url if isinstance(url, str) else str(url)
        kwargs.setdefault("timeout", 60)
        headers = dict(kwargs.get("headers") or {})
        token = ""
        handler = getattr(service, "auth_handler", None)
        if handler is not None:
            token = _normalize_bearer_token(getattr(handler, "token", ""))
        if token:
            headers["Authorization"] = "Bearer " + token
        kwargs["headers"] = headers
        try:
            return original(method, href, **kwargs)
        except requests.exceptions.HTTPError as exc:
            raise RuntimeError(_format_sta_http_error(exc, href)) from exc

    service.execute = execute
    return service


def _normalize_bearer_token(token):
    text = str(token or "").strip().replace("\r", "").replace("\n", "")
    if text.lower().startswith("bearer "):
        text = text[7:].strip()
    return text


def sta_service(access_token):
    auth = auth_handler.AuthHandler(_normalize_bearer_token(access_token))
    return attach_sta_http_errors(dggs.compose(url, auth_handler=auth))


def _reuse_or_create_base_observed_property(service, observed_property, by_definition, by_name):
    existing = None
    if observed_property.definition:
        existing = by_definition.get(observed_property.definition)
    if existing is None and observed_property.name:
        existing = by_name.get(observed_property.name)
    if existing is not None:
        print("reusing ObservedProperty {} ({})".format(existing.id, existing.name))
        return existing
    observed_property.properties = {'role': 'base'}
    op_id = service.create(observed_property)
    created = service.observed_properties().find(op_id)
    if created.definition:
        by_definition[created.definition] = created
    if created.name:
        by_name[created.name] = created
    print("created ObservedProperty {} ({})".format(created.id, created.name))
    return created

def _reuse_or_create_sensor(service, sensor):
    result = service.sensors().query().filter("name eq " + _odata_quote(sensor.name)).list()
    if result.entities:
        existing = result.entities[0]
        print("reusing Sensor {} ({})".format(existing.id, existing.name))
        return existing
    sensor_id = service.create(sensor)
    created = service.sensors().find(sensor_id)
    print("created Sensor {} ({})".format(created.id, created.name))
    return created

def setup(service, user, location):

    sub = user.get("sub") if isinstance(user, dict) else None
    if not sub:
        raise RuntimeError("Sign-in did not return a user id. Sign in again, then retry Start publishing.")
    parties = service.parties().query().filter("authId eq " + _odata_quote(sub))
    if (len(parties.list().entities) == 0):
        preferred_username = user.get('preferred_username') if 'preferred_username' in user.keys() else ''
        ljs = staPlus.Party(description='', display_name=preferred_username, role='individual')
        ljs_id = service.create(ljs)
    else:
        ljs = parties.list().entities[0]
        ljs_id = ljs.auth_id

    result = service.parties().query().filter("authId eq " + _odata_quote(ljs_id)).expand('Things').list()
    thing_found = False
    raspi = None
    if result.entities[0].things.entities:
        for thing in result.entities[0].things.entities:
            if 'sck_id' in thing.properties and thing.properties['sck_id'] == kit_id:
                thing_found = True
                print(json.dumps(transform_entity_to_json_dict(location)))
                location.things = [thing]
                locationId = service.create(location)
                print(locationId)
                raspi = thing
                break

    print('thing exists:' + str(thing_found))
    if thing_found == False:
        raspi = staPlus.Thing('Smart Citizen Kit 2.1', 'The Smart Citizen Kit that publishes on STAplus',
                              {'sck_id': kit_id})
        raspi.locations = [location]
        raspi.party = ljs
        raspiId = service.create(raspi)
        raspi = service.things().find(raspiId)

    lon, lat = location.location.coordinates
    elevation = get_elevation(lat, lon)
    
    cell_id = h3.latlng_to_cell(lat, lon, resolution)                    
            
    response = service.execute("GET", service.url.url)
    conformance = response.json()["serverSettings"]["conformance"]

    dggs_enabled = False
    for c in conformance:
        if (c == 'http://www.opengis.net/spec/sensorthings-dggs/1.0/conf/core'):
            dggs_enabled = True
            break;

    # Reuse ObservedProperties tagged as catalog "base" entries; create them on first run.
    temperature = staPlus.ObservedProperty('temp', 'https://vocabs.lter-europe.net/EnvThes/en/page/22035', 'Air Temperature')
    humidity = staPlus.ObservedProperty('RH', 'http://vocabs.lter-europe.net/EnvThes/22032', 'Relative Humidity')
    light = staPlus.ObservedProperty('light', 'https://qudt.org/vocab/quantitykind/LuminousExposure', 'Ambient Light')
    noise = staPlus.ObservedProperty('noise', 'https://www.merriam-webster.com/dictionary/noise', 'Noise Level')
    pressure = staPlus.ObservedProperty('pres', 'https://qudt.org/vocab/quantitykind/AtmosphericPressure', 'Barometric Pressure')
    pm1 = staPlus.ObservedProperty('PM1', 'http://codes.wmo.int/wmdr/ParticleSizeRange/60', 'Particulate matter with an average aerodynamic diameter of up to 1 micrometers')
    pm25 = staPlus.ObservedProperty('PM25', 'https://codes.wmo.int/wmdr/ParticleSizeRange/_70', 'Particulate matter with an average aerodynamic diameter of up to 2.5 micrometers')
    pm10 = staPlus.ObservedProperty('PM10', 'https://codes.wmo.int/wmdr/ParticleSizeRange/_100', 'Particulate matter with an average aerodynamic diameter of up to 10 micrometers')

    base_ops_by_definition = {}
    base_ops_by_name = {}
    for op in service.observed_properties().query().filter("properties/role eq 'base'").list():
        if op.definition:
            base_ops_by_definition[op.definition] = op
        if op.name:
            base_ops_by_name[op.name] = op

    temperature = _reuse_or_create_base_observed_property(service, temperature, base_ops_by_definition, base_ops_by_name)
    humidity = _reuse_or_create_base_observed_property(service, humidity, base_ops_by_definition, base_ops_by_name)
    light = _reuse_or_create_base_observed_property(service, light, base_ops_by_definition, base_ops_by_name)
    noise = _reuse_or_create_base_observed_property(service, noise, base_ops_by_definition, base_ops_by_name)
    pressure = _reuse_or_create_base_observed_property(service, pressure, base_ops_by_definition, base_ops_by_name)
    pm1 = _reuse_or_create_base_observed_property(service, pm1, base_ops_by_definition, base_ops_by_name)
    pm25 = _reuse_or_create_base_observed_property(service, pm25, base_ops_by_definition, base_ops_by_name)
    pm10 = _reuse_or_create_base_observed_property(service, pm10, base_ops_by_definition, base_ops_by_name)

    # CC-BY license for all datastreams
    cc_by = service.licenses().find('CC_BY')
    cc_by_clone = staPlus.License(name=cc_by.name, 
                                  definition=cc_by.definition, 
                                  logo=cc_by.logo,
                                  description='My CC_BY', 
                                  attribution_text='contributed by Secure Dimensions')
    cc_by_clone_id = service.create(cc_by_clone)

    # Reuse Sensors by name; create them on first run.
    sensorTemperatureHumidity = _reuse_or_create_sensor(service, staPlus.Sensor(
        'Sensirion SHT31', 'Sensirion SHT31 Humidity and Temperature Sensor', 'application/pdf',
        {'sck_id': 'SHT31', 'description': 'https://www.seeedstudio.com/Smart-Citizen-Starter-Kit-p-2865.html'},
        'https://www.farnell.com/datasheets/2901984.pdf'))
    sensorLight = _reuse_or_create_sensor(service, staPlus.Sensor(
        'Rohm BH1721FVC', 'Rohm BH1721FVC Digital 16bit Serial Output Type Ambient Light Sensor ICt',
        'application/pdf',
        {'description': 'https://www.seeedstudio.com/Smart-Citizen-Starter-Kit-p-2865.html'},
        'https://fscdn.rohm.com/en/products/databook/datasheet/ic/sensor/light/bh1721fvc-e.pdf'))
    sensorNoise = _reuse_or_create_sensor(service, staPlus.Sensor(
        'Invensense ICS-434342', 'Invensense ICS-434342. Low‐Noise Microphone with I2S Digital Output',
        'application/pdf',
        {'description': 'https://www.seeedstudio.com/Smart-Citizen-Starter-Kit-p-2865.html'},
        'https://invensense.tdk.com/wp-content/uploads/2015/02/ICS-43432-data-sheet-v1.3.pdf'))
    sensorPressure = _reuse_or_create_sensor(service, staPlus.Sensor(
        'MPL3115A2S', 'I2C precision pressure sensor with altimetry',
        'application/pdf',
        {'description': 'https://www.seeedstudio.com/Smart-Citizen-Starter-Kit-p-2865.html'},
        'https://www.nxp.com/docs/en/data-sheet/MPL3115A2S.pdf'))
    sensorPM = _reuse_or_create_sensor(service, staPlus.Sensor(
        'Planttower PMS 5003', 'Planttower PMS 5003 Digital universal particle concentration sensor',
        'application/pdf',
        {'description': 'https://www.seeedstudio.com/Smart-Citizen-Starter-Kit-p-2865.html'},
        'https://cdn-shop.adafruit.com/product-files/3686/plantower-pms5003-manual_v2-3.pdf'))

    # A new Datastream is created on every application start.
    celsius = staPlus.UnitOfMeasurement('Celsius', 'C', 'https://qudt.org/vocab/unit/DEG_C')
    datastream = staPlus.Datastream('Air Temperature', 'air temperature measured with the SmartCitizen Kit',
                                    'http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement', celsius)
    datastream.observed_property = temperature.clone()
    datastream.party = ljs
    datastream.thing = raspi
    datastream.license = cc_by_clone
    datastream.sensor = sensorTemperatureHumidity.clone()
    if dggs_enabled:
        datastream.cell = dggs.Cell(cell_id).clone()
    dsTemperatureId = service.create(datastream)

    # Air Humidity
    percentage = staPlus.UnitOfMeasurement('Percentage', '%', 'https://qudt.org/vocab/unit/PERCENT')
    datastream = staPlus.Datastream('Relative Humidity', 'air relative humidity measured with the SmartCitizen Kit',
                                    'http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement', percentage)
    datastream.observed_property = humidity.clone()
    datastream.party = ljs
    datastream.thing = raspi
    datastream.license = cc_by_clone
    datastream.sensor = sensorTemperatureHumidity.clone()
    if dggs_enabled:
            datastream.cell = dggs.Cell(cell_id).clone()
    dsHumidityId = service.create(datastream)

    # Light
    lux = staPlus.UnitOfMeasurement('Lumens per square meter', 'LUX', 'https://qudt.org/vocab/unit/LUX')
    datastream = staPlus.Datastream('Ambient Light', 'ambient light measured with the SmartCitizen Kit',
                                    'http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement', lux)
    datastream.observed_property = light.clone()
    datastream.party = ljs
    datastream.thing = raspi
    datastream.license = cc_by_clone
    datastream.sensor = sensorLight.clone()
    if dggs_enabled:
            datastream.cell = dggs.Cell(cell_id).clone()
    dsLightId = service.create(datastream)

    # Noise
    db = staPlus.UnitOfMeasurement('A-weighted decibel', 'dBA', 'https://qudt.org/vocab/unit/DeciB_A')
    datastream = staPlus.Datastream('Noise Level', 'noise measured with the SmartCitizen Kit',
                                    'http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement', db)
    datastream.observed_property = noise.clone()
    datastream.party = ljs
    datastream.thing = raspi
    datastream.license = cc_by_clone
    datastream.sensor = sensorNoise.clone()
    if dggs_enabled:
            datastream.cell = dggs.Cell(cell_id).clone()
    dsNoiseId = service.create(datastream)

    # Pressure
    kPa = staPlus.UnitOfMeasurement('kiloPascals', 'kPa', 'https://qudt.org/vocab/unit/KiloPA')
    datastream = staPlus.Datastream('Barometric Pressure', 'air pressure measured with the SmartCitizen Kit',
                                    'http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement', kPa)
    datastream.observed_property = pressure.clone()
    datastream.party = ljs
    datastream.thing = raspi
    datastream.license = cc_by_clone
    datastream.sensor = sensorPressure.clone()
    if dggs_enabled:
            datastream.cell = dggs.Cell(cell_id).clone()
    dsPressureId = service.create(datastream)

    # Unit of measure for PM
    ugm3 = staPlus.UnitOfMeasurement('Microgram per cubic meter', 'µg/m³', 'http://dd.eionet.europa.eu/vocabulary/uom/concentration/ug.m-3')

    # PM 1
    datastream = staPlus.Datastream('PM 1', 'PM 1 measured with the SmartCitizen Kit',
                                    'http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement', ugm3)
    datastream.observed_property = pm1.clone()
    datastream.party = ljs
    datastream.thing = raspi
    datastream.license = cc_by_clone
    datastream.sensor = sensorPM.clone()
    if dggs_enabled:
            datastream.cell = dggs.Cell(cell_id).clone()
    dsPM1Id = service.create(datastream)

    # PM 2.5
    datastream = staPlus.Datastream('PM 2.5', 'PM 2.5 measured with the SmartCitizen Kit',
                                    'http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement', ugm3)
    datastream.observed_property = pm25.clone()
    datastream.party = ljs
    datastream.thing = raspi
    datastream.license = cc_by_clone
    datastream.sensor = sensorPM.clone()
    if dggs_enabled:
            datastream.cell = dggs.Cell(cell_id).clone()
    dsPM25Id = service.create(datastream)

    # PM 10
    datastream = staPlus.Datastream('PM 10', 'PM 10 measured with the SmartCitizen Kit',
                                    'http://www.opengis.net/def/observationType/OGC-OM/2.0/OM_Measurement', ugm3)
    datastream.observed_property = pm10.clone()
    datastream.party = ljs
    datastream.thing = raspi
    datastream.license = cc_by_clone
    datastream.sensor = sensorPM.clone()
    if dggs_enabled:
            datastream.cell = dggs.Cell(cell_id).clone()
    dsPM10Id = service.create(datastream)

    return {'thing_id': str(raspi.id), 'temp_id': dsTemperatureId, 'humidity_id' : dsHumidityId, 'light_id': dsLightId, 'noise_id': dsNoiseId,
            'pressure_id': dsPressureId, 'pm1_id': dsPM1Id, 'pm25_id': dsPM25Id, 'pm10_id': dsPM10Id, 'elevation': elevation, 'license_id': cc_by_clone_id}

def on_publish(client, userdata, mid, reason_code, properties):
    print("mid: " + str(mid))

if __name__ == "__main__":
    configure_ssl_certs()
    access_token, refresh_token, user = authorize()
    service = sta_service(access_token)
    _logger.debug("processing with access token: " + access_token)
    config = setup(service, user, location)
    party = service.parties().find(user['sub'])
    client = connect_mqtt(access_token, refresh_token)
    sck = Serial(DEFAULT_SCK_PORT, SCK_BAUD, timeout=10)
    try:
        publish(service, client, config, party, sck, location)
    finally:
        client.user_data_get()['shutting_down'] = True
        client.loop_stop()
        client.disconnect()
        sck.close()

