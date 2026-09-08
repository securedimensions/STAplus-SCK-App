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
from geojson import Point, Feature, LineString, Polygon, MultiPolygon
from staplus_client.service import auth_handler
from paho.mqtt import client as mqtt_client
from paho.mqtt.client import error_string
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
from urllib.parse import unquote, urlencode, urlsplit
from requests.auth import HTTPBasicAuth
import staplus_client as staPlus
import sta_dggs_client as dggs

FIRST_RECONNECT_DELAY = 1
MAX_RECONNECT_DELAY = 60
# AUTHENIX access tokens last 1800s; refresh ahead of that with the offline_access RT.
ACCESS_TOKEN_LIFETIME = 1800
TOKEN_REFRESH_INTERVAL = 25 * 60
OAUTH_SCOPES = [
    "openid",
    "profile",
    "idp",
    "offline_access",
    "citiobs.secd.eu#create",
    "citiobs.secd.eu#update",
]
# STAplus demo API audience registered with AUTHENIX (client registration only).
STA_AUDIENCE = "3042e50b-dc09-4817-b34c-1b06c709da78"
OAUTH_SOFTWARE_ID = "b8815b0ff48b66ed3adbecb5d405fb15d941dbdb"
OAUTH_SOFTWARE_VERSION = "1.3"
AUTHENIX_ORIGIN = "https://authenix.eu"
AUTHENIX_AUTHORIZE = AUTHENIX_ORIGIN + "/oauth/authorize"
AUTHENIX_TOKEN = AUTHENIX_ORIGIN + "/oauth/token"
AUTHENIX_JWKS = AUTHENIX_ORIGIN + "/.well-known/jwks.json"
AUTHENIX_TOKENINFO = AUTHENIX_ORIGIN + "/oauth/tokeninfo"
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
MQTT_PUBLISH_TOPIC = "v1.1/ObservationGroups"
# FROST MQTT does not PUBACK ObservationGroups; QoS 1 times out with rc=0.
MQTT_PUBLISH_QOS = 0
MQTT_PUBLISH_TIMEOUT = 5
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


OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
OVERPASS_USER_AGENT = (
    "STAplus-SCK-App/1.3 (https://github.com/securedimensions/STAplus-SCK-App)"
)
NEARBY_PLACES_RADIUS_M = 300
NEARBY_PLACES_LIMIT = 40
_OVERPASS_LEISURE = "park|playground|garden|nature_reserve"
_OVERPASS_NATURAL = "water|wood"
_OVERPASS_AMENITY = (
    "school|university|college|library|hospital|clinic|townhall|"
    "community_centre|theatre|cinema|place_of_worship|arts_centre"
)
_OVERPASS_TOURISM = "museum|attraction|gallery"
_OVERPASS_BUILDING = "public|civic|school|university|hospital|church|cathedral"


def _haversine_m(lat1, lon1, lat2, lon2):
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(min(1.0, a)))


def _overpass_coords(geom):
    coords = []
    for pt in geom or []:
        try:
            coords.append([float(pt["lon"]), float(pt["lat"])])
        except (KeyError, TypeError, ValueError):
            continue
    return coords


def _close_ring(coords):
    if len(coords) < 3:
        return coords
    if coords[0] != coords[-1]:
        return coords + [coords[0]]
    return coords


def _way_geometry(geom):
    coords = _overpass_coords(geom)
    if len(coords) < 2:
        return None
    closed = len(coords) >= 4 and coords[0] == coords[-1]
    if not closed and len(coords) >= 3:
        first, last = coords[0], coords[-1]
        if abs(first[0] - last[0]) < 1e-7 and abs(first[1] - last[1]) < 1e-7:
            coords = _close_ring(coords)
            closed = True
    if closed and len(coords) >= 4:
        return {"type": "Polygon", "coordinates": [_close_ring(coords)]}
    return {"type": "LineString", "coordinates": coords}


def _relation_geometry(el):
    outers = []
    inners = []
    for member in el.get("members") or []:
        if member.get("type") != "way":
            continue
        coords = _overpass_coords(member.get("geometry"))
        if len(coords) < 3:
            continue
        ring = _close_ring(coords)
        if len(ring) < 4:
            continue
        role = (member.get("role") or "outer").lower()
        if role == "inner":
            inners.append(ring)
        else:
            outers.append(ring)
    if not outers:
        return None
    if len(outers) == 1:
        return {"type": "Polygon", "coordinates": [outers[0]] + inners}
    return {"type": "MultiPolygon", "coordinates": [[ring] for ring in outers]}


def _element_geometry(el):
    etype = el.get("type")
    if etype == "node":
        try:
            return {"type": "Point", "coordinates": [float(el["lon"]), float(el["lat"])]}
        except (KeyError, TypeError, ValueError):
            return None
    if etype == "way":
        return _way_geometry(el.get("geometry"))
    if etype == "relation":
        return _relation_geometry(el)
    return None


def _geom_centroid_latlon(geom):
    if not isinstance(geom, dict):
        return None
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Point" and coords and len(coords) >= 2:
        return float(coords[1]), float(coords[0])
    if gtype == "LineString":
        pts = coords or []
    elif gtype == "Polygon":
        pts = (coords or [[]])[0]
    elif gtype == "MultiPolygon":
        pts = ((coords or [[[]]])[0] or [[]])[0]
    else:
        return None
    if not pts:
        return None
    lon = sum(float(p[0]) for p in pts) / len(pts)
    lat = sum(float(p[1]) for p in pts) / len(pts)
    return lat, lon


def _place_kind(tags):
    for key in ("leisure", "amenity", "tourism", "building", "natural", "landuse"):
        val = tags.get(key)
        if val:
            return str(val)
    return "place"


def _overpass_query(lat, lon, radius_m):
    around = "(around:%d,%.7f,%.7f)" % (int(radius_m), float(lat), float(lon))
    return (
        "[out:json][timeout:25];\n"
        "(\n"
        "  nwr%s[name][leisure~\"^(%s)$\"];\n"
        "  nwr%s[name][landuse=recreation_ground];\n"
        "  nwr%s[name][natural~\"^(%s)$\"];\n"
        "  nwr%s[name][amenity~\"^(%s)$\"];\n"
        "  nwr%s[name][tourism~\"^(%s)$\"];\n"
        "  nwr%s[name][building~\"^(%s)$\"];\n"
        ");\n"
        "out geom;"
    ) % (
        around, _OVERPASS_LEISURE,
        around,
        around, _OVERPASS_NATURAL,
        around, _OVERPASS_AMENITY,
        around, _OVERPASS_TOURISM,
        around, _OVERPASS_BUILDING,
    )


def _overpass_post(url, query, timeout=30.0):
    return requests.post(
        url,
        data={"data": query},
        headers={
            "User-Agent": OVERPASS_USER_AGENT,
            "Accept": "application/json",
        },
        timeout=timeout,
    )


def lookup_nearby_public_places(lat, lon, radius_m=NEARBY_PLACES_RADIUS_M):
    """Return a GeoJSON FeatureCollection of named public OSM places near lat/lon."""
    query = _overpass_query(lat, lon, radius_m)
    last_error = None
    data = None
    for index, url in enumerate(OVERPASS_ENDPOINTS):
        try:
            resp = _overpass_post(url, query)
            if resp.status_code in (429, 504) and index == 0:
                last_error = requests.HTTPError(
                    "%s %s" % (resp.status_code, url), response=resp
                )
                continue
            resp.raise_for_status()
            data = resp.json()
            break
        except (requests.RequestException, ValueError, json.JSONDecodeError) as err:
            last_error = err
            if index == 0:
                continue
            break
    if data is None:
        if last_error is not None:
            raise last_error
        raise RuntimeError("Overpass lookup failed")

    features = []
    seen = set()
    for el in data.get("elements") or []:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        etype = el.get("type")
        eid = el.get("id")
        if etype not in ("node", "way", "relation") or eid is None:
            continue
        osm_id = "%s/%s" % (etype, eid)
        if osm_id in seen:
            continue
        geom = _element_geometry(el)
        if not geom:
            continue
        center = _geom_centroid_latlon(geom)
        if center is None:
            continue
        seen.add(osm_id)
        distance_m = round(_haversine_m(lat, lon, center[0], center[1]))
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "osm_id": osm_id,
                "name": name,
                "kind": _place_kind(tags),
                "distance_m": distance_m,
            },
        })
    features.sort(key=lambda f: f["properties"]["distance_m"])
    return {
        "type": "FeatureCollection",
        "features": features[:NEARBY_PLACES_LIMIT],
    }


def _as_geojson_geometry(geom):
    if not isinstance(geom, dict):
        return None
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not gtype or coords is None:
        return None
    if gtype == "Point":
        return Point(tuple(coords))
    if gtype == "LineString":
        return LineString(coords)
    if gtype == "Polygon":
        return Polygon(coords)
    if gtype == "MultiPolygon":
        return MultiPolygon(coords)
    return geom


def _world_feature_of_interest(service):
    fois = service.features_of_interest().query().filter("substringof('World',name)").list()
    if fois.entities:
        return fois.entities[0]
    foi = staplus_client.model.feature_of_interest.FeatureOfInterest(
        name="The World",
        description="somewhere on this planet",
        encoding_type="application/geo+json",
        feature=Feature(geometry=None),
    )
    service.create(foi)
    return foi


def _place_feature_of_interest(service, foi_spec):
    props = foi_spec.get("properties") if isinstance(foi_spec, dict) else None
    geom = foi_spec.get("geometry") if isinstance(foi_spec, dict) else None
    if not props:
        return None
    osm_id = str(props.get("osm_id") or "").strip()
    name = str(props.get("name") or "").strip()
    geometry = _as_geojson_geometry(geom)
    if not osm_id or not name or geometry is None:
        return None
    key = "osm:" + osm_id
    try:
        fois = service.features_of_interest().query().filter(
            "substringof(" + _odata_quote(key) + ",description)"
        ).list()
        if fois.entities:
            return fois.entities[0]
    except Exception:
        pass
    foi = staplus_client.model.feature_of_interest.FeatureOfInterest(
        name=name[:200],
        description="Public OSM feature %s" % key,
        encoding_type="application/geo+json",
        feature=Feature(geometry=geometry),
    )
    service.create(foi)
    return foi


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
        return [part for part in value.replace(",", " ").split() if part]
    if isinstance(value, (list, tuple)):
        return [str(part) for part in value if part]
    return []


def _valid_client_metadata(meta):
    if not isinstance(meta, dict) or "error" in meta or not meta.get("client_id"):
        return False
    if not meta.get("client_secret"):
        return False
    grants = _as_string_list(meta.get("grant_types"))
    return "authorization_code" in grants


def _client_metadata_expired(meta):
    if not isinstance(meta, dict):
        return True
    expires = meta.get("expires")
    if expires is not None:
        try:
            return int(time.time()) >= int(expires)
        except (TypeError, ValueError):
            return True
    issued = meta.get("client_id_issued_at")
    if issued is not None:
        try:
            return int(time.time()) >= int(issued) + 7 * 24 * 3600
        except (TypeError, ValueError):
            return True
    return False


def _usable_client_metadata(meta):
    return _valid_client_metadata(meta) and not _client_metadata_expired(meta)


def _http_session():
    """STAplus/AUTHENIX HTTP that ignores Windows Internet Settings proxies.

    requests.trust_env is on by default, so Windows registry PAC/HTTP_PROXY
    can rewrite or fold the Authorization header. FROST then introspects a
    broken Bearer and returns HTTP 401 with an empty body.
    """
    session = getattr(_http_session, "_session", None)
    if session is None:
        session = requests.Session()
        session.trust_env = False
        session.proxies = {}
        session.headers.update({"Accept": "application/json"})
        _http_session._session = session
    return session


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
        "proxies": {},
    }
    if client_secret:
        data["client_secret"] = client_secret
        kwargs["auth"] = HTTPBasicAuth(client_id, client_secret)
    return _http_session().post(url, **kwargs)


def _load_sensor_app_json():
    candidates = [os.path.join(os.getcwd(), "SensorApp.json")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "SensorApp.json"))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, "SensorApp.json"))
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
        if _usable_client_metadata(data):
            return data, path
    return {}, None


def _register_error_text(body, response):
    if not isinstance(body, dict):
        return (response.text or "")[:300] or "unknown error"
    return (
        body.get("error_description")
        or body.get("error")
        or (response.text or "")[:300]
        or "unknown error"
    )


def _register_needs_new_client(detail, body):
    text = "%s %s" % (detail or "", json.dumps(body, default=str) if isinstance(body, dict) else "")
    text = text.lower()
    return any(
        token in text
        for token in (
            "client_id not found",
            "invalid_client",
            "unknown client",
            "expired",
        )
    )


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
        "software_id": OAUTH_SOFTWARE_ID,
        "software_version": OAUTH_SOFTWARE_VERSION,
        "token_endpoint_auth_method": "client_secret_basic",
    }
    last_detail = "unknown error"
    versions = [OAUTH_SOFTWARE_VERSION, "%s.%s" % (OAUTH_SOFTWARE_VERSION, int(time.time()))]
    for version in versions:
        request["software_version"] = version
        for attempt in range(2):
            if attempt:
                time.sleep(11)
            response = _http_session().post(
                AUTHENIX_REGISTER,
                json=request,
                headers={"Accept": "application/json"},
                timeout=30,
                proxies={},
            )
            try:
                body = response.json()
            except ValueError:
                body = {}
            if response.status_code == 200 and _usable_client_metadata(body):
                return body
            if response.status_code == 200 and _valid_client_metadata(body):
                last_detail = "AUTHENIX returned an expired client"
                break
            if response.status_code == 429:
                last_detail = "AUTHENIX registration rate-limited"
                continue
            last_detail = _register_error_text(body, response)
            if _register_needs_new_client(last_detail, body):
                break
            if response.status_code != 429:
                raise RuntimeError("App registration failed: %s" % last_detail)
    raise RuntimeError("App registration failed: %s" % last_detail)


def registerApp() -> Tuple[str, str]:
    dest = os.path.join(os.getcwd(), "SensorApp.json")
    app_metadata, loaded_from = _load_sensor_app_json()
    register = not _usable_client_metadata(app_metadata)

    if register:
        app_metadata = _register_web_client()
        with open(dest, "w", encoding="utf-8") as handle:
            json.dump(app_metadata, handle)
    elif loaded_from and os.path.abspath(loaded_from) != os.path.abspath(dest):
        with open(dest, "w", encoding="utf-8") as handle:
            json.dump(app_metadata, handle)

    client_id = app_metadata["client_id"]
    client_secret = app_metadata.get("client_secret") or ""
    _logger.info("client_id :%s", client_id)
    return client_id, client_secret


def _access_token_expires_at(body, issued_at=None):
    """Unix time when the access token should be treated as expired."""
    issued_at = time.time() if issued_at is None else float(issued_at)
    expires_in = body.get("expires_in")
    if expires_in is not None:
        try:
            return issued_at + max(0, int(expires_in))
        except (TypeError, ValueError):
            pass
    claims = _access_token_claims(body.get("access_token") or "")
    exp = claims.get("exp")
    if exp is not None:
        try:
            return float(exp)
        except (TypeError, ValueError):
            pass
    return issued_at + ACCESS_TOKEN_LIFETIME


def updateTokens(refresh_token):
    client_id, client_secret = registerApp()
    response = _oauth_form_post(
        AUTHENIX_TOKEN,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
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
    expires_at = _access_token_expires_at(body)
    _logger.info(
        "Refreshed AUTHENIX access token; expires in %ss",
        max(0, int(expires_at - time.time())),
    )
    return (
        body["access_token"],
        body.get("refresh_token") or refresh_token,
        expires_at,
    )


def ensure_fresh_tokens(access_token, refresh_token, expires_at=None, skew=60):
    """Return a still-valid access token, refreshing with offline_access when needed."""
    if refresh_token and not access_token_usable(
        access_token, skew=skew, expires_at=expires_at
    ):
        return updateTokens(refresh_token)
    return access_token, refresh_token, expires_at


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


def _parse_oauth_query(query):
    params = {}
    for part in (query or "").lstrip("?").split("&"):
        if not part:
            continue
        key, _, val = part.partition("=")
        # unquote, not parse_qsl: '+' is valid in AUTHENIX codes. Windows QUrl
        # PrettyDecoded turns %2B into '+', and parse_qsl then turns that into a space.
        params[unquote(key)] = unquote(val)
    return params


def _parse_oauth_redirect(url):
    parts = urlsplit(url)
    params = _parse_oauth_query(parts.query)
    params.update(_parse_oauth_query(parts.fragment))
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
    return (
        body["access_token"],
        body.get("refresh_token") or "",
        user,
        id_token,
        _access_token_expires_at(body),
    )


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
    access_token, refresh_token, user, _id_token, expires_at = finish_authorization(
        started, result["url"]
    )
    _logger.info(user)
    return access_token, refresh_token, user, expires_at


def _mqtt_reason_text(reason_code, properties=None):
    """Human-readable MQTT 5 reason code plus optional Reason String."""
    if reason_code is None:
        return "unknown"
    name = None
    if hasattr(reason_code, "getName"):
        try:
            name = reason_code.getName()
        except Exception:
            name = None
    value = getattr(reason_code, "value", None)
    if value is None:
        try:
            value = int(reason_code)
        except (TypeError, ValueError):
            value = reason_code
    bits = []
    if name:
        bits.append(str(name))
    bits.append("code %s" % value)
    extra = None
    if properties is not None:
        try:
            extra = properties.json()
        except Exception:
            extra = None
    if extra:
        reason = extra.get("ReasonString") or extra.get("reasonString")
        if reason:
            bits.append(str(reason))
        elif extra:
            bits.append(str(extra))
    return "; ".join(bits)


def _mqtt_reason_failed(reason_code):
    if reason_code is None:
        return False
    if hasattr(reason_code, "is_failure"):
        try:
            return bool(reason_code.is_failure)
        except Exception:
            pass
    try:
        return int(reason_code) not in (0, int(MQTTErrorCode.MQTT_ERR_SUCCESS))
    except (TypeError, ValueError):
        return True


def _on_mqtt_connect(client, userdata, flags, reason_code, properties):
    userdata["renewing_session"] = False
    text = _mqtt_reason_text(reason_code, properties)
    if _mqtt_reason_failed(reason_code):
        _logger.error("MQTT connect failed: %s", text)
        return
    _logger.info("MQTT connected: %s", text)


def _on_mqtt_disconnect(client, userdata, flags, reason_code, properties):
    text = _mqtt_reason_text(reason_code, properties)
    if userdata.get("shutting_down"):
        _logger.info("MQTT disconnected (shutdown): %s", text)
        return
    if userdata.get("renewing_session"):
        _logger.info("MQTT disconnected for token refresh: %s", text)
        return
    if _mqtt_reason_failed(reason_code):
        _logger.error("MQTT disconnected: %s", text)
    else:
        _logger.warning("MQTT disconnected: %s", text)
    try:
        refresh_mqtt_auth(client)
    except Exception as err:
        _logger.error("Failed to refresh MQTT token before reconnect: %s", err)


def _on_mqtt_publish(client, userdata, mid, reason_code, properties):
    text = _mqtt_reason_text(reason_code, properties)
    failed = _mqtt_reason_failed(reason_code)
    userdata["last_puback"] = {"mid": mid, "reason": text, "failed": failed}
    if failed:
        _logger.error("MQTT PUBACK failed mid=%s %s", mid, text)
    else:
        _logger.debug("MQTT PUBACK mid=%s %s", mid, text)


def _mqtt_publish_failed(rc):
    return rc not in (
        MQTTErrorCode.MQTT_ERR_SUCCESS,
        MQTTErrorCode.MQTT_ERR_AGAIN,
        0,
    )


def _await_mqtt_publish(client, msg_info, qos=MQTT_PUBLISH_QOS):
    """Wait until the message has left the client; raise on local MQTT errors.

    The STAplus broker does not send PUBACK for ObservationGroups, so QoS 0
    (socket write) is the delivery signal. Broker auth failures show up as
    connect/disconnect reason codes or a non-zero publish rc.
    """
    if _mqtt_publish_failed(msg_info.rc):
        detail = error_string(msg_info.rc)
        _logger.error(
            "MQTT publish failed mid=%s rc=%s (%s) connected=%s",
            msg_info.mid,
            msg_info.rc,
            detail,
            client.is_connected(),
        )
        raise RuntimeError("MQTT publish failed: %s" % detail)

    try:
        msg_info.wait_for_publish(timeout=MQTT_PUBLISH_TIMEOUT)
    except ValueError as err:
        _logger.error(
            "MQTT publish not queued mid=%s rc=%s (%s): %s",
            msg_info.mid,
            msg_info.rc,
            error_string(msg_info.rc),
            err,
        )
        raise RuntimeError("MQTT publish not queued: %s" % err) from err
    except RuntimeError as err:
        _logger.error(
            "MQTT publish failed mid=%s rc=%s (%s): %s",
            msg_info.mid,
            msg_info.rc,
            error_string(msg_info.rc),
            err,
        )
        raise

    delivered = False
    try:
        delivered = msg_info.is_published()
    except RuntimeError as err:
        _logger.error(
            "MQTT publish status error mid=%s rc=%s (%s): %s",
            msg_info.mid,
            msg_info.rc,
            error_string(msg_info.rc),
            err,
        )
        raise

    userdata = client.user_data_get() or {}
    puback = userdata.get("last_puback") or {}
    if qos >= 1 and puback.get("mid") == msg_info.mid and puback.get("failed"):
        _logger.error("MQTT broker rejected publish mid=%s %s", msg_info.mid, puback.get("reason"))
        raise RuntimeError("MQTT PUBACK failed: %s" % puback.get("reason"))

    if delivered and not _mqtt_publish_failed(msg_info.rc):
        _logger.debug(
            "MQTT published mid=%s rc=%s (%s) qos=%s",
            msg_info.mid,
            msg_info.rc,
            error_string(msg_info.rc),
            qos,
        )
        return msg_info

    detail = error_string(msg_info.rc) if msg_info.rc else "timed out waiting to send"
    _logger.error(
        "MQTT publish not sent mid=%s rc=%s (%s) qos=%s delivered=%s connected=%s",
        msg_info.mid,
        msg_info.rc,
        detail,
        qos,
        delivered,
        client.is_connected(),
    )
    raise RuntimeError("MQTT publish not sent: %s" % detail)

def renew_mqtt_session(client, wait=5.0):
    """CONNECT again so the broker session uses the current Bearer token.

    username_pw_set only affects the next CONNECT; a live connection keeps the
    old access token until this runs. Must not be called from MQTT callbacks.
    """
    userdata = client.user_data_get()
    if userdata.get('shutting_down'):
        return False
    userdata['renewing_session'] = True
    try:
        client.loop_stop()
        rc = client.reconnect()
        client.loop_start()
    except Exception:
        userdata['renewing_session'] = False
        try:
            client.loop_start()
        except Exception:
            pass
        raise
    if rc not in (MQTTErrorCode.MQTT_ERR_SUCCESS, 0):
        userdata['renewing_session'] = False
        _logger.warning("MQTT reconnect after token refresh failed: %s", rc)
        return False
    if wait:
        deadline = time.time() + wait
        while not client.is_connected() and time.time() < deadline:
            time.sleep(0.05)
    if client.is_connected():
        _logger.info("MQTT reconnected with refreshed access token")
        return True
    userdata['renewing_session'] = False
    _logger.warning("MQTT did not come back after token refresh")
    return False


def refresh_mqtt_auth(client, reconnect=False):
    """Refresh OAuth tokens and MQTT credentials. Reconnect if reconnect=True."""
    userdata = client.user_data_get()
    access_token, refresh_token, expires_at = updateTokens(userdata['refresh_token'])
    userdata['access_token'] = access_token
    userdata['refresh_token'] = refresh_token
    userdata['expires_at'] = expires_at
    userdata['last_refresh'] = time.time()
    client.username_pw_set('Bearer', access_token)
    _logger.debug('MQTT credentials refreshed')
    if reconnect:
        renew_mqtt_session(client)
    return access_token, refresh_token

def connect_mqtt(token, refresh_token, expires_at=None):
    userdata = {
        'access_token': token,
        'refresh_token': refresh_token,
        'expires_at': expires_at,
        'last_refresh': time.time(),
        'shutting_down': False,
        'renewing_session': False,
        'last_puback': None,
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
    mqtt_log = logging.getLogger("paho.mqtt.client")
    mqtt_log.setLevel(logging.INFO)
    client.enable_logger(mqtt_log)
    client.on_connect = _on_mqtt_connect
    client.on_disconnect = _on_mqtt_disconnect
    client.on_publish = _on_mqtt_publish
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


def prepare_publish(service, config, foi_spec=None):
    """Resolve FoI, Observation templates and license used for each MQTT publish."""
    foi = None
    if foi_spec is not None:
        foi = _place_feature_of_interest(service, foi_spec)
    if foi is None:
        foi = _world_feature_of_interest(service)

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
    if not client.is_connected():
        _logger.error("MQTT publish skipped: client is not connected")
        raise RuntimeError("MQTT publish skipped: not connected")
    msg_info = client.publish(MQTT_PUBLISH_TOPIC, payload, qos=MQTT_PUBLISH_QOS)
    return _await_mqtt_publish(client, msg_info, qos=MQTT_PUBLISH_QOS)


def publish(service, client, config, party, sck, loc=None):
    loc = loc if loc is not None else location
    thing = service.things().query().filter("id eq '" + config.get('thing_id') + "'") #.expand("Locations").list().get(0)
    thing.locations = [loc]

    ctx = prepare_publish(service, config)
    start_sck_monitor(sck)
    while True:
        userdata = client.user_data_get()
        token_stale = not access_token_usable(
            userdata.get('access_token'),
            expires_at=userdata.get('expires_at'),
        )
        interval_due = time.time() - userdata.get('last_refresh', 0) >= TOKEN_REFRESH_INTERVAL
        if token_stale or interval_due:
            try:
                refresh_mqtt_auth(client, reconnect=True)
            except Exception as err:
                _logger.error("Proactive MQTT token refresh failed: %s", err)

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


def _normalize_bearer_token(token):
    text = str(token or "")
    if text.startswith("\ufeff"):
        text = text[1:]
    # JWTs cannot contain whitespace; Windows proxies and QString can inject CR/LF.
    text = "".join(text.split())
    if text.lower().startswith("bearer"):
        text = text[6:].lstrip(":")
    try:
        return text.encode("ascii").decode("ascii")
    except UnicodeEncodeError:
        return text.encode("ascii", "ignore").decode("ascii")


def _authorization_header(token):
    return "Bearer " + _normalize_bearer_token(token)


def _authorization_wire_debug(token):
    raw = _authorization_header(token).encode("ascii", "replace")
    return "Authorization %d bytes head=%s tail=%s" % (
        len(raw),
        raw[:16].hex(),
        raw[-8:].hex(),
    )


def _windows_proxy_debug():
    if sys.platform != "win32":
        return ""
    try:
        from urllib.request import getproxies
        proxies = {key: value for key, value in getproxies().items() if value}
    except Exception:
        return ""
    if not proxies:
        return ""
    return "Windows system proxy %s is ignored for STAplus/AUTHENIX." % proxies


def _introspect_access_token(token, scope=None):
    text = _normalize_bearer_token(token)
    if not text:
        return {}
    meta, _loaded_from = _load_sensor_app_json()
    data = {"token": text, "token_type_hint": "access_token"}
    if scope:
        data["scope"] = scope
    kwargs = {
        "data": data,
        "headers": {"Accept": "application/json"},
        "timeout": 15,
        "proxies": {},
    }
    if meta.get("client_id") and meta.get("client_secret"):
        kwargs["auth"] = HTTPBasicAuth(meta["client_id"], meta["client_secret"])
    try:
        response = _http_session().post(AUTHENIX_TOKENINFO, **kwargs)
        body = response.json()
        return body if isinstance(body, dict) else {"raw": response.text[:300]}
    except Exception as err:
        return {"error": str(err)}


def access_token_usable(token, skew=30, expires_at=None):
    """True if the access token is still within its lifetime.

    AUTHENIX issues opaque tokens with no JWT exp, so callers should pass
    expires_at from the token response's expires_in. Without that, opaque
    tokens are treated as unusable so the refresh_token path can run.
    """
    text = _normalize_bearer_token(token)
    if not text:
        return False
    if expires_at is not None:
        try:
            return float(expires_at) > time.time() + int(skew)
        except (TypeError, ValueError):
            pass
    claims = _access_token_claims(text)
    exp = claims.get("exp")
    if exp is None:
        return False
    try:
        return int(exp) > int(time.time()) + int(skew)
    except (TypeError, ValueError):
        return False


def _access_token_claims(token):
    text = _normalize_bearer_token(token)
    if not text:
        return {}
    try:
        return jwt.decode(
            text,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_aud": False,
            },
            algorithms=["RS256", "HS256"],
        )
    except Exception:
        return {}


def _format_access_token_debug(token):
    text = _normalize_bearer_token(token)
    if not text:
        return "no access token"
    bits = ["Bearer token %s chars" % len(text), "prefix=%s" % text[:12]]
    claims = _access_token_claims(text)
    if claims:
        aud = claims.get("aud")
        azp = claims.get("azp") or claims.get("client_id")
        scope = claims.get("scope") or claims.get("scp")
        exp = claims.get("exp")
        bits.extend(["aud=%s" % aud, "azp=%s" % azp, "scope=%s" % scope])
        if exp:
            bits.append("exp in %ss" % (int(exp) - int(time.time())))
    return "; ".join(bits)


def _format_sta_http_error(exc, href="", token=""):
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    body = ""
    www = ""
    if response is not None:
        text = (response.text or "").strip()
        www = (response.headers.get("WWW-Authenticate") or "").strip()
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
    if www:
        msg += "\n\n" + www[:800]
    if status in (401, 403):
        debug = _format_access_token_debug(token)
        if debug:
            msg += "\n\n" + debug
        msg += "\n\n" + _authorization_wire_debug(token)
        proxy_note = _windows_proxy_debug()
        if proxy_note:
            msg += "\n" + proxy_note
        info = _introspect_access_token(token)
        info_scoped = _introspect_access_token(token, " ".join(OAUTH_SCOPES))
        if info:
            msg += "\n\nAUTHENIX tokeninfo active=%s scope=%s" % (
                info.get("active"),
                info.get("scope") or "",
            )
        if info_scoped and info_scoped.get("active") != info.get("active"):
            msg += "\nAUTHENIX tokeninfo with app scopes active=%s scope=%s error=%s" % (
                info_scoped.get("active"),
                info_scoped.get("scope") or "",
                info_scoped.get("error") or info_scoped.get("error_description") or "",
            )
        msg += "\n\nSign in again, then retry Start publishing."
    return msg


def format_setup_error(err):
    """User-facing text for setup failures; keep HTTP status when the client hid it."""
    if isinstance(err, RuntimeError):
        return str(err)
    http = err if isinstance(err, requests.exceptions.HTTPError) else getattr(err, "__context__", None)
    if isinstance(http, requests.exceptions.HTTPError):
        href = ""
        if http.response is not None:
            href = http.response.url or ""
        return _format_sta_http_error(http, href)
    return "".join(traceback.format_exception(type(err), err, err.__traceback__))


def attach_sta_http_errors(service):
    """Send a raw ASCII Bearer header and ignore Windows system proxies."""
    session = _http_session()

    def execute(method, url, **kwargs):
        href = url if isinstance(url, str) else str(url)
        kwargs.setdefault("timeout", 60)
        token = ""
        handler = getattr(service, "auth_handler", None)
        if handler is not None:
            token = _normalize_bearer_token(getattr(handler, "token", ""))
        headers = dict(kwargs.pop("headers", None) or {})
        if token:
            headers["Authorization"] = _authorization_header(token)
        headers.setdefault("Accept", "application/json")
        kwargs.pop("auth", None)
        try:
            response = session.request(
                method,
                href,
                headers=headers,
                proxies={},
                **kwargs,
            )
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as exc:
            raise RuntimeError(_format_sta_http_error(exc, href, token)) from exc

    service.execute = execute
    return service


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

if __name__ == "__main__":
    configure_ssl_certs()
    access_token, refresh_token, user, expires_at = authorize()
    access_token, refresh_token, expires_at = ensure_fresh_tokens(
        access_token, refresh_token, expires_at
    )
    service = sta_service(access_token)
    _logger.debug("processing with access token: " + access_token)
    config = setup(service, user, location)
    party = service.parties().find(user['sub'])
    client = connect_mqtt(access_token, refresh_token, expires_at)
    sck = Serial(DEFAULT_SCK_PORT, SCK_BAUD, timeout=10)
    try:
        publish(service, client, config, party, sck, location)
    finally:
        client.user_data_get()['shutting_down'] = True
        client.loop_stop()
        client.disconnect()
        sck.close()

