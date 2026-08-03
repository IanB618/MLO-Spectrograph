
import json
import subprocess
from pathlib import Path

from astropy.io import fits
from astropy.time import Time
from astropy.coordinates import EarthLocation, SkyCoord

from .models import ExposureRequest, SystemSnapshot

MLO = EarthLocation(lat=32.841, lon=-116.427, height=1860.)

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

def update_fits_metadata(request: ExposureRequest, system_status: SystemSnapshot):
    filepath = system_status.last_exposure.path
    exp_result = system_status.last_exposure
    tcs_status = system_status.tcs
    stages = system_status.axes
    if not filepath.exists():
        raise FileNotFoundError(filepath.as_posix())

    with fits.open(filepath, mode="update") as f:
        orig_header = f[0].header.copy()
        for kw in ["COMMENT", "ROWORDER", "FOCUSTEM"]:
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
        camera = f[0].header.get("INSTRUME", None)
        f[0].header.set("INSTRUME", "Fiber-Fed Spectrograph", "Instrument name", after="TELESCOP")
        f[0].header.set("CAMERA", camera, "Camera name (from INDI)", after="INSTRUME")
        f[0].header.set("FILTER", "ThorLabs FGL400S", "ID of filter in use", after="CAMERA") # TODO
        f[0].header.set("GRATING", "Newport 270R", "ID of grating in use", after="FILTER") # TODO

        f[0].header.set("OBJECT", request.object_name, "Target name", after="GRATING")
        f[0].header.set("RA", tcs_status.ra, "[deg] Nominal right ascension", after="OBJECT")
        f[0].header.set("DEC", tcs_status.dec, "[deg] Nominal declination", after="RA")
        f[0].header.set("AIRMASS", tcs_status.airmass, "Airmass at end of observation", after="DEC")
        for axis in stages:
            f[0].header.set(axis.name.replace("_", "").upper().replace("FOCUS", "Z"), axis.position,
                            f"{axis.name.split('_')[1].capitalize()} stage position")
        f[0].header.set("STAGEX", after="DEC")
        f[0].header.set("STAGEY", after="STAGEX")
        f[0].header.set("STAGEZ", after="STAGEY")
        f[0].header.rename_keyword("FOCUSPOS", "CAMFOCUS")
        f[0].header.set("TELFOCUS", None, "Telescope focus position", before="CAMFOCUS") # TODO: tcs_status.focus_position

        date_obs = Time(f[0].header.get("DATE-OBS"), format="fits", location=MLO)
        f[0].header.set("MJD-OBS", round(date_obs.mjd, 6), "MJD start of observation", after="DATE-OBS")
        f[0].header.set("SIDEREAL", date_obs.sidereal_time("mean").to_string(sep=":", precision=1).zfill(10),
                        "Mean sidereal time at start of observation", after="MJD-OBS")

        f[0].header.set("BOX-TEMP", None, "[degC] Instrument enclosure ambient temperature", after="CCD-TEMP") # TODO
        f[0].header.set("CPU-TEMP", get_cpu_temp(), "[degC] Instrument computer processor temperature", after="BOX-TEMP")
        f[0].header.set("TECPOWER", system_status.science_camera.cooler_power_pct, "[%] Thermoelectric cooler power", after="CCD-TEMP")
        f[0].header.set("DATE", Time.now().isot, "Time HDU was created/modified")
        f[0].add_checksum()
