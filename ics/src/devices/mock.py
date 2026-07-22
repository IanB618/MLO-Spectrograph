import time
from pathlib import Path
from uuid import uuid4

import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.coordinates import SkyCoord

from src.models import AxisStatus, CameraStatus, DeviceStatus, ExposureRequest, ExposureResult, LensStatus, TcsStatus


class MockScienceCamera:
    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.connected = False
        self.setpoint_c = -20.0
        self.temperature_c = 18.0
        self.exposing = False
        self.binning = (1, 1)
        self.last_result = None

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def status(self) -> CameraStatus:
        if self.connected and self.temperature_c > self.setpoint_c:
            self.temperature_c -= 0.1
        return CameraStatus(
            name="FLI Kepler Science Camera",
            connected=self.connected,
            ready=self.connected and not self.exposing,
            state="mock",
            temperature_c=round(self.temperature_c, 2),
            setpoint_c=self.setpoint_c,
            cooler_power_pct=42.0 if self.connected else 0.0,
            exposing=self.exposing,
            binning=self.binning,
            roi=(0, 0, 2048, 2048),
            gain_mode="mock-low-gain",
        )

    def set_temperature(self, setpoint_c: float):
        self.setpoint_c = setpoint_c

    def expose(self, request: ExposureRequest) -> ExposureResult:
        self.exposing = True
        self.binning = request.binning_tuple
        exp_start = Time.now()
        exposure_id = f"raw_{exp_start.datetime.strftime('%Y%m%dT%H%M%S')}_{request.image_type}_{uuid4().hex[:8]}"
        night_dir = self.data_root / time.strftime("%Y-%m-%d")
        night_dir.mkdir(parents=True, exist_ok=True)
        path = night_dir / f"{exposure_id}.fits"
        time.sleep(min(request.exposure_s, 0.25))
        data = np.tile(np.arange(0, 65536, dtype=np.uint16), 64//(request.binning_value**2)).reshape((-1, 2048//request.binning_value))
        exp_end = Time.now()
        hdu = fits.PrimaryHDU(data=data)
        hdu.header.set("INSTRUME", "MLO 50\" Fiber-Fed Spectrograph", "Instrument name")
        hdu.header.set("CAMERA", "FLI Kepler KL400", "Camera name")
        hdu.header.set("DETECTOR", "GSENSE 400", "Sensor name")
        hdu.header.update(request.to_header())
        hdu.header.set("DATE-OBS", exp_start.isot, "[UTC] Exposure start time")
        hdu.header.set("DATE-END", exp_end.isot, "[UTC] Exposure end time")
        hdu.header["COMMENT"] = "This is a dummy FITS file containing an incrementing test pattern."
        hdu.writeto(path)
        self.exposing = False
        self.last_result = ExposureResult(
            exposure_id=exposure_id,
            image_type=request.image_type,
            exposure_s=request.exposure_s,
            path=path,
            success=True,
            message="Mock exposure complete",
        )
        return self.last_result

    def abort(self):
        self.exposing = False


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


class MockLensFocus:
    def __init__(self):
        self.connected = False
        self.position = 0
        self.moving = False

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def status(self) -> LensStatus:
        return LensStatus(
            name="Pinefeat EF Lens Controller",
            connected=self.connected,
            ready=self.connected and not self.moving,
            state="mock",
            position=self.position,
            moving=self.moving,
        )

    def move_absolute(self, position: int):
        self.moving = True
        self.position = position
        self.moving = False

    def move_relative(self, delta: int):
        self.move_absolute(self.position + delta)

    def stop(self):
        self.moving = False


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
