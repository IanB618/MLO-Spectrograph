from pathlib import Path

import numpy as np
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
from astropy.io import fits
from astropy.time import Time
from astropy import units as u

from src.models import AxisStatus, CameraStatus, TcsStatus
from src.sim.simulator import ThroughputCurve, DetectorModel, SpectrographModel, InstrumentSimulator

MLO = EarthLocation(lat=32.841*u.deg, lon=-116.427*u.deg, height=1860*u.m)

REPO_ROOT = Path(__file__).resolve().parents[3]
CSV_DIR = REPO_ROOT / "data" / "csv files"


def build_default_simulator() -> InstrumentSimulator:
    fiber_wav, fiber_att = np.loadtxt(CSV_DIR / "fiber_attenuation.csv", delimiter=",").T
    fiber_tx = 10 ** (-(fiber_att * (10. / 1000.)) / 10)
    fiber = ThroughputCurve(fiber_wav * 10, fiber_tx, name="fiber")

    misc_losses = ThroughputCurve(wavelength=np.array([3000, 10500]), throughput=np.array([0.94, 0.94]), name="misc.")
    collimator = ThroughputCurve.from_csv(CSV_DIR / "thorlabs_ar_coating.csv", name="collimator")
    filt = ThroughputCurve.from_csv(CSV_DIR / "FGL400S_transmission.csv", name="longpass filter")
    grating = ThroughputCurve.from_csv(CSV_DIR / "master 1294 unpolarized.csv", name="grating")
    qe = ThroughputCurve.from_csv(CSV_DIR / "gsense400bsi_qe.csv", name="detector QE")
    window = ThroughputCurve.from_csv(CSV_DIR / "F101_coating.csv", name="detector window")

    detector = DetectorModel(
        nx=2048, ny=2048,
        gain_e_per_adu=0.478,
        read_noise_e=1.6,
        dark_current_e_per_s=0.4,
        bias_adu=200.0,
        full_well_e=90000.0,
    )

    spectrograph = SpectrographModel(
        central_wavelength=6263.304,
        dispersion=3.4346,
        x_center=(detector.nx - 1) / 2,
        trace_y=(detector.ny - 1) / 2,
        spectral_sigma_px=2.03,
        spatial_sigma_px=2.25,
        kernel_radius_sigma=4.0,
    )

    return InstrumentSimulator(
        spectrograph=spectrograph,
        detector=detector,
        throughputs=[fiber, misc_losses, collimator, filt, grating, window, qe],
    )


class MockAcquisitionCamera:
    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.connected = False
        self.last_preview_path = ""
        self.simulator = build_default_simulator()

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def status(self) -> CameraStatus:
        return CameraStatus(
            name="Guide Camera / Acquisition",
            connected=self.connected,
            ready=self.connected,
            state="mock",
            temperature_c=None,
            exposing=False,
            binning=(1, 1),
            roi=(0, 0, 1280, 960),
        )

    def capture_preview(self, exposure_s: float = 0.2) -> str:
        wave = np.linspace(3800, 9400, 2000)
        flux = np.full_like(wave, 1e-16)

        image_adu = self.simulator.simulate(
            wavelength=wave,
            flux_density=flux,
            exposure_s=exposure_s,
            add_noise=True,
        )
        image_adu = np.round(image_adu).astype(np.uint16)

        preview_dir = self.data_root / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        path = preview_dir / "latest_guide_preview.fits"
        fits.writeto(path, image_adu, overwrite=True)
        self.last_preview_path = str(path)
        return self.last_preview_path


class MockMotionController:
    def __init__(self):
        self.connected = False
        self._axes = {
            "stage_x": AxisStatus(name="stage_x", units="steps", min_limit=-50000, max_limit=50000),
            "stage_y": AxisStatus(name="stage_y", units="steps", min_limit=-50000, max_limit=50000),
            "stage_focus": AxisStatus(name="stage_focus", units="steps", min_limit=-20000, max_limit=20000),
        }

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def axes(self) -> list[AxisStatus]:
        return list(self._axes.values())

    def home(self, axis: str):
        status = self._get_axis(axis)
        status.moving = True
        status.position = 0.0
        status.homed = True
        status.moving = False

    def move_absolute(self, axis: str, position: float):
        status = self._get_axis(axis)
        if status.min_limit is not None and position < status.min_limit:
            raise ValueError(f"{axis} move below minimum limit")
        if status.max_limit is not None and position > status.max_limit:
            raise ValueError(f"{axis} move above maximum limit")
        status.moving = True
        status.position = position
        status.moving = False

    def move_relative(self, axis: str, delta: float):
        status = self._get_axis(axis)
        self.move_absolute(axis, status.position + delta)

    def stop(self, axis: str | None = None):
        if axis:
            self._get_axis(axis).moving = False
            return
        for status in self._axes.values():
            status.moving = False

    def _get_axis(self, axis: str) -> AxisStatus:
        if axis not in self._axes:
            raise KeyError(f"Unknown axis: {axis}")
        return self._axes[axis]


class MockTcs:
    def __init__(self):
        self.connected = False
        self.east_offset_arcsec = 0.0
        self.north_offset_arcsec = 0.0
        self.ra_deg = 188.73625
        self.dec_deg = 12.58222

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def skycoord(self) -> SkyCoord:
        return SkyCoord(ra=self.ra_deg, dec=self.dec_deg,
                        unit="deg", frame="icrs")

    def get_altaz(self, obstime: Time | None = None, location: EarthLocation = MLO):
        if obstime is None:
            obstime = Time.now()
        elif not isinstance(obstime, Time):
            obstime = Time(obstime)
        altaz_frame = AltAz(obstime=obstime, location=location)
        altaz = self.skycoord().transform_to(altaz_frame)
        return altaz.alt, altaz.az

    def get_airmass(self, obstime: Time | None = None, location: EarthLocation = MLO) -> float:
        if obstime is None:
            obstime = Time.now()
        elif not isinstance(obstime, Time):
            obstime = Time(obstime)
        altaz_frame = AltAz(obstime=obstime, location=location)
        altaz = self.skycoord().transform_to(altaz_frame)
        if altaz.alt.deg < 0:
            return float("inf")
        return float(altaz.secz)

    def radec_str(self) -> tuple[str]:
        return self.skycoord.to_string("hmsdms")

    def status(self) -> TcsStatus:
        alt, az = self.get_altaz()
        airmass = self.get_airmass()
        return TcsStatus(
            name="ACE TCS Adapter",
            connected=self.connected,
            ready=self.connected,
            state="mock",
            target_name="Mock Target",
            ra=self.ra_deg,
            dec=self.dec_deg,
            altitude_deg=float(alt.to("deg").value),
            azimuth_deg=float(az.to("deg").value),
            airmass=airmass,
            tracking=self.connected,
            guiding=False,
        )

    def go_to_j2000(self, ra_deg: float, dec_deg: float):
        self.ra_deg = float(ra_deg)
        self.dec_deg = float(dec_deg)
        return {
            "ra_deg": self.ra_deg,
            "dec_deg": self.dec_deg,
            "message": "Mock telescope slew requested",
        }

    def offset(self, east_arcsec: float, north_arcsec: float):
        self.east_offset_arcsec += east_arcsec
        self.north_offset_arcsec += north_arcsec
        self.ra_deg += east_arcsec / 3600.0
        self.dec_deg += north_arcsec / 3600.0
        return {
            "east_offset_arcsec": self.east_offset_arcsec,
            "north_offset_arcsec": self.north_offset_arcsec,
            "commanded_ra_deg": self.ra_deg,
            "commanded_dec_deg": self.dec_deg,
            "method": "mock linear offset",
        }
