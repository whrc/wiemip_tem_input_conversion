# wiemip_input_conversion

Convert [WIEMIP](https://jules.jchmr.org/content/wiemip) 6-hourly climate driver files to the
[dvmdostem](https://github.com/uaf-arctic-eco-modeling/dvm-dos-tem) `historic-climate.nc` layout.

---

## What it does

WIEMIP provides per-year, per-variable NetCDF files on a global 0.5° geographic grid
(lat × lon, noleap calendar, 6-hourly).  This tool:

1. Downloads files year-by-year from Google Cloud Storage with `gsutil cp`.
2. Aggregates each variable from 6-hourly to **monthly** (mean or flux-sum).
3. Applies unit conversions (K → °C, kg m⁻² s⁻¹ → mm month⁻¹, kg/kg + Pa → hPa).
4. Writes a single NetCDF with dimensions **`(time, Y, X)`** where `Y` is the latitude
   axis and `X` is the longitude axis — matching the dvmdostem climate file convention.
5. Deletes each year's raw download before fetching the next year (~1.5 GB peak disk use).

### Variable mapping

| WIEMIP token | WIEMIP units  | dvmdostem variable | Output units  |
|--------------|---------------|--------------------|---------------|
| `tmp`        | K             | `tair`             | celsius       |
| `pre`        | kg m⁻² s⁻¹   | `precip`           | mm month⁻¹   |
| `dswrf`      | W m⁻²        | `nirr`             | W m⁻²        |
| `spfh` + `pres` | kg/kg, Pa  | `vapor_press`      | hPa           |

---

## Requirements

- Python ≥ 3.7
- [Google Cloud SDK](https://cloud.google.com/sdk) (`gsutil`) — authenticated and on `PATH`
- Python packages (install from project root):

```bash
pip install -e .
# or
pip install -r requirements.txt
```

For the interactive visualiser, also install Bokeh (see [bokeh_viz/requirements.txt](bokeh_viz/requirements.txt)):

```bash
pip install -r bokeh_viz/requirements.txt
```

---

## Usage

### 1 — Stream from GCS (recommended for large year ranges)

Downloads, converts, and appends one year at a time. Scratch files are deleted after each year.

```bash
python -m wiemip_to_dvmdostem convert \
  --gcs-prefix gs://wiemip/1pctCO2/input/GFDL-ESM4/05deg \
  --wiemip-dir /path/to/scratch \
  --file-prefix GFDL-ESM4_clim3_50perc_1pctCO2 \
  --reference-nc path/to/historic-climate.nc \
  --year-start 1850 --year-end 2000 \
  --output historic-climate-from-wiemip.nc
```

`--wiemip-dir` is a local scratch directory (must exist, ~1.5 GB free space needed).  
`--reference-nc` supplies only variable metadata (units, standard_name); the output grid comes from the WIEMIP files.

### 2 — Convert from pre-downloaded local files

If WIEMIP files are already on disk, omit `--gcs-prefix`:

```bash
python -m wiemip_to_dvmdostem convert \
  --wiemip-dir /path/to/local_wiemip \
  --file-prefix GFDL-ESM4_clim3_50perc_1pctCO2 \
  --reference-nc path/to/historic-climate.nc \
  --year-start 1850 --year-end 2000 \
  --output historic-climate-from-wiemip.nc
```

### 3 — Convert WIEMIP CO2 text file

Downloads `WIEMIP_1pctco2.txt` from GCS (or uses a local copy) and writes a
dvmdostem-style `co2.nc` with dimensions `year(UNLIMITED)` and variables
`float co2(year)` / `int64 year(year)`.

```bash
# from GCS (default source):
python -m wiemip_to_dvmdostem convert-co2 --output co2.nc

# custom source / output:
python -m wiemip_to_dvmdostem convert-co2 \
  --source gs://wiemip/1pctCO2/input/co2/WIEMIP_1pctco2.txt \
  --output /path/to/co2.nc
```

### 4 — Inspect a reference file

```bash
python -m wiemip_to_dvmdostem inspect-reference path/to/historic-climate.nc
```

### 5 — List unique WIEMIP variable tokens in a local directory

```bash
python -m wiemip_to_dvmdostem list-wiemip-vars \
  --directory /path/to/local_wiemip \
  --file-prefix GFDL-ESM4_clim3_50perc_1pctCO2
```

---

## Output format

```
netcdf historic-climate-from-wiemip {
dimensions:
    time = UNLIMITED ;   // monthly steps
    Y = 360 ;            // latitude axis  (-89.75 … 89.75)
    X = 720 ;            // longitude axis (-179.75 … 179.75)
variables:
    float tair(time, Y, X) ;        // celsius
    float precip(time, Y, X) ;      // mm month-1
    float nirr(time, Y, X) ;        // W m-2
    float vapor_press(time, Y, X) ; // hPa
    double time(time) ;             // days since 1901-01-01, calendar 365_day
    float Y(Y) ;                    // latitude values
    float X(X) ;                    // longitude values
    float lat(Y, X) ;               // 2D latitude  (CF geolocation)
    float lon(Y, X) ;               // 2D longitude (CF geolocation)
}
```

---

## Interactive visualiser

Launch a Bokeh server app to explore the output file:

```bash
# default file (tmp/historic-climate-from-wiemip.nc):
bokeh serve bokeh_viz/explore_climate.py --show

# specific file:
bokeh serve bokeh_viz/explore_climate.py --show --args /path/to/file.nc

# or via environment variable:
WIEMIP_VIZ_NC=/path/to/file.nc bokeh serve bokeh_viz/explore_climate.py --show
```

The app shows:
- **Left panel** — world map of the selected variable at the current time step.
- **Right panel** — variable selector (click to switch between `tair`, `precip`, `nirr`, `vapor_press`).
- **Bottom** — time slider and Play/Pause button to step through all months.

---

## Project layout

```
wiemip_input_conversion/
├── wiemip_to_dvmdostem/
│   ├── cli.py           # CLI entry-point (subcommands: convert, inspect-reference, list-wiemip-vars)
│   ├── convert.py       # Batch and streaming conversion logic
│   ├── aggregate.py     # 6-hourly → monthly aggregations and unit conversions
│   ├── paths.py         # Filename helpers, GCS download/delete via gsutil
│   ├── schema.py        # Variable map, target calendar / fill-value constants
│   └── inspect_tools.py # Human-readable summary of a NetCDF file
├── bokeh_viz/
│   ├── explore_climate.py  # Interactive Bokeh visualiser
│   └── requirements.txt
├── requirements.txt
├── setup.py
└── README.md
```

---

## WIEMIP data on GCS

| Path | Description |
|------|-------------|
| `gs://wiemip/1pctCO2/input/GFDL-ESM4/05deg/` | 0.5° 1pctCO2 experiment, GFDL-ESM4 |

File naming: `{prefix}.{var}.{year}_6hr.noleap.nc`  
Variables: `dlwrf`, `dswrf`, `pre`, `pres`, `spfh`, `tmp`, `wind`  
Time: 1460 steps per year (6-hourly, noleap calendar)

## dvmdostem reference data on GCS

| Path | Description |
|------|-------------|
| `gs://circumpolar_model_output/recent2/H10_V18/ssp1_2_6_mri_esm2_0/historic-climate.nc` | Example target file |

Reference file variables: `tair` (celsius), `precip` (mm month⁻¹), `nirr` (W m⁻²), `vapor_press` (hPa).  
Time: monthly, 1901-01 to 2024-12, calendar `365_day`.
