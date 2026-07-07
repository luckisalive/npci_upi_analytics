import re
import sqlite3
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

PAYER_DIR     = Path("raw/top15_psp/payer")
PAYEE_DIR     = Path("raw/top15_psp/payee")
STAGING_DIR   = Path("staging")
LOG_DIR       = Path("logs")
DB_PATH       = STAGING_DIR / "npci_upi.db"
TABLE_NAME    = "stg_top15_psp"

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
            logging.FileHandler(LOG_DIR / "etl_top15_psp.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def extract_date_from_filename(filepath: Path) -> tuple[int, int]:
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


def clean_psp_name(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"[#*]+$", "", regex=True)
        .str.strip()
    )


def parse_top15_psp(filepath: Path, psp_type: str, year: int, month: int) -> pd.DataFrame | None:
    try:
        raw = pd.read_excel(filepath, sheet_name=0, header=1, engine="openpyxl")
    except Exception as e:
        log.error(f"[{filepath.name}] Cannot open file: {e}")
        return None

    expected_label = "Payer PSP" if psp_type == "payer" else "Payee PSP"
    required_columns = [
        "Sr. No.",
        expected_label,
        "Total Volume (In Mn)",
        "Approved %",
        "BD %",
        "TD %"
    ]

    missing = [col for col in required_columns if col not in raw.columns]
    if missing:
        log.error(
            f"[{filepath.name}] Missing expected columns: {missing}. "
            f"Found columns: {raw.columns.tolist()}"
        )
        return None

    df = raw.rename(columns={
        expected_label: "psp_name",
        "Total Volume (In Mn)": "total_volume_mn",
        "Approved %": "approved_percent",
        "BD %": "business_decline_percent",
        "TD %": "technical_decline_percent"
    })[
        ["psp_name", "total_volume_mn", "approved_percent", "business_decline_percent", "technical_decline_percent"]
    ].copy()

    df["psp_name"] = clean_psp_name(df["psp_name"])
    numeric_cols = [
        "total_volume_mn",
        "approved_percent",
        "business_decline_percent",
        "technical_decline_percent"
    ]
    for col in numeric_cols:
        df[col] = clean_numeric(df[col])

    df = df[
        df["psp_name"].notna() &
        (df["psp_name"] != "") &
        (df["psp_name"].str.lower() != "nan")
    ].reset_index(drop=True)

    df["psp_type"] = psp_type
    df["year"] = year
    df["month"] = month
    return df


def create_table_if_not_exists(conn: sqlite3.Connection):
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id                         INTEGER PRIMARY KEY AUTOINCREMENT,
            psp_name                   TEXT NOT NULL,
            psp_type                   TEXT NOT NULL,
            total_volume_mn            REAL,
            approved_percent           REAL,
            business_decline_percent   REAL,
            technical_decline_percent  REAL,
            year                       INTEGER NOT NULL,
            month                      INTEGER NOT NULL
        )
    """)
    conn.commit()

def already_loaded(conn: sqlite3.Connection, year: int, month: int,
                   psp_type: str) -> bool:
    """
    Checks by year + month + psp_type.
    Payer and payee are separate files so need separate guards.
    """
    try:
        cursor = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE_NAME} "
            f"WHERE year=? AND month=? AND psp_type=?",
            (year, month, psp_type)
        )
        return cursor.fetchone()[0] > 0
    except sqlite3.OperationalError:
        return False

def load_to_sqlite(df: pd.DataFrame, conn: sqlite3.Connection):
    df.to_sql(TABLE_NAME, conn, if_exists="append", index=False)


def run():
    configure_logging()
    log.info("=" * 60)
    log.info(f"Top15 PSP ETL started: {datetime.now()}")

    files = [
        *(PAYER_DIR.glob("*.xlsx")),
        *(PAYEE_DIR.glob("*.xlsx"))
    ]
    if not files:
        log.error("No .xlsx files found in payer or payee directories. Exiting.")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        create_table_if_not_exists(conn)

        success, skipped, failed = 0, 0, 0
        for filepath in sorted(files):
            try:
                year, month = extract_date_from_filename(filepath)
            except ValueError as e:
                log.error(str(e))
                failed += 1
                continue

            psp_type = "payer" if filepath.parent == PAYER_DIR else "payee"
            if already_loaded(conn, year, month, psp_type):
                log.info(f"[{filepath.name}] ({psp_type}) Already loaded — skipping.")
                skipped += 1
                continue
        
            df = parse_top15_psp(filepath, psp_type, year, month)
            if df is None:
                failed += 1
                continue
            try:
                load_to_sqlite(df, conn)
                success += 1
            except Exception as e:
                log.error(f"Error loading {filepath.name}: {e}")
                failed += 1
    finally:
        conn.close()

    log.info("=" * 60)
    log.info(f"Done. Success: {success} | Skipped: {skipped} | Failed: {failed}")
    log.info(f"DB: {DB_PATH.resolve()}")
    log.info("=" * 60)

if __name__ == "__main__":
    run()