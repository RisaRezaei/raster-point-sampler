# Raster Point Sampler

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![rasterio](https://img.shields.io/badge/built%20with-rasterio%20%C2%B7%20GeoPandas-2E7D32)](https://rasterio.readthedocs.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Extract values from **many rasters at many points** in one command and get a single table (Excel, CSV or GeoPackage): one row per point and one column per raster. Typical uses are pulling time series from a folder of daily or monthly maps at monitoring stations, flood points or field sites.

## Features

- **Any point source**: shapefile, GeoPackage, GeoJSON, or CSV with lon/lat columns
- **Any raster stack**: glob patterns such as `"maps/*.tif"`, single- or multi-band
- **Automatic reprojection**: points are transformed to each raster's CRS
- **Clean values**: nodata and points outside a raster become empty cells, not junk numbers
- **Readable column names**: from file names, or a regex capture such as a date (`--name-regex "(\d{8})"`)
- **Output**: `.xlsx`, `.csv` (with WGS84 lon/lat added), `.gpkg` or `.geojson`

## Installation

```bash
git clone https://github.com/RisaRezaei/raster-point-sampler.git
cd raster-point-sampler
pip install -r requirements.txt
```

## Usage

```bash
# Points from a shapefile, all GeoTIFFs in a folder -> Excel
python sample_rasters.py --points FloodPoints.shp --rasters "maps/*.tif" --out results.xlsx

# CSV points, date taken from file names like precip_20240101.tif
python sample_rasters.py --points stations.csv --lon-col lon --lat-col lat \
    --rasters "precip/*.tif" --name-regex "(\d{8})" --out precip_at_stations.csv

# Keep only some attributes, sample band 1 only, write a GeoPackage
python sample_rasters.py --points sites.gpkg --keep site_id Time \
    --rasters "stack/*.tif" --bands 1 --out sites_sampled.gpkg
```

### Options

| Option | Description |
|---|---|
| `--points` | Points file (`.shp`, `.gpkg`, `.geojson`, `.csv`) |
| `--rasters` | One or more raster files or quoted glob patterns |
| `--out` | Output `.xlsx`, `.csv`, `.gpkg` or `.geojson` |
| `--keep` | Point attributes to keep (default: all) |
| `--bands` | Band numbers to sample (default: all bands) |
| `--name-regex` | Regex for column names; the first capture group is used |
| `--lon-col` / `--lat-col` | Coordinate columns for CSV input (default `lon` / `lat`) |
| `--points-crs` | CRS for CSV points or files without a CRS (default `EPSG:4326`) |

## Output example

| lon_wgs84 | lat_wgs84 | id | 20240101 | 20240201 |
|---|---|---|---|---|
| 45.50 | 35.50 | 2 | 45.0 | 7.0 |
| 60.00 | 10.00 | 3 | *(empty: outside raster)* | |

Multi-band rasters get one column per band (`name_b1`, `name_b2`, …).

## Author

**Parisa Abbasalizadehrezaei** · [risarezaei.github.io](https://risarezaei.github.io)

Released under the [MIT License](LICENSE).
