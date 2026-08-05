# MLO Spectrograph

Shared repo for [SDSU MLO](https://astronomy.sdsu.edu/mount-laguna-observatory-facilities/) Spectrograph code.

### Contents

- [`data/`](./data): supporting files such as reference spectra and throughput/response data
- [`etc/`](./etc): Exposure time calculator; computes SNR given exposure time or vice versa, given an input signal and instrument response information
- [`ics/`](./ics): Instrument control software; web app for controlling the instrument during observing operations
- [`sim/`](./sim): Instrument simulator; generates semi-realistic data products from an input spectrum and instrument response information
