class AceTcsPlaceholder:
    """Placeholder for ACE TCS integration.

    Start with read-only telescope status and small offset requests. Do not put
    full slew authority here until the operational boundary with ACE is clear.
    """

    def connect(self):
        raise NotImplementedError("Implement ACE TCS connection here")

    def get_status(self):
        raise NotImplementedError("Implement ACE TCS status readback here")

    def offset(self, east_arcsec: float, north_arcsec: float):
        raise NotImplementedError("Implement small telescope offset here")
