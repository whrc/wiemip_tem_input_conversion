from __future__ import print_function

import os
import sys

import cftime
import numpy as np
import xarray as xr

from wiemip_to_dvmdostem import aggregate
from wiemip_to_dvmdostem.paths import (
    delete_wiemip_year,
    download_wiemip_year,
    wiemip_year_path,
)
from wiemip_to_dvmdostem.schema import (
    TARGET_CALENDAR,
    TARGET_FILL,
    TARGET_TIME_UNITS,
    VARIABLE_MAP,
)

_TARGET_VARS = ("tair", "precip", "nirr", "vapor_press")
_ATTR_SKIP = frozenset(("_FillValue", "grid_mapping", "coordinates"))


def _open_ds(path, decode_times=True):
    return xr.open_dataset(path, engine="h5netcdf", decode_times=decode_times)


def _target_time_coord(year_start, year_end):
    n_months = (int(year_end) - int(year_start) + 1) * 12
    return xr.cftime_range(
        start="{:04d}-01-01".format(int(year_start)),
        periods=n_months,
        freq="MS",
        calendar=TARGET_CALENDAR,
    )


def _year_time_coord(year):
    return xr.cftime_range(
        start="{:04d}-01-01".format(int(year)),
        periods=12,
        freq="MS",
        calendar=TARGET_CALENDAR,
    )


def _spatial_coords_from_wiemip(ds_tmp):
    """Y = lat axis, X = lon axis; lat/lon also as 2D (Y, X) for CF-style geolocation."""
    lat1 = ds_tmp["lat"].values.astype(np.float32)
    lon1 = ds_tmp["lon"].values.astype(np.float32)
    lat2d, lon2d = np.meshgrid(lat1, lon1, indexing="ij")
    coord_Y = xr.DataArray(lat1, dims=("Y",), attrs=dict(ds_tmp["lat"].attrs))
    coord_X = xr.DataArray(lon1, dims=("X",), attrs=dict(ds_tmp["lon"].attrs))
    coord_lat = xr.DataArray(lat2d, dims=("Y", "X"), attrs=dict(ds_tmp["lat"].attrs))
    coord_lon = xr.DataArray(lon2d, dims=("Y", "X"), attrs=dict(ds_tmp["lon"].attrs))
    return coord_Y, coord_X, coord_lat, coord_lon, lat1, lon1


def _read_ref_attrs(reference_nc):
    """Open reference NetCDF and extract per-variable CF attributes only."""
    ds = _open_ds(reference_nc, decode_times=True)
    try:
        return {v: dict(ds[v].attrs) for v in _TARGET_VARS}
    finally:
        ds.close()


def _process_year(ds_tmp, ds_pre, ds_sw, ds_q, ds_p, year, lat_ref, lon_ref):
    """
    Aggregate one year of 6-hourly WIEMIP data → dict of float32 (12, Y, X) arrays.
    Validates that lat/lon match lat_ref/lon_ref.
    """
    if not np.array_equal(ds_tmp["lat"].values, lat_ref) or not np.array_equal(
        ds_tmp["lon"].values, lon_ref
    ):
        raise ValueError("lat/lon coordinates differ from the reference year in file for {}".format(year))

    da_tair = aggregate.monthly_mean_temperature_celsius(ds_tmp, year)
    da_pre = aggregate.monthly_precip_mm(ds_pre, year)
    da_nirr = aggregate.monthly_mean_dswrf(ds_sw, year)
    da_vp = aggregate.monthly_mean_vapor_pressure_hpa(ds_q, ds_p, year)

    result = {}
    for name, da in (
        ("tair", da_tair),
        ("precip", da_pre),
        ("nirr", da_nirr),
        ("vapor_press", da_vp),
    ):
        arr = da.values.astype(np.float64)
        if arr.shape[0] != 12:
            raise ValueError(
                "Expected 12 months for year {}, got {} for {}".format(year, arr.shape[0], name)
            )
        arr = np.where(np.isfinite(arr), arr, np.float64(TARGET_FILL))
        result[name] = arr.astype(np.float32)
    return result


def _time_numeric_for_year(year):
    times = _year_time_coord(year)
    return cftime.date2num(list(times), units=TARGET_TIME_UNITS, calendar=TARGET_CALENDAR)


def _build_year_dataset(year_data, year, coord_Y, coord_X, coord_lat, coord_lon, ref_attrs):
    """Build an xr.Dataset for one year (12 time steps)."""
    time_numeric = _time_numeric_for_year(year)
    time_da = xr.DataArray(
        time_numeric,
        dims=("time",),
        attrs={
            "long_name": "time",
            "units": TARGET_TIME_UNITS,
            "calendar": TARGET_CALENDAR,
        },
    )
    out_vars = {name: (("time", "Y", "X"), year_data[name]) for name in year_data}
    ds = xr.Dataset(
        out_vars,
        coords={
            "time": time_da,
            "Y": coord_Y,
            "X": coord_X,
            "lat": coord_lat,
            "lon": coord_lon,
        },
    )
    for tgt in _TARGET_VARS:
        attrs = ref_attrs[tgt]
        ds[tgt].attrs = {k: v for k, v in attrs.items() if k not in _ATTR_SKIP}
    return ds


def _base_encoding():
    enc = {
        "time": {"dtype": "float64"},
        "Y": {"dtype": "float32", "_FillValue": None},
        "X": {"dtype": "float32", "_FillValue": None},
        "lat": {"dtype": "float32", "_FillValue": np.float32(TARGET_FILL)},
        "lon": {"dtype": "float32", "_FillValue": np.float32(TARGET_FILL)},
    }
    for v in _TARGET_VARS:
        enc[v] = {"dtype": "float32", "_FillValue": np.float32(TARGET_FILL)}
    return enc


def _write_first_year(output_nc, ds_year, engine):
    """Create the output file fresh with unlimited time dimension."""
    ds_year.to_netcdf(
        output_nc,
        engine=engine,
        encoding=_base_encoding(),
        unlimited_dims=["time"],
    )


def _append_year(output_nc, year_data, year):
    """
    Append 12 monthly time steps to an existing HDF5-backed NetCDF using h5py.

    Requires that the time and data variables were created with unlimited time
    dimension (resizable HDF5 datasets), which _write_first_year guarantees via
    ``unlimited_dims=['time']``.
    """
    import h5py

    time_numeric = _time_numeric_for_year(year)
    with h5py.File(output_nc, "a") as f:
        t0 = int(f["time"].shape[0])
        new_t = t0 + 12
        f["time"].resize((new_t,))
        f["time"][t0:new_t] = time_numeric
        for v in _TARGET_VARS:
            old_shape = f[v].shape
            f[v].resize((new_t, old_shape[1], old_shape[2]))
            f[v][t0:new_t, :, :] = year_data[v]


def convert_wiemip_to_dvmdostem(
    wiemip_dir,
    file_prefix,
    reference_nc,
    year_start,
    year_end,
    output_nc,
    engine="h5netcdf",
):
    """
    Build a climate NetCDF from WIEMIP 6-hourly yearly files on the native WIEMIP grid.

    *wiemip_dir* must contain ``{prefix}.{var}.{year}_6hr.noleap.nc`` for tmp, pre, dswrf,
    spfh, pres for every year in [year_start, year_end].

    Output dimensions are (time, Y, X) with Y aligned to WIEMIP *lat* and X to *lon*.
    *reference_nc* supplies only the expected time length and CF attributes for data
    variables (units, standard_name); it does not define the output horizontal grid.
    """
    year_start = int(year_start)
    year_end = int(year_end)
    if year_end < year_start:
        raise ValueError("year_end must be >= year_start")

    ref = _open_ds(reference_nc, decode_times=True)
    try:
        times = _target_time_coord(year_start, year_end)
        if len(times) != ref.dims["time"]:
            raise ValueError(
                "Reference time length {} does not match requested range ({} months). "
                "Use a reference file with matching time dimension or adjust years.".format(
                    ref.dims["time"], len(times)
                )
            )
        ref_attrs = {v: dict(ref[v].attrs) for v in _TARGET_VARS}
    finally:
        ref.close()

    p0 = wiemip_year_path(wiemip_dir, file_prefix, "tmp", year_start)
    if not os.path.isfile(p0):
        raise FileNotFoundError("Missing WIEMIP file for grid: {}".format(p0))

    ds0 = _open_ds(p0)
    try:
        coord_Y, coord_X, coord_lat, coord_lon, lat_ref, lon_ref = _spatial_coords_from_wiemip(ds0)
    finally:
        ds0.close()

    stacks = {entry["target_name"]: [] for entry in VARIABLE_MAP}

    for year in range(year_start, year_end + 1):
        p_tmp = wiemip_year_path(wiemip_dir, file_prefix, "tmp", year)
        p_pre = wiemip_year_path(wiemip_dir, file_prefix, "pre", year)
        p_sw = wiemip_year_path(wiemip_dir, file_prefix, "dswrf", year)
        p_q = wiemip_year_path(wiemip_dir, file_prefix, "spfh", year)
        p_p = wiemip_year_path(wiemip_dir, file_prefix, "pres", year)
        for p in (p_tmp, p_pre, p_sw, p_q, p_p):
            if not os.path.isfile(p):
                raise FileNotFoundError("Missing WIEMIP file: {}".format(p))

        ds_tmp = _open_ds(p_tmp)
        ds_pre = _open_ds(p_pre)
        ds_sw = _open_ds(p_sw)
        ds_q = _open_ds(p_q)
        ds_p = _open_ds(p_p)

        try:
            year_data = _process_year(ds_tmp, ds_pre, ds_sw, ds_q, ds_p, year, lat_ref, lon_ref)
            for name in year_data:
                stacks[name].append(year_data[name])
        finally:
            ds_tmp.close()
            ds_pre.close()
            ds_sw.close()
            ds_q.close()
            ds_p.close()

    n_steps = np.concatenate(stacks["tair"], axis=0).shape[0]
    if n_steps != len(times):
        raise RuntimeError("Internal error: time steps {} != {}".format(n_steps, len(times)))

    out_vars = {}
    for name in stacks:
        data = np.concatenate(stacks[name], axis=0).astype(np.float32)
        out_vars[name] = (("time", "Y", "X"), data)

    time_numeric = cftime.date2num(
        list(times),
        units=TARGET_TIME_UNITS,
        calendar=TARGET_CALENDAR,
    )
    time_da = xr.DataArray(
        time_numeric,
        dims=("time",),
        attrs={
            "long_name": "time",
            "units": TARGET_TIME_UNITS,
            "calendar": TARGET_CALENDAR,
        },
    )

    ds_out = xr.Dataset(
        out_vars,
        coords={
            "time": time_da,
            "Y": coord_Y,
            "X": coord_X,
            "lat": coord_lat,
            "lon": coord_lon,
        },
    )

    for tgt in _TARGET_VARS:
        attrs = ref_attrs[tgt]
        ds_out[tgt].attrs = {k: v for k, v in attrs.items() if k not in _ATTR_SKIP}

    ds_out.to_netcdf(output_nc, engine=engine, encoding=_base_encoding())
    ds_out.close()


def convert_wiemip_streaming(
    gcs_prefix,
    file_prefix,
    wiemip_dir,
    reference_nc,
    year_start,
    year_end,
    output_nc,
    engine="h5netcdf",
):
    """
    Download, convert, and append WIEMIP data year-by-year from GCS.

    For each year in [year_start, year_end]:
      1. Download the 5 WIEMIP variable files for that year via gsutil cp.
      2. Aggregate to 12 monthly slices in the dvmdostem variable layout.
      3. Write (first year) or append (subsequent years) to *output_nc*.
      4. Delete the downloaded files to keep disk usage bounded (~1.5 GB at a time).

    *gcs_prefix*: GCS directory URL, e.g. ``gs://wiemip/1pctCO2/input/GFDL-ESM4/05deg``
    *wiemip_dir*: local scratch directory for downloaded files (must exist).
    *reference_nc*: provides variable CF attributes only (units, standard_name).
    """
    year_start = int(year_start)
    year_end = int(year_end)
    if year_end < year_start:
        raise ValueError("year_end must be >= year_start")
    if not os.path.isdir(wiemip_dir):
        raise FileNotFoundError("wiemip_dir does not exist: {}".format(wiemip_dir))

    ref_attrs = _read_ref_attrs(reference_nc)

    coord_Y = coord_X = coord_lat = coord_lon = lat_ref = lon_ref = None
    n_years = year_end - year_start + 1

    for i, year in enumerate(range(year_start, year_end + 1)):
        print(
            "[{}/{}] year {}".format(i + 1, n_years, year),
            flush=True,
        )
        try:
            download_wiemip_year(gcs_prefix, file_prefix, wiemip_dir, year, verbose=True)
        except Exception as e:
            print("  ERROR downloading year {}: {}".format(year, e), file=sys.stderr, flush=True)
            raise

        p_tmp = wiemip_year_path(wiemip_dir, file_prefix, "tmp", year)
        p_pre = wiemip_year_path(wiemip_dir, file_prefix, "pre", year)
        p_sw = wiemip_year_path(wiemip_dir, file_prefix, "dswrf", year)
        p_q = wiemip_year_path(wiemip_dir, file_prefix, "spfh", year)
        p_p = wiemip_year_path(wiemip_dir, file_prefix, "pres", year)

        ds_tmp = ds_pre = ds_sw = ds_q = ds_p = None
        try:
            ds_tmp = _open_ds(p_tmp)
            ds_pre = _open_ds(p_pre)
            ds_sw = _open_ds(p_sw)
            ds_q = _open_ds(p_q)
            ds_p = _open_ds(p_p)

            if coord_Y is None:
                coord_Y, coord_X, coord_lat, coord_lon, lat_ref, lon_ref = (
                    _spatial_coords_from_wiemip(ds_tmp)
                )

            year_data = _process_year(ds_tmp, ds_pre, ds_sw, ds_q, ds_p, year, lat_ref, lon_ref)
        except Exception as e:
            print("  ERROR processing year {}: {}".format(year, e), file=sys.stderr, flush=True)
            raise
        finally:
            for ds in (ds_tmp, ds_pre, ds_sw, ds_q, ds_p):
                if ds is not None:
                    try:
                        ds.close()
                    except Exception:
                        pass
            delete_wiemip_year(wiemip_dir, file_prefix, year, verbose=True)

        if year == year_start:
            ds_year = _build_year_dataset(
                year_data, year, coord_Y, coord_X, coord_lat, coord_lon, ref_attrs
            )
            try:
                _write_first_year(output_nc, ds_year, engine)
            finally:
                ds_year.close()
        else:
            _append_year(output_nc, year_data, year)

        print("  year {} written to {}".format(year, output_nc), flush=True)

    print("Done. Output: {}".format(output_nc), flush=True)
