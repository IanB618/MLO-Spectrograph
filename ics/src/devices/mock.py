from pathlib import Path

from astropy.coordinates import SkyCoord

from src.models import AxisStatus, CameraStatus, TcsStatus


class MockAcquisitionCamera:
    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.connected = False
        self.last_preview_path = ""

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def status(self) -> CameraStatus:
        return CameraStatus(
            name="Guide Camera / Acquisition",
            connected=self.connected,
            ready=self.connected,
            state="mock",
            temperature_c=None,
            exposing=False,
            binning=(1, 1),
            roi=(0, 0, 1280, 960),
        )

    def capture_preview(self, exposure_s: float = 0.2) -> str:
        preview_dir = self.data_root / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        path = preview_dir / "latest_guide_preview.txt"
        path.write_text(f"Mock guide camera preview, exposure_s={exposure_s}\n", encoding="utf-8")
        self.last_preview_path = str(path)
        return self.last_preview_path


class MockMotionController:
    def __init__(self):
        self.connected = False
        self._axes = {
            "stage_x": AxisStatus(name="stage_x", units="steps", min_limit=-50000, max_limit=50000),
            "stage_y": AxisStatus(name="stage_y", units="steps", min_limit=-50000, max_limit=50000),
            "stage_focus": AxisStatus(name="stage_focus", units="steps", min_limit=-20000, max_limit=20000),
        }

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def axes(self) -> list[AxisStatus]:
        return list(self._axes.values())

    def home(self, axis: str):
        status = self._get_axis(axis)
        status.moving = True
        status.position = 0.0
        status.homed = True
        status.moving = False

    def move_absolute(self, axis: str, position: float):
        status = self._get_axis(axis)
        if status.min_limit is not None and position < status.min_limit:
            raise ValueError(f"{axis} move below minimum limit")
        if status.max_limit is not None and position > status.max_limit:
            raise ValueError(f"{axis} move above maximum limit")
        status.moving = True
        status.position = position
        status.moving = False

    def move_relative(self, axis: str, delta: float):
        status = self._get_axis(axis)
        self.move_absolute(axis, status.position + delta)

    def stop(self, axis: str | None = None):
        if axis:
            self._get_axis(axis).moving = False
            return
        for status in self._axes.values():
            status.moving = False

    def _get_axis(self, axis: str) -> AxisStatus:
        if axis not in self._axes:
            raise KeyError(f"Unknown axis: {axis}")
        return self._axes[axis]


class MockTcs:
    def __init__(self):
        self.connected = False
        self.east_offset_arcsec = 0.0
        self.north_offset_arcsec = 0.0
        self.ra_deg = 188.73625
        self.dec_deg = 12.58222

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def skycoord(self) -> SkyCoord:
        return SkyCoord(ra=self.ra_deg, dec=self.dec_deg,
                        unit="deg", frame="icrs")

    def radec_str(self) -> tuple[str]:
        return self.skycoord.to_string("hmsdms")

    def status(self) -> TcsStatus:
        return TcsStatus(
            name="ACE TCS Adapter",
            connected=self.connected,
            ready=self.connected,
            state="mock",
            target_name="Mock Target",
            ra=f"{self.ra_deg:.6f} deg",
            dec=f"{self.dec_deg:.6f} deg",
            altitude_deg=62.1,
            azimuth_deg=211.3,
            airmass=1.13,
            tracking=self.connected,
            guiding=False,
        )

    def go_to_j2000(self, ra_deg: float, dec_deg: float):
        self.ra_deg = float(ra_deg)
        self.dec_deg = float(dec_deg)
        return {
            "ra_deg": self.ra_deg,
            "dec_deg": self.dec_deg,
            "message": "Mock telescope slew requested",
        }

    def offset(self, east_arcsec: float, north_arcsec: float):
        self.east_offset_arcsec += east_arcsec
        self.north_offset_arcsec += north_arcsec
        self.ra_deg += east_arcsec / 3600.0
        self.dec_deg += north_arcsec / 3600.0
        return {
            "east_offset_arcsec": self.east_offset_arcsec,
            "north_offset_arcsec": self.north_offset_arcsec,
            "commanded_ra_deg": self.ra_deg,
            "commanded_dec_deg": self.dec_deg,
            "method": "mock linear offset",
        }
