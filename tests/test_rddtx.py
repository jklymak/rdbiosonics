import glob
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from rdbiosonics import rddtx

DATA = sorted(glob.glob(str(Path(__file__).parent.parent / "example_data" / "*.dt4")))

pytestmark = pytest.mark.skipif(not DATA, reason="example_data/*.dt4 not present")


def test_returns_datatree_with_expected_groups():
    dt = rddtx(DATA[0])
    assert isinstance(dt, xr.DataTree)
    for group in ("Beam", "Environment", "Platform", "Vendor_specific"):
        assert group in dt


def test_beam_dimensions_and_decimation():
    spp = int(rddtx(DATA[0]).Vendor_specific.attrs["samples_per_ping"])

    full = rddtx(DATA[0], numdec=1)
    dec = rddtx(DATA[0], numdec=3)

    assert full.Beam.sizes["range_sample"] == spp
    assert dec.Beam.sizes["range_sample"] == spp
    # decimation groups pings in blocks of 3
    assert dec.Beam.sizes["ping_time"] == full.Beam.sizes["ping_time"] // 3


def test_decimated_backscatter_is_finite():
    # numdec > 1 fills short pings via median(NaN) -> max(NaN, 1) -> 0
    b = rddtx(DATA[0], numdec=3).Beam.backscatter.values
    assert np.isfinite(b).all()
    assert b.min() >= 0.0


def test_physical_values_are_plausible():
    dt = rddtx(DATA[0])
    env = dt.Environment
    assert 1400 < float(env.sound_speed) < 1600
    assert 0 < float(env.salinity) < 40

    rng = dt.Beam.echo_range.values
    assert rng[0] > 0 and np.all(np.diff(rng) > 0)

    lat = dt.Platform.latitude.values
    lon = dt.Platform.longitude.values
    assert np.nanmin(lat) > -90 and np.nanmax(lat) < 90
    assert np.nanmin(lon) > -180 and np.nanmax(lon) < 180

    pt = dt.Beam.ping_time.values
    assert np.all(np.diff(pt).astype("timedelta64[ns]") >= np.timedelta64(0))


def test_multifile_chaining():
    if len(DATA) < 2:
        pytest.skip("need >=2 example files")
    one = rddtx(DATA[0]).Beam.sizes["ping_time"]
    chained = rddtx(DATA).Beam.sizes["ping_time"]
    # chained count is within rounding of the sum (decimation spans files)
    assert chained >= one
    assert abs(chained - one * len(DATA)) <= len(DATA)
