import logging
from threading import Lock

from src.data import DataManager
from src.models import ExposureRequest, ExposureResult, LensMoveRequest, MotionMoveRequest, SystemSnapshot, SystemState, TcsGotoRequest

logger = logging.getLogger(__name__)


class InstrumentSupervisor:
    def __init__(self, devices, data_manager: DataManager):
        self.devices = devices
        self.data_manager = data_manager
        self.state = SystemState.OFFLINE
        self.message = "Not connected"
        self.last_exposure: ExposureResult | None = None
        self._lock = Lock()

    def connect_all(self):
        with self._lock:
            self.devices.science_camera.connect()
            self.devices.acquisition_camera.connect()
            self.devices.lens.connect()
            self.devices.motion.connect()
            self.devices.tcs.connect()
            self.state = SystemState.IDLE
            self.message = "All devices connected"

    def disconnect_all(self):
        with self._lock:
            self.devices.science_camera.disconnect()
            self.devices.acquisition_camera.disconnect()
            self.devices.lens.disconnect()
            self.devices.motion.disconnect()
            self.devices.tcs.disconnect()
            self.state = SystemState.OFFLINE
            self.message = "Disconnected"

    def snapshot(self) -> SystemSnapshot:
        return SystemSnapshot(
            state=self.state,
            message=self.message,
            science_camera=self.devices.science_camera.status(),
            acquisition_camera=self.devices.acquisition_camera.status(),
            lens=self.devices.lens.status(),
            tcs=self.devices.tcs.status(),
            axes=self.devices.motion.axes(),
            last_exposure=self.last_exposure,
        )

    def set_safe(self, message: str = "Manual safe mode"):
        with self._lock:
            self.devices.science_camera.abort()
            self.devices.motion.stop()
            self.devices.lens.stop()
            self.state = SystemState.SAFE
            self.message = message

    def clear_safe(self):
        with self._lock:
            self.state = SystemState.IDLE
            self.message = "Safe mode cleared"

    def set_science_temperature(self, setpoint_c: float):
        self.devices.science_camera.set_temperature(setpoint_c)
        self.message = f"Science camera setpoint set to {setpoint_c:.1f} C"

    def capture_acquisition_preview(self, exposure_s: float = 0.2):
        with self._lock:
            self.state = SystemState.ACQUIRING
            self.message = "Capturing guide camera preview"
            path = self.devices.acquisition_camera.capture_preview(exposure_s)
            self.state = SystemState.IDLE
            self.message = "Guide camera preview complete"
            return {"path": path}

    def move_axis(self, request: MotionMoveRequest):
        with self._lock:
            if request.position is not None:
                self.devices.motion.move_absolute(request.axis, request.position)
            elif request.delta is not None:
                self.devices.motion.move_relative(request.axis, request.delta)
            else:
                raise ValueError("Motion request requires position or delta")
            self.message = f"Moved guide stage axis {request.axis}"

    def home_axis(self, axis: str):
        with self._lock:
            self.devices.motion.home(axis)
            self.message = f"Homed guide stage axis {axis}"

    def move_lens(self, request: LensMoveRequest):
        with self._lock:
            self.state = SystemState.FOCUSING
            if request.position is not None:
                self.devices.lens.move_absolute(request.position)
            elif request.delta is not None:
                self.devices.lens.move_relative(request.delta)
            else:
                raise ValueError("Lens request requires position or delta")
            self.state = SystemState.IDLE
            self.message = "Lens focus moved"

    def tcs_go_to_j2000(self, request: TcsGotoRequest):
        result = self.devices.tcs.go_to_j2000(request.ra_deg, request.dec_deg)
        self.message = "TCS J2000 slew requested"
        return result

    def tcs_offset(self, east_arcsec: float, north_arcsec: float):
        result = self.devices.tcs.offset(east_arcsec, north_arcsec)
        self.message = "TCS offset requested"
        return result

    def take_exposure(self, request: ExposureRequest) -> ExposureResult:
        with self._lock:
            if self.state in [SystemState.SAFE, SystemState.ERROR]:
                raise RuntimeError(f"Cannot expose while state is {self.state}")
            self.state = SystemState.EXPOSING
            self.message = f"Taking {request.image_type} exposure"
            try:
                result = self.devices.science_camera.expose(request)
                self.last_exposure = result
                self.state = SystemState.IDLE
                self.message = result.message
                self.data_manager.record_exposure(request, result, self.snapshot())
                return result
            except Exception:
                logger.exception("Exposure failed")
                self.state = SystemState.ERROR
                self.message = "Exposure failed"
                raise

    def abort_exposure(self):
        with self._lock:
            self.devices.science_camera.abort()
            self.state = SystemState.IDLE
            self.message = "Exposure aborted"

    def run_focus_sweep_placeholder(self):
        with self._lock:
            self.state = SystemState.FOCUSING
            self.message = "Focus sweep placeholder complete"
            self.state = SystemState.IDLE
            return {"best_position": self.devices.lens.status().position}

    def center_target_placeholder(self):
        with self._lock:
            self.state = SystemState.ACQUIRING
            self.message = "Guide camera target centering placeholder complete"
            self.state = SystemState.IDLE
            return {"dx_arcsec": 0.0, "dy_arcsec": 0.0}

    def run_calibration_placeholder(self):
        with self._lock:
            self.state = SystemState.CALIBRATING
            self.message = "Calibration placeholder complete"
            self.state = SystemState.IDLE
            return {"frames": []}
