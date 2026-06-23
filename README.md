# MLO-Spectrograph
Shared repo for misc. SDSU MLO Spectrograph code

### Exposure Time Calculator (ETC)
Outputs the Signal to Noise Ratio (SNR) at a given exposure time and wavelength bin(s) for an expected spectrum. To use the ETC, navigate to the `ETC` directory and run `python3 ETC.py`. You should see 2 dialog boxes pop up. The following steps will guide you through the UI and features of the ETC.

#### 1. Select spectrum file:
In the small dialog box, click your desired spectrum file and then 'Open' to dismiss the box. The spectrum `SNIa_max_z0p05.txt` is the default spectrum, but any spectrum may be uploaded to the ETC, provided it is a `.txt` file and in a 2-column format (Wavelength should be in units of Angstrom and Flux should be in erg/s/cm2/A (or an equivalent quantity)). Examine the default spectrum file for correct formatting.

#### 2. Choose instrument parameters:
There are 2 grating options and 8 airmass options to choose from the respective dropdown menus which help determine the overall instrument throughput:
- Gratings: Master numbers 1229 (insert link) & 1294 (insert link) from Newport. Grating 1229's throughput curve has been inferrred from an average of the S and P polarization angles.
- Airmass: There are 7 observatory airmass models as well as an average model to choose from. The 7 observatory models were taken from the `specreduce.calibration_data` package (see (link) for more info). The `Average` option is the average of all 7 observatory airmass curves.

When calculating throughput, the `Included Throughput Factors` box allows you to choose which instrument factors contribute to the total instrument throughput. The fiber and detector curves represent the individual components' throughput, like the grating/airmass curves. The lens curve is simply a constant at 0.99.

#### 3. Enter SNR inputs:

#### 4. Output Results
