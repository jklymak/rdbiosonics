"""Reader for Biosonics DTX ``.DT4`` echosounder files.

Python port of ``matlab/rddtx.m`` (Rich Pawlowicz, UBC). Record decoding
follows the MATLAB original, with two bug fixes: the environment ``power``
field reads the correct byte, and GPS latitude/longitude signs follow the
NMEA hemisphere fields instead of assuming the western hemisphere. The return
type is an :class:`xarray.DataTree` with groups loosely following the
echopype / SONAR-netCDF4 layout.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

__all__ = ["rddtx"]

_EPOCH = np.datetime64("1970-01-01T00:00:00", "ns")

_CLOCK_SOURCE = {0x02: "calendar", 0x06: "radio", 0x09: "chronometer",
                 0x11: "GPS", 0x12: "LORAN-C"}
_PULSE_TYPE = {0: "raw", 1: "integrated", 2: "chirp"}


# --------------------------------------------------------------------------
# low-level helpers
# --------------------------------------------------------------------------
def _u16(b, i):
    return int(b[i]) + int(b[i + 1]) * 256


def _u32(b, i):
    return (int(b[i]) + int(b[i + 1]) * 256 + int(b[i + 2]) * 65536
            + int(b[i + 3]) * 16777216)


def _twoscvt(x, nbytes=2):
    """Interpret an unsigned integer as a two's-complement signed integer."""
    m = 256 ** nbytes
    return x - m if x > m // 2 - 1 else x


def _to_str(arr):
    """Decode a byte array to text, dropping trailing nulls/whitespace."""
    s = bytes(int(v) & 0xFF for v in arr).decode("latin1")
    return s.split("\x00", 1)[0].strip()


def _sec_to_dt64(sec):
    """Seconds since the Unix epoch -> ``datetime64[ns]`` (NaN -> NaT)."""
    sec = np.asarray(sec, dtype=np.float64)
    out = np.full(sec.shape, np.datetime64("NaT", "ns"))
    good = np.isfinite(sec)
    out[good] = _EPOCH + np.round(sec[good] * 1e9).astype("timedelta64[ns]")
    return out


def _nmea_deg(field, hemi):
    """NMEA ddmm.mmmm + hemisphere ('N'/'S'/'E'/'W') -> signed decimal degrees."""
    x = float(field)
    deg = np.trunc(x / 100.0) + (x % 100.0) / 60.0
    return -deg if hemi.strip().upper() in ("S", "W") else deg


# --------------------------------------------------------------------------
# record decoders (one per DT4 tag, mirroring rddtx.m sub-functions)
# --------------------------------------------------------------------------
def _records(buf):
    """Yield ``(tag, siz, bits)`` for each record; stop at the EOF tag."""
    n = buf.size
    p = 0
    while p + 4 <= n:
        siz = _u16(buf, p)
        tag = f"{buf[p + 2]:02X}{buf[p + 3]:02X}"
        end = p + 4 + siz + 2
        if end > n:
            break
        bits = buf[p + 4:end].astype(np.int64)
        yield tag, siz, bits
        if tag == "FEFF":
            return
        p = end


def _rd_env(b):
    return dict(
        absorb=(b[0] + b[1] * 256) / 10000,
        sv=(b[2] + b[3] * 256) * 0.0025 + 1400,
        temperature=_twoscvt(b[4] + b[5] * 256) * 0.01,
        salinity=(b[6] + b[7] * 256) * 0.01,
        power=_twoscvt(b[8] + b[9] * 256) * 0.1,
        nsdr=_u16(b, 10),
    )


def _rd_snd(b):
    rxee = b[22:150]
    snd = dict(
        address=_u16(b, 0),
        npings=_twoscvt(_u32(b, 2), 4),
        sampperping=_u16(b, 6),
        sampperiod=_u16(b, 8) / 1000,
        ccor=_u16(b, 10) * 0.001,
        pulselen=_u16(b, 12) / 1000,
        pingperiod=_u16(b, 14) / 1000,
        blank=_u16(b, 16),
        maxdata=_u16(b, 18),
        threshold=_twoscvt(_u16(b, 20)) * 0.01,
        serialnum=_to_str(rxee[2:10]),
        cal_tech=_to_str(rxee[52:56]),
        freq=_twoscvt(_u32(rxee, 86), 4),
        transducer=_u16(rxee, 83),
    )
    snd["calibration"] = _sec_to_dt64(_u32(rxee, 36))
    return snd


def _rd_pulse(b):
    code = _twoscvt(_u16(b, 0))
    return dict(type=_PULSE_TYPE.get(code, f"unknown({code})"),
                address=_u16(b, 2))


def _rd_chron(b):
    ptime = _u32(b, 6)
    # chron.time is whole Unix seconds; ptime carries the millisecond fraction.
    return dict(
        source=_CLOCK_SOURCE.get(int(b[4]), f"unknown(0x{int(b[4]):02X})"),
        ptime=ptime,
        mtime=_u32(b, 0) + (ptime % 1000) / 1000.0,
    )


def _rd_ping(b):
    """Decode a single-beam ping (tag 1500) -> ``(pingnum, samples)``.

    Samples are stored as exponent/mantissa pairs; a high byte of 0xFF marks a
    run-length-encoded block of zeros whose length is ``low_byte + 2``.
    """
    pingnum = _u32(b, 2)
    nsamp = _u16(b, 10)

    high = b[13::2]
    low = b[12::2]
    n = min(high.size, low.size)
    high, low = high[:n], low[:n]

    exponent = high >> 4
    mantissa = low + 256 * (high & 15)
    shift = np.maximum(exponent - 1, 0)
    samps = np.where(exponent == 0, mantissa,
                     (mantissa + 0x1000) << shift).astype(np.float64)

    # rle holds 1-based marker positions plus the [0, ..., nsamp] sentinels,
    # matching the indexing arithmetic in rddtx.m.
    marks = np.flatnonzero(high == 255) + 1
    rle = np.concatenate(([0], marks, [nsamp]))

    segments = []
    for k in range(1, rle.size):
        a, c = int(rle[k - 1]), int(rle[k])
        segments.append(samps[a:c - 1])
        if k < rle.size - 1:  # interior entries are markers -> emit zero run
            segments.append(np.zeros(int(b[10 + 2 * c]) + 2))
    return pingnum, np.concatenate(segments) if segments else np.zeros(0)


def _parse_nmea(s, cur_chron, prev_mtimes):
    """Parse a GPRMC (preferred) or GPGGA sentence -> ``(time, lat, lon)``.

    Latitude and longitude signs follow the sentence's N/S and E/W fields.
    Returns ``None`` if neither sentence is present.
    """
    i = s.find("$GPRMC")
    if i >= 0:
        f = s[i:].split(",")
        try:
            t, d = f[1], f[9]
            dt = datetime(2000 + int(d[4:6]), int(d[2:4]), int(d[0:2]),
                          int(t[0:2]), int(t[2:4]), int(t[4:6]),
                          tzinfo=timezone.utc).timestamp()
            return dt, _nmea_deg(f[3], f[4]), _nmea_deg(f[5], f[6])
        except (ValueError, IndexError):
            return float("nan"), float("nan"), float("nan")

    i = s.find("$GPGGA")
    if i >= 0:
        f = s[i:].split(",")
        try:
            t = f[1]
            # GGA has no date: take the day from the previous fix (or the
            # sounder clock) and only the hh:mm:ss from the sentence.
            base = prev_mtimes[-1] if prev_mtimes else cur_chron
            day = np.floor(base / 86400.0) * 86400.0
            hms = int(t[0:2]) * 3600 + int(t[2:4]) * 60 + int(t[4:6])
            return day + hms, _nmea_deg(f[2], f[3]), _nmea_deg(f[4], f[5])
        except (ValueError, IndexError):
            return float("nan"), float("nan"), float("nan")
    return None


# --------------------------------------------------------------------------
# public reader
# --------------------------------------------------------------------------
def rddtx(files, numdec=3):
    """Read Biosonics DTX ``.DT4`` files into an :class:`xarray.DataTree`.

    Parameters
    ----------
    files : path-like or sequence of path-like
        One or more ``.DT4`` files. Multiple files are read sequentially and
        concatenated, allowing long records that were split into chunks to be
        chained back together.
    numdec : int, default 3
        Decimation factor. Pings are grouped in blocks of ``numdec`` and
        reduced by an in-time median, which is effective at suppressing
        interference from other sounders. Use ``numdec=1`` for no decimation.

    Returns
    -------
    xarray.DataTree
        Groups: ``Beam`` (backscatter), ``Environment``, ``Platform`` (GPS),
        and ``Vendor_specific`` (sounder settings).
    """
    if isinstance(files, (str, Path)):
        files = [files]
    files = [str(f) for f in files]
    if numdec < 1:
        raise ValueError("numdec must be >= 1")

    env = snd = pulse = None
    cur_chron = float("nan")

    idec = 0
    den_vals = None
    den_pingnum, den_imtime = [], []

    cols, imtime, pingnum = [], [], []
    pos_ptime, pos_mtime, pos_lat, pos_lon = [], [], [], []

    for path in files:
        buf = np.fromfile(path, dtype=np.uint8)
        for tag, siz, bits in _records(buf):
            if tag == "1E00" and env is None:
                env = _rd_env(bits)
            elif tag == "1200" and snd is None:
                snd = _rd_snd(bits)
                if numdec > 1:
                    den_vals = np.full((snd["sampperping"], numdec), np.nan)
            elif tag == "1300":
                pulse = _rd_pulse(bits)
            elif tag == "0F00":
                cur_chron = _rd_chron(bits)["mtime"]
            elif tag == "1500":
                if snd is None:
                    continue  # ping before settings (rddtx.m warns and skips)
                spp = snd["sampperping"]
                pn, samps = _rd_ping(bits)
                if samps.size > spp:
                    samps = samps[:spp - 1]
                if numdec == 1:
                    col = np.full(spp, np.nan)
                    col[:samps.size] = np.log10(np.fmax(samps, 1.0))
                    cols.append(col)
                    imtime.append(cur_chron)
                    pingnum.append(pn)
                else:
                    den_vals[:, idec] = np.nan
                    den_vals[:samps.size, idec] = samps
                    den_pingnum.append(pn)
                    den_imtime.append(cur_chron)
                    idec += 1
                    if idec == numdec:
                        med = np.median(den_vals, axis=1)
                        cols.append(np.log10(np.fmax(med, 1.0)))
                        imtime.append(float(np.median(den_imtime)))
                        pingnum.append(float(np.median(den_pingnum)))
                        idec = 0
                        den_pingnum.clear()
                        den_imtime.clear()
            elif tag == "1100":
                fix = _parse_nmea(_to_str(bits[:siz]), cur_chron, pos_mtime)
                if fix is not None:
                    pos_mtime.append(fix[0])
                    pos_lat.append(fix[1])
                    pos_lon.append(fix[2])
                    pos_ptime.append(cur_chron)

    if snd is None or env is None:
        raise ValueError("no sounder-settings (1200) or environment (1E00) "
                         "record found; not a valid DT4 file?")

    return _build_tree(files, numdec, env, snd, pulse,
                       cols, imtime, pingnum,
                       pos_ptime, pos_mtime, pos_lat, pos_lon)


def _build_tree(files, numdec, env, snd, pulse, cols, imtime, pingnum,
                pos_ptime, pos_mtime, pos_lat, pos_lon):
    spp = snd["sampperping"]
    npings = len(cols)
    backscatter = (np.stack(cols) if npings
                   else np.empty((0, spp), dtype=np.float64))
    imtime = np.asarray(imtime, dtype=np.float64)
    pingnum = np.asarray(pingnum, dtype=np.float64)

    # range to the centre of each sample (rddtx.m: dtx.range)
    echo_range = ((np.arange(spp) + 1 + snd["blank"])
                  * snd["sampperiod"] * env["sv"] / 2e6)

    # interpolate GPS fixes onto ping times via the internal sounder clock
    lat = np.full(npings, np.nan)
    lon = np.full(npings, np.nan)
    nmea_time = np.full(npings, np.nan)
    if len(pos_ptime) > 2:
        pp = np.asarray(pos_ptime, dtype=np.float64)
        keep = np.isfinite(pp)
        keep[1:] &= (np.diff(pos_lat) != 0) & (np.diff(pos_lon) != 0)
        idx = np.flatnonzero(keep)
        if idx.size >= 2:
            x = pp[idx]
            lat = np.interp(imtime, x, np.asarray(pos_lat)[idx])
            lon = np.interp(imtime, x, np.asarray(pos_lon)[idx])
            nmea_time = np.interp(imtime, x, np.asarray(pos_mtime)[idx])

    ping_time = _sec_to_dt64(imtime)

    beam = xr.Dataset(
        data_vars={
            "backscatter": (
                ("ping_time", "range_sample"), backscatter,
                {"long_name": "log10 of raw echo counts",
                 "units": "log10(count)",
                 "comment": "log10(max(count, 1)); see rddtx.m"}),
            "ping_number": (
                "ping_time", pingnum,
                {"long_name": "sounder ping counter"}),
        },
        coords={
            "ping_time": ("ping_time", ping_time,
                          {"long_name": "internal sounder clock time"}),
            "range_sample": ("range_sample", np.arange(spp)),
            "echo_range": ("range_sample", echo_range,
                           {"long_name": "range to sample centre",
                            "units": "m"}),
        },
    )

    platform = xr.Dataset(
        data_vars={
            "latitude": ("ping_time", lat,
                         {"long_name": "latitude", "units": "degrees_north"}),
            "longitude": ("ping_time", lon,
                          {"long_name": "longitude", "units": "degrees_east"}),
            "nmea_time": ("ping_time", _sec_to_dt64(nmea_time),
                          {"long_name": "time from NMEA strings, "
                                        "interpolated to ping times"}),
        },
        coords={"ping_time": ("ping_time", ping_time)},
    )

    environment = xr.Dataset(
        data_vars={
            "sound_speed": ((), env["sv"], {"units": "m/s"}),
            "sound_absorption": ((), env["absorb"], {"units": "dB/m"}),
            "temperature": ((), env["temperature"], {"units": "degC"}),
            "salinity": ((), env["salinity"], {"units": "1e-3"}),
            "power": ((), env["power"]),
            "nsdr": ((), env["nsdr"]),
        },
    )

    vendor = xr.Dataset(
        data_vars={
            "frequency": ((), snd["freq"], {"units": "Hz"}),
            "transducer": ((), snd["transducer"]),
            "sample_interval": ((), snd["sampperiod"], {"units": "us"}),
            "sample_blanking": ((), snd["blank"], {"units": "sample"}),
            "pulse_length": ((), snd["pulselen"], {"units": "ms"}),
            "ping_period": ((), snd["pingperiod"], {"units": "s"}),
            "threshold": ((), snd["threshold"], {"units": "dB"}),
            "ccor": ((), snd["ccor"]),
            "max_data": ((), snd["maxdata"]),
        },
        attrs={
            "serial_number": snd["serialnum"],
            "calibration_tech": snd["cal_tech"],
            "calibration_date": str(snd["calibration"]),
            "sounder_address": snd["address"],
            "pings_expected": int(snd["npings"]),
            "samples_per_ping": spp,
            "pulse_type": pulse["type"] if pulse else "unknown",
        },
    )

    root = xr.Dataset(attrs={
        "title": "Biosonics DTX DT4 echosounder data",
        "source_files": [Path(f).name for f in files],
        "decimation": numdec,
        "n_pings": npings,
        "converted_by": "rdbiosonics.rddtx (port of rddtx.m)",
    })

    return xr.DataTree.from_dict({
        "/": root,
        "/Beam": beam,
        "/Environment": environment,
        "/Platform": platform,
        "/Vendor_specific": vendor,
    })
