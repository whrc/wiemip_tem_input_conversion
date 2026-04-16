"""
Apply a run-mask to historic-climate.nc.

Pixels where run-mask == 0 (or NaN) are set to each variable's fill value.
Pixels where run-mask == 1 are kept unchanged.

Usage:
    python apply_run_mask_to_climate.py [mask.nc] [climate.nc] [output.nc]

Defaults:
    mask   : merge/merge/input/ssp1_2_6_mri_esm2_0/merged/half_deg/run-mask_merged_halfdeg.nc
    climate: ~/wiemip_tem_input_conversion/tem_output/historic-climate.nc
    output : merge/merge/input/ssp1_2_6_mri_esm2_0/merged/half_deg/historic-climate_masked.nc
"""

import os
import sys
from datetime import datetime, timezone

import numpy as np
import netCDF4 as nc

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_MASK = os.path.join(
    SCRIPT_DIR,
    "merge/input/ssp1_2_6_mri_esm2_0/merged/half_deg",
    "run-mask_merged_halfdeg.nc",
)
DEFAULT_CLIMATE = os.path.expanduser(
    "~/wiemip_tem_input_conversion/tem_output/historic-climate.nc"
)
DEFAULT_OUTPUT = os.path.join(
    SCRIPT_DIR,
    "merge/input/ssp1_2_6_mri_esm2_0/merged/half_deg",
    "historic-climate_masked.nc",
)

# Climate variables that carry the fill value and need masking
CLIMATE_VARS = ["tair", "precip", "nirr", "vapor_press"]


def apply_mask(mask_path: str, climate_path: str, output_path: str) -> None:
    with nc.Dataset(mask_path, "r") as mask_ds:
        run = mask_ds.variables["run"][:]          # (lat, lon)
        valid = (run == 1)                          # True where we keep data

    print(f"Mask shape : {run.shape}")
    print(f"Valid cells: {valid.sum()} / {valid.size}")

    with nc.Dataset(climate_path, "r") as src, nc.Dataset(output_path, "w") as dst:
        # --- dimensions ---
        for name, dim in src.dimensions.items():
            dst.createDimension(name, None if dim.isunlimited() else len(dim))

        # --- create all variables, copy attributes ---
        for name, var in src.variables.items():
            fill = var._FillValue if hasattr(var, "_FillValue") else None
            dst_var = dst.createVariable(
                name, var.datatype, var.dimensions,
                fill_value=fill,
                zlib=True, complevel=4,
            )
            attrs = {a: getattr(var, a) for a in var.ncattrs() if a != "_FillValue"}
            dst_var.setncatts(attrs)

        # --- write coordinate / auxiliary variables unchanged ---
        passthrough = [v for v in src.variables if v not in CLIMATE_VARS]
        for name in passthrough:
            dst.variables[name][:] = src.variables[name][:]
            print(f"  Copied  {name}")

        # --- apply mask to climate variables ---
        for vname in CLIMATE_VARS:
            src_var = src.variables[vname]
            fill_val = src_var._FillValue if hasattr(src_var, "_FillValue") else np.nan
            print(f"  Masking {vname} ...", end=" ", flush=True)

            data = src_var[:]                       # (time, Y, X)
            # broadcast mask over time axis: (Y, X) -> (1, Y, X)
            data[:, ~valid] = fill_val
            dst.variables[vname][:] = data
            print(f"done — shape {data.shape}, fill={fill_val}")

        # --- global attributes ---
        dst.setncatts({a: getattr(src, a) for a in src.ncattrs()})
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        existing_history = getattr(src, "history", "")
        dst.history = (
            f"{timestamp}: apply_run_mask_to_climate.py — "
            f"masked with {os.path.basename(mask_path)} (run==1 kept); "
            + existing_history
        )

    print(f"\nOutput written to: {output_path}")


def main():
    mask_path    = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MASK
    climate_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_CLIMATE
    output_path  = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_OUTPUT

    for label, path in [("mask", mask_path), ("climate", climate_path)]:
        if not os.path.isfile(path):
            sys.exit(f"Error: {label} file not found: {path}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    apply_mask(mask_path, climate_path, output_path)


if __name__ == "__main__":
    main()
