# SCS-CN Builder

**SCS-CN Builder** is a QGIS plugin for automated Curve Number (CN) estimation using the Soil Conservation Service (SCS) method.

**Author:** Nikola V. Djokic  
**Version:** 1.0  
**License:** GPL-3.0-or-later
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20036703.svg)](https://doi.org/10.5281/zenodo.20036703)

## Overview

The plugin combines land use/land cover (LULC), Hydrologic Soil Group (HSG) and basin polygon data to calculate spatially distributed CN values and basin-average CN statistics. It is intended for hydrological modelling workflows where CN values are required as input parameters.

The plugin calculates:

- **CN2** for average antecedent moisture conditions,
- **CN3** for high antecedent moisture conditions,
- basin-level zonal statistics for CN2 and CN3,
- quality-control summaries,
- an HTML report documenting inputs, lookup values and outputs.

## Main features

- Editable CN lookup table inside the plugin interface.
- CSV import/export for CN lookup values.
- Automatic alignment of the HSG raster to the LULC raster grid.
- Generation of CN2 and CN3 raster maps.
- Basin-level zonal statistics for CN2 and CN3.
- Quality-control checks for raster alignment, missing lookup classes, HSG classes and unmatched pixels.
- HTML report for transparent documentation of the calculation workflow.

## Inputs

### LULC raster

A raster containing integer LULC class codes.

Default classes used in the built-in lookup table:

| LULC code | Class |
|---:|---|
| 1 | Urban |
| 2 | Cropland |
| 3 | Grassland |
| 4 | Forest |
| 5 | Shrub |
| 6 | Bare |
| 7 | Water/Wetland |

### HSG raster

A raster containing Hydrologic Soil Group classes encoded as integers:

| HSG code | Group |
|---:|---|
| 1 | A |
| 2 | B |
| 3 | C |
| 4 | D |

### Basin vector

A polygon vector layer representing basins or sub-basins for zonal statistics.

### CN lookup table

The lookup table must contain the following columns:

```text
LULC_code,CN_A,CN_B,CN_C,CN_D
```

The table can be edited directly in the plugin or loaded from a CSV file.

## Method

CN2 values are assigned according to the selected LULC class and Hydrologic Soil Group. CN3 values are then calculated from CN2 using:

```text
CN3 = 23 * CN2 / (10 + 0.13 * CN2)
```

Basin-average CN values are calculated using zonal statistics over the generated CN raster maps. For equal-area raster cells, this corresponds to a spatially weighted average.

## Outputs

The plugin creates the following files in the selected output folder:

| Output | Description |
|---|---|
| `HSG_aligned_to_LULC.tif` | HSG raster aligned to the LULC raster grid |
| `CN2_map.tif` | CN2 raster map |
| `CN3_map.tif` | CN3 raster map |
| `basins_cn.gpkg` | Basin layer with CN zonal statistics |
| `CN_by_basin.csv` | Basin-level CN statistics table |
| `CN_quality_control.txt` | Quality-control summary |
| `CN_report.html` | HTML calculation report |

## Recommended citation

Djokic, N. V. (2026). *SCS-CN Builder: A QGIS plugin for automated Curve Number estimation using LULC and Hydrologic Soil Group data* (Version 1.0).

After publication with a DOI, replace this citation with the final DOI citation.

## Installation

Install the plugin from the official QGIS Plugin Repository when available, or install manually from a ZIP package using:

```text
QGIS → Plugins → Manage and Install Plugins → Install from ZIP
```

## Notes before QGIS repository upload

Before uploading to the official QGIS Plugin Repository, update `metadata.txt` with the final public repository, homepage, issue tracker and contact email.
