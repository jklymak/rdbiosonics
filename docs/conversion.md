# Converting to netCDF

DT4 is a sequential, run-length-encoded format — there is no way to read part
of a file without decoding it from the start, so none of xarray's lazy
loading, `.sel()`, or dask support applies to it directly. For anything
beyond a quick look — and especially for large multi-day deployments —
**convert once to netCDF** and work from that.

{py:func}`rdbiosonics.dt4_to_netcdf` reads DT4 file(s) and writes a
**compressed, chunked** netCDF that round-trips the full {py:class}`~xarray.DataTree`
(`Beam`, `Environment`, `Platform`, `Vendor_specific`). Pass `flat=True` to
merge everything into a single group-free netCDF instead.

```{note}
Writing netCDF needs the `netcdf4` package: `pip install 'rdbiosonics[netcdf]'`
(already included in the pixi environment).
```

## From Python

```python
from rdbiosonics import dt4_to_netcdf

dt4_to_netcdf("Bark2620260509_110000.dt4")              # -> ...110000.nc
dt4_to_netcdf("in.dt4", "out.nc", dtype="int16")        # half the size
dt4_to_netcdf("in.dt4", "flat.nc", flat=True)           # no groups
```

Convert a whole deployment one file at a time, then open them lazily as a
single dataset:

```python
from pathlib import Path
import xarray as xr

for f in sorted(Path("raw").glob("*.dt4")):
    dt4_to_netcdf(f, Path("nc") / f.with_suffix(".nc").name)

beam = xr.open_mfdataset("nc/*.nc", group="Beam", combine="nested",
                         concat_dim="ping_time")
```

With `flat=True` the files have no groups, so `open_mfdataset` works directly:

```python
for f in sorted(Path("raw").glob("*.dt4")):
    dt4_to_netcdf(f, Path("nc") / f.with_suffix(".nc").name, flat=True)

ds = xr.open_mfdataset("nc/*.nc", combine="nested", concat_dim="ping_time")
```

## From the command line

The package installs a `rdbiosonics-convert` tool:

```bash
# one netCDF per input file, written next to each
rdbiosonics-convert raw/*.dt4

# scan a directory, write into another, int16 storage
rdbiosonics-convert raw/ -o nc/ --dtype int16

# chain split files into a single netCDF
rdbiosonics-convert part1.dt4 part2.dt4 --chain -o combined.nc

# flat netCDF with no groups
rdbiosonics-convert raw/*.dt4 --flat
```

## Storage options

`backscatter` storage `dtype`:

`float32` (default)
: Simple and converter-free on read. The data's precision (a 12-bit
  mantissa) sits comfortably inside float32.

`int16`
: Packed with the CF `scale_factor` / `add_offset` convention — xarray
  unpacks it **automatically** on read, so it is just as convenient as
  float32 but roughly half the size. The quantisation step matches the
  data's intrinsic precision, so it is lossless in practice.

Compression is always on: zlib with the byte-shuffle filter, chunked along
`ping_time`. Tune with `complevel` (1-9) and `ping_chunk`. Below the seabed
the data is all zeros and compresses to almost nothing.

## Reading the result

```python
import xarray as xr

# grouped netCDF
dt = xr.open_datatree("out.nc")          # the full group tree
beam = xr.open_dataset("out.nc", group="Beam")   # just one group

# flat netCDF — plain open_dataset, no group argument needed
ds = xr.open_dataset("flat.nc")
```

Decompression and CF unpacking are automatic — there is never a manual decode
step.
