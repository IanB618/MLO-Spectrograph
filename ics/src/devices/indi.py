import logging
import time
from pathlib import Path
from threading import Condition, Lock
from uuid import uuid4

from src.models import CameraStatus, ExposureRequest, ExposureResult, LensStatus

import PyIndi

logger = logging.getLogger(__name__)


class IndiUnavailableError(RuntimeError):
    pass


class IndiClient(PyIndi.BaseClient):
    """Small PyIndi client wrapper with blocking waits for properties and BLOBs."""

    def __init__(self):
        super().__init__()
        self._condition = Condition()
        self._connected = False
        self._last_blob = None
        self._messages: list[str] = []

    def serverConnected(self):
        with self._condition:
            self._connected = True
            self._condition.notify_all()

    def serverDisconnected(self, code):
        with self._condition:
            self._connected = False
            self._condition.notify_all()
        logger.warning("INDI server disconnected with code %s", code)

    def newDevice(self, device):
        with self._condition:
            self._condition.notify_all()
        logger.info("INDI device discovered: %s", device.getDeviceName())

    def removeDevice(self, device):
        with self._condition:
            self._condition.notify_all()
        logger.info("INDI device removed: %s", device.getDeviceName())

    def newProperty(self, prop):
        self._store_blob_if_needed(prop)
        with self._condition:
            self._condition.notify_all()

    def updateProperty(self, prop):
        self._store_blob_if_needed(prop)
        with self._condition:
            self._condition.notify_all()

    def removeProperty(self, prop):
        with self._condition:
            self._condition.notify_all()

    def newMessage(self, device, message_id):
        message = device.messageQueue(message_id)
        with self._condition:
            self._messages.append(message)
            self._condition.notify_all()
        logger.info("INDI message from %s: %s", device.getDeviceName(), message)

    def connect(self, host: str, port: int, timeout_s: float):
        self.setServer(host, port)
        if not self.connectServer():
            raise RuntimeError(f"Could not connect to INDI server at {host}:{port}")
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while not self._connected and time.monotonic() < deadline:
                self._condition.wait(timeout=0.1)
        if not self._connected:
            raise TimeoutError(f"Timed out connecting to INDI server at {host}:{port}")

    def disconnect(self):
        if self._connected:
            self.disconnectServer()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def wait_for_device(self, device_name: str, timeout_s: float):
        return self._wait_until(lambda: self.get_device(device_name), timeout_s, f"INDI device '{device_name}'")

    def wait_for_property(self, device_name: str, property_name: str, timeout_s: float):
        return self._wait_until(
            lambda: self.get_property(device_name, property_name),
            timeout_s,
            f"INDI property '{device_name}.{property_name}'",
        )

    def get_device(self, device_name: str):
        for device in self.getDevices():
            if device.getDeviceName() == device_name:
                return device
        return None

    def get_property(self, device_name: str, property_name: str):
        device = self.get_device(device_name)
        if device is None:
            return None
        for prop in device.getProperties():
            if prop.getName() == property_name:
                return prop
        return None

    def property_state(self, device_name: str, property_name: str) -> str:
        prop = self.get_property(device_name, property_name)
        if prop is None:
            return "unknown"
        return prop.getStateAsString().lower()

    def set_number(self, device_name: str, property_name: str, values: dict[str, float]):
        prop = self._number_property(device_name, property_name)
        self._set_widgets_by_name_or_first(prop, values, setter_name="setValue")
        self.sendNewNumber(prop)

    def read_number(self, device_name: str, property_name: str) -> dict[str, float]:
        prop = self._number_property(device_name, property_name)
        return {widget.getName(): widget.getValue() for widget in prop}

    def set_switch(self, device_name: str, property_name: str, on_name: str):
        prop = self._switch_property(device_name, property_name)
        if hasattr(prop, "reset"):
            prop.reset()
        else:
            for widget in prop:
                widget.setState(PyIndi.ISS_OFF)
        widget = self._find_widget(prop, on_name)
        if widget is None:
            available = ", ".join(item.getName() for item in prop)
            raise ValueError(f"Switch '{on_name}' not found in {device_name}.{property_name}; available: {available}")
        widget.setState(PyIndi.ISS_ON)
        self.sendNewSwitch(prop)

    def read_switch(self, device_name: str, property_name: str) -> dict[str, str]:
        prop = self._switch_property(device_name, property_name)
        return {widget.getName(): widget.getStateAsString() for widget in prop}

    def request_blobs(self, device_name: str, property_name: str | None = None):
        blob_name = property_name or None
        self.setBLOBMode(PyIndi.B_ALSO, device_name, blob_name)

    def clear_last_blob(self):
        with self._condition:
            self._last_blob = None

    def wait_for_blob(self, device_name: str, property_name: str, timeout_s: float):
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while time.monotonic() < deadline:
                if (
                    self._last_blob is not None
                    and self._last_blob["device"] == device_name
                    and self._last_blob["property"] == property_name
                ):
                    return self._last_blob
                self._condition.wait(timeout=0.1)
        raise TimeoutError(f"Timed out waiting for BLOB {device_name}.{property_name}")

    def _wait_until(self, getter, timeout_s: float, description: str):
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while time.monotonic() < deadline:
                value = getter()
                if value is not None:
                    return value
                self._condition.wait(timeout=0.1)
        raise TimeoutError(f"Timed out waiting for {description}")

    def _number_property(self, device_name: str, property_name: str):
        generic = self.wait_for_property(device_name, property_name, timeout_s=1.0)
        prop = PyIndi.PropertyNumber(generic)
        if not prop.isValid():
            raise TypeError(f"{device_name}.{property_name} is not an INDI number property")
        return prop

    def _switch_property(self, device_name: str, property_name: str):
        generic = self.wait_for_property(device_name, property_name, timeout_s=1.0)
        prop = PyIndi.PropertySwitch(generic)
        if not prop.isValid():
            raise TypeError(f"{device_name}.{property_name} is not an INDI switch property")
        return prop

    def _set_widgets_by_name_or_first(self, prop, values: dict[str, float], setter_name: str):
        widgets = list(prop)
        for name, value in values.items():
            widget = self._find_widget(prop, name)
            if widget is None and len(values) == 1 and len(widgets) == 1:
                widget = widgets[0]
            if widget is None:
                available = ", ".join(item.getName() for item in widgets)
                raise ValueError(f"Widget '{name}' not found in {prop.getDeviceName()}.{prop.getName()}; available: {available}")
            getattr(widget, setter_name)(value)

    def _find_widget(self, prop, name: str):
        if hasattr(prop, "findWidgetByName"):
            widget = prop.findWidgetByName(name)
            if widget is not None:
                return widget
        for widget in prop:
            if widget.getName() == name:
                return widget
        return None

    def _store_blob_if_needed(self, prop):
        if prop.getType() != PyIndi.INDI_BLOB:
            return
        blob_prop = PyIndi.PropertyBlob(prop)
        if not blob_prop.isValid():
            return
        for widget in blob_prop:
            raw_blob = widget.getBlob()
            if raw_blob is None:
                continue
            data = self._blob_to_bytes(raw_blob)
            with self._condition:
                self._last_blob = {
                    "device": prop.getDeviceName(),
                    "property": prop.getName(),
                    "widget": widget.getName(),
                    "format": widget.getFormat(),
                    "size": widget.getSize(),
                    "bloblen": widget.getBlobLen(),
                    "data": data,
                }
                self._condition.notify_all()

    def _blob_to_bytes(self, raw_blob) -> bytes:
        if isinstance(raw_blob, bytes):
            return raw_blob
        if isinstance(raw_blob, bytearray):
            return bytes(raw_blob)
        if isinstance(raw_blob, memoryview):
            return raw_blob.tobytes()
        if isinstance(raw_blob, str):
            return raw_blob.encode("latin1")
        return bytes(raw_blob)


class IndiDeviceBase:
    def __init__(self, host: str, port: int, device_name: str, connect_timeout_s: float, command_timeout_s: float):
        self.host = host
        self.port = port
        self.device_name = device_name
        self.connect_timeout_s = connect_timeout_s
        self.command_timeout_s = command_timeout_s
        self.client: IndiClient | None = None
        self._lock = Lock()

    @property
    def connected(self) -> bool:
        return self.client is not None and self.client.is_connected

    def connect(self):
        with self._lock:
            if self.connected:
                return
            self.client = IndiClient()
            self.client.connect(self.host, self.port, self.connect_timeout_s)
            self.client.wait_for_device(self.device_name, self.connect_timeout_s)
            self._connect_driver_if_supported()

    def disconnect(self):
        with self._lock:
            if self.client is not None:
                self._disconnect_driver_if_supported()
                self.client.disconnect()
                self.client = None

    def _require_client(self) -> IndiClient:
        if self.client is None or not self.client.is_connected:
            raise RuntimeError(f"{self.device_name} is not connected to INDI")
        return self.client

    def _connect_driver_if_supported(self):
        assert self.client is not None
        if self.client.get_property(self.device_name, "CONNECTION") is None:
            return
        self.client.set_switch(self.device_name, "CONNECTION", "CONNECT")
        time.sleep(0.25)

    def _disconnect_driver_if_supported(self):
        assert self.client is not None
        if self.client.get_property(self.device_name, "CONNECTION") is None:
            return
        try:
            self.client.set_switch(self.device_name, "CONNECTION", "DISCONNECT")
        except Exception:
            logger.exception("Could not disconnect INDI device %s cleanly", self.device_name)


class IndiCcdCamera(IndiDeviceBase):
    def __init__(
        self,
        host: str,
        port: int,
        device_name: str,
        data_root: Path,
        blob_property: str,
        connect_timeout_s: float,
        command_timeout_s: float,
    ):
        super().__init__(host, port, device_name, connect_timeout_s, command_timeout_s)
        self.data_root = data_root
        self.blob_property = blob_property
        self.binning = (1, 1)
        self.exposing = False
        self.last_result: ExposureResult | None = None

    def connect(self):
        super().connect()
        client = self._require_client()
        client.request_blobs(self.device_name, self.blob_property)

    def status(self) -> CameraStatus:
        if not self.connected:
            return CameraStatus(name=self.device_name, connected=False, ready=False, state="offline")

        client = self._require_client()
        temperature = self._read_first_number("CCD_TEMPERATURE")
        cooler_power = self._read_first_number("CCD_COOLER_POWER")
        roi = self._read_roi()
        binning = self._read_binning()
        state = client.property_state(self.device_name, "CCD_EXPOSURE")
        exposing = self.exposing or state == "busy"
        return CameraStatus(
            name=self.device_name,
            connected=True,
            ready=not exposing,
            state=state,
            temperature_c=temperature,
            setpoint_c=temperature,
            cooler_power_pct=cooler_power,
            exposing=exposing,
            binning=binning,
            roi=roi,
            gain_mode="INDI CCD",
        )

    def set_temperature(self, setpoint_c: float):
        client = self._require_client()
        client.set_number(self.device_name, "CCD_TEMPERATURE", {"CCD_TEMPERATURE_VALUE": setpoint_c})

    def expose(self, request: ExposureRequest) -> ExposureResult:
        client = self._require_client()
        self.exposing = True
        self.binning = request.binning_tuple
        exposure_id = f"{time.strftime('%Y%m%dT%H%M%S')}_{request.image_type}_{uuid4().hex[:8]}"
        night_dir = self.data_root / time.strftime("%Y-%m-%d")
        night_dir.mkdir(parents=True, exist_ok=True)
        path = night_dir / f"{exposure_id}.fits"
        try:
            self._set_frame_type(request)
            client.set_number(
                self.device_name,
                "CCD_BINNING",
                {"HOR_BIN": request.binning_tuple[0], "VER_BIN": request.binning_tuple[1]},
            )
            client.clear_last_blob()
            client.request_blobs(self.device_name, self.blob_property)
            client.set_number(self.device_name, "CCD_EXPOSURE", {"CCD_EXPOSURE_VALUE": request.exposure_s})
            blob = client.wait_for_blob(self.device_name, self.blob_property, request.exposure_s + self.command_timeout_s)
            path.write_bytes(blob["data"])
            result = ExposureResult(
                exposure_id=exposure_id,
                image_type=request.image_type,
                exposure_s=request.exposure_s,
                path=path,
                success=True,
                message=f"INDI exposure complete from {self.device_name}.{self.blob_property}",
            )
            self.last_result = result
            return result
        finally:
            self.exposing = False

    def abort(self):
        if not self.connected:
            self.exposing = False
            return
        client = self._require_client()
        try:
            client.set_switch(self.device_name, "CCD_ABORT_EXPOSURE", "ABORT")
        except Exception:
            logger.exception("Could not send CCD abort command")
        self.exposing = False

    def _set_frame_type(self, request: ExposureRequest):
        frame_map = {
            "light": "FRAME_LIGHT",
            "dark": "FRAME_DARK",
            "bias": "FRAME_BIAS",
            "flat": "FRAME_FLAT",
            "arc": "FRAME_LIGHT",
        }
        client = self._require_client()
        if client.get_property(self.device_name, "CCD_FRAME_TYPE") is None:
            return
        client.set_switch(self.device_name, "CCD_FRAME_TYPE", frame_map[request.image_type.value])

    def _read_first_number(self, property_name: str) -> float | None:
        client = self._require_client()
        if client.get_property(self.device_name, property_name) is None:
            return None
        values = client.read_number(self.device_name, property_name)
        if not values:
            return None
        return float(next(iter(values.values())))

    def _read_binning(self) -> tuple[int, int]:
        client = self._require_client()
        if client.get_property(self.device_name, "CCD_BINNING") is None:
            return self.binning
        values = client.read_number(self.device_name, "CCD_BINNING")
        return (int(values.get("HOR_BIN", self.binning[0])), int(values.get("VER_BIN", self.binning[1])))

    def _read_roi(self) -> tuple[int, int, int, int] | None:
        client = self._require_client()
        if client.get_property(self.device_name, "CCD_FRAME") is None:
            return None
        values = client.read_number(self.device_name, "CCD_FRAME")
        return (
            int(values.get("X", 0)),
            int(values.get("Y", 0)),
            int(values.get("WIDTH", 0)),
            int(values.get("HEIGHT", 0)),
        )


class IndiFocuser(IndiDeviceBase):
    def status(self) -> LensStatus:
        if not self.connected:
            return LensStatus(name=self.device_name, connected=False, ready=False, state="offline")
        client = self._require_client()
        position = self._read_position()
        state = client.property_state(self.device_name, "ABS_FOCUS_POSITION")
        moving = state == "busy"
        return LensStatus(
            name=self.device_name,
            connected=True,
            ready=not moving,
            state=state,
            position=position,
            moving=moving,
        )

    def move_absolute(self, position: int):
        client = self._require_client()
        client.set_number(self.device_name, "ABS_FOCUS_POSITION", {"FOCUS_ABSOLUTE_POSITION": position})

    def move_relative(self, delta: int):
        client = self._require_client()
        direction = "FOCUS_INWARD" if delta < 0 else "FOCUS_OUTWARD"
        client.set_switch(self.device_name, "FOCUS_MOTION", direction)
        client.set_number(self.device_name, "REL_FOCUS_POSITION", {"FOCUS_RELATIVE_POSITION": abs(delta)})

    def stop(self):
        if not self.connected:
            return
        client = self._require_client()
        if client.get_property(self.device_name, "FOCUS_ABORT_MOTION") is None:
            return
        try:
            client.set_switch(self.device_name, "FOCUS_ABORT_MOTION", "ABORT")
        except Exception:
            logger.exception("Could not send focuser abort command")

    def _read_position(self) -> int:
        client = self._require_client()
        if client.get_property(self.device_name, "ABS_FOCUS_POSITION") is None:
            return 0
        values = client.read_number(self.device_name, "ABS_FOCUS_POSITION")
        return int(values.get("FOCUS_ABSOLUTE_POSITION", next(iter(values.values()), 0)))
