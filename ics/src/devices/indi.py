class IndiClientPlaceholder:
    """Placeholder boundary for future INDI client integration.

    Intended uses:
    - FLI Kepler INDI driver as an initial science-camera backend
    - Pinefeat Canon EF lens controller
    - Acquisition camera, if the selected camera has a stable driver

    Keep all INDI property names and XML protocol details in this module or in
    backend-specific modules, not in the supervisor or UI.
    """

    def __init__(self, host: str = "localhost", port: int = 7624):
        self.host = host
        self.port = port

    def connect(self):
        raise NotImplementedError("Implement INDI connection here")

    def get_property(self, device_name: str, property_name: str):
        raise NotImplementedError("Implement INDI property read here")

    def set_property(self, device_name: str, property_name: str, values: dict):
        raise NotImplementedError("Implement INDI property write here")
