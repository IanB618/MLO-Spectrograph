# ICS - Instrument Control Software

Flask-based instrument control software for fiber-fed spectrograph.

This software provides:

- Web UI for operators
- JSON API for device control
- Supervisor state machine
- Mock hardware backends for development
- Adapter boundaries for INDI, ACE TCS, stepper motion, FLI Kepler, acquisition camera, and Pinefeat EF lens focus
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

By default, all devices use mock backends.

## Architecture

```text
Flask UI/API
    |
InstrumentSupervisor
    |
    +-- ScienceCameraBackend   mock, INDI, libflipro later
    +-- AcquisitionCameraBackend mock, INDI later
    +-- LensFocusBackend       mock, INDI/Pinefeat later
    +-- MotionController       mock, serial/ethernet later
    +-- TcsBackend             mock, ACE adapter later
    +-- DataManager            FITS/logging placeholders
```

## Development notes

The UI intentionally talks only to the Flask API. It does not know device-specific protocols.
The supervisor exposes domain-level operations such as acquisition, centering, focusing, calibration, and science exposure.
