# ICS - Instrument Control Software

Flask-based instrument control software for fiber-fed spectrograph.

This software provides:

- Web UI for operators
- JSON API for device control
- Supervisor state machine
- Mock hardware backends for development
- PyIndi-backed INDI client adapters for the instrument-side CCD and focuser
- ACE Connector telescope adapter for status, J2000 pointing, and small offset hooks
- Adapter boundaries for stepper motion, acquisition camera, and future services
- Observation sequence hooks
- FITS/data-product placeholders
- Basic tests

## Deployment architecture

- Flask ICS web server
- INDI server on 127.0.0.1:7624
- USB connection to FLI Kepler science camera
- USB connection to Pinefeat Canon EF lens controller

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app src.web:create_app run --host 0.0.0.0 --port 5000
```

Open `http://<instrument-host>:5000` from the LAN.

## ACE Connector telescope backend

The ACE telescope backend uses the documented Python interface:

```python
ace.syscore.AceConnection(host, port=9889)
ace.telescope.Telescope(connection, node_name, instrument_name)
telescope.get_position()
telescope.get_target()
telescope.go_to_j2000(ra_deg, dec_deg)
```

Example `.env` settings:

```bash
ICS_TCS_BACKEND=ace
ICS_ACE_HOST=192.168.1.20
ICS_ACE_PORT=9889
ICS_ACE_NODE=Telescope PC
ICS_ACE_TELESCOPE_NAME=Telescope
ICS_ACE_USERNAME=observer
ICS_ACE_PASSWORD=password
```

## Configuration

Copy `.env.example` to `.env` and adjust values.

By default, all devices use mock backends. Set `ICS_BACKEND_MODE=indi` to use the local INDI server for the science camera and lens controller. Set `ICS_TCS_BACKEND=ace` to use ACE Connector for telescope status and pointing while keeping other selected backends unchanged.

## Architecture

```text
Flask UI/API
    |
InstrumentSupervisor
    |
    +-- ScienceCameraBackend    mock or PyIndi CCD client
    +-- AcquisitionCameraBackend mock for now
    +-- LensFocusBackend        mock or PyIndi focuser client
    +-- MotionController        mock for now
    +-- TcsBackend              mock or ACE Connector telescope client
    +-- DataManager             FITS/logging placeholders
```

## Development notes

The UI intentionally talks only to the Flask API. It does not know device-specific protocols.
The supervisor exposes domain-level operations such as acquisition, centering, focusing, calibration, and science exposure.
