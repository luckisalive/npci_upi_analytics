-- ═══════════════════════════════════════════════════════════════════
-- STEP 6 (diagnostic) — PAYEE-SIDE WEIGHTED APPROVAL DECLINE DECOMPOSITION
-- Mirrors the existing payer-side decomposition
-- (sql/qa/psp_payer_weighted_decline_decomposition.sql) so results are
-- directly comparable. 2022 vs 2025 full-year comparison; 2026
-- excluded per the existing 2026-aggregate-exclusion rule.
--
-- Purpose: decide whether the payee-side multi-year approval decline
-- is concentrated in a small set of PSPs (like the payer side was —
-- Yes Bank/Axis Bank/ICICI Bank, ~84% of the weighted decline) or
-- broad-based across the top-15. This determines whether a payee-side
-- entry belongs in DECISIONS.md at all.
-- ═══════════════════════════════════════════════════════════════════

WITH payee_2022 AS (
    SELECT psp_name,
           AVG(approved_percent) AS approval,
           SUM(total_volume_mn)  AS volume
    FROM stg_top15_psp
    WHERE psp_type = 'payee' AND year = 2022
    GROUP BY psp_name
),
payee_2025 AS (
    SELECT psp_name,
           AVG(approved_percent) AS approval,
           SUM(total_volume_mn)  AS volume
    FROM stg_top15_psp
    WHERE psp_type = 'payee' AND year = 2025
    GROUP BY psp_name
),
totals AS (
    SELECT
        (SELECT SUM(volume) FROM payee_2022) AS total_2022,
        (SELECT SUM(volume) FROM payee_2025) AS total_2025
),
matched AS (
    -- Only PSPs present in the payee top-15 in BOTH years — same
    -- "matched set" restriction used on the payer side, so the churn
    -- residual is isolated the same way.
    SELECT
        a.psp_name,
        a.approval AS approval_2022,
        b.approval AS approval_2025,
        ROUND(b.approval - a.approval, 2) AS delta_approval,
        ROUND(100.0 * a.volume / t.total_2022, 2) AS share_2022,
        ROUND(100.0 * b.volume / t.total_2025, 2) AS share_2025,
        ROUND(((100.0 * a.volume / t.total_2022) + (100.0 * b.volume / t.total_2025)) / 2.0, 4) AS avg_weight
    FROM payee_2022 a
    JOIN payee_2025 b ON b.psp_name = a.psp_name
    CROSS JOIN totals t
),
contributions AS (
    SELECT *,
           ROUND(avg_weight * delta_approval / 100.0, 4) AS contribution_pts
    FROM matched
),
overall AS (
    -- True weighted averages (all PSPs, not just matched) for the
    -- headline weighted-shift number, same as payer-side Block 2.
    SELECT
        ROUND(SUM(a.approval * a.volume) / SUM(a.volume), 2) AS weighted_2022,
        (SELECT ROUND(SUM(b.approval * b.volume) / SUM(b.volume), 2) FROM payee_2025 b)
            AS weighted_2025
    FROM payee_2022 a
)

-- ── Query 1: headline weighted-average shift (payee, all PSPs) ──────
SELECT weighted_2022, weighted_2025,
       ROUND(weighted_2025 - weighted_2022, 2) AS total_weighted_shift
FROM overall;

-- ── Query 2: matched-PSP decomposition, ranked by contribution ──────
-- Most negative contribution_pts = biggest driver of the decline.
-- Expect: check whether decline is concentrated (few PSPs, most of the
-- total_weighted_shift) or broad-based (contributions spread evenly
-- across most/all matched PSPs) — this is the actual decision point.
SELECT psp_name, share_2022, share_2025, approval_2022, approval_2025,
       delta_approval, contribution_pts
FROM contributions
ORDER BY contribution_pts ASC;

-- ── Query 3: sum of contributions vs total shift (residual = churn) ─
SELECT
    (SELECT ROUND(SUM(contribution_pts), 2) FROM contributions) AS sum_of_contributions,
    (SELECT ROUND(weighted_2025 - weighted_2022, 2) FROM overall) AS total_weighted_shift,
    (SELECT COUNT(*) FROM payee_2022) AS psp_count_2022,
    (SELECT COUNT(*) FROM payee_2025) AS psp_count_2025,
    (SELECT COUNT(*) FROM contributions) AS matched_count;