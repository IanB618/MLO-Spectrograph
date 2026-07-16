from dataclasses import dataclass
from pathlib import Path

from src.config import Config
from src.devices.indi import IndiCcdCamera, IndiFocuser
from src.devices.mock import MockAcquisitionCamera, MockLensFocus, MockMotionController, MockScienceCamera, MockTcs


@dataclass
class DeviceBundle:
    science_camera: object
    acquisition_camera: object
    lens: object
    motion: object
    tcs: object


def build_device_bundle(config: Config) -> DeviceBundle:
    if config.backend_mode == "mock":
        return DeviceBundle(
            science_camera=MockScienceCamera(config.data_root),
            acquisition_camera=MockAcquisitionCamera(config.data_root),
            lens=MockLensFocus(),
            motion=MockMotionController(),
            tcs=MockTcs(),
        )

    if config.backend_mode == "indi":
        return DeviceBundle(
            science_camera=IndiCcdCamera(
                host=config.indi_host,
                port=config.indi_port,
                device_name=config.indi_ccd_device,
                data_root=config.data_root,
                blob_property=config.indi_blob_property,
                connect_timeout_s=config.indi_connect_timeout_s,
                command_timeout_s=config.indi_command_timeout_s,
            ),
            acquisition_camera=MockAcquisitionCamera(config.data_root),
            lens=IndiFocuser(
                host=config.indi_host,
                port=config.indi_port,
                device_name=config.indi_focuser_device,
                connect_timeout_s=config.indi_connect_timeout_s,
                command_timeout_s=config.indi_command_timeout_s,
            ),
            motion=MockMotionController(),
            tcs=MockTcs(),
        )

    raise ValueError(f"Unsupported backend mode: {config.backend_mode}")
