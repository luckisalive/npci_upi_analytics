-- ───────────────────────────────────────────────────────────────────
-- 1. ROW COUNTS PER TABLE
-- ───────────────────────────────────────────────────────────────────
SELECT 'stg_p2p_p2m'   AS table_name, COUNT(*) AS row_count FROM stg_p2p_p2m
UNION ALL
SELECT 'stg_upi_apps',            COUNT(*) FROM stg_upi_apps
UNION ALL
SELECT 'stg_top15_psp',           COUNT(*) FROM stg_top15_psp;

-- Sanity expectation:
--   stg_p2p_p2m   ≈ 1 row  * (# months loaded)
--   stg_upi_apps  ≈ (apps per month, varies) * (# months loaded)
--   stg_top15_psp ≈ 15 rows * (# months loaded) * 2 (payer+payee), minus the 2 known-missing files


-- ───────────────────────────────────────────────────────────────────
-- 2. MONTH COVERAGE PER TABLE (year, month, row count)
-- ───────────────────────────────────────────────────────────────────
SELECT 'stg_p2p_p2m' AS table_name, year, month, COUNT(*) AS rows_this_month
FROM stg_p2p_p2m
GROUP BY year, month
ORDER BY year, month;

SELECT 'stg_upi_apps' AS table_name, year, month, COUNT(*) AS rows_this_month
FROM stg_upi_apps
GROUP BY year, month
ORDER BY year, month;

SELECT 'stg_top15_psp' AS table_name, year, month, psp_type, COUNT(*) AS rows_this_month
FROM stg_top15_psp
GROUP BY year, month, psp_type
ORDER BY year, month, psp_type;


-- ───────────────────────────────────────────────────────────────────
-- 3. MISSING MONTHS — generate the expected 2022_01..2026_05 calendar
--    and LEFT JOIN each table against it to find gaps.
-- ───────────────────────────────────────────────────────────────────
WITH RECURSIVE months(year, month) AS (
    SELECT 2022, 1
    UNION ALL
    SELECT
        CASE WHEN month = 12 THEN year + 1 ELSE year END,
        CASE WHEN month = 12 THEN 1 ELSE month + 1 END
    FROM months
    WHERE (year < 2026) OR (year = 2026 AND month < 5)
)
SELECT m.year, m.month
FROM months m
LEFT JOIN stg_p2p_p2m t ON t.year = m.year AND t.month = m.month
WHERE t.year IS NULL
ORDER BY m.year, m.month;
-- Expect: empty result set (P2P/P2M should have no gaps per DECISIONS.md)

WITH RECURSIVE months(year, month) AS (
    SELECT 2022, 1
    UNION ALL
    SELECT
        CASE WHEN month = 12 THEN year + 1 ELSE year END,
        CASE WHEN month = 12 THEN 1 ELSE month + 1 END
    FROM months
    WHERE (year < 2026) OR (year = 2026 AND month < 5)
)
SELECT m.year, m.month
FROM months m
LEFT JOIN (SELECT DISTINCT year, month FROM stg_upi_apps) t
    ON t.year = m.year AND t.month = m.month
WHERE t.year IS NULL
ORDER BY m.year, m.month;
-- Expect: exactly one row — 2026, 3 (the documented gap)

WITH RECURSIVE months(year, month) AS (
    SELECT 2022, 1
    UNION ALL
    SELECT
        CASE WHEN month = 12 THEN year + 1 ELSE year END,
        CASE WHEN month = 12 THEN 1 ELSE month + 1 END
    FROM months
    WHERE (year < 2026) OR (year = 2026 AND month < 5)
)
SELECT m.year, m.month, p.psp_type
FROM months m
CROSS JOIN (SELECT 'payer' AS psp_type UNION SELECT 'payee') p
LEFT JOIN (SELECT DISTINCT year, month, psp_type FROM stg_top15_psp) t
    ON t.year = m.year AND t.month = m.month AND t.psp_type = p.psp_type
WHERE t.year IS NULL
ORDER BY m.year, m.month, p.psp_type;
-- Expect: exactly two rows — (2022,12,'payee') and (2026,4,'payer')


-- ───────────────────────────────────────────────────────────────────
-- 4. DUPLICATE MONTH CHECK 
-- ───────────────────────────────────────────────────────────────────
SELECT year, month, COUNT(*) AS n
FROM stg_p2p_p2m
GROUP BY year, month
HAVING COUNT(*) > 1;
-- Expect: empty (one row per month by design)

SELECT year, month, psp_type, COUNT(*) AS n
FROM stg_top15_psp
GROUP BY year, month, psp_type
HAVING COUNT(*) != 15;
-- Expect: empty (15 PSPs per month per type, per "Top 15" schema decision)

SELECT year, month, app_name, COUNT(*) AS n
FROM stg_upi_apps
GROUP BY year, month, app_name
HAVING COUNT(*) > 1;
-- Expect: empty (one row per app per month)


-- ───────────────────────────────────────────────────────────────────
-- 5. RE-CHECK FOR THE 2024_06/2024_07 DUPLICATE-VALUE PATTERN
-- ───────────────────────────────────────────────────────────────────
SELECT
    a.year AS year1, a.month AS month1, a.total_volume_mn AS vol1,
    b.year AS year2, b.month AS month2, b.total_volume_mn AS vol2
FROM stg_p2p_p2m a
JOIN stg_p2p_p2m b
    ON (b.year * 12 + b.month) = (a.year * 12 + a.month) + 1
WHERE a.total_volume_mn = b.total_volume_mn
ORDER BY a.year, a.month;
-- Expect: empty. Any row here = two consecutive months with byte-identical


-- ───────────────────────────────────────────────────────────────────
-- 6. NULL / ZERO SPOT-CHECK ON KEY METRIC COLUMNS
--    (broad smoke test — not exhaustive, just catches obvious breakage)
-- ───────────────────────────────────────────────────────────────────
SELECT year, month, total_volume_mn, p2p_volume_mn, p2m_volume_mn
FROM stg_p2p_p2m
WHERE total_volume_mn IS NULL
   OR p2p_volume_mn IS NULL
   OR p2m_volume_mn IS NULL
   OR total_volume_mn <= 0;

SELECT year, month, COUNT(*) AS null_share_rows
FROM stg_upi_apps
WHERE market_share_pct IS NULL
GROUP BY year, month;

SELECT year, month, psp_type, COUNT(*) AS null_approval_rows
FROM stg_top15_psp
WHERE approved_percent IS NULL
GROUP BY year, month, psp_type;


-- ───────────────────────────────────────────────────────────────────
-- 7. MARKET SHARE SUMS TO ~100% PER MONTH (stg_upi_apps)
-- ───────────────────────────────────────────────────────────────────
SELECT year, month, ROUND(SUM(market_share_pct), 2) AS share_sum
FROM stg_upi_apps
GROUP BY year, month
HAVING ABS(SUM(market_share_pct) - 100) > 0.5
ORDER BY year, month;
-- Expect: empty (allowing 0.5pp rounding slack)