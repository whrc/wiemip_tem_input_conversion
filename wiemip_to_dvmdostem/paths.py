import os
import re
import subprocess
import sys


def wiemip_year_path(directory, file_prefix, wiemip_token, year):
    """Local path to one WIEMIP yearly 6-hourly file."""
    name = "{prefix}.{var}.{year}_6hr.noleap.nc".format(
        prefix=file_prefix, var=wiemip_token, year=int(year)
    )
    return os.path.join(directory, name)


_filename_re = re.compile(
    r"^(?P<prefix>.+)\.(?P<var>[a-z]+)\.(?P<year>\d{4})_6hr\.noleap\.nc$"
)


def parse_wiemip_filename(basename):
    """Return dict prefix, var, year or None if pattern does not match."""
    m = _filename_re.match(basename)
    if not m:
        return None
    return {
        "prefix": m.group("prefix"),
        "var": m.group("var"),
        "year": int(m.group("year")),
    }


# Variables required for the dvmdostem conversion
GCS_WIEMIP_VARS = ("tmp", "pre", "dswrf", "spfh", "pres")


def wiemip_gcs_year_url(gcs_prefix, file_prefix, wiemip_token, year):
    """GCS URL for one variable / year file."""
    name = "{prefix}.{var}.{year}_6hr.noleap.nc".format(
        prefix=file_prefix, var=wiemip_token, year=int(year)
    )
    return gcs_prefix.rstrip("/") + "/" + name


def download_wiemip_year(gcs_prefix, file_prefix, local_dir, year, verbose=True):
    """
    Download all GCS_WIEMIP_VARS files for *year* into *local_dir* using gsutil cp.

    Returns a list of local file paths that were downloaded.
    Raises subprocess.CalledProcessError on download failure.
    """
    gsutil = _find_gsutil()
    downloaded = []
    for var in GCS_WIEMIP_VARS:
        url = wiemip_gcs_year_url(gcs_prefix, file_prefix, var, year)
        dst = wiemip_year_path(local_dir, file_prefix, var, year)
        if verbose:
            print("  downloading {} → {}".format(url, dst), flush=True)
        subprocess.run(
            [gsutil, "cp", url, dst],
            check=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        downloaded.append(dst)
    return downloaded


def delete_wiemip_year(local_dir, file_prefix, year, verbose=True):
    """Delete local WIEMIP files for *year* (silently skips missing files)."""
    for var in GCS_WIEMIP_VARS:
        path = wiemip_year_path(local_dir, file_prefix, var, year)
        try:
            os.remove(path)
            if verbose:
                print("  deleted {}".format(path), flush=True)
        except OSError:
            pass


def _find_gsutil():
    """Return the path to gsutil, checking common locations."""
    candidates = [
        "gsutil",
        os.path.expanduser("~/google-cloud-sdk/bin/gsutil"),
        "/usr/bin/gsutil",
        "/usr/local/bin/gsutil",
    ]
    for c in candidates:
        try:
            subprocess.run(
                [c, "version"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return c
        except (OSError, subprocess.CalledProcessError):
            continue
    raise RuntimeError(
        "gsutil not found. Install the Google Cloud SDK or add gsutil to PATH."
    )
