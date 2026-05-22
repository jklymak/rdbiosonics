"""Tests for the dt4_to_netcdf converter."""

from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from rdbiosonics import dt4_to_netcdf, rddtx

HERE = Path(__file__).parent
SAMPLE = HERE / "data" / "sample.dt4"


def test_float32_roundtrip(tmp_path):
    dst = dt4_to_netcdf(SAMPLE, tmp_path / "out.nc", dtype="float32")
    assert dst.exists()

    orig = rddtx(SAMPLE)
    dt = xr.open_datatree(dst)
    try:
        for group in ("Beam", "Environment", "Platform", "Vendor_specific"):
            assert group in dt
        assert dt.Beam.sizes == orig.Beam.sizes
        assert dt.Beam.backscatter.dtype == np.float32

        # compression and chunking were applied
        enc = dt.Beam.backscatter.encoding
        assert enc["zlib"] is True
        assert enc["chunksizes"][1] == orig.Beam.sizes["range_sample"]

        np.testing.assert_allclose(
            dt.Beam.backscatter.values, orig.Beam.backscatter.values,
            rtol=1e-6, atol=1e-5)
    finally:
        dt.close()


def test_int16_roundtrip_within_quantisation(tmp_path):
    dst = dt4_to_netcdf(SAMPLE, tmp_path / "out16.nc", dtype="int16")
    orig = rddtx(SAMPLE)
    dt = xr.open_datatree(dst)
    try:
        # CF packing -> exact to within one quantisation step
        step = dt.Beam.backscatter.encoding["scale_factor"]
        diff = np.abs(dt.Beam.backscatter.values
                      - orig.Beam.backscatter.values)
        assert np.nanmax(diff) <= step
    finally:
        dt.close()


def test_int16_is_smaller_than_float32(tmp_path):
    f32 = dt4_to_netcdf(SAMPLE, tmp_path / "a.nc", dtype="float32")
    i16 = dt4_to_netcdf(SAMPLE, tmp_path / "b.nc", dtype="int16")
    assert i16.stat().st_size < f32.stat().st_size


def test_default_output_path(tmp_path):
    src = tmp_path / "copy.dt4"
    src.write_bytes(SAMPLE.read_bytes())
    dst = dt4_to_netcdf(src)
    assert dst == src.with_suffix(".nc")
    assert dst.exists()


def test_flat_netcdf_has_no_groups(tmp_path):
    dst = dt4_to_netcdf(SAMPLE, tmp_path / "flat.nc", flat=True)
    ds = xr.open_dataset(dst)
    try:
        # All variables in one flat dataset
        assert "backscatter" in ds
        assert "latitude" in ds
        assert "longitude" in ds
        assert "nmea_time" in ds
        assert "sound_speed" in ds
        assert "frequency" in ds
    finally:
        ds.close()


def test_flat_rddtx_returns_dataset():
    flat = rddtx(SAMPLE, flat=True)
    assert isinstance(flat, xr.Dataset)
    grouped = rddtx(SAMPLE)
    # Platform vars present
    np.testing.assert_array_equal(
        flat["latitude"].values,
        grouped["Platform"]["latitude"].values)
    np.testing.assert_array_equal(
        flat["longitude"].values,
        grouped["Platform"]["longitude"].values)
    # Backscatter unchanged
    np.testing.assert_array_equal(
        flat["backscatter"].values,
        grouped["Beam"]["backscatter"].values)


def test_invalid_dtype_rejected(tmp_path):
    with pytest.raises(ValueError):
        dt4_to_netcdf(SAMPLE, tmp_path / "x.nc", dtype="float64")
