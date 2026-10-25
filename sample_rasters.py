#!/usr/bin/env python3
"""
Raster point sampler.

Sample a stack of rasters (GeoTIFFs or any format GDAL reads) at point
locations and write one table: one row per point and one column per raster
(and band). Points can come from a shapefile, GeoPackage, GeoJSON or a CSV
with longitude/latitude columns.

Points are reprojected to each raster's CRS automatically, and nodata and
out-of-extent points become empty cells instead of junk values.

Examples
--------
    python sample_rasters.py --points FloodPoints.shp \
        --rasters "maps/*.tif" --out results.xlsx

    python sample_rasters.py --points stations.csv --lon-col lon --lat-col lat \
        --rasters "era5/*.tif" --name-regex "(\\d{8})" --out samples.csv

Author: Parisa Abbasalizadehrezaei · https://risarezaei.github.io
License: MIT
"""
from __future__ import annotations

import argparse
import glob
import logging
import re
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

log = logging.getLogger("sampler")


def read_points(path: Path, lon_col: str, lat_col: str, crs: str) -> gpd.GeoDataFrame:
    """Read points from a vector file or a CSV with coordinate columns."""
    if path.suffix.lower() in {".csv", ".txt"}:
        df = pd.read_csv(path)
        missing = {lon_col, lat_col} - set(df.columns)
        if missing:
            raise SystemExit(f"CSV is missing column(s): {sorted(missing)}")
        return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[lon_col], df[lat_col]), crs=crs)
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        log.warning("points have no CRS; assuming %s", crs)
        gdf = gdf.set_crs(crs)
    if not all(gdf.geometry.geom_type == "Point"):
        log.warning("non-point geometries found; using their centroids")
        gdf["geometry"] = gdf.geometry.centroid
    return gdf


def column_name(path: Path, regex: str | None, band: int, nbands: int) -> str:
    """Column name from the file name (optionally a regex capture) and band."""
    name = path.stem
    if regex:
        m = re.search(regex, path.name)
        if m:
            name = m.group(1) if m.groups() else m.group(0)
        else:
            log.warning("regex did not match %s; using file name", path.name)
    return name if nbands == 1 else f"{name}_b{band}"


def sample_raster(path: Path, points: gpd.GeoDataFrame, bands: list[int] | None,
                  regex: str | None) -> dict[str, np.ndarray]:
    """Return {column: values} for one raster."""
    out: dict[str, np.ndarray] = {}
    with rasterio.open(path) as src:
        pts = points.to_crs(src.crs) if src.crs and points.crs != src.crs else points
        coords = list(zip(pts.geometry.x, pts.geometry.y))
        use = bands or list(range(1, src.count + 1))
        bad = [b for b in use if b < 1 or b > src.count]
        if bad:
            raise SystemExit(f"{path.name} has {src.count} band(s); cannot read {bad}")

        values = np.array(list(src.sample(coords, indexes=use)), dtype="float64")  # (n, bands)

        # Nodata -> NaN (per band)
        for j, band in enumerate(use):
            nd = src.nodatavals[band - 1]
            if nd is not None:
                values[np.isclose(values[:, j], nd) | (np.isnan(nd) & np.isnan(values[:, j])), j] = np.nan

        # Points outside the raster extent come back as 0/nodata; blank them.
        b = src.bounds
        inside = np.array([(b.left <= x <= b.right) and (b.bottom <= y <= b.top) for x, y in coords])
        values[~inside, :] = np.nan

        for j, band in enumerate(use):
            out[column_name(path, regex, band, len(use))] = values[:, j]
    return out


def write_table(df: pd.DataFrame, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    suffix = out.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        df.to_excel(out, index=False)
    elif suffix == ".csv":
        df.to_csv(out, index=False)
    elif suffix in {".gpkg", ".geojson", ".shp"}:
        gpd.GeoDataFrame(df, geometry="geometry", crs=df.attrs.get("crs")).to_file(out)
    else:
        raise SystemExit(f"Unsupported output format: {suffix} (use .xlsx, .csv, .gpkg, .geojson)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Sample many rasters at point locations into one table.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--points", required=True, type=Path, help="points: .shp/.gpkg/.geojson or .csv")
    p.add_argument("--rasters", required=True, nargs="+",
                   help="raster files or glob patterns (quote them), e.g. 'maps/*.tif'")
    p.add_argument("--out", required=True, type=Path, help="output .xlsx, .csv, .gpkg or .geojson")
    p.add_argument("--keep", nargs="+", help="point attribute columns to keep (default: all)")
    p.add_argument("--bands", nargs="+", type=int, help="band numbers to sample (default: all)")
    p.add_argument("--name-regex", help="regex for column names from file names, e.g. '(\\d{8})'")
    p.add_argument("--lon-col", default="lon", help="longitude column for CSV points")
    p.add_argument("--lat-col", default="lat", help="latitude column for CSV points")
    p.add_argument("--points-crs", default="EPSG:4326", help="CRS of CSV points / points without CRS")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    if a.out.suffix.lower() not in {".xlsx", ".xls", ".csv", ".gpkg", ".geojson", ".shp"}:
        raise SystemExit(f"Unsupported output format: {a.out.suffix} (use .xlsx, .csv, .gpkg, .geojson)")

    files = sorted({Path(f) for pattern in a.rasters for f in glob.glob(pattern)})
    if not files:
        raise SystemExit(f"No rasters matched {a.rasters}")
    points = read_points(a.points, a.lon_col, a.lat_col, a.points_crs)
    log.info("%d points, %d rasters", len(points), len(files))

    table = points.copy()
    if a.keep:
        table = table[[c for c in a.keep if c in table.columns] + ["geometry"]]

    columns: dict[str, np.ndarray] = {}
    for i, f in enumerate(files, 1):
        log.info("[%d/%d] %s", i, len(files), f.name)
        for col, vals in sample_raster(f, points, a.bands, a.name_regex).items():
            if col in columns:
                log.warning("duplicate column name '%s'; adding suffix", col)
                col = f"{col}_{i}"
            columns[col] = vals

    table = pd.concat([table.reset_index(drop=True), pd.DataFrame(columns)], axis=1)
    if a.out.suffix.lower() in {".xlsx", ".xls", ".csv"}:
        geo = table.geometry.to_crs("EPSG:4326") if points.crs else table.geometry
        table = pd.DataFrame(table.drop(columns="geometry"))
        table.insert(0, "lat_wgs84", geo.y.round(6).values)
        table.insert(0, "lon_wgs84", geo.x.round(6).values)
    else:
        table.attrs["crs"] = points.crs

    write_table(table, a.out)
    n_missing = int(pd.DataFrame(columns).isna().sum().sum())
    log.info("wrote %s (%d rows x %d raster columns, %d empty cells)",
             a.out, len(table), len(columns), n_missing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
