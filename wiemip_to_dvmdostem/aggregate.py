import numpy as np
import xarray as xr

SIX_HOUR_SECONDS = 6 * 3600


def _mask_year_monthly(da, year):
    """Keep only monthly bins whose cftime year equals *year* (drops resample spillover)."""
    times = da["time"].values
    mask = np.array([getattr(t, "year") == int(year) for t in times], dtype=bool)
    return da.isel(time=mask)


def monthly_mean_temperature_celsius(ds_tmp, year):
    """tmp (K) -> monthly mean tair (C)."""
    t_c = ds_tmp["tmp"] - 273.15
    m = t_c.resample(time="1M").mean()
    return _mask_year_monthly(m, year)


def monthly_precip_mm(ds_pre, year):
    """pre (kg m-2 s-1) -> monthly sum mm (kg m-2)."""
    depth = ds_pre["pre"] * SIX_HOUR_SECONDS
    m = depth.resample(time="1M").sum()
    return _mask_year_monthly(m, year)


def monthly_mean_dswrf(ds_dswrf, year):
    m = ds_dswrf["dswrf"].resample(time="1M").mean()
    return _mask_year_monthly(m, year)


def monthly_mean_vapor_pressure_hpa(ds_spfh, ds_pres, year):
    q = ds_spfh["spfh"]
    p = ds_pres["pres"]
    e_pa = q * p / (0.622 + 0.378 * q)
    e_hpa = e_pa / 100.0
    m = e_hpa.resample(time="1M").mean()
    return _mask_year_monthly(m, year)
