"""
Schemas and WIEMIP → dvmdostem-style climate variable mapping.

Legacy dvmdostem example (circumpolar historic-climate.nc)
----------------------------------------------------------
Some projects use a **projected** grid: time (monthly), Y=100, X=100, with lat(Y,X) and lon(Y,X)
on an Albers (or similar) projection, grid_mapping albers_conical_equal_area, etc.

Output of this converter (native WIEMIP grid)
---------------------------------------------
Dimensions: time (monthly), Y = len(WIEMIP lat), X = len(WIEMIP lon) (e.g. 360×720 at 0.5°).
Coordinates:
  - Y(Y): latitude values (degrees north), same as WIEMIP *lat* axis.
  - X(X): longitude values (degrees east), same as WIEMIP *lon* axis.
  - lat(Y,X), lon(Y,X): 2D latitude/longitude (meshgrid) for CF-style geolocation.
Data variables (all (time, Y, X)):
  - tair: celsius, standard_name air_temperature
  - precip: mm month-1, standard_name precipitation_amount
  - nirr: W m-2, standard_name downwelling_shortwave_flux_in_air
  - vapor_press: hPa, standard_name water_vapor_pressure
Fill: _FillValue -999 on data variables. No projected grid_mapping (geographic lat/lon).

Time encoding: days since 1901-01-01, calendar 365_day, monthly bounds consistent with
the reference template used only for time length and variable metadata.

WIEMIP driver files (example GFDL-ESM4 05deg 6hr)
-------------------------------------------------
Pattern: {prefix}.{var}.{year}_6hr.noleap.nc
Dimensions: time=1460 per year (6-hourly noleap), lat=360, lon=720 (0.5° grid, lon -179.75..179.75).
Per-variable NetCDF name equals the short token in the filename (tmp, pre, dswrf, ...).
"""

# WIEMIP file token -> NetCDF variable name (same string in practice)
WIEMIP_FILE_TOKENS = ("dlwrf", "dswrf", "pre", "pres", "spfh", "tmp", "wind")

# Variables required to populate the target historic-climate fields
WIEMIP_INPUTS_FOR_TARGET = ("tmp", "pre", "dswrf", "spfh", "pres")

TARGET_CALENDAR = "365_day"
TARGET_TIME_UNITS = "days since 1901-01-01"
TARGET_FILL = -999.0

# Explicit mapping: WIEMIP field -> target field name and transformation notes
VARIABLE_MAP = (
    {
        "wiemip_file": "tmp",
        "wiemip_nc_var": "tmp",
        "target_name": "tair",
        "wiemip_units": "K",
        "target_units": "celsius",
        "aggregate": "mean",
        "transform": "subtract_273.15",
    },
    {
        "wiemip_file": "pre",
        "wiemip_nc_var": "pre",
        "target_name": "precip",
        "wiemip_units": "kg m-2 s-1",
        "target_units": "mm month-1",
        "aggregate": "sum_mass",
        "transform": "integrate_6h",
        "note": "Each 6 h sample is multiplied by 21600 s before summing over the month.",
    },
    {
        "wiemip_file": "dswrf",
        "wiemip_nc_var": "dswrf",
        "target_name": "nirr",
        "wiemip_units": "W m-2",
        "target_units": "W m-2",
        "aggregate": "mean",
        "transform": "identity",
    },
    {
        "wiemip_file": "spfh",
        "wiemip_nc_var": "spfh",
        "target_name": "vapor_press",
        "wiemip_units": "kg kg-1",
        "target_units": "hPa",
        "aggregate": "mean",
        "transform": "vapor_pressure_from_specific_humidity",
        "pressure_var": "pres",
        "note": "e = q*p/(0.622 + 0.378*q) with q=spfh, p=pres (Pa); result converted to hPa.",
    },
)
