# API reference

```{eval-rst}
.. autofunction:: rdbiosonics.rddtx
```

```{eval-rst}
.. autofunction:: rdbiosonics.dt4_to_netcdf
```

## Differences from `rddtx.m`

Record decoding follows the MATLAB original, with two deliberate bug fixes:

- **Environment `power`** reads its own two bytes. `rddtx.m` accidentally
  reads the salinity high byte instead, producing a meaningless value.
- **GPS latitude / longitude signs** follow the NMEA `N/S` and `E/W`
  hemisphere fields. `rddtx.m` hard-codes the western hemisphere
  (longitude always negative, latitude always positive).

The return type is an {py:class}`xarray.DataTree` rather than a MATLAB
struct. Backscatter is stored as ``log10(max(count, 1))``, matching
`rddtx.m`; it is **not** calibrated `Sv` or power in dB.
