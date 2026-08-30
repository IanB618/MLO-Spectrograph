
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from astropy import constants as const, units as u

SIM_DIR = Path(__file__).resolve().parent
DATA_DIR = SIM_DIR.parent / "data"

TELESCOPE_DIAMETER = 1.25 * u.m
OBSTRUCTION_DIAMETER = 0.30 * TELESCOPE_DIAMETER
TELESCOPE_AREA = np.pi * (TELESCOPE_DIAMETER**2 - OBSTRUCTION_DIAMETER**2) / 4
FLUX_DENSITY_UNIT = u.erg / u.s / u.cm**2 / u.AA

PALOMAR_EXTINCTION = pd.read_csv(DATA_DIR / "csv files/palomar_atm_ext_per_airmass.csv",
                                 header=None, names=["wav", "ext"])


@dataclass
class ThroughputCurve:
    wavelength: u.Quantity
    throughput: np.ndarray
    name: str = ""
    fill_value: float = 0.0

    def __post_init__(self) -> None:
        self.wavelength = u.Quantity(self.wavelength)
        if self.wavelength.unit == u.dimensionless_unscaled:
            raise u.UnitConversionError("Throughput wavelength values must have units.")

        throughput = u.Quantity(self.throughput)
        self.throughput = throughput.to_value(u.dimensionless_unscaled)
        if self.wavelength.shape != self.throughput.shape:
            raise ValueError("wavelength and throughput must have the same shape.")

    def __call__(self, wavelength: u.Quantity) -> np.ndarray:
        wavelength = u.Quantity(wavelength).to(self.wavelength.unit)
        return np.interp(
            wavelength.value,
            self.wavelength.value,
            self.throughput,
            left=self.fill_value,
            right=self.fill_value,
        )

    @classmethod
    def from_csv(
        cls,
        fname,
        name: str = "",
        fill_value: float = 0.0,
        wavelength_unit: u.UnitBase = u.nm,
    ):
        df = pd.read_csv(fname, header=None, names=["wav", "tx"])
        return cls(
            df["wav"].values * wavelength_unit,
            df["tx"].values,
            name,
            fill_value,
        )


class AtmosphericExtinction(ThroughputCurve):

    def __init__(
        self,
        airmass: float = 1.0,
        name: str = "atmosphere",
        fill_value: float = 0.0,
    ):
        throughput = 10 ** (-0.4 * PALOMAR_EXTINCTION["ext"].values * airmass)
        wavelength = PALOMAR_EXTINCTION["wav"].values * u.nm
        super().__init__(wavelength, throughput, name=name, fill_value=fill_value)


@dataclass
class SpectrographModel:
    central_wavelength: u.Quantity
    dispersion: u.Quantity
    x_center: u.Quantity
    trace_y: u.Quantity

    fiber_count: int = 1
    fiber_pitch_px: u.Quantity = field(
        default_factory=lambda: 0.0 * u.pixel
    )

    spectral_sigma_px: u.Quantity = field(
        default_factory=lambda: 2.03 * u.pixel
    )
    spatial_sigma_px: u.Quantity = field(
        default_factory=lambda: 2.25 * u.pixel
    )
    kernel_radius_sigma: float = 4.0
    render_sampling_px: float = 0.5

    trace_func: Callable[[u.Quantity, u.Quantity], u.Quantity] | None = None

    def __post_init__(self) -> None:
        self.central_wavelength = u.Quantity(self.central_wavelength).to(u.AA)
        self.dispersion = u.Quantity(self.dispersion).to(u.AA / u.pixel)
        self.x_center = u.Quantity(self.x_center).to(u.pixel)
        self.trace_y = u.Quantity(self.trace_y).to(u.pixel)
        self.fiber_pitch_px = u.Quantity(self.fiber_pitch_px).to(u.pixel)
        self.spectral_sigma_px = u.Quantity(self.spectral_sigma_px).to(u.pixel)
        self.spatial_sigma_px = u.Quantity(self.spatial_sigma_px).to(u.pixel)

    def wavelength_to_x(self, wavelength: u.Quantity) -> u.Quantity:
        wavelength = u.Quantity(wavelength).to(self.central_wavelength.unit)
        pixel_offset = (
            (wavelength - self.central_wavelength) / self.dispersion
        ).to(u.pixel)
        return self.x_center - pixel_offset

    def fiber_trace_centers(self) -> u.Quantity:
        offsets = (
            np.arange(self.fiber_count)
            - (self.fiber_count - 1) / 2
        )

        return self.trace_y + offsets * self.fiber_pitch_px

    def wavelength_to_y(
        self,
        wavelength: u.Quantity,
        x: u.Quantity,
        fiber_trace_y: u.Quantity | None = None,
    ) -> u.Quantity:
        if fiber_trace_y is None:
            fiber_trace_y = self.trace_y
        if self.trace_func is None:
            return np.full(x.shape, fiber_trace_y.to_value(u.pixel)) * u.pixel

        return fiber_trace_y + u.Quantity(
            self.trace_func(wavelength, x)
        ).to(u.pixel)


@dataclass
class DetectorModel:
    nx: int
    ny: int

    gain: u.Quantity = field(
        default_factory=lambda: 1.0 * u.electron / u.adu
    )
    read_noise: u.Quantity = field(
        default_factory=lambda: 0.0 * u.electron
    )
    dark_current: u.Quantity = field(
        default_factory=lambda: 0.0 * u.electron / u.s
    )
    bias: u.Quantity = field(
        default_factory=lambda: 0.0 * u.adu
    )
    full_well: u.Quantity | None = None

    def __post_init__(self) -> None:
        self.gain = u.Quantity(self.gain).to(u.electron / u.adu)
        self.read_noise = u.Quantity(self.read_noise).to(u.electron)
        self.dark_current = u.Quantity(self.dark_current).to(u.electron / u.s)
        self.bias = u.Quantity(self.bias).to(u.adu)
        if self.full_well is not None:
            self.full_well = u.Quantity(self.full_well).to(u.electron)

    def apply_noise(
        self,
        image_e: u.Quantity,
        exposure: u.Quantity,
        rng: np.random.Generator,
    ) -> u.Quantity:
        image_e = u.Quantity(image_e).to(u.electron)
        exposure = u.Quantity(exposure).to(u.s)

        expected_e = image_e + self.dark_current * exposure
        expected_values = np.clip(expected_e.to_value(u.electron), 0, None)
        noisy_e = rng.poisson(expected_values).astype(float) * u.electron

        if self.read_noise_e.value > 0:
            noisy_e += (
                rng.normal(
                    0.0,
                    self.read_noise_e.to_value(u.electron),
                    size=noisy_e.shape,
                )
                * u.electron
            )

        if self.full_well_e is not None:
            noisy_e = (
                np.clip(
                    noisy_e.to_value(u.electron),
                    0,
                    self.full_well_e.to_value(u.electron),
                )
                * u.electron
            )

        return (noisy_e / self.gain).to(u.adu) + self.bias


class InstrumentSimulator:
    def __init__(
        self,
        spectrograph: SpectrographModel,
        detector: DetectorModel,
        throughputs: list[ThroughputCurve],
    ) -> None:
        self.spectrograph = spectrograph
        self.detector = detector
        self.throughputs = throughputs

    def combined_throughput(self, wavelength: u.Quantity) -> np.ndarray:
        wavelength = u.Quantity(wavelength)
        throughput = np.ones(wavelength.shape, dtype=float)

        for curve in self.throughputs:
            throughput *= curve(wavelength)

        return throughput

    def render_electrons(
        self,
        wavelength: u.Quantity,
        flux_density: u.Quantity,
        exposure: u.Quantity,
        vignetting=None,
    ) -> u.Quantity:
        wavelength = u.Quantity(wavelength).to(u.AA)
        flux_density = u.Quantity(flux_density).to(FLUX_DENSITY_UNIT)
        exposure = u.Quantity(exposure).to(u.s)

        if wavelength.ndim != 1:
            raise ValueError("wavelength must be a 1D array.")

        if flux_density.ndim == 1:
            if self.spectrograph.fiber_count != 1:
                raise ValueError(
                    "flux_density must have shape (fiber_count, n_wavelength) "
                    "when simulating multiple fibers."
                )
            flux_density = flux_density[np.newaxis, :]
        elif flux_density.ndim != 2:
            raise ValueError(
                "flux_density must be a 1D array for one fiber or a 2D array "
                "with shape (fiber_count, n_wavelength)."
            )

        if flux_density.shape[0] != self.spectrograph.fiber_count:
            raise ValueError(
                "flux_density must contain one spectrum per fiber: "
                f"expected {self.spectrograph.fiber_count}, "
                f"got {flux_density.shape[0]}."
            )

        if wavelength.size != flux_density.shape[1]:
            raise ValueError(
                "wavelength length must match the number of wavelength samples "
                "in each input spectrum."
            )

        order = np.argsort(wavelength.value)
        wavelength = wavelength[order]
        flux_density = flux_density[:, order]

        wavelength, flux_density = self._resample_for_detector(
            wavelength,
            flux_density,
        )

        throughput = self.combined_throughput(wavelength)
        d_wavelength = self._trapezoid_bin_widths(wavelength)
        photon_energy = (const.h * const.c / wavelength).to(u.erg)

        expected_electrons = (
            flux_density
            * TELESCOPE_AREA
            * d_wavelength
            * exposure
            * throughput
            / photon_energy
        ).to_value(u.dimensionless_unscaled) * u.electron

        expected_electrons = (
            np.clip(expected_electrons.to_value(u.electron), 0, None)
            * u.electron
        )

        x_centers = self.spectrograph.wavelength_to_x(wavelength)
        image = np.zeros((self.detector.ny, self.detector.nx), dtype=float) * u.electron

        for fiber_trace_y, fiber_bin_electrons in zip(
            self.spectrograph.fiber_trace_centers(),
            expected_electrons,
        ):
            y_centers = self.spectrograph.wavelength_to_y(
                wavelength,
                x_centers,
                fiber_trace_y,
            )

            self._deposit_gaussian_packets(
                image=image,
                x_centers=x_centers,
                y_centers=y_centers,
                counts=fiber_bin_electrons,
                sigma_x=self.spectrograph.spectral_sigma_px,
                sigma_y=self.spectrograph.spatial_sigma_px,
                radius_sigma=self.spectrograph.kernel_radius_sigma,
            )

        return self._apply_vignetting(image, vignetting)

    def _resample_for_detector(
        self,
        wavelength: u.Quantity,
        flux_density: u.Quantity,
    ) -> tuple[u.Quantity, u.Quantity]:
        if wavelength.size < 2:
            raise ValueError("At least two wavelength samples are required.")

        wavelength_steps = np.diff(wavelength)
        if np.any(wavelength_steps <= 0 * wavelength.unit):
            raise ValueError("wavelength samples must be unique.")

        target_step = (
            abs(self.spectrograph.dispersion)
            * self.spectrograph.render_sampling_px
            * u.pixel
        ).to(wavelength.unit)
        if target_step.value <= 0:
            raise ValueError("render_sampling_px and dispersion must be non-zero.")

        if np.all(wavelength_steps <= target_step):
            return wavelength, flux_density

        span = wavelength[-1] - wavelength[0]
        uniform_count = int(np.ceil((span / target_step).value)) + 1
        uniform_wavelength = (
            np.linspace(
                wavelength[0].value,
                wavelength[-1].value,
                uniform_count,
            )
            * wavelength.unit
        )

        render_wavelength = (
            np.unique(
                np.concatenate(
                    (
                        wavelength.value,
                        uniform_wavelength.value,
                    )
                )
            )
            * wavelength.unit
        )
        render_flux_density = (
            np.vstack([
                np.interp(
                    render_wavelength.value,
                    wavelength.value,
                    spectrum.to_value(FLUX_DENSITY_UNIT),
                )
                for spectrum in flux_density
            ])
            * FLUX_DENSITY_UNIT
        )

        return render_wavelength, render_flux_density

    @staticmethod
    def _trapezoid_bin_widths(wavelength: u.Quantity) -> u.Quantity:
        values = wavelength.value
        widths = np.empty_like(values, dtype=float)
        widths[0] = 0.5 * (values[1] - values[0])
        widths[-1] = 0.5 * (values[-1] - values[-2])
        widths[1:-1] = 0.5 * (values[2:] - values[:-2])
        return widths * wavelength.unit

    def simulate(
        self,
        wavelength: u.Quantity,
        flux_density: u.Quantity,
        exposure: u.Quantity,
        vignetting=None,
        add_noise: bool = True,
        seed: int = None,
    ) -> u.Quantity:
        image_e = self.render_electrons(
            wavelength=wavelength,
            flux_density=flux_density,
            exposure=exposure,
            vignetting=vignetting,
        )

        if not add_noise:
            return image_e

        rng = np.random.default_rng(seed)
        return self.detector.apply_noise(
            image_e=image_e,
            exposure=exposure,
            rng=rng,
        )

    @staticmethod
    def _deposit_gaussian_packets(
        image: u.Quantity,
        x_centers: u.Quantity,
        y_centers: u.Quantity,
        counts: u.Quantity,
        sigma_x: u.Quantity,
        sigma_y: u.Quantity,
        radius_sigma: float,
    ) -> None:
        ny, nx = image.shape
        x_centers = u.Quantity(x_centers).to_value(u.pixel)
        y_centers = u.Quantity(y_centers).to_value(u.pixel)
        sigma_x = u.Quantity(sigma_x).to_value(u.pixel)
        sigma_y = u.Quantity(sigma_y).to_value(u.pixel)

        radius_x = int(np.ceil(radius_sigma * sigma_x))
        radius_y = int(np.ceil(radius_sigma * sigma_y))

        for x0, y0, count in zip(x_centers, y_centers, counts):
            if count.value <= 0:
                continue

            ix0 = int(np.floor(x0))
            iy0 = int(np.floor(y0))

            x_idx_full = np.arange(ix0 - radius_x, ix0 + radius_x + 1)
            y_idx_full = np.arange(iy0 - radius_y, iy0 + radius_y + 1)

            x_weight = np.exp(-0.5 * ((x_idx_full - x0) / sigma_x) ** 2)
            y_weight = np.exp(-0.5 * ((y_idx_full - y0) / sigma_y) ** 2)

            kernel_full = np.outer(y_weight, x_weight)
            kernel_sum = kernel_full.sum()

            if kernel_sum <= 0:
                continue

            x_ok = (x_idx_full >= 0) & (x_idx_full < nx)
            y_ok = (y_idx_full >= 0) & (y_idx_full < ny)

            if not np.any(x_ok) or not np.any(y_ok):
                continue

            x_idx = x_idx_full[x_ok]
            y_idx = y_idx_full[y_ok]
            kernel = kernel_full[np.ix_(y_ok, x_ok)]

            image[np.ix_(y_idx, x_idx)] += count * kernel / kernel_sum

    @staticmethod
    def _apply_vignetting(image: u.Quantity, vignetting) -> u.Quantity:
        if vignetting is None:
            return image

        if callable(vignetting):
            yy, xx = np.indices(image.shape)
            factor = vignetting(yy, xx)
        else:
            factor = vignetting

        factor = u.Quantity(factor).to_value(u.dimensionless_unscaled)
        if factor.shape != image.shape:
            raise ValueError("vignetting must have the same shape as the detector image.")

        return image * np.clip(factor, 0, None)


def f_lambda_to_photon_flux_density(
    wavelength: u.Quantity,
    flux_density: u.Quantity,
    collecting_area: u.Quantity,
) -> u.Quantity:
    wavelength = u.Quantity(wavelength).to(u.AA)
    flux_density = u.Quantity(flux_density).to(FLUX_DENSITY_UNIT)
    collecting_area = u.Quantity(collecting_area).to(u.cm**2)
    photon_energy = (const.h * const.c / wavelength).to(u.erg)

    return (flux_density * collecting_area / photon_energy).to(1 / u.s / u.AA)
