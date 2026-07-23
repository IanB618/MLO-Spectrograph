import numpy as np

from astropy.wcs import WCS
from astropy.wcs.wcsapi import SlicedLowLevelWCS


class LongSlitWCS(SlicedLowLevelWCS):
    """
    Two-pixel-axis long-slit WCS with three world coordinates.

    Pixel axes
    ----------
    x
        Spectral direction.
    y
        Spatial direction along the slit.

    World coordinates
    -----------------
    ra, dec, wavelength

    The underlying serializable FITS WCS contains a dummy cross-slit pixel
    axis. This class slices that axis away for coordinate transformations.
    """

    def __init__(self, parent_wcs):
        self._parent_wcs = parent_wcs

        # NumPy axis order for the parent is (cross_slit, y, x).
        super().__init__(
            parent_wcs,
            (0, slice(None), slice(None)),
        )

    @classmethod
    def from_instrument(
        cls,
        *,
        ra_deg,
        dec_deg,
        position_angle_deg,
        nx=2048,
        ny=2048,
        pixel_size_mm=0.011,
        groove_density_per_mm=300.0,
        collimator_focal_length_mm=180.0,
        camera_focal_length_mm=100.0,
        slit_width_mm=0.105,
        central_wavelength_nm=600.0,
        telescope_focal_length_mm=8125.0,
        incidence_angle_deg=32.0,
        diffraction_order=1,
        reference_pixel=None,
        wavelength_increases_with_x=True,
    ):
        """
        Construct a long-slit WCS from the instrument geometry.

        Parameters
        ----------
        ra_deg, dec_deg : float
            ICRS sky position at the reference pixel.

        position_angle_deg : float
            Slit position angle east of north. Increasing detector y moves
            along this position angle.

        reference_pixel : tuple[float, float] or None
            Zero-based ``(x, y)`` reference pixel. By default, the geometric
            center of the detector is used.

        wavelength_increases_with_x : bool
            Whether wavelength increases toward increasing detector x.
        """
        if reference_pixel is None:
            reference_x = (nx - 1) / 2.0
            reference_y = (ny - 1) / 2.0
        else:
            reference_x, reference_y = reference_pixel

        groove_spacing_mm = 1.0 / groove_density_per_mm
        central_wavelength_mm = central_wavelength_nm * 1e-6

        incidence_angle_rad = np.deg2rad(incidence_angle_deg)

        sin_diffraction_angle = (
            diffraction_order
            * central_wavelength_mm
            / groove_spacing_mm
            - np.sin(incidence_angle_rad)
        )

        if not -1.0 <= sin_diffraction_angle <= 1.0:
            raise ValueError(
                "The requested central wavelength is not physically reachable "
                "for this grating angle and diffraction order."
            )

        diffraction_angle_rad = np.arcsin(sin_diffraction_angle)

        dispersion_mm_per_pixel = (
            groove_spacing_mm
            * np.cos(diffraction_angle_rad)
            / (
                diffraction_order
                * camera_focal_length_mm
            )
            * pixel_size_mm
        )
        dispersion_nm_per_pixel = dispersion_mm_per_pixel * 1e6

        if not wavelength_increases_with_x:
            dispersion_nm_per_pixel *= -1.0

        telescope_plate_scale_arcsec_per_mm = (
            206264.80624709636 / telescope_focal_length_mm
        )

        slit_plane_mm_per_pixel = (
            pixel_size_mm
            * collimator_focal_length_mm
            / camera_focal_length_mm
        )

        spatial_scale_arcsec_per_pixel = (
            telescope_plate_scale_arcsec_per_mm
            * slit_plane_mm_per_pixel
        )

        position_angle_rad = np.deg2rad(position_angle_deg)
        spatial_scale_deg = spatial_scale_arcsec_per_pixel / 3600.0

        # Tangent-plane motion for increasing detector y.
        along_slit_east_deg = (
            spatial_scale_deg * np.sin(position_angle_rad)
        )
        along_slit_north_deg = (
            spatial_scale_deg * np.cos(position_angle_rad)
        )

        # Arbitrary orthogonal dummy direction required to make the
        # underlying celestial FITS WCS nonsingular.
        cross_slit_east_deg = (
            spatial_scale_deg * np.cos(position_angle_rad)
        )
        cross_slit_north_deg = (
            -spatial_scale_deg * np.sin(position_angle_rad)
        )

        parent_wcs = WCS(
            naxis=3,
            preserve_units=True,
        )

        parent_wcs.wcs.ctype = [
            "RA---TAN",
            "DEC--TAN",
            "WAVE",
        ]
        parent_wcs.wcs.cunit = [
            "deg",
            "deg",
            "nm",
        ]
        parent_wcs.wcs.crval = [
            float(ra_deg),
            float(dec_deg),
            float(central_wavelength_nm),
        ]

        # CRPIX follows the one-based FITS convention.
        parent_wcs.wcs.crpix = [
            float(reference_x + 1.0),
            float(reference_y + 1.0),
            1.0,
        ]

        parent_wcs.wcs.cd = np.array(
            [
                [
                    0.0,
                    along_slit_east_deg,
                    cross_slit_east_deg,
                ],
                [
                    0.0,
                    along_slit_north_deg,
                    cross_slit_north_deg,
                ],
                [
                    dispersion_nm_per_pixel,
                    0.0,
                    0.0,
                ],
            ],
            dtype=float,
        )

        parent_wcs.pixel_shape = (nx, ny, 1)
        parent_wcs.array_shape = (1, ny, nx)
        parent_wcs.wcs.set()

        instance = cls(parent_wcs)

        # Retain useful derived instrument parameters.
        anamorphic_factor = (
            np.cos(incidence_angle_rad)
            / np.cos(diffraction_angle_rad)
        )

        instance.nx = nx
        instance.ny = ny
        instance.reference_pixel = (
            reference_x,
            reference_y,
        )
        instance.diffraction_angle_deg = np.rad2deg(
            diffraction_angle_rad
        )
        instance.dispersion_nm_per_pixel = (
            dispersion_nm_per_pixel
        )
        instance.spatial_scale_arcsec_per_pixel = (
            spatial_scale_arcsec_per_pixel
        )
        instance.slit_width_arcsec = (
            slit_width_mm
            * telescope_plate_scale_arcsec_per_mm
        )
        instance.projected_slit_width_pixels = (
            slit_width_mm
            * camera_focal_length_mm
            / collimator_focal_length_mm
            * anamorphic_factor
            / pixel_size_mm
        )

        return instance

    @property
    def parent_wcs(self):
        """The underlying serializable three-dimensional FITS WCS."""
        return self._parent_wcs

    def to_header(self, *args, **kwargs):
        """
        Serialize the underlying three-dimensional FITS WCS.

        The returned header includes the dummy cross-slit axis.
        """
        return self._parent_wcs.to_header(*args, **kwargs)

    def to_fits(self, *args, **kwargs):
        """Serialize the underlying WCS as an HDUList."""
        return self._parent_wcs.to_fits(*args, **kwargs)