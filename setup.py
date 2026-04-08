from setuptools import find_packages, setup

setup(
    name="wiemip-to-dvmdostem",
    version="0.1.0",
    description="Convert WIEMIP 6-hourly driver NetCDF to dvmdostem-style climate on native lat/lon grid",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=[
        "numpy>=1.19",
        "xarray>=0.19",
        "cftime>=1.5",
        "h5py>=3.1",
        "h5netcdf>=1.0",
        "pandas>=1.1",
        "importlib-metadata>=4.0,<5; python_version<'3.10'",
    ],
    extras_require={"gcs": ["gcsfs>=2021.10", "google-auth>=1.30"]},
    entry_points={"console_scripts": ["wiemip-to-dvmdostem=wiemip_to_dvmdostem.cli:main"]},
)
