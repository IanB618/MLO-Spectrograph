import importlib
import logging
import math
from dataclasses import dataclass

from src.models import TcsStatus

logger = logging.getLogger(__name__)


class AceUnavailableError(RuntimeError):
    pass


@dataclass
class AceTelescopeConfig:
    host: str
    port: int
    node: str
    instrument: str
    username: str | None = None
    password: str | None = None


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
        ace_syscore, ace_telescope = self._load_ace_modules()
        self.connection = ace_syscore.AceConnection(self.config.host, self.config.port)
        if self.config.username and self.config.password:
            self.connection.authenticate(self.config.username, self.config.password)
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

    def _load_ace_modules(self):
        try:
            ace_syscore = importlib.import_module("ace.syscore")
            ace_telescope = importlib.import_module("ace.telescope")
        except ImportError as error:
            raise AceUnavailableError(
                "ACE Python modules are not installed or are not on PYTHONPATH. "
                "Install ACE Connector's Python interface on this host."
            ) from error
        return ace_syscore, ace_telescope

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
        value = getattr(position, name, None)
        if value is None:
            return None
        return float(value)

    def _format_degrees(self, value: float | None) -> str | None:
        if value is None:
            return None
        return f"{value:.6f} deg"

    def _validate_ra_dec(self, ra_deg: float, dec_deg: float):
        if not 0.0 <= float(ra_deg) < 360.0:
            raise ValueError("RA must be in degrees in the range [0, 360)")
        if not -90.0 <= float(dec_deg) <= 90.0:
            raise ValueError("Dec must be in degrees in the range [-90, 90]")
