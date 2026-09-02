# STAplus Smart Citizen Kit

Desktop app that publishes observations from a [Smart Citizen Kit](https://smartcitizen.me) v2.1 to a SensorThings PLUS (STAplus) API.

The usual way to run it is the PyQt6 application `SCK-App.py`. Sign-in uses AUTHENIX in the embedded browser. Location is set on the map. The kit is connected over USB serial. Publishing goes to the CitiObs STAplus demo:

https://citiobs.demo.secure-dimensions.de/stapluscelltest/v1.1

`SensorApp.py` still contains the STAplus/MQTT logic and a command-line entry point for headless use.

**This software is in development and probably buggy. Please report issues.**

## GDPR note

The STAplus data model allows attaching the acting user to the `Thing` and the `Datastream`. The `Thing` is associated with `Location` and `HistoricalLocation`. The `Datastream` used to record observations is also associated with a `Party` representing the acting user.

If `Party/role` is `individual`, the acting user is a person. This implementation then records personal data (a spatio-temporal tuple) via `Thing/Location`, `Thing/HistoricalLocation`, and `Datastream/Observation`. `Thing/Location` provides the space and `Observation/phenomenonTime` the time.

The service endpoint used to upload observations for human users (`Party/role == 'individual'`) must therefore protect access to `Locations` and `HistoricalLocations` so personal information is not leaked.

To avoid creating personal information via `FeatureOfInterest`, do not use a geometry unless the observed feature is a publicly observable object such as a lake, a public park, or a public building. In those cases, `FeatureOfInterest/Feature/geometry` may describe the spatial extent. For a private home, garden, and similar features, the geometry should be `null`.

This application uploads observations with a feature of interest that is "The World" and has no geometry. Change that feature of interest if needed before publishing.

The configured STAplus endpoint follows the STAplus 1.0.1 corrigendum GDPR note: access to `/Locations` and `HistoricalLocations` is granted only to the user linked to `Thing/Party`. The access token’s Bearer subject must equal `Thing/Party/authId`. Anonymous or other users receive an empty JSON array.

## Hardware

You need:

- A computer running **macOS**, **Windows**, or **Linux**
- A Smart Citizen Kit v2.1 (Fablab Barcelona) and a decent USB cable

Typical serial ports:

- Raspberry Pi / Linux: `/dev/ttyACM0`
- macOS: `/dev/tty.usbmodem<number>` (the number changes)
- Windows: `COMx`

The desktop app lists ports in **Smart Citizen Kit**; pick the kit and click **Connect kit**. You do not need to edit the port in source for normal use.

## Desktop app (`SCK-App.py`)

Left-hand cards (each can be collapsed from its title):

1. **Smart Citizen Kit** — choose the serial port and connect
2. **Location** — name, marker coordinates, **Use this marker**
3. **Account** — AUTHENIX **Sign in** / **Log out**
4. **STAplus** — **Start publishing** / **Stop**
5. **Live readings** — latest sample; after the kit is connected, click the map marker for charts

The map is on the right. Click or drag the marker, then confirm it before publishing. On macOS, **Use my location** uses the bundled `sck-locate` helper (Core Location). Enable Location Services for STAplus SCK if macOS asks.

**Start publishing** is enabled when you are signed in, the kit is connected, and the marker is confirmed.

### AUTHENIX sign-in and logout

Sign-in opens AUTHENIX in the map pane (not the system browser). Consent is stored in the persistent `ASCookieConsent` cookie so the cookie page should not appear on every login.

Cookie and profile data live under the application support directory:

- macOS: `~/Library/Application Support/STAplus-SCK/`
- Windows: `%APPDATA%\STAplus-SCK\`
- Linux: `~/.local/share/STAplus-SCK/`

WebEngine profile: `…/QtWebEngine/sck-authenix`  
OAuth client file used when frozen: `SensorApp.json` in that same support directory  
Last map position: `sck_location.json`

**Log out** calls AUTHENIX `https://authenix.eu/openid/logout` in the same embedded profile so the AUTHENIX session cookies are cleared. Consent (`ASCookieConsent`) is kept. After logout, **Sign in** can be used for a different account.

Do not delete the whole profile directory just to switch user; use **Log out**.

## Installation (from source)

Python 3.11 is recommended. Create a **project** venv (not `python3 -m venv .`, and not `--system-site-packages`: a PyPI `uuid` package on the system Python breaks freezing).

```shell
git clone https://github.com/securedimensions/STAplus-SCK-App.git
cd STAplus-SCK-App
python3 -m venv venv
```

macOS / Linux:

```shell
source venv/bin/activate
pip install -r requirements.txt
```

Windows:

```bat
venv\Scripts\activate
pip install -r requirements.txt
```

`staplus-client` and `sta-dggs-client` must resolve (PyPI and/or your local editable installs). If `cryptography` fails to install, install a Rust compiler from https://rustup.rs and run `pip install -r requirements.txt` again.

On macOS, build the location helper once:

```shell
./vendor/sck-locate/build.sh
```

### Run

```shell
python SCK-App.py
```

If AUTHENIX has not seen this app before, `SensorApp.py` registers a web client and writes `SensorApp.json` in the working directory.

### Optional CLI

Headless publish (system browser for AUTHENIX, hardcoded serial port `DEFAULT_SCK_PORT` in `SensorApp.py`):

```shell
python SensorApp.py
```

## What is published

About every 10 seconds, while publishing:

- Air temperature
- Air humidity
- Atmospheric pressure
- Noise
- Light intensity
- PM 1, PM 2.5, PM 10

MQTT uses the same AUTHENIX access token (refreshed before the typical 30-minute expiry). Find **your** Datastreams on the STAplus endpoint after the first successful publish.

The STAplus URL and MQTT broker are set near the top of `SensorApp.py` (`url`, `broker`). The Smart Citizen kit id used on the `Thing` is `kit_id` in the same file.

## Packaging

Keep `STAplus SCK.spec` next to the build scripts. `.gitignore` includes `*.spec`, so that file is easy to lose when cloning; copy it with the project if you build on another machine.

Create the venv and install requirements first. QGIS (and similar tools) often set `PYTHONPATH`; the build scripts clear it because it confuses PyInstaller.

macOS (produces `dist/STAplus SCK.app`, including Leaflet map files and `sck-locate.app` under `Contents/Resources`):

```shell
./build-macos-app.sh
```

Windows (produces `dist\STAplus SCK\STAplus SCK.exe`):

```bat
build-windows-app.bat
```

The frozen app stores `SensorApp.json` and location cache under the application support directory above, not inside the `.app` / `_internal` tree.

Launch the newly built `dist/STAplus SCK.app` (macOS) or `STAplus SCK.exe` (Windows). Do not keep using an older copy after a rebuild.

## Stopping

- Desktop: close the window, or **Stop** to end MQTT publish while leaving the kit connected.
- CLI foreground: `Ctrl+C`
- CLI background: `kill` the Python process (`ps` / Task Manager)

## Appreciation

Work on this project has been funded by the European Union under Horizon Europe project [CitiObs](https://www.citiobs.eu).
