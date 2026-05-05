from __future__ import annotations

from pathlib import Path
import csv
import html
from datetime import datetime

import numpy as np
from osgeo import gdal
from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsVectorFileWriter
from qgis.analysis import QgsZonalStatistics
import processing


def _read_cn_lookup(csv_path: str) -> dict[tuple[int, int], float]:
    table: dict[tuple[int, int], float] = {}
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"LULC_code", "CN_A", "CN_B", "CN_C", "CN_D"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"CN lookup CSV must contain columns: {sorted(required)}")
        for row in reader:
            lulc = int(float(row["LULC_code"]))
            table[(lulc, 1)] = float(row["CN_A"])
            table[(lulc, 2)] = float(row["CN_B"])
            table[(lulc, 3)] = float(row["CN_C"])
            table[(lulc, 4)] = float(row["CN_D"])
    return table


def _raster_info(path: str) -> dict[str, object]:
    ds = gdal.Open(path)
    if ds is None:
        raise ValueError(f"Cannot open raster: {path}")
    gt = ds.GetGeoTransform()
    band = ds.GetRasterBand(1)
    return {
        "path": path,
        "cols": ds.RasterXSize,
        "rows": ds.RasterYSize,
        "pixel_x": gt[1],
        "pixel_y": abs(gt[5]),
        "extent": (gt[0], gt[3] + ds.RasterYSize * gt[5], gt[0] + ds.RasterXSize * gt[1], gt[3]),
        "nodata": band.GetNoDataValue(),
        "projection": ds.GetProjectionRef(),
    }


def _unique_values(path: str) -> set[int]:
    ds = gdal.Open(path)
    band = ds.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    arr = band.ReadAsArray()
    if nodata is not None:
        arr = arr[arr != nodata]
    arr = arr[np.isfinite(arr)]
    return {int(v) for v in np.unique(arr)}


def _write_float_raster(reference_path: str, output_path: str, array: np.ndarray, nodata: float = -9999.0) -> None:
    ref = gdal.Open(reference_path)
    driver = gdal.GetDriverByName("GTiff")
    out = driver.Create(
        output_path,
        ref.RasterXSize,
        ref.RasterYSize,
        1,
        gdal.GDT_Float32,
        options=["COMPRESS=LZW", "TILED=YES"],
    )
    out.SetGeoTransform(ref.GetGeoTransform())
    out.SetProjection(ref.GetProjection())
    band = out.GetRasterBand(1)
    band.SetNoDataValue(nodata)
    band.WriteArray(array.astype(np.float32))
    band.FlushCache()
    out.FlushCache()
    out = None


def _build_cn2_cn3_rasters(lulc_path: str, hsg_path: str, cn_lookup: dict[tuple[int, int], float], cn2_path: str, cn3_path: str) -> dict[str, object]:
    lulc_ds = gdal.Open(lulc_path)
    hsg_ds = gdal.Open(hsg_path)
    lulc_band = lulc_ds.GetRasterBand(1)
    hsg_band = hsg_ds.GetRasterBand(1)
    lulc_nodata = lulc_band.GetNoDataValue()
    hsg_nodata = hsg_band.GetNoDataValue()
    lulc = lulc_band.ReadAsArray()
    hsg = hsg_band.ReadAsArray()

    nodata = -9999.0
    cn2 = np.full(lulc.shape, nodata, dtype=np.float32)
    matched = np.zeros(lulc.shape, dtype=bool)

    valid = np.ones(lulc.shape, dtype=bool)
    if lulc_nodata is not None:
        valid &= lulc != lulc_nodata
    if hsg_nodata is not None:
        valid &= hsg != hsg_nodata

    for (lulc_code, hsg_code), cn in cn_lookup.items():
        mask = valid & (lulc == lulc_code) & (hsg == hsg_code)
        cn2[mask] = cn
        matched |= mask

    cn3 = np.full(lulc.shape, nodata, dtype=np.float32)
    valid_cn2 = cn2 != nodata
    cn3[valid_cn2] = (23.0 * cn2[valid_cn2]) / (10.0 + 0.13 * cn2[valid_cn2])

    _write_float_raster(lulc_path, cn2_path, cn2, nodata)
    _write_float_raster(lulc_path, cn3_path, cn3, nodata)

    unknown_lulc = sorted({int(v) for v in np.unique(lulc[valid & ~matched])}) if np.any(valid & ~matched) else []
    unknown_hsg = sorted({int(v) for v in np.unique(hsg[valid & ~matched])}) if np.any(valid & ~matched) else []
    return {
        "matched_pixels": int(np.count_nonzero(matched)),
        "unmatched_pixels": int(np.count_nonzero(valid & ~matched)),
        "nodata_pixels": int(np.size(valid) - np.count_nonzero(valid)),
        "unknown_lulc_values": unknown_lulc,
        "unknown_hsg_values": unknown_hsg,
    }


def _qc_summary(lulc_path: str, aligned_hsg_path: str, basin_path: str, cn_lookup: dict[tuple[int, int], float]) -> list[str]:
    messages: list[str] = []
    lulc = _raster_info(lulc_path)
    hsg = _raster_info(aligned_hsg_path)
    lookup_lulc = sorted({k[0] for k in cn_lookup})
    lulc_values = sorted(_unique_values(lulc_path))
    hsg_values = sorted(_unique_values(aligned_hsg_path))

    messages.append(f"LULC raster size: {lulc['cols']} x {lulc['rows']}; pixel size: {lulc['pixel_x']} x {lulc['pixel_y']}.")
    messages.append(f"Aligned HSG raster size: {hsg['cols']} x {hsg['rows']}; pixel size: {hsg['pixel_x']} x {hsg['pixel_y']}.")
    if (lulc["cols"], lulc["rows"]) == (hsg["cols"], hsg["rows"]):
        messages.append("OK: HSG raster is aligned to the LULC grid.")
    else:
        messages.append("WARNING: HSG raster size differs after alignment.")

    missing_lookup = sorted(set(lulc_values) - set(lookup_lulc))
    if missing_lookup:
        messages.append(f"WARNING: LULC classes not present in CN lookup table: {missing_lookup}.")
    else:
        messages.append("OK: All LULC classes found in the raster are present in the CN lookup table.")

    unexpected_hsg = sorted(set(hsg_values) - {1, 2, 3, 4})
    if unexpected_hsg:
        messages.append(f"WARNING: HSG raster contains values outside 1=A, 2=B, 3=C, 4=D: {unexpected_hsg}.")
    else:
        messages.append("OK: HSG raster contains only expected classes 1=A, 2=B, 3=C, 4=D.")

    vlayer = QgsVectorLayer(basin_path, "basins", "ogr")
    messages.append(f"Basin features: {vlayer.featureCount()}.")
    return messages


def _create_html_report(report_path: str, title: str, qc_messages: list[str], outputs: dict[str, str], cn_csv: str, cn_lookup_csv: str, raster_stats: dict[str, object]) -> None:
    rows = []
    with open(cn_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(row)

    lookup_rows = []
    with open(cn_lookup_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            lookup_rows.append(row)

    def table_html(data):
        if not data:
            return "<p>No data.</p>"
        head = "".join(f"<th>{html.escape(str(x))}</th>" for x in data[0])
        body = "".join("<tr>" + "".join(f"<td>{html.escape(str(x))}</td>" for x in r) + "</tr>" for r in data[1:])
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    content = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>{html.escape(title)}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 32px; color: #222; }}
h1, h2 {{ color: #1f4e5f; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px 0; }}
th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
th {{ background: #eef4f6; }}
.ok {{ color: #1b7f3a; }} .warn {{ color: #a15c00; font-weight: bold; }}
code {{ background: #f5f5f5; padding: 2px 4px; }}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p><strong>Author:</strong> Nikola V. Djokic<br>
<strong>Plugin version:</strong> 1.0<br>
<strong>Created:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<h2>Method</h2>
<p>CN2 values are calculated for average antecedent moisture conditions using the SCS-CN method. CN3 values for high antecedent moisture conditions are calculated automatically from CN2 using:</p>
<p><code>CN3 = 23 * CN2 / (10 + 0.13 * CN2)</code></p>
<h2>Quality control</h2>
<ul>{''.join('<li class="warn">' + html.escape(m) + '</li>' if m.startswith('WARNING') else '<li class="ok">' + html.escape(m) + '</li>' for m in qc_messages)}</ul>
<p>Pixel matching summary: matched={raster_stats.get('matched_pixels')}, unmatched={raster_stats.get('unmatched_pixels')}, nodata={raster_stats.get('nodata_pixels')}.</p>
<h2>CN lookup table</h2>{table_html(lookup_rows)}
<h2>Average CN values by basin</h2>{table_html(rows)}
<h2>Output files</h2>
<ul>{''.join('<li><strong>' + html.escape(k) + ':</strong> ' + html.escape(v) + '</li>' for k, v in outputs.items())}</ul>
</body></html>"""
    Path(report_path).write_text(content, encoding="utf-8")


def run_cn_workflow(lulc_path: str, hsg_path: str, subbasins_path: str, cn_lookup_csv: str, output_dir: str) -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    aligned_hsg = str(out_dir / "HSG_aligned_to_LULC.tif")
    cn2_raster = str(out_dir / "CN2_map.tif")
    cn3_raster = str(out_dir / "CN3_map.tif")
    basins_gpkg = str(out_dir / "basins_cn.gpkg")
    csv_out = str(out_dir / "CN_by_basin.csv")
    qc_txt = str(out_dir / "CN_quality_control.txt")
    report_html = str(out_dir / "CN_report.html")

    lulc_rl = QgsRasterLayer(lulc_path, "lulc")
    hsg_rl = QgsRasterLayer(hsg_path, "hsg")
    vlayer = QgsVectorLayer(subbasins_path, "basins", "ogr")

    if not lulc_rl.isValid():
        raise ValueError("Invalid LULC raster.")
    if not hsg_rl.isValid():
        raise ValueError("Invalid HSG raster.")
    if not vlayer.isValid():
        raise ValueError("Invalid basin layer.")

    processing.run("gdal:warpreproject", {
        "INPUT": hsg_path,
        "SOURCE_CRS": None,
        "TARGET_CRS": lulc_rl.crs(),
        "RESAMPLING": 0,
        "NODATA": 0,
        "TARGET_RESOLUTION": lulc_rl.rasterUnitsPerPixelX(),
        "OPTIONS": "",
        "DATA_TYPE": 5,
        "TARGET_EXTENT": lulc_rl.extent(),
        "TARGET_EXTENT_CRS": lulc_rl.crs(),
        "MULTITHREADING": False,
        "EXTRA": "",
        "OUTPUT": aligned_hsg,
    })

    cn_lookup = _read_cn_lookup(cn_lookup_csv)
    qc_messages = _qc_summary(lulc_path, aligned_hsg, subbasins_path, cn_lookup)
    raster_stats = _build_cn2_cn3_rasters(lulc_path, aligned_hsg, cn_lookup, cn2_raster, cn3_raster)
    if raster_stats["unmatched_pixels"]:
        qc_messages.append(
            f"WARNING: {raster_stats['unmatched_pixels']} valid pixels did not match the CN lookup table and were written as NoData. "
            f"Unknown LULC values: {raster_stats['unknown_lulc_values']}; unknown HSG values: {raster_stats['unknown_hsg_values']}."
        )

    Path(qc_txt).write_text("\n".join(qc_messages) + "\n", encoding="utf-8")

    err = QgsVectorFileWriter.writeAsVectorFormat(vlayer, basins_gpkg, "utf-8", vlayer.crs(), "GPKG")
    if err[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Failed to write basin copy: {err}")

    zonal_layer = QgsVectorLayer(basins_gpkg, "basins_cn", "ogr")
    if not zonal_layer.isValid():
        raise RuntimeError("Failed to reopen output geopackage.")

    for raster_path, prefix in [(cn2_raster, "CN2_"), (cn3_raster, "CN3_")]:
        # QGIS 3.x expects a QgsRasterLayer object here, not a raster path string.
        # Positional arguments are used for better compatibility between QGIS versions.
        stats_raster = QgsRasterLayer(raster_path, prefix.rstrip("_"))
        if not stats_raster.isValid():
            raise RuntimeError(f"Failed to open raster for zonal statistics: {raster_path}")
        zs = QgsZonalStatistics(
            zonal_layer,
            stats_raster,
            prefix,
            1,
            QgsZonalStatistics.Mean | QgsZonalStatistics.Min | QgsZonalStatistics.Max,
        )
        result = zs.calculateStatistics(None)
        if result != 0:
            raise RuntimeError(f"Zonal statistics failed for {raster_path} with code {result}")

    field_names = [f.name() for f in zonal_layer.fields()]
    stat_fields = [n for n in ["CN2_mean", "CN2_min", "CN2_max", "CN3_mean", "CN3_min", "CN3_max"] if n in field_names]
    desired = [name for name in field_names if name not in stat_fields] + stat_fields

    with open(csv_out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(desired)
        for feat in zonal_layer.getFeatures():
            writer.writerow([feat[c] for c in desired])

    outputs = {
        "aligned_hsg": aligned_hsg,
        "cn2_raster": cn2_raster,
        "cn3_raster": cn3_raster,
        "basins_gpkg": basins_gpkg,
        "cn_csv": csv_out,
        "qc_txt": qc_txt,
        "report_html": report_html,
    }
    _create_html_report(report_html, "SCS-CN Builder Report", qc_messages, outputs, csv_out, cn_lookup_csv, raster_stats)
    return outputs
