import sqlite3
import sys
from datetime import datetime, date
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# CONFIG — keep in sync with DECISIONS.md
# ─────────────────────────────────────────────────────────────

DB_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("staging/npci_upi.db")
OUT_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("sql/qualityAnalysis")

CALENDAR_START = (2022, 1)
CALENDAR_END = (2026, 5)  # inclusive — matches the recursive CTE bound in sanityCheck.sql

KNOWN_UPI_APPS_GAPS = {(2026, 3)}
KNOWN_TOP15_PSP_GAPS = {(2022, 12, "payee"), (2026, 4, "payer")}


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


CALENDAR = month_range(CALENDAR_START, CALENDAR_END)

# ─────────────────────────────────────────────────────────────
# QUERIES — mirrors sanityCheck.sql section by section
# ─────────────────────────────────────────────────────────────

Q_ROW_COUNTS = """
SELECT 'stg_p2p_p2m' AS table_name, COUNT(*) AS row_count FROM stg_p2p_p2m
UNION ALL
SELECT 'stg_upi_apps', COUNT(*) FROM stg_upi_apps
UNION ALL
SELECT 'stg_top15_psp', COUNT(*) FROM stg_top15_psp;
"""

Q_COVERAGE_P2P = """
SELECT year, month, COUNT(*) AS rows_this_month
FROM stg_p2p_p2m GROUP BY year, month ORDER BY year, month;
"""

Q_COVERAGE_APPS = """
SELECT year, month, COUNT(*) AS rows_this_month
FROM stg_upi_apps GROUP BY year, month ORDER BY year, month;
"""

Q_COVERAGE_PSP = """
SELECT year, month, psp_type, COUNT(*) AS rows_this_month
FROM stg_top15_psp GROUP BY year, month, psp_type ORDER BY year, month, psp_type;
"""

Q_DUP_MONTH_P2P = """
SELECT year, month, COUNT(*) AS n
FROM stg_p2p_p2m GROUP BY year, month HAVING COUNT(*) > 1;
"""

Q_DUP_MONTH_PSP = """
SELECT year, month, psp_type, COUNT(*) AS n
FROM stg_top15_psp GROUP BY year, month, psp_type HAVING COUNT(*) != 15;
"""

Q_DUP_APP = """
SELECT year, month, app_name, COUNT(*) AS n
FROM stg_upi_apps GROUP BY year, month, app_name HAVING COUNT(*) > 1;
"""

Q_CONSECUTIVE_IDENTICAL = """
SELECT
    a.year AS year1, a.month AS month1, a.total_volume_mn AS vol1,
    b.year AS year2, b.month AS month2, b.total_volume_mn AS vol2
FROM stg_p2p_p2m a
JOIN stg_p2p_p2m b
    ON (b.year * 12 + b.month) = (a.year * 12 + a.month) + 1
WHERE a.total_volume_mn = b.total_volume_mn
ORDER BY a.year, a.month;
"""

Q_NULL_ZERO_P2P = """
SELECT year, month, total_volume_mn, p2p_volume_mn, p2m_volume_mn
FROM stg_p2p_p2m
WHERE total_volume_mn IS NULL OR p2p_volume_mn IS NULL
   OR p2m_volume_mn IS NULL OR total_volume_mn <= 0;
"""

Q_NULL_SHARE_APPS = """
SELECT year, month, COUNT(*) AS null_share_rows
FROM stg_upi_apps WHERE market_share_pct IS NULL GROUP BY year, month;
"""

Q_NULL_APPROVAL_PSP = """
SELECT year, month, psp_type, COUNT(*) AS null_approval_rows
FROM stg_top15_psp WHERE approved_percent IS NULL GROUP BY year, month, psp_type;
"""

Q_MARKET_SHARE_SUM = """
SELECT year, month, ROUND(SUM(market_share_pct), 2) AS share_sum
FROM stg_upi_apps GROUP BY year, month
HAVING ABS(SUM(market_share_pct) - 100) > 0.5 ORDER BY year, month;
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
# EVALUATORS — return (status, note)
# ─────────────────────────────────────────────────────────────

def expect_empty(cols, rows, label):
    if not rows:
        return "PASS", f"{label}: no rows returned, as expected."
    return "FAIL", f"{label}: {len(rows)} unexpected row(s) returned."


def evaluate_missing_months(cols, rows, known_gaps, label, key_len):
    found = set()
    for r in rows:
        found.add(tuple(r[:key_len]))
    unexpected = found - known_gaps
    missing_expected = known_gaps - found
    if unexpected:
        return "FAIL", (
            f"{label}: {len(unexpected)} undocumented gap(s) found: "
            f"{sorted(unexpected)}."
        )
    if missing_expected:
        return "FAIL", (
            f"{label}: a documented gap no longer appears missing "
            f"({sorted(missing_expected)}) — data may have been backfilled; "
            f"update DECISIONS.md if intentional."
        )
    return "PASS", f"{label}: exactly the documented gap(s) {sorted(known_gaps)}."


def build_missing_months_query(join_expr, extra_select=""):
    return f"""
WITH RECURSIVE months(year, month) AS (
    SELECT {CALENDAR_START[0]}, {CALENDAR_START[1]}
    UNION ALL
    SELECT
        CASE WHEN month = 12 THEN year + 1 ELSE year END,
        CASE WHEN month = 12 THEN 1 ELSE month + 1 END
    FROM months
    WHERE (year < {CALENDAR_END[0]}) OR (year = {CALENDAR_END[0]} AND month < {CALENDAR_END[1]})
)
{join_expr}
"""


Q_MISSING_P2P = build_missing_months_query("""
SELECT m.year, m.month
FROM months m
LEFT JOIN stg_p2p_p2m t ON t.year = m.year AND t.month = m.month
WHERE t.year IS NULL
ORDER BY m.year, m.month;
""")

Q_MISSING_APPS = build_missing_months_query("""
SELECT m.year, m.month
FROM months m
LEFT JOIN (SELECT DISTINCT year, month FROM stg_upi_apps) t
    ON t.year = m.year AND t.month = m.month
WHERE t.year IS NULL
ORDER BY m.year, m.month;
""")

Q_MISSING_PSP = build_missing_months_query("""
SELECT m.year, m.month, p.psp_type
FROM months m
CROSS JOIN (SELECT 'payer' AS psp_type UNION SELECT 'payee') p
LEFT JOIN (SELECT DISTINCT year, month, psp_type FROM stg_top15_psp) t
    ON t.year = m.year AND t.month = m.month AND t.psp_type = p.psp_type
WHERE t.year IS NULL
ORDER BY m.year, m.month, p.psp_type;
""")


def main():
    if not DB_PATH.exists():
        print(f"ERROR: database not found at {DB_PATH.resolve()}")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    results = []  # list of dicts: name, status, note, cols, rows, informational(bool)

    def add(name, sql, evaluator=None, informational=False):
        cols, rows = run_query(conn, sql)
        if informational:
            results.append({
                "name": name, "status": "INFO", "note": f"{len(rows)} row(s) returned.",
                "cols": cols, "rows": rows, "informational": True,
            })
        else:
            if evaluator is None:
                raise ValueError(f"Check '{name}': evaluator required when informational=False")
            status, note = evaluator(cols, rows)
            results.append({
                "name": name, "status": status, "note": note,
                "cols": cols, "rows": rows, "informational": False,
            })

    try:
        # 1. Row counts (informational)
        add("1. Row counts per table", Q_ROW_COUNTS, informational=True)

        # 2. Month coverage (informational)
        add("2a. Month coverage — stg_p2p_p2m", Q_COVERAGE_P2P, informational=True)
        add("2b. Month coverage — stg_upi_apps", Q_COVERAGE_APPS, informational=True)
        add("2c. Month coverage — stg_top15_psp", Q_COVERAGE_PSP, informational=True)

        # 3. Missing months
        add("3a. Missing months — stg_p2p_p2m",
            Q_MISSING_P2P,
            lambda c, r: expect_empty(c, r, "stg_p2p_p2m missing-month check"))
        add("3b. Missing months — stg_upi_apps",
            Q_MISSING_APPS,
            lambda c, r: evaluate_missing_months(c, r, KNOWN_UPI_APPS_GAPS, "stg_upi_apps missing-month check", 2))
        add("3c. Missing months — stg_top15_psp",
            Q_MISSING_PSP,
            lambda c, r: evaluate_missing_months(c, r, KNOWN_TOP15_PSP_GAPS, "stg_top15_psp missing-month check", 3))

        # 4. Duplicate month checks
        add("4a. Duplicate months — stg_p2p_p2m",
            Q_DUP_MONTH_P2P,
            lambda c, r: expect_empty(c, r, "stg_p2p_p2m duplicate-month check"))
        add("4b. Row count != 15 per month/type — stg_top15_psp",
            Q_DUP_MONTH_PSP,
            lambda c, r: expect_empty(c, r, "stg_top15_psp count-per-month check"))
        add("4c. Duplicate app per month — stg_upi_apps",
            Q_DUP_APP,
            lambda c, r: expect_empty(c, r, "stg_upi_apps duplicate-app check"))

        # 5. Consecutive identical volume (2024_06/07 pattern recurrence)
        add("5. Consecutive-month identical volume check",
            Q_CONSECUTIVE_IDENTICAL,
            lambda c, r: expect_empty(c, r, "consecutive-identical-volume check"))

        # 6. Null/zero spot checks
        add("6a. Null/zero spot check — stg_p2p_p2m",
            Q_NULL_ZERO_P2P,
            lambda c, r: expect_empty(c, r, "stg_p2p_p2m null/zero check"))
        add("6b. Null market_share_pct — stg_upi_apps",
            Q_NULL_SHARE_APPS,
            lambda c, r: expect_empty(c, r, "stg_upi_apps null market_share_pct check"))
        add("6c. Null approved_percent — stg_top15_psp",
            Q_NULL_APPROVAL_PSP,
            lambda c, r: expect_empty(c, r, "stg_top15_psp null approved_percent check"))

        # 7. Market share sums to ~100%
        add("7. Market share sums to ~100% per month — stg_upi_apps",
            Q_MARKET_SHARE_SUM,
            lambda c, r: expect_empty(c, r, "stg_upi_apps market-share-sum check"))
    finally:
        conn.close()

    # ── Build markdown report ──────────────────────────────────
    timestamp = datetime.now()
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    info_count = sum(1 for r in results if r["status"] == "INFO")

    lines = []
    lines.append(f"# DB Sanity Check Results — {timestamp:%Y-%m-%d %H:%M}")
    lines.append("")
    lines.append(f"Database: `{DB_PATH}`")
    lines.append("")
    lines.append(f"**{pass_count} pass · {fail_count} fail · {info_count} informational**")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Check | Status | Note |")
    lines.append("| --- | --- | --- |")
    for r in results:
        badge = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "INFO": "ℹ️ INFO"}[r["status"]]
        lines.append(f"| {r['name']} | {badge} | {r['note']} |")
    lines.append("")

    if fail_count:
        lines.append("## Unexpected results — detail")
        lines.append("")
        for r in results:
            if r["status"] == "FAIL":
                lines.append(f"### {r['name']}")
                lines.append("")
                lines.append(r["note"])
                lines.append("")
                lines.append(rows_to_md_table(r["cols"], r["rows"]))
                lines.append("")
    else:
        lines.append("## Unexpected results — detail")
        lines.append("")
        lines.append("None. All checks matched expectations from `sanityCheck.sql`.")
        lines.append("")

    lines.append("## Informational output")
    lines.append("")
    for r in results:
        if r["informational"]:
            lines.append(f"### {r['name']}")
            lines.append("")
            lines.append(rows_to_md_table(r["cols"], r["rows"]))
            lines.append("")

    out_path = OUT_DIR / f"sanity_results_{timestamp:%Y_%m_%d_%H%M}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Done. {pass_count} pass, {fail_count} fail, {info_count} informational.")
    print(f"Report written to {out_path.resolve()}")
    if fail_count:
        sys.exit(1)


if __name__ == "__main__":
    main()