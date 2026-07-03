# NPCI UPI Analytics — UPI Apps ETL

A small ETL utility to parse NPCI "Ecosystem Statistics" Excel files (UPI APPS sheet),
clean and standardize the data, and load it into a local SQLite staging table (`stg_upi_apps`).

## Overview

- Reads monthly Excel files from `raw/` named using the `YYYY_MM.xlsx` convention (for example `raw/2022_01.xlsx`).
- Parses the UPI APPS sheet, normalizes headers and numeric values, computes derived KPIs, and writes results to `staging/npci_upi.db`.

## Prerequisites

- Python 3.10+ (or compatible)
- Recommended Python packages: `pandas`, `numpy`, `openpyxl` (for Excel), and `sqlite3` (standard library).

You can install typical dependencies with pip (example):

```bash
pip install pandas numpy openpyxl
```

## Project layout

- `raw/` — place input Excel files here (required naming: `YYYY_MM.xlsx`).
- `staging/` — output directory (created when running the script).
- `script.py` — main ETL script (`python script.py`).

Confirmed input sheet layout (do not change without re-validating):

- Row 0: Title row — skipped
- Row 1: Group label row — e.g. `Sr.No. | Application Name | CIT | B2C | B2B | On-us | Total`
- Row 2: Sub-label row — e.g. `NaN | NaN | Volume (Mn) | Value (Cr) | ...`
- Row 3+: Data rows

## Usage

From the `ecosystemStatistics/` directory run:

```bash
python script.py
```

Behavior notes:

- The script creates `staging/` and writes logs to `staging/etl_upi_apps.log` when executed.
- Importing `script.py` as a module will not create the `staging/` directory or configure logging (safe for reuse).

## Outputs

- `staging/npci_upi.db` — SQLite database containing the `stg_upi_apps` staging table.
- `staging/etl_upi_apps.log` — execution log.

## File naming rule

Input files must be named as `YYYY_MM.xlsx` (example: `2022_01.xlsx`). The script extracts year/month from the filename and will raise an error for invalid names.

## Notes & Troubleshooting

- If no `.xlsx` files are found in `raw/`, the script exits with an error message in the log.
- The parser expects 12 columns; if only 10 are present the script inserts placeholder columns for the missing "On-us" fields.

## License & Contact

This repository is provided as-is. For questions or improvements, open an issue or contact the maintainers.

