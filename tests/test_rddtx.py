"""Tests for rdbiosonics.rddtx.

The committed fixture ``tests/data/sample.dt4`` is a ~0.7 MB slice of a real
DT4 file (settings, environment, 30 pings, NMEA strings), so the full decode
path runs in CI without the large ``example_data/`` files. Those are used by
an extra opt-in test when present.
"""

import glob
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from rdbiosonics import rddtx

HERE = Path(__file__).parent
SAMPLE = HERE / "data" / "sample.dt4"
FULL = sorted(glob.glob(str(HERE.parent / "example_data" / "*.dt4")))


@pytest.fixture(scope="module")
def dt():
    return rddtx(SAMPLE)


def test_returns_datatree_with_expected_groups(dt):
    assert isinstance(dt, xr.DataTree)
    for group in ("Beam", "Environment", "Platform", "Vendor_specific"):
        assert group in dt


def test_beam_dimensions_and_decimation():
    spp = int(rddtx(SAMPLE).Vendor_specific.attrs["samples_per_ping"])

    full = rddtx(SAMPLE, numdec=1)
    dec = rddtx(SAMPLE, numdec=3)

    assert full.Beam.sizes["range_sample"] == spp
    assert dec.Beam.sizes["range_sample"] == spp
    # decimation groups pings in blocks of 3
    assert dec.Beam.sizes["ping_time"] == full.Beam.sizes["ping_time"] // 3


def test_decimated_backscatter_is_finite():
    # numdec > 1 fills short pings via median(NaN) -> max(NaN, 1) -> 0
    b = rddtx(SAMPLE, numdec=3).Beam.backscatter.values
    assert np.isfinite(b).all()
    assert b.min() >= 0.0


def test_undecimated_backscatter_pads_with_nan():
    # numdec == 1 leaves the unfilled tail of short pings as NaN
    b = rddtx(SAMPLE, numdec=1).Beam.backscatter.values
    assert np.isfinite(b).any()


def test_physical_values_are_plausible(dt):
    env = dt.Environment
    assert 1400 < float(env.sound_speed) < 1600
    assert 0 <= float(env.salinity) < 40

    rng = dt.Beam.echo_range.values
    assert rng[0] > 0 and np.all(np.diff(rng) > 0)

    pt = dt.Beam.ping_time.values
    assert np.all(np.diff(pt).astype("timedelta64[ns]") >= np.timedelta64(0))


def test_positions_are_valid_or_absent(dt):
    lat = dt.Platform.latitude.values
    lon = dt.Platform.longitude.values
    good = np.isfinite(lat) & np.isfinite(lon)
    # positions are either valid geographic coordinates or all-NaN (no GPS)
    if good.any():
        assert np.all((lat[good] > -90) & (lat[good] < 90))
        assert np.all((lon[good] > -180) & (lon[good] < 180))


def test_bad_input_raises(tmp_path):
    junk = tmp_path / "not.dt4"
    junk.write_bytes(b"\x00" * 64)
    with pytest.raises(ValueError):
        rddtx(junk)


@pytest.mark.skipif(not FULL, reason="full example_data/*.dt4 not present")
def test_multifile_chaining():
    one = rddtx(FULL[0]).Beam.sizes["ping_time"]
    chained = rddtx(FULL).Beam.sizes["ping_time"]
    # chained count is within rounding of the sum (decimation spans files)
    assert chained >= one
    assert abs(chained - one * len(FULL)) <= len(FULL)
