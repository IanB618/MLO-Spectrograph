import logging
from threading import Lock

from src.data import DataManager
from src.devices.base import ExposureAbortedError
from src.models import ExposureRequest, ExposureResult, LensMoveRequest, MotionMoveRequest, SystemSnapshot, SystemState, TcsGotoRequest

logger = logging.getLogger(__name__)


class InstrumentSupervisor:
    def __init__(self, devices, data_manager: DataManager):
        self.devices = devices
        self.data_manager = data_manager
        self.state = SystemState.OFFLINE
        self.message = "Not connected"
        self.last_exposure: ExposureResult | None = None
        self._operation_lock = Lock()
        self._state_lock = Lock()

    def _set_status(self, state: SystemState | None = None, message: str | None = None):
        with self._state_lock:
            if state is not None:
                self.state = state
            if message is not None:
                self.message = message

    def connect_all(self):
        with self._operation_lock:
            self.devices.science_camera.connect()
            self.devices.acquisition_camera.connect()
            self.devices.lens.connect()
            self.devices.motion.connect()
            self.devices.tcs.connect()
            self._set_status(SystemState.IDLE, "All devices connected")

    def disconnect_all(self):
        with self._operation_lock:
            self.devices.science_camera.disconnect()
            self.devices.acquisition_camera.disconnect()
            self.devices.lens.disconnect()
            self.devices.motion.disconnect()
            self.devices.tcs.disconnect()
            self._set_status(SystemState.OFFLINE, "Disconnected")

    def snapshot(self) -> SystemSnapshot:
        with self._state_lock:
            state = self.state
            message = self.message
            last_exposure = self.last_exposure

        return SystemSnapshot(
            state=state,
            message=message,
            science_camera=self.devices.science_camera.status(),
            acquisition_camera=self.devices.acquisition_camera.status(),
            lens=self.devices.lens.status(),
            tcs=self.devices.tcs.status(),
            axes=self.devices.motion.axes(),
            last_exposure=last_exposure,
        )

    def set_science_temperature(self, setpoint_c: float):
        self.devices.science_camera.set_temperature(setpoint_c)
        self._set_status(message=f"Science camera setpoint set to {setpoint_c:.1f} C")

    def capture_acquisition_preview(self, exposure_s: float = 0.2):
        with self._operation_lock:
            self._set_status(SystemState.ACQUIRING, "Capturing guide camera preview")
            path = self.devices.acquisition_camera.capture_preview(exposure_s)
            self._set_status(SystemState.IDLE, "Guide camera preview complete")
            return {"path": path}

    def move_axis(self, request: MotionMoveRequest):
        with self._operation_lock:
            if request.position is not None:
                self.devices.motion.move_absolute(request.axis, request.position)
            elif request.delta is not None:
                self.devices.motion.move_relative(request.axis, request.delta)
            else:
                raise ValueError("Motion request requires position or delta")
            self._set_status(message=f"Moved guide stage axis {request.axis}")

    def home_axis(self, axis: str):
        with self._operation_lock:
            self.devices.motion.home(axis)
            self._set_status(message=f"Homed guide stage axis {axis}")

    def move_lens(self, request: LensMoveRequest):
        with self._operation_lock:
            self._set_status(SystemState.FOCUSING)
            if request.position is not None:
                self.devices.lens.move_absolute(request.position)
            elif request.delta is not None:
                self.devices.lens.move_relative(request.delta)
            else:
                raise ValueError("Lens request requires position or delta")
            self._set_status(SystemState.IDLE, "Lens focus moved")

    def tcs_go_to_j2000(self, request: TcsGotoRequest):
        result = self.devices.tcs.go_to_j2000(request.ra_deg, request.dec_deg)
        self._set_status(message="TCS J2000 slew requested")
        return result

    def tcs_offset(self, east_arcsec: float, north_arcsec: float):
        result = self.devices.tcs.offset(east_arcsec, north_arcsec)
        self._set_status(message="TCS offset requested")
        return result

    def take_exposure(self, request: ExposureRequest) -> ExposureResult:
        with self._operation_lock:
            with self._state_lock:
                if self.state == SystemState.ERROR:
                    raise RuntimeError(f"Cannot expose while state is {self.state}")

            self._set_status(SystemState.EXPOSING, f"Taking {request.image_type} exposure")
            try:
                result = self.devices.science_camera.expose(request)
                with self._state_lock:
                    self.last_exposure = result
                self._set_status(SystemState.IDLE, result.message)
                self.data_manager.process_exposure(request, result, self.snapshot())
                return result
            except ExposureAbortedError:
                logger.info("Exposure aborted")
                self._set_status(SystemState.IDLE, "Exposure aborted")
                raise
            except Exception:
                logger.exception("Exposure failed")
                self._set_status(SystemState.ERROR, "Exposure failed")
                raise

    def abort_exposure(self):
        with self._state_lock:
            exposure_active = self.state == SystemState.EXPOSING

        if not exposure_active:
            self._set_status(message="No exposure is currently in progress")
            return

        self.devices.science_camera.abort() # deliberately bypass _operation_lock since take_exposure holds it
        self._set_status(message="Exposure abort requested")

    def run_focus_sweep_placeholder(self):
        with self._operation_lock:
            self._set_status(SystemState.FOCUSING, "Focus sweep placeholder complete")
            self._set_status(SystemState.IDLE)
            return {"best_position": self.devices.lens.status().position}

    def center_target_placeholder(self):
        with self._operation_lock:
            self._set_status(SystemState.ACQUIRING, "Guide camera target centering placeholder complete")
            self._set_status(SystemState.IDLE)
            return {"dx_arcsec": 0.0, "dy_arcsec": 0.0}

    def run_calibration_placeholder(self):
        with self._operation_lock:
            self._set_status(SystemState.CALIBRATING, "Calibration placeholder complete")
            self._set_status(SystemState.IDLE)
            return {"frames": []}
