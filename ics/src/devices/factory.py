from dataclasses import dataclass
from pathlib import Path

from src.config import Config
from src.devices.ace_tcs import (
    AceCameraConfig,
    AceGuideCamera,
    AceGuideStageMotion,
    AceStageAxisConfig,
    AceStageConfig,
    AceTcs,
    AceTelescopeConfig,
)
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
    science_camera, lens = _build_instrument_side_devices(config)
    return DeviceBundle(
        science_camera=science_camera,
        acquisition_camera=_build_guide_camera(config, data_root),
        lens=lens,
        motion=_build_stage_motion(config),
        tcs=_build_tcs(config),
    )


def _build_instrument_side_devices(config: Config):
    if config.backend_mode == "mock":
        return MockScienceCamera(config.data_root), MockLensFocus()

    if config.backend_mode == "indi":
        return (
            IndiCcdCamera(
                host=config.indi_host,
                port=config.indi_port,
                device_name=config.indi_ccd_device,
                data_root=config.data_root,
                blob_property=config.indi_blob_property,
                connect_timeout_s=config.indi_connect_timeout_s,
                command_timeout_s=config.indi_command_timeout_s,
            ),
            IndiFocuser(
                host=config.indi_host,
                port=config.indi_port,
                device_name=config.indi_focuser_device,
                connect_timeout_s=config.indi_connect_timeout_s,
                command_timeout_s=config.indi_command_timeout_s,
            ),
        )

    raise ValueError(f"Unsupported backend mode: {config.backend_mode}")


def _build_guide_camera(config: Config, data_root: Path):
    if config.guide_camera_backend == "mock":
        return MockAcquisitionCamera(data_root)

    if config.guide_camera_backend == "ace":
        return AceGuideCamera(
            AceCameraConfig(
                host=config.ace_host,
                port=config.ace_port,
                node=config.ace_guide_camera_node,
                instrument=config.ace_guide_camera_name,
                username=config.ace_username,
                password=config.ace_password,
            )
        )

    raise ValueError(f"Unsupported guide camera backend: {config.guide_camera_backend}")


def _build_stage_motion(config: Config):
    if config.stage_backend == "mock":
        return MockMotionController()

    if config.stage_backend == "ace":
        axes = []
        if config.ace_stage_x_name:
            axes.append(AceStageAxisConfig("stage_x", config.ace_stage_node, config.ace_stage_x_name))
        if config.ace_stage_y_name:
            axes.append(AceStageAxisConfig("stage_y", config.ace_stage_node, config.ace_stage_y_name))
        if config.ace_stage_focus_name:
            axes.append(AceStageAxisConfig("stage_focus", config.ace_stage_node, config.ace_stage_focus_name))
        if not axes:
            raise ValueError("ICS_STAGE_BACKEND=ace requires at least one ACE guide stage axis name")
        return AceGuideStageMotion(
            AceStageConfig(
                host=config.ace_host,
                port=config.ace_port,
                username=config.ace_username,
                password=config.ace_password,
                axes=axes,
            )
        )

    raise ValueError(f"Unsupported stage backend: {config.stage_backend}")


def _build_tcs(config: Config):
    if config.tcs_backend == "mock":
        return MockTcs()

    if config.tcs_backend == "ace":
        return AceTcs(
            AceTelescopeConfig(
                host=config.ace_host,
                port=config.ace_port,
                node=config.ace_node,
                instrument=config.ace_telescope_name,
                username=config.ace_username,
                password=config.ace_password,
            )
        )

    raise ValueError(f"Unsupported TCS backend: {config.tcs_backend}")
