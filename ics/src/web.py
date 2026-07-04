from flask import Flask, jsonify, render_template, request

from src.config import Config
from src.data import DataManager
from src.devices import build_device_bundle
from src.logging_config import configure_logging
from src.models import ExposureRequest, LensMoveRequest, MotionMoveRequest
from src.supervisor import InstrumentSupervisor


def create_app():
    configure_logging()
    config = Config()
    app = Flask(__name__)
    app.config.update(config.flask_config())

    data_manager = DataManager(app.config["ICS_DATA_ROOT"])
    devices = build_device_bundle(app.config["ICS_BACKEND_MODE"], app.config["ICS_DATA_ROOT"])
    supervisor = InstrumentSupervisor(devices, data_manager)
    app.extensions["ics_supervisor"] = supervisor
    app.extensions["ics_data_manager"] = data_manager

    @app.get("/")
    def index():
        return render_template("index.html", site_name=app.config["ICS_SITE_NAME"])

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

    @app.post("/api/safe")
    def api_safe():
        payload = request.get_json(silent=True) or {}
        supervisor.set_safe(payload.get("message", "Manual safe mode"))
        return jsonify(supervisor.snapshot().model_dump(mode="json"))

    @app.post("/api/safe/clear")
    def api_clear_safe():
        supervisor.clear_safe()
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

    @app.post("/api/acquisition/preview")
    def api_acquisition_preview():
        payload = request.get_json(silent=True) or {}
        result = supervisor.capture_acquisition_preview(float(payload.get("exposure_s", 0.2)))
        return jsonify(result)

    @app.post("/api/acquisition/center")
    def api_acquisition_center():
        return jsonify(supervisor.center_target_placeholder())

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

    @app.post("/api/lens/focus-sweep")
    def api_lens_focus_sweep():
        return jsonify(supervisor.run_focus_sweep_placeholder())

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
