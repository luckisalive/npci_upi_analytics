-- ───────────────────────────────────────────────────────────────────
-- 1. ROW COUNTS PER TABLE
-- ───────────────────────────────────────────────────────────────────
SELECT 'stg_p2p_p2m'   AS table_name, COUNT(*) AS row_count FROM stg_p2p_p2m
UNION ALL
SELECT 'stg_upi_apps',            COUNT(*) FROM stg_upi_apps
UNION ALL
SELECT 'stg_top15_psp',           COUNT(*) FROM stg_top15_psp;


-- ───────────────────────────────────────────────────────────────────
-- 2. MONTH COVERAGE PER TABLE
-- ───────────────────────────────────────────────────────────────────
SELECT year, month, COUNT(*) AS rows_this_month FROM stg_p2p_p2m GROUP BY year, month ORDER BY year, month;
SELECT year, month, COUNT(*) AS rows_this_month FROM stg_upi_apps GROUP BY year, month ORDER BY year, month;
SELECT year, month, psp_type, COUNT(*) AS rows_this_month FROM stg_top15_psp GROUP BY year, month, psp_type ORDER BY year, month, psp_type;


-- ───────────────────────────────────────────────────────────────────
-- 2b. TRAILING-EDGE REPORT (informational, not a fail condition)
--     Formalizes the "cross-source trailing-edge mismatch" decision —
--     these three numbers are EXPECTED to differ; this just surfaces
--     the current gap so it's visible at a glance, not rediscovered
--     by accident during analysis.
-- ───────────────────────────────────────────────────────────────────
SELECT 'stg_p2p_p2m' AS table_name, MAX(year * 100 + month) AS latest_yyyymm FROM stg_p2p_p2m
UNION ALL
SELECT 'stg_upi_apps', MAX(year * 100 + month) FROM stg_upi_apps
UNION ALL
SELECT 'stg_top15_psp', MAX(year * 100 + month) FROM stg_top15_psp;


-- ───────────────────────────────────────────────────────────────────
-- 3. MISSING MONTHS
--    FIX: each table's calendar now ends at ITS OWN latest loaded
--    month (via subquery), not a hardcoded global date. This removes
--    the trailing-edge false-positive and the need to hand-edit an
--    end date every month.
-- ───────────────────────────────────────────────────────────────────

-- 3a. stg_p2p_p2m — Expect: empty (no gaps, per DECISIONS.md)
WITH RECURSIVE months(year, month) AS (
    SELECT 2022, 1
    UNION ALL
    SELECT CASE WHEN month = 12 THEN year + 1 ELSE year END,
           CASE WHEN month = 12 THEN 1 ELSE month + 1 END
    FROM months
    WHERE (year * 12 + month) < (SELECT MAX(year * 12 + month) FROM stg_p2p_p2m)
)
SELECT m.year, m.month
FROM months m
LEFT JOIN stg_p2p_p2m t ON t.year = m.year AND t.month = m.month
WHERE t.year IS NULL
ORDER BY m.year, m.month;

-- 3b. stg_upi_apps — Expect: exactly one row, (2026, 3)
WITH RECURSIVE months(year, month) AS (
    SELECT 2022, 1
    UNION ALL
    SELECT CASE WHEN month = 12 THEN year + 1 ELSE year END,
           CASE WHEN month = 12 THEN 1 ELSE month + 1 END
    FROM months
    WHERE (year * 12 + month) < (SELECT MAX(year * 12 + month) FROM stg_upi_apps)
)
SELECT m.year, m.month
FROM months m
LEFT JOIN (SELECT DISTINCT year, month FROM stg_upi_apps) t
    ON t.year = m.year AND t.month = m.month
WHERE t.year IS NULL
ORDER BY m.year, m.month;

-- 3c. stg_top15_psp — Expect: exactly two rows, (2022,12,'payee') and (2026,4,'payer')
WITH RECURSIVE months(year, month) AS (
    SELECT 2022, 1
    UNION ALL
    SELECT CASE WHEN month = 12 THEN year + 1 ELSE year END,
           CASE WHEN month = 12 THEN 1 ELSE month + 1 END
    FROM months
    WHERE (year * 12 + month) < (SELECT MAX(year * 12 + month) FROM stg_top15_psp)
)
SELECT m.year, m.month, p.psp_type
FROM months m
CROSS JOIN (SELECT 'payer' AS psp_type UNION SELECT 'payee') p
LEFT JOIN (SELECT DISTINCT year, month, psp_type FROM stg_top15_psp) t
    ON t.year = m.year AND t.month = m.month AND t.psp_type = p.psp_type
WHERE t.year IS NULL
ORDER BY m.year, m.month, p.psp_type;


-- ───────────────────────────────────────────────────────────────────
-- 4. DUPLICATE MONTH / ROW-COUNT CHECKS
-- ───────────────────────────────────────────────────────────────────
SELECT year, month, COUNT(*) AS n FROM stg_p2p_p2m GROUP BY year, month HAVING COUNT(*) > 1;
-- Expect: empty

SELECT year, month, psp_type, COUNT(*) AS n FROM stg_top15_psp GROUP BY year, month, psp_type HAVING COUNT(*) != 15;
-- Expect: empty. NOTE: if this ever fails, run query 9 below before assuming a
-- source-file problem — a collapsed name-override collision (two raw spellings
-- mapping onto the same canonical name in the same month) produces this exact
-- symptom and is a different fix (add a disambiguating override) than a genuine
-- missing PSP.

-- Duplicate check for UPI APPS
SELECT year, month, app_name, COUNT(*) AS n FROM stg_upi_apps GROUP BY year, month, app_name HAVING COUNT(*) > 1;
-- Expect: empty (any row here is a NEW, undocumented duplicate)


-- ───────────────────────────────────────────────────────────────────
-- 5. CONSECUTIVE-MONTH IDENTICAL VOLUME (2024_06/07 pattern recurrence)
-- ───────────────────────────────────────────────────────────────────
SELECT a.year AS year1, a.month AS month1, a.total_volume_mn AS vol1,
       b.year AS year2, b.month AS month2, b.total_volume_mn AS vol2
FROM stg_p2p_p2m a
JOIN stg_p2p_p2m b ON (b.year * 12 + b.month) = (a.year * 12 + a.month) + 1
WHERE a.total_volume_mn = b.total_volume_mn
ORDER BY a.year, a.month;
-- Expect: empty. NOTE: this same fingerprint also caught the separate
-- 2024_03 stg_upi_apps duplicate-file incident, but that check needs the
-- app-level table, not this one — see query 6 below.

-- Same pattern check, extended to stg_upi_apps at the app-name grain
-- (this is what actually caught the 2024_03 incident — add it here as a
-- permanent guard instead of a one-off investigation query).
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
-- Expect: empty. Threshold is "nearly every app identical" rather than an
-- exact match, since a couple of genuinely flat small apps month-to-month
-- shouldn't false-positive this.


-- ───────────────────────────────────────────────────────────────────
-- 6. NULL / ZERO SPOT-CHECKS
-- ───────────────────────────────────────────────────────────────────
SELECT year, month, total_volume_mn, p2p_volume_mn, p2m_volume_mn
FROM stg_p2p_p2m
WHERE total_volume_mn IS NULL OR p2p_volume_mn IS NULL OR p2m_volume_mn IS NULL OR total_volume_mn <= 0;

SELECT year, month, COUNT(*) AS null_share_rows FROM stg_upi_apps WHERE market_share_pct IS NULL GROUP BY year, month;

SELECT year, month, psp_type, COUNT(*) AS null_approval_rows FROM stg_top15_psp WHERE approved_percent IS NULL GROUP BY year, month, psp_type;


-- ───────────────────────────────────────────────────────────────────
-- 7. MARKET SHARE SUMS TO ~100% PER MONTH (stg_upi_apps)
-- ───────────────────────────────────────────────────────────────────
SELECT year, month, ROUND(SUM(market_share_pct), 2) AS share_sum
FROM stg_upi_apps GROUP BY year, month
HAVING ABS(SUM(market_share_pct) - 100) > 0.5 ORDER BY year, month;
-- Expect: empty


-- ───────────────────────────────────────────────────────────────────
-- 8. NEW — PERCENT-SUM REGRESSION GUARD (stg_top15_psp)
--    This is the check that originally caught the percent-scaling bug
--    (previously lived only in the analytical psp_reliability.sql —
--    promoted here as a permanent pipeline-health check).
-- ───────────────────────────────────────────────────────────────────
SELECT year, month, psp_type, psp_name,
       ROUND(approved_percent + business_decline_percent + technical_decline_percent, 2) AS pct_sum
FROM stg_top15_psp
WHERE ABS(approved_percent + business_decline_percent + technical_decline_percent - 100) > 0.5
ORDER BY year, month, psp_type;
-- Expect: empty


-- ───────────────────────────────────────────────────────────────────
-- 9. NEW — psp_name CASING/SPELLING REGRESSION GUARD
--    Confirms clean_psp_name() is still normalizing every month —
--    this is QA A from psp_name_casing_scope_check.sql, promoted to
--    a permanent check rather than a one-time investigation.
-- ───────────────────────────────────────────────────────────────────
SELECT UPPER(TRIM(psp_name)) AS normalized_name, psp_type,
       COUNT(DISTINCT psp_name) AS distinct_raw_spellings,
       GROUP_CONCAT(DISTINCT psp_name) AS raw_spellings_seen
FROM stg_top15_psp
GROUP BY normalized_name, psp_type
HAVING COUNT(DISTINCT psp_name) > 1;
-- Expect: empty


-- ───────────────────────────────────────────────────────────────────
-- 10. NEW — OVERRIDE-COLLISION GUARD
--     Confirms PSP_NAME_OVERRIDES never collapses two distinct raw
--     rows onto the same canonical name within a single (year, month,
--     psp_type) — this would silently understate that month's top-15
--     to 14 real PSPs even though query 4's row-count check might not
--     make the cause obvious.
-- ───────────────────────────────────────────────────────────────────
SELECT year, month, psp_type, psp_name, COUNT(*) AS n
FROM stg_top15_psp
GROUP BY year, month, psp_type, psp_name
HAVING COUNT(*) > 1;
-- Expect: empty


-- ───────────────────────────────────────────────────────────────────
-- 11. NEW — PRE-OVERRIDE LEGACY NAME LEAKAGE GUARD
--     Confirms the entity-lineage overrides (Slice/NESFB, BHIM/NBSL,
--     IDFC Bank/IDFC First Bank) are actually being applied on every
--     reload — catches the override dict silently falling out of
--     sync with clean_psp_name()'s call site.
-- ───────────────────────────────────────────────────────────────────
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
-- Expect: empty


-- ───────────────────────────────────────────────────────────────────
-- 12. HEADER-LEAK PERMANENT GUARD (promoted from investigation.sql)
--     The 2022-04 instance was fixed via manual DELETE, not an ETL
--     fix — this guard protects against a future file hitting the
--     same row-offset parsing issue.
-- ───────────────────────────────────────────────────────────────────
SELECT year, month, app_name, total_volume_mn, total_value_cr
FROM stg_upi_apps
WHERE app_name IN ('Application Name', 'Sr No', 'Sr. No.', 'Sr.No.')
   OR total_volume_mn IS NULL;
-- Expect: empty


-- ───────────────────────────────────────────────────────────────────
-- 13. NEW — BD/TD COMPOSITION ANOMALY DETECTOR
--     Flags any (year, month, psp_type) where business_decline_percent
--     is near-zero across the board — the fingerprint of the 2023-06
--     payer anomaly. That one instance is documented/explained in
--     DECISIONS.md; this check exists to catch a RECURRENCE, which
--     would mean it's not actually a one-off template change.
-- ───────────────────────────────────────────────────────────────────
SELECT year, month, psp_type, ROUND(AVG(business_decline_percent), 3) AS avg_bd_pct
FROM stg_top15_psp
GROUP BY year, month, psp_type
HAVING AVG(business_decline_percent) < 0.2
   AND (year, month, psp_type) != (2023, 6, 'payer');
-- Expect: empty. A hit here = investigate as a NEW anomaly, don't assume
-- it's explained by the existing 2023-06 write-up.