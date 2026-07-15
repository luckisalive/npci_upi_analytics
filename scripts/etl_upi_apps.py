import re
import sqlite3
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

RAW_DIR      = Path("raw/upi_apps/")
STAGING_DIR  = Path("staging")
LOG_DIR     = Path("logs")
DB_PATH      = STAGING_DIR / "npci_upi.db"
SHEET_NAME   = 0 # UPI APPS sheet name in NPCI Excel files


# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────

def configure_logging():
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "etl_upi_apps.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

# Logger for module-level use. Configuration is applied by `configure_logging()`
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# COLUMN SCHEMA
# Final standardized column names after parsing merged headers.
# Order matches the Excel column positions exactly.
# ─────────────────────────────────────────────────────────────

COLUMN_SCHEMA = [
    "sr_no",
    "app_name",
    "cit_volume_mn",      # Customer Initiated Transactions
    "cit_value_cr",
    "b2c_volume_mn",      # Business to Consumer
    "b2c_value_cr",
    "b2b_volume_mn",      # Business to Business
    "b2b_value_cr",
    "onus_volume_mn",     # On-us Transactions
    "onus_value_cr",
    "total_volume_mn",
    "total_value_cr",
]

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def extract_date_from_filename(filepath: Path) -> tuple[int, int]:
    """
    Parses YYYY_MM from filename.
    Fails loudly — wrong filename = wrong date on every row.
    """
    match = re.fullmatch(r"(\d{4})_(\d{2})", filepath.stem)
    if not match:
        raise ValueError(
            f"'{filepath.name}' does not match YYYY_MM.xlsx. "
            f"Rename before running."
        )
    year, month = int(match.group(1)), int(match.group(2))
    if not (2000 <= year <= 2030) or not (1 <= month <= 12):
        raise ValueError(
            f"Implausible date parsed from '{filepath.name}': {year}-{month}. "
            f"Check filename."
        )
    return year, month

def clean_numeric(series: pd.Series) -> pd.Series:
    
    if pd.api.types.is_numeric_dtype(series):
        return series
        
    return (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.strip()
        .str.extract(r"^([\d.]+)")[0]
        .pipe(pd.to_numeric, errors="coerce")
    )

APP_NAME_OVERRIDES = {
    "PAYTMWALLET": "Paytm",
    "Paytm (OCL )": "Paytm",
    "Paytm (OCL)": "Paytm",
    "Paytm Payments Bank App": "Paytm",
    "Bajaj Finserv PPI": "Bajaj Finserv",
    "Bajaj Markets": "Bajaj Finserv",
    "Bajaj Pay Wallet": "Bajaj Finserv",
    "Federal Bank Apps": "Federal Bank App",
    "Mobikwik PPI": "Mobikwik",
    "Other Apps": "Other",
    "Others": "Other",
}

def clean_app_name(series: pd.Series) -> pd.Series:
    """
    Strips whitespace and footnote markers like '#', '*', '**'.
    Preserves original casing — app names are proper nouns.
    """
    s = (
        series.astype(str)
        .str.strip()
        .str.replace(r"[#*]+$", "", regex=True)
        .str.strip()
    )
    s = s.replace(APP_NAME_OVERRIDES)

    return s.str.strip()

# ─────────────────────────────────────────────────────────────
# PARSER
# ─────────────────────────────────────────────────────────────

def parse_upi_apps(filepath: Path, year: int, month: int) -> pd.DataFrame | None:
    """
    Parses UPI APPS sheet from a single monthly Excel file.
    Returns normalized DataFrame or None on failure.
    """
    try:
        raw = pd.read_excel(filepath, sheet_name=SHEET_NAME, header=None)
    except Exception as e:
        log.error(f"[{filepath.name}] Cannot open sheet '{SHEET_NAME}': {e}")
        return None

    # ── Validate structure before parsing ──────────────────
    row1_values = raw.iloc[1].tolist()
    if "Application Name" not in row1_values:
        log.error(
            f"[{filepath.name}] Unexpected sheet structure — "
            f"'Application Name' not found in row 1. "
            f"Row 1 contents: {row1_values}"
        )
        return None

    # If 10 columns, insert empty onus columns at positions 8 and 9
    if raw.shape[1] == 10:
        log.warning(f"[{filepath.name}] 10 columns found — On-us columns absent. Inserting nulls.")
        raw.insert(8, "onus_vol_placeholder", None)
        raw.insert(9, "onus_val_placeholder", None)
    elif raw.shape[1] != 12:
        log.error(f"[{filepath.name}] Expected 12 columns, got {raw.shape[1]}. Skipping.")
        return None

    # ── Extract data rows ───────────────────────────────────
    df = raw.iloc[3:].copy()
    df.columns = COLUMN_SCHEMA
    df = df.reset_index(drop=True)

    # ── Clean app_name ──────────────────────────────────────
    df["app_name"] = clean_app_name(df["app_name"])

    # Drop rows with null, empty, or 'nan' app_name (footer/blank rows)
    df = df[
        df["app_name"].notna() & 
        (df["app_name"] != "") & 
        (df["app_name"].str.lower() != "nan")
    ]

    # Drop sr_no — not useful for analysis, date+app_name is the grain
    df = df.drop(columns=["sr_no"])

    # ── Drop On-us columns ──────────────────────────────────
    df = df.drop(columns=["onus_volume_mn", "onus_value_cr"])

    # ── Numeric conversion ──────────────────────────────────
    numeric_cols = [c for c in COLUMN_SCHEMA if c not in ("sr_no", "app_name", "onus_volume_mn", "onus_value_cr")]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = clean_numeric(df[col])

    # ── Check if B2C/B2B/On-us are consistently zero ────────
    sparse_cols = ["b2c_volume_mn", "b2b_volume_mn"]
    for col in sparse_cols:
        zero_pct = (df[col] == 0).mean() * 100
        if zero_pct == 100:
            log.warning(
                f"[{filepath.name}] '{col}' is 100% zero this month. "
                f"If consistent across all months, drop this column."
            )

    # ── Derived KPIs ────────────────────────────────────────
    total_vol = df["total_volume_mn"].sum()
    if total_vol > 0:
        df["market_share_pct"] = (df["total_volume_mn"] / total_vol * 100).round(4)
    else:
        df["market_share_pct"] = None
        log.warning(f"[{filepath.name}] Total volume is 0 — market_share_pct set to NULL.")

    # Fix: Value is in Crores, Volume is in Millions. Multiply ratio by 10 for rupees per transaction.
    df["avg_ticket_size"] = np.where(
        df["total_volume_mn"] > 0,
        ((df["total_value_cr"] / df["total_volume_mn"]) * 10).round(2),
        0.0  # Set to 0 if volume is 0
    )
    # ── Add time dimension ───────────────────────────────────
    df["year"]  = year
    df["month"] = month

    # ── Final null check ─────────────────────────────────────
    null_pct = df[["app_name", "total_volume_mn", "total_value_cr"]].isnull().mean()
    high_null = null_pct[null_pct > 0.3]
    if not high_null.empty:
        log.warning(
            f"[{filepath.name}] High null % in critical columns: "
            f"{high_null.to_dict()}"
        )

    log.info(
        f"[{filepath.name}] Parsed {len(df)} app rows | "
        f"Total vol: {total_vol:.2f} Mn | "
        f"Year: {year}, Month: {month}"
    )

    return df


# ─────────────────────────────────────────────────────────────
# SQLITE LOADER
# ─────────────────────────────────────────────────────────────

def create_table_if_not_exists(conn: sqlite3.Connection):
    """
    Creates stg_upi_apps table with explicit schema.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stg_upi_apps (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            app_name         TEXT    NOT NULL,
            cit_volume_mn    REAL,
            cit_value_cr     REAL,
            b2c_volume_mn    REAL,
            b2c_value_cr     REAL,
            b2b_volume_mn    REAL,
            b2b_value_cr     REAL,
            total_volume_mn  REAL,
            total_value_cr   REAL,
            market_share_pct REAL,
            avg_ticket_size  REAL,
            year             INTEGER NOT NULL,
            month            INTEGER NOT NULL
        )
    """)
    conn.commit()


def load_to_sqlite(df: pd.DataFrame, conn: sqlite3.Connection):
    df.to_sql("stg_upi_apps", conn, if_exists="append", index=False)


# ─────────────────────────────────────────────────────────────
# DUPLICATE GUARD
# ─────────────────────────────────────────────────────────────

def already_loaded(conn: sqlite3.Connection, year: int, month: int) -> bool:
    """
    Checks if data for this year/month already exists in the table.
    """
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM stg_upi_apps WHERE year=? AND month=?",
            (year, month)
        )
        return cursor.fetchone()[0] > 0
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return False


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def run():
    log.info("=" * 60)
    log.info(f"UPI Apps ETL started: {datetime.now()}")

    files = sorted(RAW_DIR.glob("*.xlsx"))
    if not files:
        log.error(f"No .xlsx files in {RAW_DIR.resolve()}. Exiting.")
        return

    log.info(f"Files found: {len(files)}")

    conn = sqlite3.connect(DB_PATH)
    create_table_if_not_exists(conn)

    success, skipped, failed = 0, 0, 0

    for filepath in files:
        try:
            year, month = extract_date_from_filename(filepath)
        except ValueError as e:
            log.error(str(e))
            failed += 1
            continue

        # Skip if already loaded
        if already_loaded(conn, year, month):
            log.info(f"[{filepath.name}] Already loaded — skipping.")
            skipped += 1
            continue

        df = parse_upi_apps(filepath, year, month)

        if df is not None:
            load_to_sqlite(df, conn)
            success += 1
        else:
            failed += 1

    conn.close()

    log.info("=" * 60)
    log.info(f"Done. Success: {success} | Skipped: {skipped} | Failed: {failed}")
    log.info(f"DB: {DB_PATH.resolve()}")
    log.info("=" * 60)


if __name__ == "__main__":
    configure_logging()
    run()