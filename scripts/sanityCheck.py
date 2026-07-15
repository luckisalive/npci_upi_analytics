import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# CONFIG — keep in sync with DECISIONS.md
# ─────────────────────────────────────────────────────────────

DB_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("staging/npci_upi.db")
OUT_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("sql/qualityAnalysis/results")

CALENDAR_START = (2022, 1)
# NOTE: there is no CALENDAR_END constant anymore. Each table's missing-
# month check now bounds itself to that table's own MAX(year, month),
# read from the DB at runtime. 

KNOWN_UPI_APPS_GAPS = {(2026, 3)}
KNOWN_TOP15_PSP_GAPS = {(2022, 12, "payee"), (2026, 4, "payer")}

KNOWN_BD_TD_ANOMALIES = {(2023, 6, "payer")}


def month_range(start, end):
    y, m = start
    out = []
    while (y, m) <= end:
        out.append((y, m))
        m += 1
        if m == 13:
            m = 1
            y += 1
    return out


def table_max_month(conn, table, where=""):
    """Returns (year, month) of the latest loaded month for a table."""
    cur = conn.execute(f"SELECT MAX(year * 100 + month) FROM {table} {where}")
    val = cur.fetchone()[0]
    if val is None:
        return None
    return (val // 100, val % 100)


def build_missing_months_query(join_expr, end_ym):
    return f"""
WITH RECURSIVE months(year, month) AS (
    SELECT {CALENDAR_START[0]}, {CALENDAR_START[1]}
    UNION ALL
    SELECT
        CASE WHEN month = 12 THEN year + 1 ELSE year END,
        CASE WHEN month = 12 THEN 1 ELSE month + 1 END
    FROM months
    WHERE (year < {end_ym[0]}) OR (year = {end_ym[0]} AND month < {end_ym[1]})
)
{join_expr}
"""


# ─────────────────────────────────────────────────────────────
# STATIC QUERIES (unchanged from original)
# ─────────────────────────────────────────────────────────────

Q_ROW_COUNTS = """
SELECT 'stg_p2p_p2m' AS table_name, COUNT(*) AS row_count FROM stg_p2p_p2m
UNION ALL
SELECT 'stg_upi_apps', COUNT(*) FROM stg_upi_apps
UNION ALL
SELECT 'stg_top15_psp', COUNT(*) FROM stg_top15_psp;
"""

Q_COVERAGE_P2P = "SELECT year, month, COUNT(*) AS rows_this_month FROM stg_p2p_p2m GROUP BY year, month ORDER BY year, month;"
Q_COVERAGE_APPS = "SELECT year, month, COUNT(*) AS rows_this_month FROM stg_upi_apps GROUP BY year, month ORDER BY year, month;"
Q_COVERAGE_PSP = "SELECT year, month, psp_type, COUNT(*) AS rows_this_month FROM stg_top15_psp GROUP BY year, month, psp_type ORDER BY year, month, psp_type;"

Q_TRAILING_EDGE = """
SELECT 'stg_p2p_p2m' AS table_name, MAX(year * 100 + month) AS latest_yyyymm FROM stg_p2p_p2m
UNION ALL
SELECT 'stg_upi_apps', MAX(year * 100 + month) FROM stg_upi_apps
UNION ALL
SELECT 'stg_top15_psp', MAX(year * 100 + month) FROM stg_top15_psp;
"""

Q_DUP_MONTH_P2P = "SELECT year, month, COUNT(*) AS n FROM stg_p2p_p2m GROUP BY year, month HAVING COUNT(*) > 1;"
Q_DUP_MONTH_PSP = "SELECT year, month, psp_type, COUNT(*) AS n FROM stg_top15_psp GROUP BY year, month, psp_type HAVING COUNT(*) != 15;"
Q_DUP_MONTH_APPS = "SELECT year, month, app_name, COUNT(*) AS n FROM stg_upi_apps GROUP BY year, month, app_name HAVING COUNT(*) > 1;"

Q_CONSECUTIVE_IDENTICAL_P2P = """
SELECT a.year AS year1, a.month AS month1, a.total_volume_mn AS vol1,
       b.year AS year2, b.month AS month2, b.total_volume_mn AS vol2
FROM stg_p2p_p2m a
JOIN stg_p2p_p2m b ON (b.year * 12 + b.month) = (a.year * 12 + a.month) + 1
WHERE a.total_volume_mn = b.total_volume_mn
ORDER BY a.year, a.month;
"""

Q_CONSECUTIVE_IDENTICAL_APPS = """
WITH agg AS (
    SELECT year, month, app_name, SUM(total_volume_mn) AS vol
    FROM stg_upi_apps
    WHERE app_name != 'Application Name'
    GROUP BY year, month, app_name
)
SELECT a.year AS year1, a.month AS month1, b.year AS year2, b.month AS month2,
       COUNT(*) AS identical_app_count
FROM agg a
JOIN agg b ON (b.year * 12 + b.month) = (a.year * 12 + a.month) + 1
          AND a.app_name = b.app_name AND a.vol = b.vol
GROUP BY a.year, a.month, b.year, b.month
HAVING COUNT(*) >= (SELECT COUNT(DISTINCT app_name) FROM agg) - 2
ORDER BY a.year, a.month;
"""

Q_NULL_ZERO_P2P = """
SELECT year, month, total_volume_mn, p2p_volume_mn, p2m_volume_mn
FROM stg_p2p_p2m
WHERE total_volume_mn IS NULL OR p2p_volume_mn IS NULL
   OR p2m_volume_mn IS NULL OR total_volume_mn <= 0;
"""

Q_NULL_SHARE_APPS = "SELECT year, month, COUNT(*) AS null_share_rows FROM stg_upi_apps WHERE market_share_pct IS NULL GROUP BY year, month;"
Q_NULL_APPROVAL_PSP = "SELECT year, month, psp_type, COUNT(*) AS null_approval_rows FROM stg_top15_psp WHERE approved_percent IS NULL GROUP BY year, month, psp_type;"

Q_MARKET_SHARE_SUM = """
SELECT year, month, ROUND(SUM(market_share_pct), 2) AS share_sum
FROM stg_upi_apps GROUP BY year, month
HAVING ABS(SUM(market_share_pct) - 100) > 0.5 ORDER BY year, month;
"""

Q_PERCENT_SUM_PSP = """
SELECT year, month, psp_type, psp_name,
       ROUND(approved_percent + business_decline_percent + technical_decline_percent, 2) AS pct_sum
FROM stg_top15_psp
WHERE ABS(approved_percent + business_decline_percent + technical_decline_percent - 100) > 0.5
ORDER BY year, month, psp_type;
"""

Q_CASING_REGRESSION = """
SELECT UPPER(TRIM(psp_name)) AS normalized_name, psp_type,
       COUNT(DISTINCT psp_name) AS distinct_raw_spellings,
       GROUP_CONCAT(DISTINCT psp_name) AS raw_spellings_seen
FROM stg_top15_psp
GROUP BY normalized_name, psp_type
HAVING COUNT(DISTINCT psp_name) > 1;
"""

Q_OVERRIDE_COLLISION = """
SELECT year, month, psp_type, psp_name, COUNT(*) AS n
FROM stg_top15_psp
GROUP BY year, month, psp_type, psp_name
HAVING COUNT(*) > 1;
"""

# pre-override legacy name leakage guard
Q_LEGACY_NAME_LEAKAGE = """
SELECT year, month, psp_type, psp_name
FROM stg_top15_psp
WHERE psp_name IN (
    'North East Small Finance Bank',
    'North East Small Finance Bank Acquirer',
    'Slice Small Finance Bank Acquirer',
    'Slice Small Finance Bank Limited(North East Small Finance Bank Limited)',
    'IDFC Bank',
    'Npci Bhim Services Ltd (Nbsl)'
);
"""

# header-leak permanent guard (promoted from investigation.sql)
Q_HEADER_LEAK = """
SELECT year, month, app_name, total_volume_mn, total_value_cr
FROM stg_upi_apps
WHERE app_name IN ('Application Name', 'Sr No', 'Sr. No.', 'Sr.No.')
   OR total_volume_mn IS NULL;
"""

# BD/TD composition anomaly detector, with known-exception carve-out
Q_BD_TD_ANOMALY = """
SELECT year, month, psp_type, ROUND(AVG(business_decline_percent), 3) AS avg_bd_pct
FROM stg_top15_psp
GROUP BY year, month, psp_type
HAVING AVG(business_decline_percent) < 0.2;
"""


def run_query(conn, sql):
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    return cols, rows


def rows_to_md_table(cols, rows):
    if not rows:
        return "_(no rows)_"
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = "\n".join(
        "| " + " | ".join("" if v is None else str(v) for v in r) + " |" for r in rows
    )
    return "\n".join([header, sep, body])


# ─────────────────────────────────────────────────────────────
# EVALUATORS
# ─────────────────────────────────────────────────────────────

def expect_empty(cols, rows, label):
    if not rows:
        return "PASS", f"{label}: no rows returned, as expected."
    return "FAIL", f"{label}: {len(rows)} unexpected row(s) returned."


def evaluate_known_set(cols, rows, known_set, label, key_len):
    found = set(r[:key_len] for r in rows)
    unexpected = found - known_set
    missing_expected = known_set - found
    if unexpected:
        return "FAIL", f"{label}: {len(unexpected)} undocumented case(s): {sorted(unexpected)}."
    if missing_expected:
        return "FAIL", (
            f"{label}: a documented case no longer appears ({sorted(missing_expected)}) — "
            f"data may have changed; update DECISIONS.md if intentional."
        )
    return "PASS", f"{label}: exactly the documented case(s) {sorted(known_set)}."


def main():
    if not DB_PATH.exists():
        print(f"ERROR: database not found at {DB_PATH.resolve()}")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    results = []

    def add(name, sql, evaluator=None, informational=False, key_len=None, known_set=None):
        cols, rows = run_query(conn, sql)
        if informational:
            results.append({"name": name, "status": "INFO",
                             "note": f"{len(rows)} row(s) returned.",
                             "cols": cols, "rows": rows, "informational": True})
        elif known_set is not None:
            status, note = evaluate_known_set(cols, rows, known_set, name, key_len)
            results.append({"name": name, "status": status, "note": note,
                             "cols": cols, "rows": rows, "informational": False})
        else:
            if evaluator is None:
                raise ValueError(f"Check '{name}': evaluator required when informational=False")
            status, note = evaluator(cols, rows)
            results.append({"name": name, "status": status, "note": note,
                             "cols": cols, "rows": rows, "informational": False})

    try:
        # Dynamic per-table calendar ends
        p2p_end = table_max_month(conn, "stg_p2p_p2m")
        apps_end = table_max_month(conn, "stg_upi_apps")
        psp_end = table_max_month(conn, "stg_top15_psp")

        Q_MISSING_P2P = build_missing_months_query("""
            SELECT m.year, m.month FROM months m
            LEFT JOIN stg_p2p_p2m t ON t.year = m.year AND t.month = m.month
            WHERE t.year IS NULL ORDER BY m.year, m.month;
        """, p2p_end)

        Q_MISSING_APPS = build_missing_months_query("""
            SELECT m.year, m.month FROM months m
            LEFT JOIN (SELECT DISTINCT year, month FROM stg_upi_apps) t
                ON t.year = m.year AND t.month = m.month
            WHERE t.year IS NULL ORDER BY m.year, m.month;
        """, apps_end)

        Q_MISSING_PSP = build_missing_months_query("""
            SELECT m.year, m.month, p.psp_type FROM months m
            CROSS JOIN (SELECT 'payer' AS psp_type UNION SELECT 'payee') p
            LEFT JOIN (SELECT DISTINCT year, month, psp_type FROM stg_top15_psp) t
                ON t.year = m.year AND t.month = m.month AND t.psp_type = p.psp_type
            WHERE t.year IS NULL ORDER BY m.year, m.month, p.psp_type;
        """, psp_end)

        # 1-2
        add("1. Row counts per table", Q_ROW_COUNTS, informational=True)
        add("2a. Month coverage — stg_p2p_p2m", Q_COVERAGE_P2P, informational=True)
        add("2b. Month coverage — stg_upi_apps", Q_COVERAGE_APPS, informational=True)
        add("2c. Month coverage — stg_top15_psp", Q_COVERAGE_PSP, informational=True)
        add("2d. Trailing-edge report (per-table latest month)", Q_TRAILING_EDGE, informational=True)

        # 3 — missing months, now self-bounded per table
        add("3a. Missing months — stg_p2p_p2m", Q_MISSING_P2P,
            lambda c, r: expect_empty(c, r, "stg_p2p_p2m missing-month check"))
        add("3b. Missing months — stg_upi_apps", Q_MISSING_APPS,
            known_set=KNOWN_UPI_APPS_GAPS, key_len=2)
        add("3c. Missing months — stg_top15_psp", Q_MISSING_PSP,
            known_set=KNOWN_TOP15_PSP_GAPS, key_len=3)

        # 4 — duplicates
        add("4a. Duplicate months — stg_p2p_p2m", Q_DUP_MONTH_P2P,
            lambda c, r: expect_empty(c, r, "stg_p2p_p2m duplicate-month check"))
        add("4b. Row count != 15 per month/type — stg_top15_psp", Q_DUP_MONTH_PSP,
            lambda c, r: expect_empty(c, r, "stg_top15_psp count-per-month check"))
        add("4c. Undocumented duplicate app per month — stg_upi_apps", Q_DUP_MONTH_APPS,
            lambda c, r: expect_empty(c, r, "stg_upi_apps undocumented-duplicate-app check"))

        # 5 — consecutive-identical (both tables)
        add("5a. Consecutive-month identical volume — stg_p2p_p2m", Q_CONSECUTIVE_IDENTICAL_P2P,
            lambda c, r: expect_empty(c, r, "p2p_p2m consecutive-identical-volume check"))
        add("5b. Consecutive-month identical volume — stg_upi_apps (app grain)", Q_CONSECUTIVE_IDENTICAL_APPS,
            lambda c, r: expect_empty(c, r, "upi_apps consecutive-identical-volume check"))

        # 6 — null/zero
        add("6a. Null/zero spot check — stg_p2p_p2m", Q_NULL_ZERO_P2P,
            lambda c, r: expect_empty(c, r, "stg_p2p_p2m null/zero check"))
        add("6b. Null market_share_pct — stg_upi_apps", Q_NULL_SHARE_APPS,
            lambda c, r: expect_empty(c, r, "stg_upi_apps null market_share_pct check"))
        add("6c. Null approved_percent — stg_top15_psp", Q_NULL_APPROVAL_PSP,
            lambda c, r: expect_empty(c, r, "stg_top15_psp null approved_percent check"))

        # 7
        add("7. Market share sums to ~100% per month — stg_upi_apps", Q_MARKET_SHARE_SUM,
            lambda c, r: expect_empty(c, r, "stg_upi_apps market-share-sum check"))

        # 8-12 — new regression guards
        add("8. Percent-sum regression guard — stg_top15_psp", Q_PERCENT_SUM_PSP,
            lambda c, r: expect_empty(c, r, "percent-sum regression check"))
        add("9. psp_name casing/spelling regression guard", Q_CASING_REGRESSION,
            lambda c, r: expect_empty(c, r, "psp_name casing regression check"))
        add("10. Name-override collision guard", Q_OVERRIDE_COLLISION,
            lambda c, r: expect_empty(c, r, "override-collision check"))
        add("11. Pre-override legacy name leakage guard", Q_LEGACY_NAME_LEAKAGE,
            lambda c, r: expect_empty(c, r, "legacy-name-leakage check"))
        add("12. Header-leak permanent guard — stg_upi_apps", Q_HEADER_LEAK,
            lambda c, r: expect_empty(c, r, "header-leak check"))

        # 13 — BD/TD anomaly, with known-exception carve-out
        add("13. BD/TD composition anomaly detector", Q_BD_TD_ANOMALY,
            known_set=KNOWN_BD_TD_ANOMALIES, key_len=3)

    finally:
        conn.close()

    timestamp = datetime.now()
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    info_count = sum(1 for r in results if r["status"] == "INFO")

    lines = [f"# DB Sanity Check Results — {timestamp:%Y-%m-%d %H:%M}", "",
             f"Database: `{DB_PATH}`", "",
             f"**{pass_count} pass · {fail_count} fail · {info_count} informational**", "",
             "## Summary", "", "| Check | Status | Note |", "| --- | --- | --- |"]
    for r in results:
        badge = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "INFO": "ℹ️ INFO"}[r["status"]]
        lines.append(f"| {r['name']} | {badge} | {r['note']} |")
    lines.append("")

    if fail_count:
        lines.append("## Unexpected results — detail")
        lines.append("")
        for r in results:
            if r["status"] == "FAIL":
                lines += [f"### {r['name']}", "", r["note"], "", rows_to_md_table(r["cols"], r["rows"]), ""]
    else:
        lines += ["## Unexpected results — detail", "", "None. All checks matched expectations.", ""]

    lines.append("## Informational output")
    lines.append("")
    for r in results:
        if r["informational"]:
            lines += [f"### {r['name']}", "", rows_to_md_table(r["cols"], r["rows"]), ""]

    out_path = OUT_DIR / f"sanity_results_{timestamp:%Y_%m_%d_%H%M}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Done. {pass_count} pass, {fail_count} fail, {info_count} informational.")
    print(f"Report written to {out_path.resolve()}")
    if fail_count:
        sys.exit(1)


if __name__ == "__main__":
    main()