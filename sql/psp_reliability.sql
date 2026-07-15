-- ─────────────────────────────────────────────────────────────────
-- BLOCK 1: Sanity check — approved% + business_decline% + technical_decline%
-- should sum to ~100 per row.
-- Expect: no rows returned (or only rows explained by known gaps above)
-- ─────────────────────────────────────────────────────────────────
SELECT
    year, month, psp_type, psp_name,
    approved_percent, business_decline_percent, technical_decline_percent,
    ROUND(approved_percent + business_decline_percent + technical_decline_percent, 2) AS pct_sum
FROM stg_top15_psp
WHERE ABS(approved_percent + business_decline_percent + technical_decline_percent - 100) > 0.5
ORDER BY year, month, psp_type;

-- ─────────────────────────────────────────────────────────────────
-- BLOCK 2: Volume-weighted overall approval rate trend, monthly, split by payer vs payee side.
-- ─────────────────────────────────────────────────────────────────
SELECT
    year, month, psp_type,
    ROUND(SUM(approved_percent * total_volume_mn) / SUM(total_volume_mn), 2) AS volume_weighted_approval_pct,
    ROUND(AVG(approved_percent), 2) AS simple_avg_approval_pct,
    ROUND(SUM(total_volume_mn), 2) AS total_volume_mn
FROM stg_top15_psp
GROUP BY year, month, psp_type
ORDER BY year, month, psp_type;


-- ─────────────────────────────────────────────────────────────────
-- BLOCK 3: Persistent leaders / laggards.
-- ─────────────────────────────────────────────────────────────────
WITH available_months AS (
    SELECT psp_type, COUNT(DISTINCT year * 100 + month) AS max_months
    FROM stg_top15_psp
    GROUP BY psp_type
)
SELECT
    t.psp_type, t.psp_name,
    COUNT(*) AS months_present,
    ROUND(AVG(t.approved_percent), 2) AS avg_approval_pct,
    ROUND(MIN(t.approved_percent), 2) AS min_approval_pct,
    ROUND(MAX(t.approved_percent), 2) AS max_approval_pct,
    ROUND(SUM(t.total_volume_mn), 2) AS total_volume_mn_across_appearances
FROM stg_top15_psp t
JOIN available_months am ON am.psp_type = t.psp_type
GROUP BY t.psp_type, t.psp_name
HAVING COUNT(*) = am.max_months
ORDER BY t.psp_type, avg_approval_pct DESC;

-- ─────────────────────────────────────────────────────────────────
-- BLOCK 4: Decline composition — of the transactions that fail,
-- what share is business decline (PSP/bank-side, e.g. insufficient
-- funds) vs technical decline (infrastructure-side, e.g. timeout)?
-- ─────────────────────────────────────────────────────────────────
SELECT
    year, month, psp_type,
    ROUND(SUM(business_decline_percent * total_volume_mn) / SUM(total_volume_mn), 2) AS volume_weighted_bd_pct,
    ROUND(SUM(technical_decline_percent * total_volume_mn) / SUM(total_volume_mn), 2) AS volume_weighted_td_pct,
    ROUND(
        SUM(technical_decline_percent * total_volume_mn) /
        NULLIF(SUM((business_decline_percent + technical_decline_percent) * total_volume_mn), 0) * 100
    , 2) AS technical_share_of_total_declines_pct
FROM stg_top15_psp
GROUP BY year, month, psp_type
ORDER BY year, month, psp_type;

-- ─────────────────────────────────────────────────────────────────
-- BLOCK 5: Top-15 churn — first and last month each PSP appears,
-- and how many distinct PSPs have cycled through the top-15 at all.
-- ─────────────────────────────────────────────────────────────────
SELECT
    psp_type, psp_name,
    MIN(year * 100 + month) AS first_ym,
    MAX(year * 100 + month) AS last_ym,
    COUNT(*) AS months_present
FROM stg_top15_psp
GROUP BY psp_type, psp_name
ORDER BY psp_type, first_ym, psp_name;

-- ─────────────────────────────────────────────────────────────────
-- BLOCK 6: Macro-level cross-table correlation.
-- Approval-rate trend vs overall ecosystem volume growth vs app-level HHI concentration
-- ─────────────────────────────────────────────────────────────────
WITH app_cleaned AS (
    SELECT year, month, app_name, SUM(total_volume_mn) AS total_volume_mn
    FROM stg_upi_apps
    WHERE app_name != 'Application Name'
    GROUP BY year, month, app_name
),
month_totals AS (
    SELECT year, month, SUM(total_volume_mn) AS month_total_volume_mn
    FROM app_cleaned
    GROUP BY year, month
),
app_shares AS (
    SELECT a.year, a.month, a.app_name,
           a.total_volume_mn * 100.0 / t.month_total_volume_mn AS share_pct
    FROM app_cleaned a
    JOIN month_totals t ON a.year = t.year AND a.month = t.month
),
hhi_monthly AS (
    SELECT year, month, ROUND(SUM(share_pct * share_pct), 2) AS hhi
    FROM app_shares
    GROUP BY year, month
),
psp_monthly AS (
    SELECT year, month,
           SUM(approved_percent * total_volume_mn) / SUM(total_volume_mn) AS volume_weighted_approval_pct
    FROM stg_top15_psp
    GROUP BY year, month, psp_type
)
SELECT
    psp.year,
    psp.month,
    ROUND(AVG(psp.volume_weighted_approval_pct), 2) AS avg_approval_pct_both_sides,
    p2p.total_volume_mn AS ecosystem_total_volume_mn,
    p2p.p2m_share_pct,
    hhi.hhi AS app_level_hhi
FROM psp_monthly psp
JOIN stg_p2p_p2m p2p
    ON p2p.year = psp.year AND p2p.month = psp.month
JOIN hhi_monthly hhi
    ON hhi.year = psp.year AND hhi.month = psp.month
WHERE (psp.year < 2026) OR (psp.year = 2026 AND psp.month <= 3)
GROUP BY psp.year, psp.month
ORDER BY psp.year, psp.month;
