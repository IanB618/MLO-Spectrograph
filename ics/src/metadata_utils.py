
import json
import subprocess
from pathlib import Path

from astropy.io import fits
from astropy.time import Time

from .models import ExposureRequest

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

def update_fits_metadata(filepath: Path, request: ExposureRequest):
    with fits.open(filepath, mode="update") as f:
        for kw in ["COMMENT", "ROWORDER"]:
            try:
                _ = f[0].header.pop(kw)
            except KeyError:
                pass
        date_obs = Time(f[0].header.get("DATE-OBS"), format="fits")
        f[0].header.set("MJD-OBS", date_obs.mjd, "MJD start of observation", after="DATE-OBS")
        f[0].header.set("TELESCOP", "Claud 1.25-m Telescope")
        camera = f[0].header.get("INSTRUME", None)
        f[0].header.set("INSTRUME", "Fiber-Fed Spectrograph", "Instrument name", after="TELESCOP")
        f[0].header.set("CAMERA", camera, "Camera name", after="INSTRUME")
        f[0].header.set("OBJECT", request.object_name, "Target name", after="CAMERA")
        f[0].header.set("CPU-TEMP", get_cpu_temp(), "[degC] Instrument computer processor temperature", after="CCD-TEMP")
        f[0].header.set("DATE", Time.now().isot, "Time HDU was created/modified")
