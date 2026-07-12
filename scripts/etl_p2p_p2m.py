import re
import sqlite3
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

RAW_DIR     = Path("raw/p2p_p2m")
STAGING_DIR = Path("staging")
LOG_DIR     = Path("logs")
DB_PATH     = STAGING_DIR / "npci_upi.db"
SHEET_NAME  = 0

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
            logging.FileHandler(LOG_DIR / "etl_p2p_p2m.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

# Logger for module-level use. Configuration is applied by `configure_logging()`
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# COLUMN SCHEMA
# Positional — order matches Excel columns exactly.
# Col 0: Month label (derived from filename, this col dropped)
# Col 1-2: Total volume/value
# Col 3-4: P2P volume/value
# Col 5-6: P2M volume/value
# ─────────────────────────────────────────────────────────────

COLUMN_SCHEMA = [
    "month_label",
    "total_volume_mn",
    "total_value_cr",
    "p2p_volume_mn",
    "p2p_value_cr",
    "p2m_volume_mn",
    "p2m_value_cr",
]

EXPECTED_COLS = 7

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
            f"Implausible date from '{filepath.name}': {year}-{month}."
        )
    return year, month


def clean_numeric(series: pd.Series) -> pd.Series:
    """Handles Indian comma formatting e.g. '8,31,993.11' → 831993.11"""
    if pd.api.types.is_numeric_dtype(series):
        return series
    return (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.strip()
        .str.extract(r"^([\d.]+)")[0]
        .pipe(pd.to_numeric, errors="coerce")
    )

# ─────────────────────────────────────────────────────────────
# PARSER
# ─────────────────────────────────────────────────────────────

def parse_p2p_p2m(filepath: Path, year: int, month: int) -> pd.DataFrame | None:
    try:
        raw = pd.read_excel(filepath, sheet_name=SHEET_NAME, header=None, engine="openpyxl")
    except Exception as e:
        log.error(f"[{filepath.name}] Cannot open file: {e}")
        return None

    # ── Validate structure ──────────────────────────────────
    if raw.shape[0] < 4:
        log.error(
            f"[{filepath.name}] Expected at least 4 rows, got {raw.shape[0]}. "
            f"File may be empty or malformed."
        )
        return None

    if raw.shape[1] != EXPECTED_COLS:
        log.error(
            f"[{filepath.name}] Expected {EXPECTED_COLS} columns, "
            f"got {raw.shape[1]}. Schema may have changed."
        )
        return None

    # Confirm row 1 contains "Total" as a group label sanity check
    row1_values = raw.iloc[1].tolist()
    if "Total" not in row1_values:
        log.error(
            f"[{filepath.name}] 'Total' not found in row 1. "
            f"Unexpected structure: {row1_values}"
        )
        return None

    # ── Extract single data row ─────────────────────────────
    df = raw.iloc[[3]].copy()
    df.columns = COLUMN_SCHEMA
    df = df.reset_index(drop=True)

    # Drop month_label — time dimension comes from filename
    df = df.drop(columns=["month_label"])

    # ── Numeric conversion ──────────────────────────────────
    numeric_cols = [c for c in COLUMN_SCHEMA if c != "month_label"]
    for col in numeric_cols:
        df[col] = clean_numeric(df[col])

    # ── Validate totals add up ──────────────────────────────
    # P2P + P2M volume should equal Total volume (within 1% tolerance)
    # If not, data integrity issue worth flagging
    computed_total = df["p2p_volume_mn"].iloc[0] + df["p2m_volume_mn"].iloc[0]
    reported_total = df["total_volume_mn"].iloc[0]
    if reported_total > 0:
        discrepancy_pct = abs(computed_total - reported_total) / reported_total * 100
        if discrepancy_pct > 1.0:
            log.warning(
                f"[{filepath.name}] Volume mismatch: P2P+P2M={computed_total:.2f} "
                f"vs Total={reported_total:.2f} "
                f"({discrepancy_pct:.2f}% discrepancy). Check source data."
            )

    # ── Derived KPIs ────────────────────────────────────────
    total_vol = df["total_volume_mn"].iloc[0]
    total_val = df["total_value_cr"].iloc[0]

    df["p2p_share_pct"] = (
        (df["p2p_volume_mn"] / df["total_volume_mn"]) * 100
    ).round(2)

    df["p2m_share_pct"] = (
        (df["p2m_volume_mn"] / df["total_volume_mn"]) * 100
    ).round(2)

    # Average ticket size in ₹ per transaction
    # Value in Crores / Volume in Millions * 10 = ₹ per transaction
    df["avg_ticket_size_overall"] = (
        (df["total_value_cr"] / df["total_volume_mn"]) * 10
    ).round(2)

    df["avg_ticket_size_p2p"] = (
        (df["p2p_value_cr"] / df["p2p_volume_mn"]) * 10
    ).round(2)

    df["avg_ticket_size_p2m"] = (
        (df["p2m_value_cr"] / df["p2m_volume_mn"]) * 10
    ).round(2)

    # ── Add time dimension ───────────────────────────────────
    df["year"]  = year
    df["month"] = month

    log.info(
        f"[{filepath.name}] Parsed | "
        f"Total vol: {total_vol:.2f} Mn | "
        f"P2P: {df['p2p_share_pct'].iloc[0]:.2f}% | "
        f"P2M: {df['p2m_share_pct'].iloc[0]:.2f}% | "
        f"Year: {year}, Month: {month}"
    )

    return df

# ─────────────────────────────────────────────────────────────
# SQLITE
# ─────────────────────────────────────────────────────────────

def create_table_if_not_exists(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stg_p2p_p2m (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            total_volume_mn         REAL,
            total_value_cr          REAL,
            p2p_volume_mn           REAL,
            p2p_value_cr            REAL,
            p2m_volume_mn           REAL,
            p2m_value_cr            REAL,
            p2p_share_pct           REAL,
            p2m_share_pct           REAL,
            avg_ticket_size_overall REAL,
            avg_ticket_size_p2p     REAL,
            avg_ticket_size_p2m     REAL,
            year                    INTEGER NOT NULL,
            month                   INTEGER NOT NULL
        )
    """)
    conn.commit()


def already_loaded(conn: sqlite3.Connection, year: int, month: int) -> bool:
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM stg_p2p_p2m WHERE year=? AND month=?",
            (year, month)
        )
        return cursor.fetchone()[0] > 0
    except sqlite3.OperationalError:
        return False


def load_to_sqlite(df: pd.DataFrame, conn: sqlite3.Connection):
    df.to_sql("stg_p2p_p2m", conn, if_exists="append", index=False)

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def run():
    log.info("=" * 60)
    log.info(f"P2P/P2M ETL started: {datetime.now()}")

    files = sorted(RAW_DIR.glob("*.xlsx"))
    if not files:
        log.error(f"No .xlsx files in {RAW_DIR.resolve()}. Exiting.")
        return

    log.info(f"Files found: {len(files)}")

    conn = sqlite3.connect(DB_PATH)
    try:
        create_table_if_not_exists(conn)

        success, skipped, failed = 0, 0, 0
        for filepath in files:
            try:
                year, month = extract_date_from_filename(filepath)
            except ValueError as e:
                log.error(str(e))
                failed += 1
                continue

            if already_loaded(conn, year, month):
                log.info(f"[{filepath.name}] Already loaded — skipping.")
                skipped += 1
                continue

            df = parse_p2p_p2m(filepath, year, month)

            if df is not None:
                load_to_sqlite(df, conn)
                success += 1
            else:
                failed += 1

    finally:
        conn.close()

    log.info("=" * 60)
    log.info(f"Done. Success: {success} | Skipped: {skipped} | Failed: {failed}")
    log.info(f"DB: {DB_PATH.resolve()}")
    log.info("=" * 60)


if __name__ == "__main__":
    configure_logging()
    run()