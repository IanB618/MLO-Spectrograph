from dataclasses import dataclass
from pathlib import Path

from src.devices.mock import MockAcquisitionCamera, MockLensFocus, MockMotionController, MockScienceCamera, MockTcs


@dataclass
class DeviceBundle:
    science_camera: object
    acquisition_camera: object
    lens: object
    motion: object
    tcs: object


def build_device_bundle(mode: str, data_root: Path) -> DeviceBundle:
    if mode != "mock":
        raise ValueError(f"Unsupported backend mode in skeleton: {mode}")

    return DeviceBundle(
        science_camera=MockScienceCamera(data_root),
        acquisition_camera=MockAcquisitionCamera(data_root),
        lens=MockLensFocus(),
        motion=MockMotionController(),
        tcs=MockTcs(),
    )
