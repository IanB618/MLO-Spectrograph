from abc import ABC, abstractmethod

from src.models import CameraStatus, ExposureRequest, ExposureResult, LensStatus, TcsStatus, AxisStatus


class DeviceBackend(ABC):
    @abstractmethod
    def connect(self):
        raise NotImplementedError

    @abstractmethod
    def disconnect(self):
        raise NotImplementedError


class ScienceCameraBackend(DeviceBackend):
    @abstractmethod
    def status(self) -> CameraStatus:
        raise NotImplementedError

    @abstractmethod
    def set_temperature(self, setpoint_c: float):
        raise NotImplementedError

    @abstractmethod
    def expose(self, request: ExposureRequest) -> ExposureResult:
        raise NotImplementedError

    @abstractmethod
    def abort(self):
        raise NotImplementedError


class AcquisitionCameraBackend(DeviceBackend):
    @abstractmethod
    def status(self) -> CameraStatus:
        raise NotImplementedError

    @abstractmethod
    def capture_preview(self, exposure_s: float = 0.2) -> str:
        raise NotImplementedError


class LensFocusBackend(DeviceBackend):
    @abstractmethod
    def status(self) -> LensStatus:
        raise NotImplementedError

    @abstractmethod
    def move_absolute(self, position: int):
        raise NotImplementedError

    @abstractmethod
    def move_relative(self, delta: int):
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        raise NotImplementedError


class MotionBackend(DeviceBackend):
    @abstractmethod
    def axes(self) -> list[AxisStatus]:
        raise NotImplementedError

    @abstractmethod
    def home(self, axis: str):
        raise NotImplementedError

    @abstractmethod
    def move_absolute(self, axis: str, position: float):
        raise NotImplementedError

    @abstractmethod
    def move_relative(self, axis: str, delta: float):
        raise NotImplementedError

    @abstractmethod
    def stop(self, axis: str | None = None):
        raise NotImplementedError


class TcsBackend(DeviceBackend):
    @abstractmethod
    def status(self) -> TcsStatus:
        raise NotImplementedError

    @abstractmethod
    def offset(self, east_arcsec: float, north_arcsec: float):
        raise NotImplementedError
