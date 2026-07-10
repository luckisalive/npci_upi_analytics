-- ───────────────────────────────────────────────────────────────────
-- 1. MONTHLY MARKET SHARE PER APP (aggregated, recomputed fresh —
--    does NOT reuse the ETL's row-level market_share_pct column,
--    since that was computed pre-aggregation and would be wrong for
--    the 5 known duplicate-name months)
-- ───────────────────────────────────────────────────────────────────
WITH agg AS (
    SELECT year, month, app_name, SUM(total_volume_mn) AS app_volume_mn
    FROM stg_upi_apps
    WHERE app_name != 'Application Name'
    GROUP BY year, month, app_name
),
monthly_totals AS (
    SELECT year, month, SUM(app_volume_mn) AS month_total_volume_mn
    FROM agg
    GROUP BY year, month
)
SELECT
    a.year,
    a.month,
    a.app_name,
    a.app_volume_mn,
    ROUND(a.app_volume_mn / m.month_total_volume_mn * 100, 4) AS share_pct
FROM agg a
JOIN monthly_totals m ON a.year = m.year AND a.month = m.month
ORDER BY a.year, a.month, share_pct DESC;


-- ───────────────────────────────────────────────────────────────────
-- 2. MONTHLY HHI + CONCENTRATION BAND
-- ───────────────────────────────────────────────────────────────────
WITH agg AS (
    SELECT year, month, app_name, SUM(total_volume_mn) AS app_volume_mn
    FROM stg_upi_apps
    WHERE app_name != 'Application Name'
    GROUP BY year, month, app_name
),
monthly_totals AS (
    SELECT year, month, SUM(app_volume_mn) AS month_total_volume_mn
    FROM agg
    GROUP BY year, month
),
shares AS (
    SELECT
        a.year, a.month, a.app_name,
        a.app_volume_mn / m.month_total_volume_mn * 100 AS share_pct
    FROM agg a
    JOIN monthly_totals m ON a.year = m.year AND a.month = m.month
)
SELECT
    year,
    month,
    ROUND(SUM(share_pct * share_pct), 2) AS hhi,
    CASE
        WHEN SUM(share_pct * share_pct) < 1500 THEN 'Unconcentrated'
        WHEN SUM(share_pct * share_pct) <= 2500 THEN 'Moderately Concentrated'
        ELSE 'Highly Concentrated'
    END AS concentration_band
FROM shares
GROUP BY year, month
ORDER BY year, month;


-- ───────────────────────────────────────────────────────────────────
-- 3. HHI TREND — same as #2 but with month-over-month change, to
--    answer "is concentration rising, falling, or flat" directly
--    rather than requiring a chart to eyeball it.
-- ───────────────────────────────────────────────────────────────────
WITH agg AS (
    SELECT year, month, app_name, SUM(total_volume_mn) AS app_volume_mn
    FROM stg_upi_apps
    WHERE app_name != 'Application Name'
    GROUP BY year, month, app_name
),
monthly_totals AS (
    SELECT year, month, SUM(app_volume_mn) AS month_total_volume_mn
    FROM agg
    GROUP BY year, month
),
shares AS (
    SELECT
        a.year, a.month, a.app_name,
        a.app_volume_mn / m.month_total_volume_mn * 100 AS share_pct
    FROM agg a
    JOIN monthly_totals m ON a.year = m.year AND a.month = m.month
),
monthly_hhi AS (
    SELECT year, month, ROUND(SUM(share_pct * share_pct), 2) AS hhi
    FROM shares
    GROUP BY year, month
)
SELECT
    year,
    month,
    hhi,
    hhi - LAG(hhi) OVER (ORDER BY year, month) AS hhi_change_mom,
    ROUND(hhi - FIRST_VALUE(hhi) OVER (ORDER BY year, month), 2) AS hhi_change_since_start
FROM monthly_hhi
ORDER BY year, month;


-- ───────────────────────────────────────────────────────────────────
-- 4. TOP-3 APP COMBINED SHARE OVER TIME — a more interview-legible
--    concentration lens alongside HHI ("top 3 apps control X% of
--    volume" is easier to communicate than a raw HHI number).
-- ───────────────────────────────────────────────────────────────────
WITH agg AS (
    SELECT year, month, app_name, SUM(total_volume_mn) AS app_volume_mn
    FROM stg_upi_apps
    WHERE app_name != 'Application Name'
    GROUP BY year, month, app_name
),
monthly_totals AS (
    SELECT year, month, SUM(app_volume_mn) AS month_total_volume_mn
    FROM agg
    GROUP BY year, month
),
shares AS (
    SELECT
        a.year, a.month, a.app_name,
        a.app_volume_mn / m.month_total_volume_mn * 100 AS share_pct
    FROM agg a
    JOIN monthly_totals m ON a.year = m.year AND a.month = m.month
),
ranked AS (
    SELECT
        year, month, app_name, share_pct,
        ROW_NUMBER() OVER (PARTITION BY year, month ORDER BY share_pct DESC) AS rnk
    FROM shares
)
SELECT
    year,
    month,
    ROUND(SUM(share_pct), 2) AS top3_combined_share_pct
FROM ranked
WHERE rnk <= 3
GROUP BY year, month
ORDER BY year, month;


-- ───────────────────────────────────────────────────────────────────
-- 5. MARKET LEADER PER MONTH — which app is #1, and how often does
--    leadership change hands (stability of dominance, not just size
--    of dominance).
-- ───────────────────────────────────────────────────────────────────
WITH agg AS (
    SELECT year, month, app_name, SUM(total_volume_mn) AS app_volume_mn
    FROM stg_upi_apps
    WHERE app_name != 'Application Name'
    GROUP BY year, month, app_name
),
monthly_totals AS (
    SELECT year, month, SUM(app_volume_mn) AS month_total_volume_mn
    FROM agg
    GROUP BY year, month
),
shares AS (
    SELECT
        a.year, a.month, a.app_name,
        a.app_volume_mn / m.month_total_volume_mn * 100 AS share_pct
    FROM agg a
    JOIN monthly_totals m ON a.year = m.year AND a.month = m.month
),
ranked AS (
    SELECT
        year, month, app_name, share_pct,
        ROW_NUMBER() OVER (PARTITION BY year, month ORDER BY share_pct DESC) AS rnk
    FROM shares
)
SELECT year, month, app_name AS market_leader, ROUND(share_pct, 2) AS leader_share_pct
FROM ranked
WHERE rnk = 1
ORDER BY year, month;