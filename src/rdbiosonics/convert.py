"""Convert Biosonics DTX ``.DT4`` files to compressed, chunked netCDF.

DT4 is a sequential, run-length-encoded format — there is no way to read a
slice of it without parsing from the start. Converting once to netCDF gives
random access, lazy loading, dask, and a portable archival format.

Use the :func:`dt4_to_netcdf` function, or the ``rdbiosonics-convert``
command-line tool installed with the package.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np

from rdbiosonics.rddtx import rddtx

__all__ = ["dt4_to_netcdf"]

_DTYPES = ("float32", "int16")


def _has_netcdf_backend():
    return (importlib.util.find_spec("netCDF4") is not None
            or importlib.util.find_spec("h5netcdf") is not None)


def _sanitize_attrs(dt):
    """Make attributes netCDF-safe (e.g. list-valued attrs -> strings)."""
    for node in dt.subtree:
        for key, value in list(node.attrs.items()):
            if isinstance(value, (list, tuple)):
                node.attrs[key] = ", ".join(str(v) for v in value)


def _backscatter_encoding(backscatter, dtype, complevel, ping_chunk):
    """Build the netCDF ``encoding`` dict for the backscatter variable."""
    if dtype not in _DTYPES:
        raise ValueError(f"dtype must be one of {_DTYPES}, got {dtype!r}")

    n_ping, n_range = backscatter.shape
    enc = {"zlib": True, "complevel": int(complevel), "shuffle": True}
    if n_ping > 0 and n_range > 0:
        enc["chunksizes"] = (min(int(ping_chunk), n_ping), n_range)

    if dtype == "float32":
        enc["dtype"] = "float32"
    else:  # int16, packed via the CF scale_factor / add_offset convention
        finite = np.isfinite(backscatter)
        if finite.any():
            vmin = float(backscatter[finite].min())
            vmax = float(backscatter[finite].max())
        else:
            vmin, vmax = 0.0, 1.0
        if vmax <= vmin:
            vmax = vmin + 1.0
        # map [vmin, vmax] onto [-32767, 32767]; -32768 is reserved for NaN
        enc.update(
            dtype="int16",
            scale_factor=np.float32((vmax - vmin) / 65534.0),
            add_offset=np.float32((vmax + vmin) / 2.0),
            _FillValue=np.int16(-32768),
        )
    return enc


def dt4_to_netcdf(src, dst=None, *, numdec=3, dtype="float32",
                  complevel=4, ping_chunk=512):
    """Convert DT4 file(s) to a single compressed, chunked netCDF file.

    Parameters
    ----------
    src : path-like or sequence of path-like
        One ``.DT4`` file, or several to chain into one dataset (passed
        straight to :func:`rdbiosonics.rddtx`).
    dst : path-like, optional
        Output ``.nc`` path. Defaults to ``src`` with a ``.nc`` suffix.
    numdec : int, default 3
        Median decimation factor (see :func:`rdbiosonics.rddtx`).
    dtype : {"float32", "int16"}, default "float32"
        Storage dtype for ``backscatter``. ``"int16"`` halves the size by
        packing with the CF ``scale_factor`` / ``add_offset`` convention,
        which xarray reverses automatically on read.
    complevel : int, default 4
        zlib compression level (1-9).
    ping_chunk : int, default 512
        Chunk size along ``ping_time``; the range axis is one chunk.

    Returns
    -------
    pathlib.Path
        The path written.
    """
    src_list = [src] if isinstance(src, (str, Path)) else [Path(s) for s in src]
    if not src_list:
        raise ValueError("no input files given")
    dst = Path(src_list[0]).with_suffix(".nc") if dst is None else Path(dst)

    if not _has_netcdf_backend():
        raise ImportError(
            "writing netCDF needs the 'netcdf4' package — install it with "
            "`pip install netcdf4` or `pip install 'rdbiosonics[netcdf]'`."
        )

    dt = rddtx(src_list, numdec=numdec)
    _sanitize_attrs(dt)

    enc = _backscatter_encoding(
        dt["Beam"]["backscatter"].values, dtype, complevel, ping_chunk)

    dst.parent.mkdir(parents=True, exist_ok=True)
    dt.to_netcdf(dst, encoding={"/Beam": {"backscatter": enc}})
    return dst


# --------------------------------------------------------------------------
# command-line interface
# --------------------------------------------------------------------------
def _expand_inputs(inputs):
    """Expand directories to the ``.dt4`` files they contain."""
    files = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            files.extend(sorted(p.glob("*.dt4")) + sorted(p.glob("*.DT4")))
        else:
            files.append(p)
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="rdbiosonics-convert",
        description="Convert Biosonics DTX .DT4 files to compressed netCDF.",
    )
    parser.add_argument(
        "inputs", nargs="+",
        help="DT4 file(s), or directories to scan for *.dt4",
    )
    parser.add_argument(
        "-o", "--outdir", type=Path,
        help="output directory (default: alongside each input file)",
    )
    parser.add_argument("--numdec", type=int, default=3,
                        help="median decimation factor (default: 3)")
    parser.add_argument("--dtype", choices=_DTYPES, default="float32",
                        help="backscatter storage dtype (default: float32)")
    parser.add_argument("--complevel", type=int, default=4,
                        help="zlib compression level 1-9 (default: 4)")
    parser.add_argument("--ping-chunk", type=int, default=512,
                        help="chunk size along ping_time (default: 512)")
    parser.add_argument(
        "--chain", action="store_true",
        help="chain all inputs into one netCDF (default: one per input)",
    )
    args = parser.parse_args(argv)

    files = _expand_inputs(args.inputs)
    if not files:
        parser.error("no .dt4 files found in the given inputs")

    def out_path(first):
        name = Path(first).with_suffix(".nc").name
        return (args.outdir / name) if args.outdir else Path(first).with_suffix(".nc")

    jobs = ([(files, out_path(files[0]))] if args.chain
            else [([f], out_path(f)) for f in files])

    total = 0.0
    for src, dst in jobs:
        print(f"converting {len(src)} file(s) -> {dst}", flush=True)
        dt4_to_netcdf(src, dst, numdec=args.numdec, dtype=args.dtype,
                      complevel=args.complevel, ping_chunk=args.ping_chunk)
        mb = dst.stat().st_size / 1e6
        total += mb
        print(f"  wrote {mb:.1f} MB")
    print(f"done: {len(jobs)} file(s), {total:.1f} MB total")


if __name__ == "__main__":
    main()
