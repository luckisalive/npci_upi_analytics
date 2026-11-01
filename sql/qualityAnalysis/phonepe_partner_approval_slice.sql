-- needs to be redacted

-- ───────────────────────────────────────────────────────────────────
-- STEP 6 — PHONEPE-PARTNER APPROVAL SLICE
-- Powers Dashboard Page 4 (Cross-cutting narrative), Panel 4a —
-- payer-side approval trend for PhonePe's confirmed UPI banking
-- partners (Yes Bank, ICICI Bank, Axis Bank) against the payer-side
-- field average, alongside each bank's volume share over the same
-- window.
--
-- GRAIN: (year, month, psp_name), payer side only. This is a filtered
-- slice of stg_top15_psp directly — it does NOT need the monthly-grain
-- join or as-of cutoff logic from unified_monthly_metrics.sql, since
-- it draws from a single source table.
--
-- FRAMING REMINDER for the dashboard caption (per DECISIONS.md,
-- "Payer-side weighted approval decline concentrated in 3 PSPs"):
-- this is a CORRELATIONAL observation, not a causal one. stg_top15_psp
-- has no per-app-per-bank transaction attribution, so this dataset
-- cannot confirm which app's traffic drives any individual PSP's
-- approval or volume trend.
--
-- Expect: 3 psp_names present in every payer-side month they're in
-- the top-15 for (not necessarily every month across the full series
-- — a bank can be present some months and absent others as top-15
-- composition shifts).
-- ───────────────────────────────────────────────────────────────────

WITH payer_totals AS (
    SELECT year, month, SUM(total_volume_mn) AS total_payer_volume_mn
    FROM stg_top15_psp
    WHERE psp_type = 'payer'
    GROUP BY year, month
),

field_avg AS (
    SELECT year, month, ROUND(AVG(approved_percent), 2) AS field_avg_approval
    FROM stg_top15_psp
    WHERE psp_type = 'payer'
    GROUP BY year, month
)

SELECT
    t.year, t.month,
    t.psp_name,
    t.approved_percent,
    ROUND(t.total_volume_mn / pt.total_payer_volume_mn * 100, 2) AS volume_share_pct,
    f.field_avg_approval
FROM stg_top15_psp t
JOIN payer_totals pt ON pt.year = t.year AND pt.month = t.month
JOIN field_avg f      ON f.year = t.year AND f.month = t.month
WHERE t.psp_type = 'payer'
  AND t.psp_name IN ('Yes Bank', 'ICICI Bank', 'Axis Bank')
ORDER BY t.psp_name, t.year, t.month;