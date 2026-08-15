
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.coordinates import EarthLocation, SkyCoord

from .models import ExposureRequest, SystemSnapshot

MLO = EarthLocation(lat=32.841, lon=-116.427, height=1860.)
BAYER_TO_OPENCV_RGB = {
    "RGGB": cv2.COLOR_BAYER_RGGB2RGB,
    "BGGR": cv2.COLOR_BAYER_BGGR2RGB,
    "GRBG": cv2.COLOR_BAYER_GRBG2RGB,
    "GBRG": cv2.COLOR_BAYER_GBRG2RGB,
}


def get_cpu_temp():
    cmd = ["sensors", "-j"]
    p = subprocess.run(cmd, text=True, capture_output=True)
    if p.returncode:
        return None
    try:
        result = json.loads(p.stdout)
        temp_c = result["cpu_thermal-virtual-0"]["temp1"]["temp1_input"]
        return temp_c
    except (KeyError, json.JSONDecodeError):
        return None

def debayer_fits(filepath: Path) -> None:
    with fits.open(filepath, mode="update") as f:
        pattern = str(f[0].header.get("BAYERPAT", "")).upper().strip()
        if pattern not in BAYER_TO_OPENCV_RGB:
            raise ValueError(f"Unsupported or missing BAYERPAT value: {pattern!r}")

        data = np.asarray(f[0].data)
        if data.ndim != 2:
            raise ValueError("Expected a 2D Bayer-matrix image before debayering")

        if np.issubdtype(data.dtype, np.floating):
            finite = np.isfinite(data)
            if not finite.any():
                raise ValueError("Input image does not contain any finite values")
            scale = float(np.nanmax(data[finite])) / 65535.0
            scale = max(scale, 1e-6)
            uint_data = np.clip(np.rint(data / scale), 0, 65535).astype(np.uint16)
        elif np.nanmax(data) > 65535 or np.nanmin(data) < 0:
            raise TypeError("Cannot handle int values that fall outside uint16 range")
        else:
            scale = 1.0
            uint_data = data.astype(np.uint16, copy=False)

        debayered = cv2.cvtColor(np.ascontiguousarray(uint_data), BAYER_TO_OPENCV_RGB[pattern])
        greyscale = np.mean(debayered, axis=-1)
        assert greyscale.shape == data.shape
        if np.issubdtype(data.dtype, np.integer):
            greyscale = np.round(greyscale)
        f[0].data = greyscale.astype(data.dtype)
        for kw in ["BAYERPAT", "XBAYROFF", "YBAYROFF"]:
            if kw in f[0].header:
                _ = f[0].header.pop(kw)

def update_fits_metadata(request: ExposureRequest, system_status: SystemSnapshot):
    filepath = system_status.last_exposure.path
    exp_result = system_status.last_exposure
    tcs_status = system_status.tcs
    stages = system_status.axes
    if not filepath.exists():
        raise FileNotFoundError(filepath.as_posix())

    orig_header = fits.getheader(filepath).copy()
    if "BAYERPAT" in orig_header and "light" in orig_header.get("IMAGETYP", "").lower():
        debayer_fits(filepath)

    with fits.open(filepath, mode="update") as f:
        for kw in ["COMMENT", "ROWORDER", "FOCUSTEM", "FOCUSPOS"]:
            try:
                _ = f[0].header.pop(kw)
            except KeyError:
                pass
            f[0].header.set("BSCALE", f[0].header.get("BSCALE", 1), after="EXTEND")
            if "BZERO" in f[0].header: # BZERO should come before BSCALE if present
                f[0].header.set("BZERO", after="EXTEND")

        f[0].header.set("ORIGIN", "SDSU", "Responsible/originating institution", after="BSCALE")
        f[0].header.set("LOCATION", "Mt Laguna Observatory", "Observatory name", after="ORIGIN")
        f[0].header.set("LATITUDE", round(MLO.lat.deg, 3), "[deg] Location latitude", after="LOCATION")
        f[0].header.set("LONGITUD", round(MLO.lon.deg, 3), "[deg] Location longitude", after="LATITUDE")
        f[0].header.set("TELESCOP", "Claud 1.25-m Telescope", "Telescope name", after="LONGITUD")
        camera = system_status.science_camera.name or f[0].header.get("INSTRUME", None)
        if "SBIG" in camera:
            f[0].data = f[0].data[:, ::-1] # X is flipped for SBIG camera
        f[0].header.set("INSTRUME", "Fiber-Fed Spectrograph", "Instrument name", after="TELESCOP")
        f[0].header.set("CAMERA", camera, "Camera name (from INDI)", after="INSTRUME")
        f[0].header.set("FILTER", "ThorLabs FGL400S", "Filter in use", after="CAMERA") # TODO: make configurable
        f[0].header.set("GRATING", "Newport 270R", "Grating in use", after="FILTER") # TODO: make configurable

        f[0].header.set("OBJECT", request.object_name, "Target name", after="GRATING")
        f[0].header.set("RA", tcs_status.ra_str, "[deg] Nominal right ascension", after="OBJECT")
        f[0].header.set("DEC", tcs_status.dec_str, "[deg] Nominal declination", after="RA")
        airmass = round(tcs_status.airmass, 3) if tcs_status.airmass is not None else None
        f[0].header.set("AIRMASS", airmass, "Airmass at end of observation", after="DEC")
        for axis in stages:
            f[0].header.set(axis.name.replace("_", "").upper().replace("FOCUS", "Z"), axis.position,
                            f"{axis.name.split('_')[1].capitalize()} stage position")
        f[0].header.set("STAGEX", after="DEC")
        f[0].header.set("STAGEY", after="STAGEX")
        f[0].header.set("STAGEZ", after="STAGEY")
        f[0].header.set("CAMFOCUS", system_status.lens.position, "Camera lens focus position", after="STAGEZ")
        f[0].header.set("CAMAPER", system_status.lens.aperture, "Camera lens aperture setting (f/)", after="CAMFOCUS")
        f[0].header.set("TELFOCUS", None, "Telescope focus position", before="CAMFOCUS") # TODO: tcs_status.focus_position

        date_obs = Time(f[0].header.get("DATE-OBS"), format="fits", location=MLO)
        f[0].header.set("MJD-OBS", round(date_obs.mjd, 6), "MJD start of observation", after="DATE-OBS")
        f[0].header.set("SIDEREAL", date_obs.sidereal_time("mean").to_string(sep=":", precision=1).zfill(10),
                        "Mean sidereal time at start of observation", after="MJD-OBS")
        f[0].header.comments["EXPTIME"] = "[s] Exposure duration"

        f[0].header.set("BOX-TEMP", None, "[degC] Instrument enclosure ambient temperature", after="CCD-TEMP") # TODO
        f[0].header.set("CPU-TEMP", get_cpu_temp(), "[degC] Instrument computer processor temperature", after="BOX-TEMP")
        f[0].header.set("TECPOWER", round(system_status.science_camera.cooler_power_pct, 1), "[%] Thermoelectric cooler power", after="CCD-TEMP")
        f[0].header.set("GAINMODE", system_status.science_camera.gain_mode, "Gain mode")#, after="GAIN")

        now = Time.now()
        f[0].header.set("DATE", now.isot, "Time HDU was created/modified")
        f[0].add_checksum(when="Checksum computed at " + now.datetime.isoformat(timespec="seconds") + "Z")
