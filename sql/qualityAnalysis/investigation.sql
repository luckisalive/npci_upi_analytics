-- ───────────────────────────────────────────────────────────────────
-- A. TRAILING-EDGE MISMATCH — confirm max month per table
-- ───────────────────────────────────────────────────────────────────
SELECT 'stg_p2p_p2m' AS table_name, MAX(year * 100 + month) AS latest_yyyymm FROM stg_p2p_p2m
UNION ALL
SELECT 'stg_upi_apps', MAX(year * 100 + month) FROM stg_upi_apps
UNION ALL
SELECT 'stg_top15_psp', MAX(year * 100 + month) FROM stg_top15_psp;


-- ───────────────────────────────────────────────────────────────────
-- B. DUPLICATE APP-MONTH ROWS
-- ───────────────────────────────────────────────────────────────────
SELECT *
FROM stg_upi_apps
WHERE (year, month, app_name) IN (
    (2023, 2, 'Bajaj Finserv'),
    (2023, 11, 'Mobikwik'),
    (2023, 12, 'Mobikwik'),
    (2024, 7, 'Federal Bank Apps'),
    (2025, 8, 'Others')
)
ORDER BY year, month, app_name, id;


-- ───────────────────────────────────────────────────────────────────
-- C. NULL market_share_pct — find the specific 2022-04 row and its
--    raw total_volume_mn / total_value_cr to see what failed to parse
-- ───────────────────────────────────────────────────────────────────
SELECT *
FROM stg_upi_apps
WHERE year = 2022 AND month = 4 AND market_share_pct IS NULL;

-- For context, the other 2022-04 rows (to compare against):
SELECT app_name, total_volume_mn, total_value_cr, market_share_pct
FROM stg_upi_apps
WHERE year = 2022 AND month = 4
ORDER BY total_volume_mn DESC;


-- ───────────────────────────────────────────────────────────────────
-- D. HEADER-LEAK CHECK — Checks for known header/label strings anywhere in app_name.
-- ───────────────────────────────────────────────────────────────────
SELECT year, month, app_name, total_volume_mn, total_value_cr
FROM stg_upi_apps
WHERE app_name IN ('Application Name', 'Sr No', 'Sr. No.', 'Sr.No.')
   OR total_volume_mn IS NULL
ORDER BY year, month;
-- Expect: only the single 2022-04 'Application Name' row already found.
-- Any other row here means the row-offset bug hit more than one file.