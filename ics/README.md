# ICS - Instrument Control Software

Flask-based instrument control software for fiber-fed spectrograph.

This software provides:

- Web UI for operators
- JSON API for device control
- Supervisor state machine
- Mock hardware backends for development
- PyIndi-backed INDI client adapters for the instrument-side spectrograph camera and lens focuser
- ACE Connector telescope adapter for status, J2000 pointing, and small offset hooks
- ACE Connector guide-camera adapter for preview/acquisition frames through the existing telescope guide camera
- ACE Connector guide-stage adapter for stage axes exposed through ACE focuser-style interfaces
- Observation sequence hooks
- FITS/data-product placeholders
- Basic tests

## Deployment architecture

The current deployment concept is:

```text
Instrument-side Raspberry Pi
  - Flask ICS web server on the LAN
  - INDI server on 127.0.0.1:7624
  - USB connection to FLI Kepler spectrograph camera
  - USB connection to Pinefeat Canon EF lens controller
  - ACE Connector client connection to the telescope-control system

ACE / telescope-control system
  - telescope pointing
  - existing guide camera used for acquisition/centering
  - existing guide-camera stage used for stage motion
  - facility/main CCD and guide camera control remain primarily under ACE
```

## Run locally (for development)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app src.web:create_app run --host 0.0.0.0 --port 5000
```

Open `http://<instrument-host>:5000` from the LAN.

## Run on the Pi with INDI + ACE

Example `.env` settings:

```bash
ICS_BACKEND_MODE=indi
ICS_INDI_HOST=127.0.0.1
ICS_INDI_PORT=7624
ICS_INDI_CCD_DEVICE=FLI Kepler
ICS_INDI_FOCUSER_DEVICE=Pinefeat Lens Controller
ICS_INDI_CCD_BLOB_PROPERTY=CCD1

ICS_TCS_BACKEND=ace
ICS_GUIDE_CAMERA_BACKEND=ace
ICS_STAGE_BACKEND=ace
ICS_ACE_HOST=192.168.1.20
ICS_ACE_PORT=9889
ICS_ACE_NODE=Telescope PC
ICS_ACE_TELESCOPE_NAME=Telescope
ICS_ACE_GUIDE_CAMERA_NODE=Telescope PC
ICS_ACE_GUIDE_CAMERA_NAME=Guide Camera
ICS_ACE_STAGE_NODE=Telescope PC
ICS_ACE_STAGE_X_NAME=Guide Stage X
ICS_ACE_STAGE_Y_NAME=Guide Stage Y
ICS_ACE_STAGE_FOCUS_NAME=
```

Start `indiserver` on the same Pi with the Kepler CCD and Pinefeat focuser drivers, then start the Flask app:

```bash
flask --app src.web:create_app run --host 0.0.0.0 --port 5000
```

## ACE Connector backends

The ACE telescope backend uses:

```python
ace.syscore.AceConnection(host, port=9889)
ace.telescope.Telescope(connection, node_name, instrument_name)
telescope.get_position()
telescope.get_target()
telescope.go_to_j2000(ra_deg, dec_deg)
```

The ACE guide camera backend uses:

```python
ace.camera.Camera(connection, node_name, instrument_name)
camera.state
camera.temperature
camera.setpoint
camera.readout_mode
camera.expose(exptime, type=ace.camera.exposure_type.LIGHT, bin_x=1, bin_y=1, save=True, block=True)
```

The ACE guide-stage backend maps each configured stage axis to an ACE `Focuser` instrument:

```python
ace.focuser.Focuser(connection, node_name, instrument_name)
focuser.position
focuser.target
focuser.minimum
focuser.maximum
focuser.go(position)
focuser.stop()
```

## Configuration

Copy `.env.example` to `.env` and adjust values.

By default, all devices use mock backends. Set `ICS_BACKEND_MODE=indi` to use the local INDI server for the spectrograph science camera and lens controller. Set `ICS_TCS_BACKEND=ace`, `ICS_GUIDE_CAMERA_BACKEND=ace`, and `ICS_STAGE_BACKEND=ace` to use ACE Connector for telescope pointing, acquisition/guide imaging, and guide-stage motion.

## Architecture

```text
Flask UI/API
    |
InstrumentSupervisor
    |
    +-- ScienceCameraBackend    mock or PyIndi CCD client
    +-- AcquisitionCameraBackend mock or ACE guide camera client
    +-- LensFocusBackend        mock or PyIndi focuser client
    +-- MotionController        mock or ACE guide-stage/focuser-axis client
    +-- TcsBackend              mock or ACE Connector telescope client
    +-- DataManager             FITS/logging placeholders
```

## Development notes

The UI intentionally talks only to the Flask API. It does not know device-specific protocols.
The supervisor exposes domain-level operations such as acquisition, centering, focusing, calibration, and science exposure.
