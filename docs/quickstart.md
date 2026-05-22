# Quickstart

## Reading a file

{py:func}`rdbiosonics.rddtx` takes one path, or a list of paths to chain
files that were split into chunks:

```python
from rdbiosonics import rddtx

dt = rddtx("example_data/Bark2620260509_110000.dt4")

# several files, read sequentially and concatenated
dt = rddtx([
    "example_data/Bark2620260509_110000.dt4",
    "example_data/Bark2620260509_111500.dt4",
])
```

## Decimation

By default pings are grouped in blocks of three and reduced by a median in
time (`numdec=3`). This strongly suppresses interference from other
sounders. Pass `numdec=1` to keep every ping:

```python
dt = rddtx("file.dt4", numdec=1)   # no decimation
```

## The DataTree

The result is an {py:class}`xarray.DataTree` with four groups:

```text
<xarray.DataTree>
Group: /
├── Group: /Beam
│       backscatter   (ping_time, range_sample)   log10 echo counts
│       ping_number   (ping_time)
│       echo_range    (range_sample)              range to sample centre [m]
├── Group: /Environment
│       sound_speed, sound_absorption, temperature, salinity, ...
├── Group: /Platform
│       latitude, longitude, nmea_time            (ping_time)
└── Group: /Vendor_specific
        frequency, pulse_length, threshold, ...    + serial number etc.
```

Access groups and variables with normal xarray syntax:

```python
beam = dt["Beam"]
backscatter = beam["backscatter"]      # 2-D DataArray
depth = beam["echo_range"]             # metres
speed_of_sound = float(dt["Environment"]["sound_speed"])
serial = dt["Vendor_specific"].attrs["serial_number"]
```

## Flat output

Pass `flat=True` to get a single {py:class}`xarray.Dataset` with no groups —
all variables and attributes are merged into one dataset:

```python
ds = rddtx("file.dt4", flat=True)

ds["backscatter"]    # 2-D DataArray
ds["latitude"]       # alongside the beam data
ds["sound_speed"]    # scalar
ds.attrs["serial_number"]
```

This is convenient when the grouped structure is not needed and you want a
simple netCDF file that any tool can read without group-aware support.

## Two time bases

The DT4 format carries two clocks, both exposed on the `ping_time`
coordinate / `Platform` group (or directly on the flat dataset):

`ping_time`
: The internal sounder clock (millisecond resolution). Very regular from
  ping to ping, but can drift in absolute terms.

`nmea_time`
: Time decoded from the GPS NMEA strings and interpolated onto the ping
  times. Correct in absolute terms but noisier (1 s input resolution).

For precise absolute timing, correct `ping_time` against `nmea_time` with a
linear or quadratic drift fit.
