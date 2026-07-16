import os
from pathlib import Path

from dotenv import load_dotenv


class Config:
    def __init__(self):
        load_dotenv()
        self.secret_key = os.getenv("ICS_SECRET_KEY", "dev-only-change-me")
        self.host = os.getenv("ICS_HOST", "0.0.0.0")
        self.port = int(os.getenv("ICS_PORT", "5000"))
        self.data_root = Path(os.getenv("ICS_DATA_ROOT", "./data")).resolve()
        self.backend_mode = os.getenv("ICS_BACKEND_MODE", "mock")
        self.site_name = os.getenv("ICS_SITE_NAME", "Spectrograph ICS")
        self.indi_host = os.getenv("ICS_INDI_HOST", "127.0.0.1")
        self.indi_port = int(os.getenv("ICS_INDI_PORT", "7624"))
        self.indi_ccd_device = os.getenv("ICS_INDI_CCD_DEVICE", "FLI Kepler")
        self.indi_focuser_device = os.getenv("ICS_INDI_FOCUSER_DEVICE", "Pinefeat Lens Controller")
        self.indi_blob_property = os.getenv("ICS_INDI_CCD_BLOB_PROPERTY", "CCD1")
        self.indi_connect_timeout_s = float(os.getenv("ICS_INDI_CONNECT_TIMEOUT_S", "10"))
        self.indi_command_timeout_s = float(os.getenv("ICS_INDI_COMMAND_TIMEOUT_S", "30"))

    def flask_config(self):
        return {
            "SECRET_KEY": self.secret_key,
            "ICS_HOST": self.host,
            "ICS_PORT": self.port,
            "ICS_DATA_ROOT": self.data_root,
            "ICS_BACKEND_MODE": self.backend_mode,
            "ICS_SITE_NAME": self.site_name,
            "ICS_INDI_HOST": self.indi_host,
            "ICS_INDI_PORT": self.indi_port,
            "ICS_INDI_CCD_DEVICE": self.indi_ccd_device,
            "ICS_INDI_FOCUSER_DEVICE": self.indi_focuser_device,
            "ICS_INDI_CCD_BLOB_PROPERTY": self.indi_blob_property,
            "ICS_INDI_CONNECT_TIMEOUT_S": self.indi_connect_timeout_s,
            "ICS_INDI_COMMAND_TIMEOUT_S": self.indi_command_timeout_s,
        }
