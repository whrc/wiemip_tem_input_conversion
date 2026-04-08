from __future__ import print_function

import argparse
import sys

from wiemip_to_dvmdostem.convert import convert_wiemip_streaming, convert_wiemip_to_dvmdostem
from wiemip_to_dvmdostem.convert_co2 import convert_co2
from wiemip_to_dvmdostem.inspect_tools import describe_climate_nc
from wiemip_to_dvmdostem.paths import parse_wiemip_filename


def _cmd_inspect_reference(args):
    print(describe_climate_nc(args.netcdf))


def _cmd_convert(args):
    if args.gcs_prefix:
        if not args.wiemip_dir:
            print(
                "error: --wiemip-dir is required as a local scratch directory when --gcs-prefix is set",
                file=sys.stderr,
            )
            sys.exit(1)
        convert_wiemip_streaming(
            gcs_prefix=args.gcs_prefix,
            file_prefix=args.file_prefix,
            wiemip_dir=args.wiemip_dir,
            reference_nc=args.reference_nc,
            year_start=args.year_start,
            year_end=args.year_end,
            output_nc=args.output,
        )
    else:
        convert_wiemip_to_dvmdostem(
            wiemip_dir=args.wiemip_dir,
            file_prefix=args.file_prefix,
            reference_nc=args.reference_nc,
            year_start=args.year_start,
            year_end=args.year_end,
            output_nc=args.output,
        )
        print("Wrote", args.output)


def _cmd_convert_co2(args):
    convert_co2(
        source=args.source,
        output_nc=args.output,
        verbose=True,
    )


def _cmd_list_wiemip_vars(args):
    import os

    seen = set()
    if os.path.isdir(args.directory):
        for name in sorted(os.listdir(args.directory)):
            info = parse_wiemip_filename(name)
            if info and info["prefix"] == args.file_prefix:
                seen.add(info["var"])
    else:
        print("Not a directory: {}".format(args.directory), file=sys.stderr)
        sys.exit(1)
    for v in sorted(seen):
        print(v)


def main(argv=None):
    p = argparse.ArgumentParser(description="WIEMIP → dvmdostem-style historic-climate NetCDF")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("inspect-reference", help="Print variables, units, and time summary")
    pi.add_argument("netcdf", help="Path to reference NetCDF (e.g. historic-climate.nc)")
    pi.set_defaults(func=_cmd_inspect_reference)

    pc = sub.add_parser(
        "convert",
        help="Convert WIEMIP yearly 6hr files to climate NetCDF on native WIEMIP Y×X grid",
    )
    pc.add_argument(
        "--wiemip-dir",
        required=False,
        default=None,
        help=(
            "Local directory with WIEMIP *.nc files (offline mode), "
            "or scratch directory for downloads (streaming mode with --gcs-prefix)"
        ),
    )
    pc.add_argument(
        "--file-prefix",
        required=True,
        help="Filename prefix, e.g. GFDL-ESM4_clim3_50perc_1pctCO2",
    )
    pc.add_argument(
        "--reference-nc",
        required=True,
        help=(
            "Template NetCDF: only data-variable metadata "
            "(units, standard_name) are used; horizontal grid comes from WIEMIP lat/lon"
        ),
    )
    pc.add_argument("--year-start", type=int, required=True)
    pc.add_argument("--year-end", type=int, required=True)
    pc.add_argument("--output", required=True, help="Output NetCDF path")
    pc.add_argument(
        "--gcs-prefix",
        default=None,
        help=(
            "GCS directory prefix, e.g. gs://wiemip/1pctCO2/input/GFDL-ESM4/05deg. "
            "When set, files are downloaded year-by-year via gsutil cp and deleted "
            "after each year is processed (streaming mode). "
            "--wiemip-dir is used as a local scratch directory."
        ),
    )
    pc.set_defaults(func=_cmd_convert)

    pco2 = sub.add_parser(
        "convert-co2",
        help=(
            "Download WIEMIP_1pctco2.txt (from GCS or local) and convert it "
            "to a dvmdostem-style co2.nc"
        ),
    )
    pco2.add_argument(
        "--source",
        default="gs://wiemip/1pctCO2/input/co2/WIEMIP_1pctco2.txt",
        help=(
            "GCS URI or local path to the WIEMIP CO2 text file "
            "(default: gs://wiemip/1pctCO2/input/co2/WIEMIP_1pctco2.txt)"
        ),
    )
    pco2.add_argument(
        "--output",
        default="co2.nc",
        help="Output NetCDF path (default: co2.nc)",
    )
    pco2.set_defaults(func=_cmd_convert_co2)

    pl = sub.add_parser(
        "list-wiemip-vars",
        help="List unique WIEMIP variable tokens for a prefix in a local directory",
    )
    pl.add_argument("--directory", required=True)
    pl.add_argument("--file-prefix", required=True)
    pl.set_defaults(func=_cmd_list_wiemip_vars)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
