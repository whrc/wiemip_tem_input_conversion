"""Print NetCDF variable metadata for dvmdostem-style climate files."""

from __future__ import print_function

import xarray as xr


def describe_climate_nc(path, engine="h5netcdf"):
    ds = xr.open_dataset(path, engine=engine, decode_times=True)
    lines = []
    lines.append("File: {}".format(path))
    lines.append("Dimensions: {}".format(dict(ds.dims)))

    lines.append("Data variables:")
    for name, da in ds.data_vars.items():
        units = da.attrs.get("units", "")
        lines.append("  {}  dims={}  dtype={}  units={!r}".format(name, da.dims, da.dtype, units))

    lines.append("Coordinates (non-dim):")
    for name, da in ds.coords.items():
        if name in ds.dims:
            continue
        units = da.attrs.get("units", "")
        lines.append("  {}  dims={}  units={!r}".format(name, da.dims, units))

    if "time" in ds.coords or "time" in ds.variables:
        t = ds["time"]
        lines.append("Time coordinate:")
        lines.append("  length={}".format(t.size))
        lines.append("  dtype={}".format(t.dtype))
        lines.append("  units={!r}".format(t.attrs.get("units", "")))
        lines.append("  calendar={!r}".format(t.attrs.get("calendar", "")))
        if t.size >= 2:
            v0, v1 = t.values[0], t.values[1]
            lines.append("  first={!r}".format(v0))
            lines.append("  second={!r}".format(v1))
            if hasattr(v1, "__sub__") and hasattr(v0, "__sub__"):
                try:
                    dt = v1 - v0
                    lines.append("  spacing(first two)={!r}".format(dt))
                except Exception:
                    pass
        if t.size >= 1:
            lines.append("  last={!r}".format(t.values[-1]))

    ds.close()
    return "\n".join(lines)
