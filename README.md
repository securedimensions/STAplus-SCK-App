# Smart Citizen Kit publishes on STAplus
The application `SensorApp` publishes observations from the Smart Citizen Kit v2.1 to a SensorThings PLUS API endpoint.

## GDPR note
The STAplus data model allows to attach the acting user to the `Thing` and the `Datastream` for example. The `Thing` is associated with `Location` and `HistoricalLocation` 
entity types. The `Datastream` used by the implementation to record the observations is also associated to `Party` representing the acting user.

In case that the `Party/role` property has the value `individual`, the acting user is a human person. In that case, this implementation is recording personal data (spatio-temporal tuple) via the `Thing/Location` and `Thing/HistoricalLocation` and the `Datastream/Observation`. The `Thing/Location` provides the space and the `Observation/phenomenonTime` provides the temporal context. 

Therefore, the service endpoint used by this application to upload observations for human users (`Party/role == 'individual'`) must protect access to 
the the `Locations` and `HistoricalLocations` entity types to avoid leaking of personal information!

To avoid the creation of personal information via the `FeatureOfInterest`, it is suggested to not use a geometry unless the observed feature is a publically 
observable object like a lake, a public park, a public building etc. In these cases, the `FeatureOfInterest/Feature/geometry` may describe the spatial extend
of the feature. In case the feature is a private home, the garden of the acting user, etc. the geometry should be set to `null`.

The latest update of this application uploads the observations with a feature of interest that is "The World" and there is no geometry. It is up to the 
user to change that feature of interest accordingly before starting to upload observations.

The configured STAplus endpoint used by the latest update of this implementation is compliant with the STAplus 1.0.1 corrigendum which explicitly
introduces a GDPR compliance note. This means that access to `/Locations` and `HistoricalLocations` is only granted for the user that is linked to the `Thing/Party`.
In particular, the authentication access token's Bearer token must be equal to the `Thing/Party/authId`. For any anonymous or other user's access 
the service returns an empty JSON array for `/Locations` or `HistoricalLocations`.

**DISCLAIMER: This software is in development stage and therefore probably buggy. Please report issues to improve the code**
## Hardware
To run the application, a Raspberry PI or another computer running Linux or MAC OS is required.
In addition, the Smart Citizen Kit v2.1 as made available from Fablab Barcelona is required.

### Connect the Hardware
Connect the Smart Citizen Kit v2.1 with a decent USB cable to your computer.
Then find the `tty` (using `ls /dev/tty*`) that makes the serial communication to the Smart Citizen Kit available:

* Raspberry PI: The Smart Citizen Kit typically connects as `/dev/ttyACM0`
* MAC OS: The Smart Citizen Kit connects as `/dev/tty.usbmodem<number>` where the `number` is subject to change

## Installation
The following installation is tested on a Raspberry PI 4 with Python 3.9 installed.

### Clone this repository
First, `cd` into your favorite directory and then clone this repository with `git clone https://github.com/securedimensions/STAplus-SCK-App.git` and change into the directory with `cd STAplus-SCK-App`.

Before continuing, please setup a Python virtual environment using `python3 -m venv .` and activate the virtual environment with `source bin/activate`.

### Install Python dependencies
To install the dependencies, simply execute `pip install -r requirements.txt`

### Install Rust (optional)
After finishing the installation of all dependencies, please make sure that the Python `cryptography` module installed. 

If the `cryptography` module did not install in the previous step, it needs to be compiled from source. To allow `pip` to compile the module, it is important to install a Rust compiler >= v1.56.0 first. 

Please follow the howto from the [Rust homepage](https://rustup.rs) and then repeat the installation of dependencies using `pip install -r requirements.txt`.

### Configure the Application
The configuration must be done in the source code ;)

The file `SensorApp.py` contains the line 57 the number for your SCK kit that you received from the registration with `https://start.smartcitizen.me`. Please update the variable `kit_id` with your number if you are using a new SCK that has not been registered before!

The file `SensorApp.py` contains the line 58 the variable `location` that is used to set the location of the `Thing` and `FeatureOfInterest`. Please update as you see fit!

```python
location = staPlus.Location(name="Munich", description="A nice place on Earth", location=Point((11.509234,48.1107284)), encoding_type='application/geo+json')
```

The file `SensorApp.py` contains in `line 61` the variable representing the serial port. Please update as you see fit (considering what is explained in the "Connect the Hardware" of this README)!

```python
sck = Serial('/dev/tty.usbmodem14301', 115200, timeout=10) 
```

### Run the Application
The application can be started from the terminal window using:

```shell
python SensorApp.py
```

The required authentication with AUTHENIX is started via the default Web-Browser. In case the Web-Browser does not open automatically (e.g. over ssh -X connections), open the URL displayed in the terminal in the Web-Browser.

Once authenticated, the application will create a STAplus `Party` entity representing you. The `Party`'s property `displayName` will be set from the value of the OpenID claim `preferred_username` received from authentication. The value for this claim was displayed during approval for this application.

Please follow these steps to start the application after the Raspberry restarted:

```shell
cd STAplus-SCK-App
source bin/activate
nohup python SensorApp.py &
# In Web-Browser, sign-in via Authenix
# Close web page
ctrl+C
```

### Run the Application in the background
To continue the execution of the application, please use the following command from the terminal window:

```shell
nohup python SensorApp.py &
```

To verify that the application is running, you can use `ps -ef|grep python`.

You can now logout from the Raspberry...


## Application publishing data
Once the application is started it will publish the following observations every 10 seconds:

* Air Temperature
* Air Humidity
* Atmospheric Pressure
* Noise
* Light intensity
* PM 1
* PM 2.5
* PM 10

The [CitiObs STAplus demo endpoint](https://citiobs.demo.secure-dimensions.de/staplus/v1.1) is used to publish the observations. Please find **your** Datastreams to evaluate the published observations.

### Stopping the Application
If started in the foreground, the execution can be aborted using `CTRL-C` from the keyboard.

If started in the background, you need to obtain the `process_id` via `ps -ef|grep python` and use `kill <process_id>` to stop the application.

### Troubleshooting
Please to try resolve the issue reported in the terminal window and run the application again. If nothing helps, please create an issue.

### Appreciation
Work on this project has being funded by the European Union under Horizon Europe project [CitiObs](https://www.citiobs.eu).
