"""Read a Biosonics DTX .DT4 file and plot it as an echogram image.

An *echogram* is the standard way to view echosounder data: time on the x
axis, range (depth) on the y axis, and backscatter strength as colour.

Run it directly to produce a PNG::

    pixi run python examples/plot_echogram.py
    pixi run python examples/plot_echogram.py path/to/file.dt4 -o out.png

or import :func:`plot_echogram` to drop an echogram onto your own axes.
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from rdbiosonics import rddtx

REPO = Path(__file__).resolve().parent.parent


def plot_echogram(dt, ax=None, cmap="viridis", clim=None):
    """Plot the backscatter of a DT4 DataTree as an echogram.

    Parameters
    ----------
    dt : xarray.DataTree
        Output of :func:`rdbiosonics.rddtx`.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on; a new figure is created if omitted.
    cmap : str
        Matplotlib colormap name.
    clim : (float, float), optional
        Colour limits. Defaults to the 5th/99th percentiles of the data.

    Returns
    -------
    matplotlib.axes.Axes
    """
    beam = dt.Beam
    backscatter = beam.backscatter.values         # (ping_time, range_sample)
    time = beam.ping_time.values                  # datetime64
    rng = beam.echo_range.values                  # metres

    if clim is None:
        clim = np.nanpercentile(backscatter, [5, 99])

    if ax is None:
        _, ax = plt.subplots(figsize=(12, 5), layout="constrained")

    # pcolormesh wants colour data shaped (y, x) = (range_sample, ping_time)
    mesh = ax.pcolormesh(
        time, rng, backscatter.T,
        shading="nearest", cmap=cmap, vmin=clim[0], vmax=clim[1],
        rasterized=True,
    )
    ax.invert_yaxis()                             # depth increases downward
    ax.set_xlabel("Ping time (internal sounder clock)")
    ax.set_ylabel("Range (m)")

    vendor = dt.Vendor_specific.attrs
    ax.set_title(
        f"Biosonics DTX  ·  {vendor['serial_number']}  ·  "
        f"{float(dt.Vendor_specific.frequency) / 1000:g} kHz  ·  "
        f"{dt.attrs['n_pings']} pings (decimation {dt.attrs['decimation']})"
    )

    cbar = ax.figure.colorbar(mesh, ax=ax, pad=0.02)
    cbar.set_label("Backscatter  [log10 echo counts]")
    return ax


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files", nargs="*",
        help="DT4 file(s) to read (default: first file in example_data/)",
    )
    parser.add_argument(
        "-o", "--output", default=str(REPO / "examples" / "echogram.png"),
        help="output image path",
    )
    parser.add_argument(
        "-d", "--decimation", type=int, default=3,
        help="median decimation factor passed to rddtx (default: 3)",
    )
    args = parser.parse_args()

    files = args.files or sorted(glob.glob(str(REPO / "example_data" / "*.dt4")))[:1]
    if not files:
        parser.error("no DT4 files given and example_data/ is empty")

    print(f"reading {len(files)} file(s)...")
    dt = rddtx(files, numdec=args.decimation)
    print(f"  -> {dt.attrs['n_pings']} pings x "
          f"{dt.Beam.sizes['range_sample']} range samples")

    ax = plot_echogram(dt)
    ax.figure.savefig(args.output, dpi=150)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
