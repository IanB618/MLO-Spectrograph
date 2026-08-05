from pathlib import Path
from types import SimpleNamespace

from src.models import (
    CameraStatus,
    ExposureRequest,
    ExposureResult,
    ExposureType,
    LensStatus,
    SystemState,
    TcsStatus,
)
from src.supervisor import InstrumentSupervisor


class FakeScienceCamera:
    def __init__(self, result):
        self.result = result

    def expose(self, request):
        return self.result

    def status(self):
        return CameraStatus(name="Science", connected=True, ready=True)


class FakeAcquisitionCamera:
    def status(self):
        return CameraStatus(name="Guide", connected=True, ready=True)


class FakeLens:
    def status(self):
        return LensStatus(name="Lens", connected=True, ready=True)


class FakeTcs:
    def status(self):
        return TcsStatus(name="TCS", connected=True, ready=True)


class FakeMotion:
    def axes(self):
        return []


class InspectingDataManager:
    def __init__(self):
        self.supervisor = None
        self.processed_snapshot = None
        self.logged = False

    def process_exposure(self, request, result, snapshot):
        assert self.supervisor.latest_exposure() is None
        assert snapshot.last_exposure.exposure_id == result.exposure_id
        assert self.supervisor.state == SystemState.EXPOSING
        self.processed_snapshot = snapshot

    def log_exposure(self, request, result, snapshot):
        self.logged = True


def test_exposure_is_published_only_after_fits_post_processing(tmp_path):
    result = ExposureResult(
        exposure_id="exp-new",
        image_type=ExposureType.LIGHT,
        exposure_s=0.1,
        path=Path(tmp_path / "exp-new.fits"),
        success=True,
        message="Exposure complete",
    )
    result.path.write_bytes(b"FITS")
    data_manager = InspectingDataManager()
    devices = SimpleNamespace(
        science_camera=FakeScienceCamera(result),
        acquisition_camera=FakeAcquisitionCamera(),
        lens=FakeLens(),
        tcs=FakeTcs(),
        motion=FakeMotion(),
    )
    supervisor = InstrumentSupervisor(devices, data_manager)
    data_manager.supervisor = supervisor
    supervisor.state = SystemState.IDLE

    returned = supervisor.take_exposure(
        ExposureRequest(
            exposure_s=0.1,
            image_type=ExposureType.LIGHT,
            object_name="Test",
            binning="1x1",
        )
    )

    assert returned.exposure_id == "exp-new"
    assert supervisor.latest_exposure().exposure_id == "exp-new"
    assert supervisor.state == SystemState.IDLE
    assert data_manager.processed_snapshot is not None
    assert data_manager.logged is True
