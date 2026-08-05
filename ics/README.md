# Instrument Control Software (ICS)

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
- FITS/data product generation and processing
- Basic tests

## Deployment architecture

The current deployment concept is:

```text
Instrument-side Raspberry Pi
  - Flask ICS web server on the LAN
  - INDI server on localhost:7624
  - USB connection to FLI Kepler spectrograph camera
  - USB connection to Pinefeat Canon EF lens controller
  - ACE Connector client connection to the telescope control system

ACE telescope control system (TCS)
  - telescope pointing
  - main CCD and guide camera control/image retrieval
  - existing guide camera used for target acquisition
  - existing guide camera stage used for X/Y/Z motion
```

## Run locally (for development)

```bash
flask --app src.web:create_app run --host 0.0.0.0 --port 5000
```

Open `http://localhost:5000` in a browser.

## Run on the Pi with INDI + ACE

Start `indiserver` on the same Pi with the Kepler CCD and Pinefeat focuser drivers, then start the Flask app:

```bash
flask --app src.web:create_app run --host 0.0.0.0 --port 5000
```

Open `http://<Raspberry Pi's IP address>:5000` in a browser.

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

The web UI intentionally talks only to the Flask API; it does not know anything about device-specific protocols. The supervisor exposes domain-level operations such as acquisition, focusing, calibration, and science exposure.
