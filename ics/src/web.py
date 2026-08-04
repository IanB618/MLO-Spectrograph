import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

from src.config import Config
from src.data import DataManager
from src.devices import build_device_bundle
from src.devices.base import ExposureAbortedError
from src.logging_config import configure_logging
from src.models import ExposureRequest, LensMoveRequest, MotionMoveRequest, TcsGotoRequest
from src.supervisor import InstrumentSupervisor


logger = logging.getLogger(__name__)


def _json_error(error, status_code, error_label, message=None, details=None, hint=None):
    payload = {
        "error": error_label,
        "message": message or str(error),
        "status": HTTPStatus(status_code).phrase,
        "status_code": status_code,
        "type": error.__class__.__name__,
    }
    if details:
        payload["details"] = details
    if hint:
        payload["hint"] = hint
    return jsonify(payload), status_code


def create_app():
    configure_logging()
    config = Config()
    app = Flask(__name__)
    app.config.update(config.flask_config())

    data_manager = DataManager(app.config["ICS_DATA_ROOT"])
    devices = build_device_bundle(config)
    supervisor = InstrumentSupervisor(devices, data_manager)
    app.extensions["ics_supervisor"] = supervisor
    app.extensions["ics_data_manager"] = data_manager

    @app.errorhandler(ValidationError)
    def handle_validation_error(error):
        return _json_error(
            error,
            400,
            "Invalid request",
            message="The request parameters were not valid.",
            details=error.errors(),
        )

    @app.errorhandler(ValueError)
    def handle_value_error(error):
        return _json_error(error, 400, "Invalid request")

    @app.errorhandler(KeyError)
    def handle_key_error(error):
        return _json_error(error, 400, "Missing request field", message=f"Missing required field: {error}")

    @app.errorhandler(ExposureAbortedError)
    def handle_exposure_aborted(error):
        return _json_error(error, 409, "Exposure aborted", message="The science-camera exposure was aborted.")

    @app.errorhandler(RuntimeError)
    def handle_runtime_error(error):
        return _json_error(error, 409, "Runtime error")

    @app.errorhandler(TimeoutError)
    def handle_timeout_error(error):
        return _json_error(
            error,
            504,
            "INDI device timeout",
            hint="Check that indiserver is running and that the configured INDI device names match the connected drivers.",
        )

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        return _json_error(error, error.code or 500, error.name, message=error.description)

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        logger.exception("Unhandled API error")
        return _json_error(
            error,
            500,
            "Internal server error",
            message="An unexpected ICS server error occurred. Check the server log for the traceback.",
        )

    @app.get("/")
    def index():
        return render_template("index.html",
                               site_name=app.config["ICS_SITE_NAME"],
                               js9_asset_base=app.config["ICS_JS9_ASSET_BASE"])

    @app.get("/api/status")
    def api_status():
        return jsonify(supervisor.snapshot().model_dump(mode="json"))

    @app.post("/api/connect")
    def api_connect():
        supervisor.connect_all()
        return jsonify(supervisor.snapshot().model_dump(mode="json"))

    @app.post("/api/disconnect")
    def api_disconnect():
        supervisor.disconnect_all()
        return jsonify(supervisor.snapshot().model_dump(mode="json"))

    @app.post("/api/science-camera/temperature")
    def api_science_temperature():
        payload = request.get_json()
        supervisor.set_science_temperature(float(payload["setpoint_c"]))
        return jsonify(supervisor.snapshot().model_dump(mode="json"))

    @app.post("/api/science-camera/expose")
    def api_science_expose():
        request_model = ExposureRequest(**request.get_json())
        result = supervisor.take_exposure(request_model)
        return jsonify(result.model_dump(mode="json"))

    @app.post("/api/science-camera/abort")
    def api_science_abort():
        supervisor.abort_exposure()
        return jsonify(supervisor.snapshot().model_dump(mode="json"))

    @app.get("/api/science-camera/latest.fits")
    def api_science_latest_fits():
        result = supervisor.latest_exposure()
        if result is None:
            abort(404, description="No science exposure is available for preview.")

        path = Path(result.path).resolve()
        data_root = Path(app.config["ICS_DATA_ROOT"]).resolve()
        try:
            path.relative_to(data_root)
        except ValueError:
            logger.error("Refusing to serve science preview outside data root: %s", path)
            abort(404, description="The latest science exposure is not available for preview.")

        if not path.is_file():
            abort(404, description="The latest science FITS file does not exist.")

        lower_name = path.name.lower()
        if not lower_name.endswith((".fits", ".fit", ".fts", ".fits.gz", ".fit.gz", ".fts.gz", ".fz")):
            abort(415, description="The latest science exposure is not a supported FITS file.")

        response = send_file(
            path,
            mimetype="application/fits",
            as_attachment=False,
            download_name=path.name,
            conditional=True,
            etag=True,
            last_modified=path.stat().st_mtime,
        )
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/api/acquisition/preview")
    def api_acquisition_preview():
        payload = request.get_json(silent=True) or {}
        result = supervisor.capture_acquisition_preview(float(payload.get("exposure_s", 0.2)))
        return jsonify(result)

    @app.post("/api/motion/home")
    def api_motion_home():
        payload = request.get_json()
        supervisor.home_axis(payload["axis"])
        return jsonify(supervisor.snapshot().model_dump(mode="json"))

    @app.post("/api/motion/move")
    def api_motion_move():
        request_model = MotionMoveRequest(**request.get_json())
        supervisor.move_axis(request_model)
        return jsonify(supervisor.snapshot().model_dump(mode="json"))

    @app.post("/api/lens/move")
    def api_lens_move():
        request_model = LensMoveRequest(**request.get_json())
        supervisor.move_lens(request_model)
        return jsonify(supervisor.snapshot().model_dump(mode="json"))

    @app.post("/api/lens/calibrate")
    def api_lens_calibrate():
        supervisor.calibrate_lens()
        return jsonify(supervisor.snapshot().model_dump(mode="json"))

    @app.post("/api/lens/aperture/absolute")
    def api_lens_aperture_absolute():
        payload = request.get_json()
        supervisor.set_lens_aperture_absolute(float(payload["f_stop"]))
        return jsonify(supervisor.snapshot().model_dump(mode="json"))

    @app.post("/api/lens/aperture/relative")
    def api_lens_aperture_relative():
        payload = request.get_json()
        supervisor.set_lens_aperture_relative(float(payload["delta"]))
        return jsonify(supervisor.snapshot().model_dump(mode="json"))

    @app.post("/api/tcs/goto-j2000")
    def api_tcs_goto_j2000():
        request_model = TcsGotoRequest(**request.get_json())
        result = supervisor.tcs_go_to_j2000(request_model)
        return jsonify(result)

    @app.post("/api/tcs/offset")
    def api_tcs_offset():
        payload = request.get_json()
        result = supervisor.tcs_offset(float(payload["east_arcsec"]), float(payload["north_arcsec"]))
        return jsonify(result)

    @app.post("/api/calibration/run")
    def api_calibration_run():
        return jsonify(supervisor.run_calibration_placeholder())

    @app.get("/api/log")
    def api_log():
        return jsonify(data_manager.recent_log_entries())

    return app
