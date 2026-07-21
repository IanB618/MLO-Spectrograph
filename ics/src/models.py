from enum import StrEnum
from pathlib import Path
from typing import Literal

from astropy.io import fits

from pydantic import BaseModel, Field


class SystemState(StrEnum):
    OFFLINE = "offline"
    IDLE = "idle"
    ACQUIRING = "acquiring"
    FOCUSING = "focusing"
    EXPOSING = "exposing"
    CALIBRATING = "calibrating"
    SAFE = "safe"
    ERROR = "error"


class ExposureType(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    BIAS = "bias"
    FLAT = "flat"
    ARC = "arc"


class DeviceStatus(BaseModel):
    name: str
    connected: bool = False
    ready: bool = False
    state: str = "unknown"
    message: str = ""


class CameraStatus(DeviceStatus):
    temperature_c: float | None = None
    setpoint_c: float | None = None
    cooler_power_pct: float | None = None
    exposing: bool = False
    exposure_remaining_s: float | None = None
    binning: tuple[int, int] = (1, 1)
    roi: tuple[int, int, int, int] | None = None
    gain_mode: str | None = None


class AxisStatus(BaseModel):
    name: str
    position: float = 0.0
    units: str = "steps"
    homed: bool = False
    moving: bool = False
    min_limit: float | None = None
    max_limit: float | None = None
    fault: str | None = None


class LensStatus(DeviceStatus):
    position: int = 0
    moving: bool = False


class TcsStatus(DeviceStatus):
    target_name: str | None = None
    ra: str | None = None
    dec: str | None = None
    altitude_deg: float | None = None
    azimuth_deg: float | None = None
    airmass: float | None = None
    tracking: bool = False
    guiding: bool = False


class ExposureRequest(BaseModel):
    exposure_s: float = Field(gt=0)
    image_type: ExposureType = ExposureType.LIGHT
    object_name: str = ""
    binning: Literal["1x1", "2x2", "4x4"] = "1x1"
    comment: str = ""

    @property
    def binning_value(self) -> int:
        value = int(self.binning.split("x", maxsplit=1)[0])
        return value

    @property
    def binning_tuple(self) -> tuple[int, int]:
        return self.binning_value, self.binning_value

    def to_header(self) -> fits.Header:
        header = fits.Header()
        header.set("BINNING", self.binning, "Pixel binning setting")
        header.set("IMAGETYP", self.image_type, "Image type (light, cal, dark, bias, etc.)")
        header.set("OBJECT", self.object_name, "Target name")
        header.set("EXPTIME", float(self.exposure_s), "[s] Requested exposure time")
        if self.comment:
            header.set("USERCMNT", self.comment, "Observer-defined comment")
        return header


class ExposureResult(BaseModel):
    exposure_id: str
    image_type: ExposureType
    exposure_s: float
    path: Path
    success: bool
    message: str = ""

    @classmethod
    def from_request(cls, request: ExposureRequest, exposure_id, path, success, message=None):
        return NotImplemented


class MotionMoveRequest(BaseModel):
    axis: str
    position: float | None = None
    delta: float | None = None


class LensMoveRequest(BaseModel):
    position: int | None = None
    delta: int | None = None


class TcsGotoRequest(BaseModel):
    ra_deg: float = Field(ge=0, lt=360)
    dec_deg: float = Field(ge=-90, le=90)


class SystemSnapshot(BaseModel):
    state: SystemState
    message: str = ""
    science_camera: CameraStatus
    acquisition_camera: CameraStatus
    lens: LensStatus
    tcs: TcsStatus
    axes: list[AxisStatus]
    last_exposure: ExposureResult | None = None
