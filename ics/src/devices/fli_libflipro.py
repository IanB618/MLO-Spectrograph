class LibfliproKeplerPlaceholder:
    """Placeholder boundary for a direct libflipro backend.

    This backend should be implemented as either:
    - a C++ service that exposes a local HTTP/gRPC API, or
    - a small Python extension/ctypes wrapper if stability is acceptable.

    Keep this behind the same ScienceCameraBackend interface used by the INDI
    backend so the supervisor and UI do not change if you switch approaches.
    """

    def connect(self):
        raise NotImplementedError("Implement direct libflipro camera open here")
