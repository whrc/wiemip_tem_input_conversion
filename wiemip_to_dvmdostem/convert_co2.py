"""Convert the WIEMIP 1pctCO2 text file to a dvmdostem-style co2.nc.

The WIEMIP source file (``WIEMIP_1pctco2.txt``) is a two-column space-delimited
table::

    year  co2_ppm
    1850  280
    1851  283
    ...

The output NetCDF mirrors the layout of the dvmdostem reference ``co2.nc``::

    dimensions:
        year = UNLIMITED ;
    variables:
        float co2(year) ;
        int64 year(year) ;

Usage (module)::

    from wiemip_to_dvmdostem.convert_co2 import convert_co2

    convert_co2(
        source="gs://wiemip/1pctCO2/input/co2/WIEMIP_1pctco2.txt",
        output_nc="co2.nc",
    )

The ``source`` argument accepts:

* a GCS URI (``gs://…``) — downloaded via ``gsutil cp`` then removed,
* a local file path.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

import numpy as np


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_gsutil() -> str:
    """Return the path to gsutil, raising RuntimeError if not found."""
    import shutil

    candidate = shutil.which("gsutil")
    if candidate:
        return candidate
    for prefix in ("/usr/local/bin", "/usr/bin", os.path.expanduser("~/.local/bin")):
        full = os.path.join(prefix, "gsutil")
        if os.path.isfile(full):
            return full
    raise RuntimeError(
        "gsutil not found on PATH. "
        "Install the Google Cloud SDK: https://cloud.google.com/sdk/install"
    )


def _download_gcs(gcs_uri: str, local_path: str, verbose: bool = True) -> None:
    gsutil = _find_gsutil()
    cmd = [gsutil, "cp", gcs_uri, local_path]
    if verbose:
        print("Downloading {} …".format(gcs_uri))
    result = subprocess.run(cmd, capture_output=not verbose)
    if result.returncode != 0:
        raise RuntimeError(
            "gsutil cp failed (exit {}): {}".format(
                result.returncode, result.stderr.decode() if result.stderr else ""
            )
        )


def _parse_txt(path: str) -> tuple[np.ndarray, np.ndarray]:
    """Parse the two-column CO2 text file, return (years, co2_values)."""
    years, values = [], []
    with open(path) as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                raise ValueError(
                    "Line {}: expected 2 columns, got {!r}".format(lineno, line)
                )
            years.append(int(parts[0]))
            values.append(float(parts[1]))
    return np.array(years, dtype=np.int64), np.array(values, dtype=np.float32)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def convert_co2(
    source: str,
    output_nc: str,
    verbose: bool = True,
) -> None:
    """Download (if needed) and convert the WIEMIP CO2 text file to NetCDF.

    Parameters
    ----------
    source:
        GCS URI (``gs://…``) or local path to the WIEMIP CO2 text file.
    output_nc:
        Destination NetCDF file path.
    verbose:
        Print progress messages.
    """
    import h5py

    tmp_txt: str | None = None

    try:
        # ---- resolve source ------------------------------------------------
        if source.startswith("gs://"):
            fd, tmp_txt = tempfile.mkstemp(suffix=".txt", prefix="wiemip_co2_")
            os.close(fd)
            _download_gcs(source, tmp_txt, verbose=verbose)
            txt_path = tmp_txt
        else:
            txt_path = source

        # ---- parse ---------------------------------------------------------
        if verbose:
            print("Parsing {} …".format(txt_path))
        years, co2 = _parse_txt(txt_path)

        if verbose:
            print(
                "  {} years: {} – {} | CO2 range: {:.1f} – {:.1f} ppm".format(
                    len(years), int(years[0]), int(years[-1]),
                    float(co2.min()), float(co2.max()),
                )
            )

        # ---- write NetCDF --------------------------------------------------
        out_dir = os.path.dirname(os.path.abspath(output_nc))
        os.makedirs(out_dir, exist_ok=True)

        if verbose:
            print("Writing {} …".format(output_nc))

        with h5py.File(output_nc, "w") as f:
            # Create dimensions
            n = len(years)

            # year — UNLIMITED (maxshape=None)
            ds_year = f.create_dataset(
                "year",
                data=years,
                dtype=np.int64,
                maxshape=(None,),
                chunks=(min(n, 512),),
                compression=None,
            )
            ds_year.dims[0].label = "year"

            # co2
            ds_co2 = f.create_dataset(
                "co2",
                data=co2,
                dtype=np.float32,
                maxshape=(None,),
                chunks=(min(n, 512),),
                compression=None,
            )
            ds_co2.dims[0].label = "year"

            # --- attach dimension scale so xarray recognises coordinates ---
            f["year"].make_scale("year")
            f["co2"].dims[0].attach_scale(f["year"])

            # --- NetCDF4/CF conventions for xarray --------------------------
            #  Mark year as a coordinate variable (same name as dimension)
            f.attrs["Conventions"] = "CF-1.8"
            f.attrs["data_source"] = (
                "gs://wiemip/1pctCO2/input/co2/WIEMIP_1pctco2.txt"
            )
            f.attrs["source"] = "wiemip_to_dvmdostem.convert_co2"

        if verbose:
            print("Done. Wrote {} rows to {}.".format(n, output_nc))

    finally:
        if tmp_txt and os.path.exists(tmp_txt):
            os.remove(tmp_txt)
