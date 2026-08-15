
from pathlib import Path
from astropy.io import fits
from astropy.time import Time
from astropy.table import Table

def read_snifs_spectrum(filepath: Path) -> fits.BinTableHDU:
    data = Table.read(filepath, format="ascii.commented_header", names=["wl", "fl", "err"])
    data["wl"].unit = "Angstrom"
    data["fl"].unit = data["err"].unit = "erg/s/cm2/Angstrom"
    hdu = fits.BinTableHDU(data=data, name="SPECTRUM")
    with open(filepath, "r") as f:
        for line in f:
            if line.startswith("#"):
                try:
                    key, val = line.lstrip("#").strip().split("=", 1)
                except:
                    continue
                hdu.header[key.replace("FLUXCAL_", "CAL")[:8]] = val.strip()
    for kw in ["EXPTIME", "AIRMASS", "MJD-OBS"]:
        if kw in hdu.header:
            hdu.header[kw] = float(hdu.header[kw].rstrip("s"))
    return hdu
