-- needs to be redacted

-- ───────────────────────────────────────────────────────────────────
-- STEP 6 — UNIFIED MONTHLY METRICS
-- Powers Dashboard Page 4 (Cross-cutting narrative), Panel 4b —
-- one row per month, HHI + P2P/P2M share + PSP approval rate on a
-- shared time axis.
--
-- GRAIN: (year, month). This is NOT a row-level join across the three
-- staging tables — stg_upi_apps (apps) and stg_top15_psp (banks) are
-- different entity types that only share the time dimension. Each
-- source is aggregated to monthly grain independently, then the three
-- monthly aggregates are LEFT JOINed on (year, month).
--
-- AS-OF CUTOFF: per the "Cross-source trailing-edge mismatch" decision
-- in DECISIONS.md, each table publishes on its own lag. This query
-- caps at the EARLIEST common latest-month across all three tables so
-- the chart never implies one series extends further than the others.
-- Cutoff is computed dynamically (MIN of each table's own MAX ym),
-- matching the pattern already used in sanityCheck.py's
-- table_max_month() rather than a hardcoded date.
--
-- Expect: 1 row per calendar month from 2022-01 through the cutoff
-- month. Metric columns may be NULL only within the three documented
-- mid-series gaps (payee 2022-12, payer 2026-04, upi_apps 2026-03) —
-- any other NULL is a new gap and should be investigated, not assumed.
-- ───────────────────────────────────────────────────────────────────

WITH cutoff AS (
    SELECT MIN(max_ym) AS cutoff_ym FROM (
        SELECT MAX(year * 100 + month) AS max_ym FROM stg_p2p_p2m
        UNION ALL
        SELECT MAX(year * 100 + month) FROM stg_upi_apps
        UNION ALL
        SELECT MAX(year * 100 + month) FROM stg_top15_psp
    )
),

-- ── stg_upi_apps: app-level share, summed first per the duplicate-
--    app-month decision (summing share_pct before squaring is
--    equivalent to summing volume first — share is volume-proportional)
app_month_agg AS (
    SELECT year, month, app_name, SUM(market_share_pct) AS share_pct
    FROM stg_upi_apps
    WHERE app_name != 'Application Name'
    GROUP BY year, month, app_name
),

hhi_monthly AS (
    SELECT year, month,
           ROUND(SUM(share_pct * share_pct), 2) AS hhi,
           CASE
               WHEN SUM(share_pct * share_pct) > 2500 THEN 'Highly Concentrated'
               WHEN SUM(share_pct * share_pct) >= 1500 THEN 'Moderately Concentrated'
               ELSE 'Unconcentrated'
           END AS hhi_band
    FROM app_month_agg
    GROUP BY year, month
),

leader_ranked AS (
    SELECT year, month, app_name, share_pct,
           ROW_NUMBER() OVER (PARTITION BY year, month ORDER BY share_pct DESC) AS rn
    FROM app_month_agg
),

leader_monthly AS (
    SELECT year, month, app_name AS top_leader, share_pct AS top_leader_share_pct
    FROM leader_ranked WHERE rn = 1
),

-- ── stg_p2p_p2m: share pct already computed at ETL time; YoY growth
--    computed here on volume (12-month LAG), not on share
p2p_p2m_yoy AS (
    SELECT year, month, p2p_share_pct, p2m_share_pct,
           p2p_volume_mn, p2m_volume_mn,
           LAG(p2p_volume_mn, 12) OVER (ORDER BY year * 12 + month) AS p2p_vol_ly,
           LAG(p2m_volume_mn, 12) OVER (ORDER BY year * 12 + month) AS p2m_vol_ly
    FROM stg_p2p_p2m
),

p2p_p2m_monthly AS (
    SELECT year, month, p2p_share_pct, p2m_share_pct,
           CASE WHEN p2p_vol_ly > 0
                THEN ROUND((p2p_volume_mn - p2p_vol_ly) / p2p_vol_ly * 100, 2) END AS p2p_yoy_pct,
           CASE WHEN p2m_vol_ly > 0
                THEN ROUND((p2m_volume_mn - p2m_vol_ly) / p2m_vol_ly * 100, 2) END AS p2m_yoy_pct
    FROM p2p_p2m_yoy
),

-- ── stg_top15_psp: simple average approval % per side, per month.
--    NOTE: this is the simple average for a general-overview chart,
--    NOT the volume-weighted figure used in the payer-side decline
--    decomposition (Decisions.md) — do not conflate the two in the
--    dashboard caption.
psp_monthly AS (
    SELECT year, month,
           ROUND(AVG(CASE WHEN psp_type = 'payer' THEN approved_percent END), 2) AS payer_approval_avg,
           ROUND(AVG(CASE WHEN psp_type = 'payee' THEN approved_percent END), 2) AS payee_approval_avg
    FROM stg_top15_psp
    GROUP BY year, month
),

-- ── calendar backbone, 2022-01 through cutoff — same recursive
--    pattern as sanityCheck.sql's missing-month checks
months(year, month) AS (
    SELECT 2022, 1
    UNION ALL
    SELECT CASE WHEN month = 12 THEN year + 1 ELSE year END,
           CASE WHEN month = 12 THEN 1 ELSE month + 1 END
    FROM months
    WHERE (year * 12 + month) < (SELECT cutoff_ym / 100 * 12 + cutoff_ym % 100 FROM cutoff)
)

SELECT
    m.year, m.month,
    h.hhi, h.hhi_band,
    l.top_leader, l.top_leader_share_pct,
    pm.p2p_share_pct, pm.p2m_share_pct, pm.p2p_yoy_pct, pm.p2m_yoy_pct,
    ps.payer_approval_avg, ps.payee_approval_avg
FROM months m
LEFT JOIN hhi_monthly    h  ON h.year = m.year  AND h.month = m.month
LEFT JOIN leader_monthly l  ON l.year = m.year  AND l.month = m.month
LEFT JOIN p2p_p2m_monthly pm ON pm.year = m.year AND pm.month = m.month
LEFT JOIN psp_monthly    ps ON ps.year = m.year AND ps.month = m.month
ORDER BY m.year, m.month;