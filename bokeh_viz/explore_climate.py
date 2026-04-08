"""
Interactive map viewer for converted climate NetCDF.

Layout: map on the left; variable list on the right (click to switch); time slider
and Play/Pause to step through time.

Run from the repository root (with venv activated):

  bokeh serve bokeh_viz/explore_climate.py --show

Pass a specific file via --args (highest priority):

  bokeh serve bokeh_viz/explore_climate.py --show --args /path/to/file.nc

Or via environment variable:

  WIEMIP_VIZ_NC=/path/to/file.nc bokeh serve bokeh_viz/explore_climate.py --show
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import xarray as xr
from bokeh.io import curdoc
from bokeh.layouts import column, row, Spacer
from bokeh.models import Button, ColorBar, ColumnDataSource, Div, LinearColorMapper, RadioGroup, Slider
from bokeh.palettes import Turbo256
from bokeh.plotting import figure

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_NC = _REPO_ROOT / "tmp" / "historic-climate-from-wiemip.nc"

# Priority: --args path  >  WIEMIP_VIZ_NC env var  >  default
if len(sys.argv) > 1 and sys.argv[1]:
    NC_PATH = sys.argv[1]
else:
    NC_PATH = os.environ.get("WIEMIP_VIZ_NC", str(_DEFAULT_NC))

_FILL_THRESHOLD = -998.0


def _open_dataset(path: str) -> xr.Dataset:
    if not os.path.isfile(path):
        raise FileNotFoundError(
            "NetCDF not found: {!r}. Set WIEMIP_VIZ_NC or create the file first.".format(path)
        )
    # Anaconda xarray often has netcdf4/scipy only; project venv uses h5netcdf. Try in order.
    last_err = None
    for engine in ("h5netcdf", "netcdf4", None):
        try:
            if engine is None:
                return xr.open_dataset(path)
            return xr.open_dataset(path, engine=engine)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(
        "Could not open NetCDF (tried engines h5netcdf, netcdf4, then default). "
        "Install one of: pip install h5netcdf  OR  conda install netcdf4. Last error: {!r}".format(
            last_err
        )
    ) from last_err


def _data_variable_names(ds: xr.Dataset):
    names = []
    for v in ds.data_vars:
        da = ds[v]
        dims = set(da.dims)
        if {"time", "Y", "X"}.issubset(dims):
            names.append(v)
    return names


def _slice_layer(ds: xr.Dataset, var: str, time_index: int) -> np.ndarray:
    z = ds[var].isel(time=time_index).values.astype(np.float64)
    z = np.where(np.isfinite(z) & (z > _FILL_THRESHOLD), z, np.nan)
    return z


def _color_limits(z: np.ndarray):
    valid = z[np.isfinite(z)]
    if valid.size == 0:
        return 0.0, 1.0
    lo, hi = float(np.nanpercentile(valid, 2)), float(np.nanpercentile(valid, 98))
    if lo >= hi:
        lo, hi = float(np.nanmin(valid)), float(np.nanmax(valid))
    if lo >= hi:
        lo, hi = lo - 1.0, hi + 1.0
    return lo, hi


def _time_label(ds: xr.Dataset, time_index: int) -> str:
    t = ds["time"]
    try:
        v = t.values[time_index]
        return str(v)
    except Exception:
        return str(time_index)


def build_ui():
    ds = _open_dataset(NC_PATH)
    var_names = _data_variable_names(ds)
    if not var_names:
        raise ValueError("No variables with dims (time, Y, X) in {!r}".format(NC_PATH))

    n_times = int(ds.sizes["time"])
    lon2d = ds["lon"].values
    lat2d = ds["lat"].values
    x0 = float(np.nanmin(lon2d))
    x1 = float(np.nanmax(lon2d))
    y0 = float(np.nanmin(lat2d))
    y1 = float(np.nanmax(lat2d))
    dw = x1 - x0
    dh = y1 - y0

    var0 = var_names[0]
    z0 = _slice_layer(ds, var0, 0)
    lo, hi = _color_limits(z0)
    mapper = LinearColorMapper(palette=Turbo256, low=lo, high=hi, nan_color="#444444")
    source = ColumnDataSource(
        data=dict(
            image=[z0],
            x=[x0],
            y=[y0],
            dw=[dw],
            dh=[dh],
        )
    )

    p = figure(
        title="{} — time 1/{}: {}".format(var0, n_times, _time_label(ds, 0)),
        x_range=(x0, x1),
        y_range=(y0, y1),
        width=880,
        height=560,
        x_axis_label="Longitude (degrees_east)",
        y_axis_label="Latitude (degrees_north)",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        active_scroll="wheel_zoom",
    )
    p.image(
        image="image",
        x="x",
        y="y",
        dw="dw",
        dh="dh",
        source=source,
        color_mapper=mapper,
    )
    color_bar = ColorBar(
        color_mapper=mapper,
        label_standoff=10,
        bar_line_color=None,
        location=(0, 0),
    )
    p.add_layout(color_bar, "right")

    slider = Slider(start=0, end=max(0, n_times - 1), value=0, step=1, title="Time index")
    play = Button(label="Play", button_type="success", width=80)
    playing = [False]

    radio = RadioGroup(labels=var_names, active=0, inline=False)

    header = Div(
        text="<h2>Climate fields</h2><p>Click a variable on the right. Use the slider or Play to change time.</p>",
        width=900,
    )
    path_div = Div(text="<code>{}</code>".format(NC_PATH), width=900)

    def update():
        var = var_names[radio.active]
        tidx = int(slider.value)
        z = _slice_layer(ds, var, tidx)
        lo2, hi2 = _color_limits(z)
        mapper.low = lo2
        mapper.high = hi2
        source.data = dict(image=[z], x=[x0], y=[y0], dw=[dw], dh=[dh])
        p.title.text = "{} — time {}/{}: {}".format(
            var, tidx + 1, n_times, _time_label(ds, tidx)
        )

    def on_radio(attr, old, new):
        update()

    def on_slider(attr, old, new):
        update()

    def toggle_play():
        playing[0] = not playing[0]
        play.label = "Pause" if playing[0] else "Play"

    def tick():
        if playing[0] and n_times > 0:
            slider.value = (int(slider.value) + 1) % n_times

    radio.on_change("active", on_radio)
    slider.on_change("value", on_slider)
    play.on_click(toggle_play)

    left = column(header, p, row(slider, Spacer(width=12), play), path_div)
    right = column(
        Div(text="<b>Variables</b>", width=200),
        radio,
        width=220,
    )
    layout = row(left, Spacer(width=16), right)

    doc = curdoc()
    doc.add_root(layout)
    doc.title = "WIEMIP / dvmdostem climate explorer"
    doc.add_periodic_callback(tick, 450)
    return doc


build_ui()
