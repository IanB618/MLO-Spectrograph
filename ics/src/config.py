import os
from pathlib import Path

from dotenv import load_dotenv


class Config:
    def __init__(self):
        load_dotenv()
        self.secret_key = os.getenv("ICS_SECRET_KEY", "dev-only-change-me")
        self.host = os.getenv("ICS_HOST", "0.0.0.0")
        self.port = int(os.getenv("ICS_PORT", "5000"))
        self.data_root = Path(os.getenv("ICS_DATA_ROOT", "../data")).resolve()
        self.backend_mode = os.getenv("ICS_BACKEND_MODE", "mock")
        self.site_name = os.getenv("ICS_SITE_NAME", "Spectrograph ICS")

    def flask_config(self):
        return {
            "SECRET_KEY": self.secret_key,
            "ICS_HOST": self.host,
            "ICS_PORT": self.port,
            "ICS_DATA_ROOT": self.data_root,
            "ICS_BACKEND_MODE": self.backend_mode,
            "ICS_SITE_NAME": self.site_name,
        }
