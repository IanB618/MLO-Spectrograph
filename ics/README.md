# ICS - Instrument Control Software

Flask-based instrument control software for fiber-fed spectrograph.

This software provides:

- Web UI for operators
- JSON API for device control
- Supervisor state machine
- Mock hardware backends for development
- PyIndi-backed INDI client adapters for the instrument-side CCD and focuser
- Adapter boundaries for ACE TCS, stepper motion, acquisition camera, and future services
- Observation sequence hooks
- FITS/data-product placeholders
- Basic tests

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app src.web:create_app run --host 0.0.0.0 --port 5000
```

Open `http://<instrument-host>:5000` from the LAN.

## Configuration

Copy `.env.example` to `.env` and adjust values.

By default, all devices use mock backends. Set `ICS_BACKEND_MODE=indi` to use an INDI server for the science camera and lens controller.

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
    +-- TcsBackend              mock / ACE adapter later
    +-- DataManager             FITS/logging placeholders
```

## Development notes

The UI intentionally talks only to the Flask API. It does not know device-specific protocols.
The supervisor exposes domain-level operations such as acquisition, centering, focusing, calibration, and science exposure.
