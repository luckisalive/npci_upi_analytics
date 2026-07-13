-- ───────────────────────────────────────────────────────────────────
-- A. DUPLICATE APP-MONTH ROWS
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
-- B. NULL market_share_pct — find the specific 2022-04 row and its
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
