
import json
import subprocess
from pathlib import Path

from astropy.io import fits
from astropy.time import Time
from astropy.coordinates import EarthLocation, SkyCoord

from .models import ExposureResult, SystemSnapshot

MLO = EarthLocation.of_site("Mount Laguna Observatory")

def get_cpu_temp():
    cmd = ["sensors", "-j"]
    p = subprocess.run(cmd, text=True, capture_output=True)
    if p.returncode:
        return float("nan")
    try:
        result = json.loads(p.stdout)
        temp_c = result["cpu_thermal-virtual-0"]["temp1"]["temp1_input"]
        return temp_c
    except (KeyError, json.JSONDecodeError):
        return float("nan")

def update_fits_metadata(request: ExposureRequest, system_status: SystemSnapshot):
    filepath = system_status.last_exposure.path
    exp_result = system_status.last_exposure
    tcs_status = system_status.tcs
    if not filepath.exists():
        raise FileNotFoundError(filepath.as_posix())

    with fits.open(filepath, mode="update") as f:
        orig_header = f[0].header.copy()
        for kw in ["COMMENT", "ROWORDER"]:
            try:
                _ = f[0].header.pop(kw)
            except KeyError:
                pass

        date_obs = Time(f[0].header.get("DATE-OBS"), format="fits", location=MLO)
        f[0].header.set("MJD-OBS", date_obs.mjd, "MJD start of observation", after="DATE-OBS")
        f[0].header.set("SIDEREAL", date_obs.sidereal_time("mean").to_string(sep=":", precision=1).zfill(10),
                        "Mean sidereal time at start of observation", after="MJD-OBS")

        f[0].header.set("TELESCOP", "Claud 1.25-m Telescope")
        f[0].header.set("LOCATION", "Mt Laguna Observatory", "Observatory name", before="TELESCOP")
        camera = f[0].header.get("INSTRUME", None)
        f[0].header.set("INSTRUME", "Fiber-Fed Spectrograph", "Instrument name", after="TELESCOP")
        f[0].header.set("CAMERA", camera, "Camera name", after="INSTRUME")

        f[0].header.set("OBJECT", request.object_name, "Target name", after="CAMERA")
        f[0].header.set("RA", tcs_status.ra, "Nominal right ascension", after="OBJECT")
        f[0].header.set("DEC", tcs_status.dec, "Nominal declination", after="RA")

        f[0].header.set("BOX-TEMP", None, "[degC] Instrument enclosure ambient temperature", after="CCD-TEMP") # TODO
        f[0].header.set("CPU-TEMP", get_cpu_temp(), "[degC] Instrument computer processor temperature", after="BOX-TEMP")
        f[0].header.set("DATE", Time.now().isot, "Time HDU was created/modified")
