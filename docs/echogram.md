# Plotting an echogram

An *echogram* is the standard view of echosounder data: ping time on the x
axis, range (depth) on the y axis, and backscatter strength as colour.

Because `backscatter` is a labelled 2-D {py:class}`xarray.DataArray`, a basic
echogram is one line of xarray plotting. The snippet below builds a slightly
nicer one with matplotlib directly — depth increasing downward, percentile
colour limits, and a labelled title.

```python
import matplotlib.pyplot as plt
import numpy as np

from rdbiosonics import rddtx

dt = rddtx("example_data/Bark2620260509_110000.dt4")
beam = dt["Beam"]

backscatter = beam["backscatter"].values     # (ping_time, range_sample)
time = beam["ping_time"].values
rng = beam["echo_range"].values              # metres

fig, ax = plt.subplots(figsize=(12, 5), layout="constrained")
mesh = ax.pcolormesh(
    time, rng, backscatter.T,                # colour data is (y, x)
    shading="nearest", cmap="viridis", rasterized=True,
    vmin=np.nanpercentile(backscatter, 5),
    vmax=np.nanpercentile(backscatter, 99),
)
ax.invert_yaxis()                            # depth increases downward
ax.set_xlabel("Ping time (internal sounder clock)")
ax.set_ylabel("Range (m)")
fig.colorbar(mesh, ax=ax, label="Backscatter  [log10 echo counts]")
fig.savefig("echogram.png", dpi=150)
```

The result for one of the example files:

![Echogram of a Biosonics DTX DT4 file](_static/echogram.png)

The bright band at the surface, the scattering layers through the water
column, and the sharp seabed echo near 140 m are all clearly visible; below
the bottom the signal is dead (dark).

## Reusable helper and command line

The repository ships `examples/plot_echogram.py`, which wraps the code above
in a `plot_echogram(dt, ax=...)` function and a small command-line interface:

```bash
# first file in example_data/ -> examples/echogram.png
pixi run echogram

# explicit file(s) and output, no decimation
pixi run python examples/plot_echogram.py path/to/file.dt4 -o out.png -d 1
```

`plot_echogram(dt, ax=...)` draws onto any matplotlib axes, so it composes
with subplots and your own figure layout.
