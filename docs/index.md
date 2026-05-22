# rdbiosonics

Read **Biosonics DTX `.DT4`** echosounder files into
[xarray](https://docs.xarray.dev).

`rdbiosonics` is a small, standalone Python port of the MATLAB `rddtx.m`
reader (Rich Pawlowicz, UBC). It decodes the DT4 binary record format —
sounder settings, environment, single-beam pings, internal clock, and GPS
strings — and returns an {py:class}`xarray.DataTree` with groups loosely
following the [echopype](https://echopype.readthedocs.io) /
SONAR-netCDF4 layout.

## Highlights

- Single function: {py:func}`rdbiosonics.rddtx`.
- Reads and chains multiple files; optional in-time **median decimation**
  for suppressing interference from other sounders.
- Faithful to `rddtx.m` — verified against the original to exact equality on
  backscatter, range, and ping number — with two genuine bugs corrected
  (see {doc}`api`).
- Output groups: `Beam`, `Environment`, `Platform`, `Vendor_specific`.

## Installation

Development uses [pixi](https://pixi.sh):

```bash
pixi install        # create the environment
pixi run test       # run the test suite
```

To use the package elsewhere, install it with pip:

```bash
pip install .
```

## At a glance

```python
from rdbiosonics import rddtx

dt = rddtx("example_data/Bark2620260509_110000.dt4")
echogram = dt["Beam"]["backscatter"]   # (ping_time, range_sample)
```

```{toctree}
:maxdepth: 2
:hidden:

quickstart
echogram
api
```
