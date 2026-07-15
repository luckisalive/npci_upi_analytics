-- ═══════════════════════════════════════════════════════════════════
-- STEP 6 — CROSS-CUTTING NARRATIVE (three-table join analysis)
-- Feeds Dashboard Page 4: "Concentration × reliability" and
-- "Unified monthly timeline" panels.
--
-- Join strategy: LEFT JOIN (per existing DECISIONS.md join-strategy
-- rule), capped at the as-of cutoff (per existing as-of-cutoff rule).
-- Each block is self-contained and independently rerunnable.
-- ═══════════════════════════════════════════════════════════════════


-- ───────────────────────────────────────────────────────────────────
-- 0. AS-OF CUTOFF DETERMINATION (informational — run first)
--    Recomputed at query time rather than hardcoded, same pattern as
--    the dynamic persistent-leader threshold fix in psp_reliability.sql.
-- ───────────────────────────────────────────────────────────────────
SELECT
  (SELECT MAX(year*100+month) FROM stg_p2p_p2m)   AS p2p_p2m_max,
  (SELECT MAX(year*100+month) FROM stg_upi_apps)  AS upi_apps_max,
  (SELECT MAX(year*100+month) FROM stg_top15_psp) AS top15_psp_max,
  MIN(
    (SELECT MAX(year*100+month) FROM stg_p2p_p2m),
    (SELECT MAX(year*100+month) FROM stg_upi_apps),
    (SELECT MAX(year*100+month) FROM stg_top15_psp)
  ) AS as_of_cutoff_yyyymm;
-- Note: MIN() is used deliberately, not MAX() — the cutoff must be
-- the LATEST month ALL THREE tables have reached, i.e. the earliest
-- of the three trailing edges.


-- ───────────────────────────────────────────────────────────────────
-- PANEL A — UNIFIED MONTHLY TIMELINE
-- HHI (stg_upi_apps) + P2M share (stg_p2p_p2m) + payer/payee approval
-- rate (stg_top15_psp), one row per month, capped at the as-of cutoff.
-- ───────────────────────────────────────────────────────────────────

WITH cutoff AS (
    SELECT MIN(
        (SELECT MAX(year*100+month) FROM stg_p2p_p2m),
        (SELECT MAX(year*100+month) FROM stg_upi_apps),
        (SELECT MAX(year*100+month) FROM stg_top15_psp)
    ) AS yyyymm
),
app_monthly AS (
    -- SUM-before-share, per the existing duplicate-app-month decision
    SELECT year, month, app_name, SUM(total_volume_mn) AS vol
    FROM stg_upi_apps
    WHERE app_name != 'Application Name'
    GROUP BY year, month, app_name
),
month_totals AS (
    SELECT year, month, SUM(vol) AS total_vol
    FROM app_monthly GROUP BY year, month
),
hhi AS (
    SELECT a.year, a.month,
           ROUND(SUM((100.0 * a.vol / m.total_vol) * (100.0 * a.vol / m.total_vol)), 2) AS hhi_score
    FROM app_monthly a
    JOIN month_totals m ON m.year = a.year AND m.month = a.month
    GROUP BY a.year, a.month
),
p2m AS (
    SELECT year, month, p2m_share_pct
    FROM stg_p2p_p2m
),
approval AS (
    SELECT year, month,
           ROUND(AVG(CASE WHEN psp_type = 'payer' THEN approved_percent END), 2) AS payer_approval_avg,
           ROUND(AVG(CASE WHEN psp_type = 'payee' THEN approved_percent END), 2) AS payee_approval_avg
    FROM stg_top15_psp
    GROUP BY year, month
)
SELECT
    h.year, h.month,
    h.hhi_score,
    CASE
        WHEN h.hhi_score > 2500 THEN 'Highly Concentrated'
        WHEN h.hhi_score >= 1500 THEN 'Moderately Concentrated'
        ELSE 'Unconcentrated'
    END AS hhi_band,
    p.p2m_share_pct,
    a.payer_approval_avg,
    a.payee_approval_avg
FROM hhi h
LEFT JOIN p2m p     ON p.year = h.year AND p.month = h.month
LEFT JOIN approval a ON a.year = h.year AND a.month = h.month
WHERE (h.year * 100 + h.month) <= (SELECT yyyymm FROM cutoff)
ORDER BY h.year, h.month;
-- Expect: one row per month from 2022-01 through the as-of cutoff.
-- NULLs in p2m_share_pct / payer_approval_avg / payee_approval_avg are
-- legitimate at the three documented gap months (payee 2022-12 has no
-- top15_psp payee data, etc.) — not a bug, per the LEFT JOIN strategy.


-- ───────────────────────────────────────────────────────────────────
-- PANEL B — CONCENTRATION × RELIABILITY
-- PhonePe-partner banks (Yes Bank, Axis Bank, ICICI Bank), payer side,
-- vs. the REST of the payer-side field (partners excluded from the
-- baseline so the comparison isn't diluted by itself).
-- Correlational only — see existing PhonePe-partner conditional-
-- inference framing in DECISIONS.md.
-- ───────────────────────────────────────────────────────────────────

WITH partner AS (
    SELECT year, month, ROUND(AVG(approved_percent), 2) AS partner_approval
    FROM stg_top15_psp
    WHERE psp_type = 'payer'
      AND psp_name IN ('Yes Bank', 'Axis Bank', 'ICICI Bank')
    GROUP BY year, month
),
rest_of_field AS (
    SELECT year, month, ROUND(AVG(approved_percent), 2) AS field_approval
    FROM stg_top15_psp
    WHERE psp_type = 'payer'
      AND psp_name NOT IN ('Yes Bank', 'Axis Bank', 'ICICI Bank')
    GROUP BY year, month
)
SELECT
    p.year, p.month,
    p.partner_approval,
    r.field_approval,
    ROUND(p.partner_approval - r.field_approval, 2) AS gap_pts
FROM partner p
JOIN rest_of_field r ON r.year = p.year AND r.month = p.month
ORDER BY p.year, p.month;
-- Expect: gap_pts near 0 in early months, widening negative over time
-- if the payer-side decomposition finding (Yes/Axis/ICICI driving the
-- weighted decline) holds up at monthly grain, not just the 2022-vs-2025
-- annual comparison already documented.


-- ───────────────────────────────────────────────────────────────────
-- PANEL B (supplement) — 2022 vs latest-available-year summary
-- Mirrors the annual-comparison grain already used in the payer-side
-- weighted-decline decomposition entry, for direct consistency check.
-- ───────────────────────────────────────────────────────────────────

WITH partner AS (
    SELECT year, ROUND(AVG(approved_percent), 2) AS partner_approval
    FROM stg_top15_psp
    WHERE psp_type = 'payer'
      AND psp_name IN ('Yes Bank', 'Axis Bank', 'ICICI Bank')
      AND year IN (2022, 2025)
    GROUP BY year
),
rest_of_field AS (
    SELECT year, ROUND(AVG(approved_percent), 2) AS field_approval
    FROM stg_top15_psp
    WHERE psp_type = 'payer'
      AND psp_name NOT IN ('Yes Bank', 'Axis Bank', 'ICICI Bank')
      AND year IN (2022, 2025)
    GROUP BY year
)
SELECT p.year, p.partner_approval, r.field_approval,
       ROUND(p.partner_approval - r.field_approval, 2) AS gap_pts
FROM partner p JOIN rest_of_field r ON r.year = p.year
ORDER BY p.year;
-- 2026 deliberately excluded — only 3 months available, per the
-- existing 2026-aggregate-exclusion rule.