from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


H_ERG_S = 6.62607015e-27
C_CM_S = 2.99792458e10

TELESCOPE_DIAMETER_CM = 125.0
OBSTRUCTION_DIAMETER_CM = 0.30 * TELESCOPE_DIAMETER_CM

TELESCOPE_AREA_CM2 = np.pi*(TELESCOPE_DIAMETER_CM**2 - OBSTRUCTION_DIAMETER_CM**2)/4


@dataclass
class ThroughputCurve:
    wavelength: np.ndarray
    throughput: np.ndarray
    name: str = ""
    fill_value: float = 0.0

    def __call__(self, wavelength: np.array) -> np.ndarray:
        return np.interp(
            wavelength,
            self.wavelength,
            self.throughput,
            left=self.fill_value,
            right=self.fill_value,
        )

    @classmethod
    def from_csv(cls, fname, name = "", fill_value = 0.):
        df = pd.read_csv(fname, header=None, names=["wav", "tx"])
        return cls(df["wav"].values*10, df["tx"].values, name, fill_value)


@dataclass
class SpectrographModel:
    central_wavelength: float
    dispersion: float
    x_center: float
    trace_y: float

    spectral_sigma_px: float = 0.7
    spatial_sigma_px: float = 1.5
    kernel_radius_sigma: float = 4.0

    trace_func: Optional[Callable[[np.ndarray, np.ndarray], np.ndarray]] = None

    def wavelength_to_x(self, wavelength: np.ndarray) -> np.ndarray:
        return self.x_center + (wavelength - self.central_wavelength) / self.dispersion

    def wavelength_to_y(self, wavelength: np.ndarray, x: np.ndarray) -> np.ndarray:
        if self.trace_func is None:
            return np.full_like(x, self.trace_y, dtype=float)

        return self.trace_func(wavelength, x)


@dataclass
class DetectorModel:
    nx: int
    ny: int

    gain_e_per_adu: float = 1.0
    read_noise_e: float = 0.0
    dark_current_e_per_s: float = 0.0
    bias_adu: float = 0.0
    full_well_e: Optional[float] = None

    def apply_noise(
        self,
        image_e: np.ndarray,
        exposure_s: float,
        rng: np.random.Generator,
    ) -> np.ndarray:
        noisy_e = image_e.copy()

        if self.dark_current_e_per_s > 0:
            noisy_e += self.dark_current_e_per_s * exposure_s

        noisy_e = rng.poisson(np.clip(noisy_e, 0, None)).astype(float)

        if self.read_noise_e > 0:
            noisy_e += rng.normal(0.0, self.read_noise_e, size=noisy_e.shape)

        if self.full_well_e is not None:
            noisy_e = np.clip(noisy_e, 0, self.full_well_e)

        image_adu = noisy_e / self.gain_e_per_adu + self.bias_adu
        return image_adu


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

    def combined_throughput(self, wavelength: np.ndarray) -> np.ndarray:
        throughput = np.ones_like(wavelength, dtype=float)

        for curve in self.throughputs:
            throughput *= curve(wavelength)

        return throughput

    def render_electrons(
        self,
        wavelength: np.ndarray,
        flux_density: np.ndarray,
        exposure_s: float,
        vignetting=None,
    ) -> np.ndarray:
        wavelength = np.asarray(wavelength, dtype=float)
        flux_density = np.asarray(flux_density, dtype=float)

        if wavelength.ndim != 1 or flux_density.ndim != 1:
            raise ValueError("wavelength and flux_density must be 1D arrays.")

        if wavelength.size != flux_density.size:
            raise ValueError("wavelength and flux_density must have the same length.")

        order = np.argsort(wavelength)
        wavelength = wavelength[order]
        flux_density = flux_density[order]

        throughput = self.combined_throughput(wavelength)

        d_wavelength = np.abs(np.gradient(wavelength))

        wavelength_cm = wavelength * 1e-8
        photon_energy_erg = H_ERG_S * C_CM_S / wavelength_cm

        photon_flux_density = flux_density / photon_energy_erg

        bin_electrons = (
            photon_flux_density
            * TELESCOPE_AREA_CM2
            * d_wavelength
            * exposure_s
            * throughput
        )

        bin_electrons = np.clip(bin_electrons, 0, None)

        x_centers = self.spectrograph.wavelength_to_x(wavelength)
        y_centers = self.spectrograph.wavelength_to_y(wavelength, x_centers)

        image = np.zeros((self.detector.ny, self.detector.nx), dtype=float)

        self._deposit_gaussian_packets(
            image=image,
            x_centers=x_centers,
            y_centers=y_centers,
            counts=bin_electrons,
            sigma_x=self.spectrograph.spectral_sigma_px,
            sigma_y=self.spectrograph.spatial_sigma_px,
            radius_sigma=self.spectrograph.kernel_radius_sigma,
        )

        image = self._apply_vignetting(image, vignetting)
        return image

    def simulate(
        self,
        wavelength: np.ndarray,
        flux_density: np.ndarray,
        exposure_s: float,
        vignetting=None,
        add_noise: bool = True,
        seed: Optional[int] = None,
    ) -> np.ndarray:
        image_e = self.render_electrons(
            wavelength=wavelength,
            flux_density=flux_density,
            exposure_s=exposure_s,
            vignetting=vignetting,
        )

        if not add_noise:
            return image_e

        rng = np.random.default_rng(seed)
        return self.detector.apply_noise(
            image_e=image_e,
            exposure_s=exposure_s,
            rng=rng,
        )

    @staticmethod
    def _deposit_gaussian_packets(
        image: np.ndarray,
        x_centers: np.ndarray,
        y_centers: np.ndarray,
        counts: np.ndarray,
        sigma_x: float,
        sigma_y: float,
        radius_sigma: float,
    ) -> None:
        ny, nx = image.shape

        radius_x = int(np.ceil(radius_sigma * sigma_x))
        radius_y = int(np.ceil(radius_sigma * sigma_y))

        for x0, y0, count in zip(x_centers, y_centers, counts):
            if count <= 0:
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
    def _apply_vignetting(image: np.ndarray, vignetting) -> np.ndarray:
        if vignetting is None:
            return image

        if callable(vignetting):
            yy, xx = np.indices(image.shape)
            factor = vignetting(yy, xx)
        else:
            factor = np.asarray(vignetting, dtype=float)

        if factor.shape != image.shape:
            raise ValueError("vignetting must have the same shape as the detector image.")

        return image * np.clip(factor, 0, None)


def f_lambda_to_photon_flux_density(
    wavelength_angstrom: np.ndarray,
    f_lambda_erg_s_cm2_angstrom: np.ndarray,
    collecting_area_cm2: float,
) -> np.ndarray:

    wavelength_cm = wavelength_angstrom * 1e-8
    photon_energy_erg = H_ERG_S * C_CM_S / wavelength_cm

    return (
        f_lambda_erg_s_cm2_angstrom
        * collecting_area_cm2
        / photon_energy_erg
    )
