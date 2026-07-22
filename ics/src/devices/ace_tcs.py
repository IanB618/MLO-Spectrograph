import importlib
import logging
import math
from dataclasses import dataclass

from src.models import AxisStatus, CameraStatus, TcsStatus

logger = logging.getLogger(__name__)


class AceUnavailableError(RuntimeError):
    pass


@dataclass
class AceConnectionConfig:
    host: str
    port: int
    username: str | None = None
    password: str | None = None


@dataclass
class AceTelescopeConfig(AceConnectionConfig):
    node: str = "Telescope PC"
    instrument: str = "Telescope"


@dataclass
class AceCameraConfig(AceConnectionConfig):
    node: str = "Telescope PC"
    instrument: str = "Guide Camera"


@dataclass
class AceStageAxisConfig:
    axis: str
    node: str
    instrument: str
    units: str = "steps"


@dataclass
class AceStageConfig(AceConnectionConfig):
    axes: list[AceStageAxisConfig] | None = None


def _load_ace_module(name: str):
    try:
        return importlib.import_module(name)
    except ImportError as error:
        raise AceUnavailableError(
            "ACE Python modules are not installed or are not on PYTHONPATH. "
            "Install ACE Connector's Python interface on this host."
        ) from error


def _open_connection(config: AceConnectionConfig):
    ace_syscore = _load_ace_module("ace.syscore")
    connection = ace_syscore.AceConnection(config.host, config.port)
    if config.username and config.password:
        connection.authenticate(config.username, config.password)
    return connection


def _constant_name(container, value) -> str:
    if container is None:
        return str(value)
    for name in dir(container):
        if name.startswith("_"):
            continue
        try:
            if getattr(container, name) == value:
                return name.lower()
        except Exception:
            continue
    return str(value)


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class AceTcs:
    """ACE Connector telescope adapter.

    ACE Connector provides absolute telescope pointing through
    ace.telescope.Telescope.go_to_j2000(). The supplied Python interface does
    not document a native offset/nudge call, so offset() performs a small-angle
    conversion around the current reported position and sends a new J2000 target.
    """

    def __init__(self, config: AceTelescopeConfig):
        self.config = config
        self.connection = None
        self.telescope = None
        self.connected = False
        self.last_message = "offline"

    def connect(self):
        ace_telescope = _load_ace_module("ace.telescope")
        self.connection = _open_connection(self.config)
        self.telescope = ace_telescope.Telescope(self.connection, self.config.node, self.config.instrument)
        self.connected = True
        self.last_message = f"Connected to ACE telescope {self.config.node}/{self.config.instrument}"

    def disconnect(self):
        self.telescope = None
        self.connection = None
        self.connected = False
        self.last_message = "Disconnected from ACE telescope"

    def status(self) -> TcsStatus:
        if not self.connected or self.telescope is None:
            return TcsStatus(
                name="ACE TCS",
                connected=False,
                ready=False,
                state="offline",
                message=self.last_message,
            )

        current_position = self._safe_call(self.telescope.get_position)
        target_position = self._safe_call(self.telescope.get_target)
        current_ra = self._position_value(current_position, "ra")
        current_dec = self._position_value(current_position, "dec")
        target_ra = self._position_value(target_position, "ra")
        target_dec = self._position_value(target_position, "dec")

        target_name = None
        if target_ra is not None and target_dec is not None:
            target_name = f"Target {target_ra:.6f}, {target_dec:.6f} deg"

        return TcsStatus(
            name="ACE TCS",
            connected=True,
            ready=True,
            state="connected",
            message=self.last_message,
            target_name=target_name,
            ra=self._format_degrees(current_ra),
            dec=self._format_degrees(current_dec),
            tracking=True,
            guiding=False,
        )

    def go_to_j2000(self, ra_deg: float, dec_deg: float):
        telescope = self._require_telescope()
        self._validate_ra_dec(ra_deg, dec_deg)
        telescope.go_to_j2000(float(ra_deg), float(dec_deg))
        self.last_message = f"ACE go_to_j2000 requested: RA {ra_deg:.6f} deg, Dec {dec_deg:.6f} deg"
        return {
            "ra_deg": float(ra_deg),
            "dec_deg": float(dec_deg),
            "message": self.last_message,
        }

    def offset(self, east_arcsec: float, north_arcsec: float):
        telescope = self._require_telescope()
        current_position = telescope.get_position()
        current_ra = self._position_value(current_position, "ra")
        current_dec = self._position_value(current_position, "dec")
        if current_ra is None or current_dec is None:
            raise RuntimeError("ACE telescope did not return a usable current RA/Dec position")

        cos_dec = math.cos(math.radians(current_dec))
        if abs(cos_dec) < 1e-6:
            raise ValueError("Cannot compute RA offset within 0.2 arcsec of a celestial pole")

        target_ra = (current_ra + float(east_arcsec) / 3600.0 / cos_dec) % 360.0
        target_dec = current_dec + float(north_arcsec) / 3600.0
        target_dec = max(-90.0, min(90.0, target_dec))
        telescope.go_to_j2000(target_ra, target_dec)
        self.last_message = (
            f"ACE offset requested: east {east_arcsec:.2f} arcsec, north {north_arcsec:.2f} arcsec; "
            f"commanded RA {target_ra:.6f} deg, Dec {target_dec:.6f} deg"
        )
        return {
            "east_offset_arcsec": float(east_arcsec),
            "north_offset_arcsec": float(north_arcsec),
            "commanded_ra_deg": target_ra,
            "commanded_dec_deg": target_dec,
            "method": "small-angle RA/Dec conversion followed by ACE go_to_j2000",
            "message": self.last_message,
        }

    def _require_telescope(self):
        if not self.connected or self.telescope is None:
            raise RuntimeError("ACE telescope is not connected")
        return self.telescope

    def _safe_call(self, func):
        try:
            return func()
        except Exception:
            logger.exception("ACE telescope status call failed")
            self.last_message = "ACE telescope status call failed"
            return None

    def _position_value(self, position, name: str) -> float | None:
        if position is None:
            return None
        return _safe_float(getattr(position, name, None))

    def _format_degrees(self, value: float | None) -> str | None:
        if value is None:
            return None
        return f"{value:.6f} deg"

    def _validate_ra_dec(self, ra_deg: float, dec_deg: float):
        if not 0.0 <= float(ra_deg) < 360.0:
            raise ValueError("RA must be in degrees in the range [0, 360)")
        if not -90.0 <= float(dec_deg) <= 90.0:
            raise ValueError("Dec must be in degrees in the range [-90, 90]")


class AceGuideCamera:
    """ACE Connector adapter for the existing telescope guide camera.

    The documented ACE camera interface supports status fields and blocking
    exposures saved by ACE. It does not document a method for retrieving the
    saved filename or image bytes, so capture_preview() returns an operation
    message rather than a local preview file path.
    """

    def __init__(self, config: AceCameraConfig):
        self.config = config
        self.connection = None
        self.camera = None
        self.ace_camera = None
        self.connected = False
        self.last_message = "offline"

    def connect(self):
        self.ace_camera = _load_ace_module("ace.camera")
        self.connection = _open_connection(self.config)
        self.camera = self.ace_camera.Camera(self.connection, self.config.node, self.config.instrument)
        self.connected = True
        self.last_message = f"Connected to ACE guide camera {self.config.node}/{self.config.instrument}"

    def disconnect(self):
        self.camera = None
        self.connection = None
        self.connected = False
        self.last_message = "Disconnected from ACE guide camera"

    def status(self) -> CameraStatus:
        if not self.connected or self.camera is None:
            return CameraStatus(
                name="ACE Guide Camera",
                connected=False,
                ready=False,
                state="offline",
                message=self.last_message,
            )

        state_value = self._safe_attr("state")
        state_label = _constant_name(getattr(self.ace_camera, "state", None), state_value)
        exposing = state_label == "exposing"
        return CameraStatus(
            name="ACE Guide Camera",
            connected=True,
            ready=not exposing,
            state=state_label,
            message=self.last_message,
            temperature_c=_safe_float(self._safe_attr("temperature")),
            setpoint_c=_safe_float(self._safe_attr("setpoint")),
            exposing=exposing,
            binning=(1, 1),
            roi=None,
            gain_mode=str(self._safe_attr("readout_mode")) if self._safe_attr("readout_mode") is not None else None,
        )

    def capture_preview(self, exposure_s: float = 0.2) -> str:
        if not self.connected or self.camera is None or self.ace_camera is None:
            raise RuntimeError("ACE guide camera is not connected")

        exposure_type = self.ace_camera.exposure_type.LIGHT
        self.camera.expose(float(exposure_s), type=exposure_type, bin_x=1, bin_y=1, save=True, block=True)
        self.last_message = (
            f"ACE guide camera exposure complete: {exposure_s:.3f} s. "
            "Image save/location is managed by ACE."
        )
        return self.last_message

    def _safe_attr(self, name: str):
        try:
            return getattr(self.camera, name)
        except Exception:
            logger.exception("ACE guide camera status read failed for %s", name)
            self.last_message = f"ACE guide camera status read failed for {name}"
            return None


class AceGuideStageMotion:
    """ACE Connector adapter for the existing guide-camera stage.

    This maps each configured stage axis to an ACE Focuser instrument. That is
    the closest documented ACE interface for a single controllable position with
    position, target, limits, go(), and stop().
    """

    def __init__(self, config: AceStageConfig):
        self.config = config
        self.connection = None
        self.ace_focuser = None
        self.focusers = {}
        self.connected = False

    def connect(self):
        self.ace_focuser = _load_ace_module("ace.focuser")
        self.connection = _open_connection(self.config)
        self.focusers = {}
        for axis_config in self.config.axes or []:
            self.focusers[axis_config.axis] = {
                "config": axis_config,
                "device": self.ace_focuser.Focuser(self.connection, axis_config.node, axis_config.instrument),
            }
        self.connected = True

    def disconnect(self):
        self.focusers = {}
        self.connection = None
        self.connected = False

    def axes(self) -> list[AxisStatus]:
        statuses = []
        for axis, entry in self.focusers.items():
            focuser = entry["device"]
            axis_config = entry["config"]
            state_value = self._safe_get(focuser, "state")
            state_label = _constant_name(getattr(self.ace_focuser, "state", None), state_value)
            moving = state_label in {"moving_fwd", "moving_rev"}
            statuses.append(
                AxisStatus(
                    name=axis,
                    position=_safe_float(self._safe_get(focuser, "position")) or 0.0,
                    units=axis_config.units,
                    homed=self.connected,
                    moving=moving,
                    min_limit=_safe_float(self._safe_get(focuser, "minimum")),
                    max_limit=_safe_float(self._safe_get(focuser, "maximum")),
                    fault=None,
                )
            )
        return statuses

    def home(self, axis: str):
        focuser = self._get_focuser(axis)
        focuser.go_to_minimum()

    def move_absolute(self, axis: str, position: float):
        focuser = self._get_focuser(axis)
        minimum = _safe_float(self._safe_get(focuser, "minimum"))
        maximum = _safe_float(self._safe_get(focuser, "maximum"))
        if minimum is not None and position < minimum:
            raise ValueError(f"{axis} move below ACE minimum limit")
        if maximum is not None and position > maximum:
            raise ValueError(f"{axis} move above ACE maximum limit")
        focuser.go(float(position))

    def move_relative(self, axis: str, delta: float):
        focuser = self._get_focuser(axis)
        current = _safe_float(self._safe_get(focuser, "position"))
        if current is None:
            raise RuntimeError(f"ACE guide stage axis {axis} did not report a usable position")
        self.move_absolute(axis, current + float(delta))

    def stop(self, axis: str | None = None):
        if axis is not None:
            self._get_focuser(axis).stop()
            return
        for entry in self.focusers.values():
            entry["device"].stop()

    def _get_focuser(self, axis: str):
        if not self.connected:
            raise RuntimeError("ACE guide stage is not connected")
        if axis not in self.focusers:
            raise KeyError(f"Unknown ACE guide stage axis: {axis}")
        return self.focusers[axis]["device"]

    def _safe_get(self, focuser, name: str):
        try:
            return getattr(focuser, name)
        except Exception:
            logger.exception("ACE guide stage status read failed for %s", name)
            return None
