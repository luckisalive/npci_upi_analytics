-- ─────────────────────────────────────────────────────────────
-- Block 1: Monthly P2P vs P2M volume and share trend
-- Full available range.
-- Expect: 51 rows (2022-01 through 2026-03), p2p_share_pct + p2m_share_pct ≈ 100 each row
-- ─────────────────────────────────────────────────────────────

SELECT
    year,
    month,
    p2p_volume_mn,
    p2m_volume_mn,
    p2p_share_pct,
    p2m_share_pct
FROM stg_p2p_p2m
ORDER BY year, month;


-- ─────────────────────────────────────────────────────────────
-- Block 2: September 2022 crossover confirmation
-- Confirms P2M share crosses 50% in 2022-09 and stays above it in every
-- subsequent month through the end of the series (not just at the crossover point).
-- Expect: first row where p2m_share_pct >= 50 is (2022, 9); zero rows in the
-- "reversion check" after that date where p2m_share_pct < 50.
-- ─────────────────────────────────────────────────────────────

-- 2a. First month P2M share reaches/exceeds 50%
SELECT year, month, p2m_share_pct
FROM stg_p2p_p2m
WHERE p2m_share_pct >= 50
ORDER BY year, month
LIMIT 1;

-- 2b. Reversion check — any month after the crossover where P2M share fell back below 50%
-- Expect: 0 rows
SELECT year, month, p2m_share_pct
FROM stg_p2p_p2m
WHERE (year * 12 + month) > (2022 * 12 + 9)
  AND p2m_share_pct < 50
ORDER BY year, month;


-- ─────────────────────────────────────────────────────────────
-- Block 3: Mid-2025 counter-trend investigation
-- DECISIONS.md flags a dip from 63.7% (Jun 2025) to 62.1% (Dec 2025).
-- This block isolates that window and checks whether it has begun
-- recovering by the end of the available series (2026-03).
-- ─────────────────────────────────────────────────────────────

SELECT
    year,
    month,
    p2m_share_pct,
    p2m_share_pct - LAG(p2m_share_pct) OVER (ORDER BY year, month) AS mom_share_change_pct_pts
FROM stg_p2p_p2m
WHERE (year = 2025 AND month >= 6) OR (year = 2026)
ORDER BY year, month;


-- ─────────────────────────────────────────────────────────────
-- Block 4a: Growth rate differential — Month-over-Month
-- MoM % change in P2P volume vs P2M volume, side by side.
-- Full available range (first row will have NULL MoM values — no prior month).
-- ─────────────────────────────────────────────────────────────

SELECT
    year,
    month,
    p2p_volume_mn,
    p2m_volume_mn,
    ROUND(
        (p2p_volume_mn - LAG(p2p_volume_mn) OVER (ORDER BY year, month))
        / LAG(p2p_volume_mn) OVER (ORDER BY year, month) * 100, 2
    ) AS p2p_mom_growth_pct,
    ROUND(
        (p2m_volume_mn - LAG(p2m_volume_mn) OVER (ORDER BY year, month))
        / LAG(p2m_volume_mn) OVER (ORDER BY year, month) * 100, 2
    ) AS p2m_mom_growth_pct
FROM stg_p2p_p2m
ORDER BY year, month;


-- ─────────────────────────────────────────────────────────────
-- Block 4b: Growth rate differential — Year-over-Year (monthly anchor)
-- Each month vs. the same month one year prior.
-- Range starts 2023-01 (earliest month with a prior-year anchor available).
-- ─────────────────────────────────────────────────────────────

SELECT
    curr.year,
    curr.month,
    curr.p2p_volume_mn,
    prev.p2p_volume_mn AS p2p_volume_mn_prior_year,
    ROUND((curr.p2p_volume_mn - prev.p2p_volume_mn) / prev.p2p_volume_mn * 100, 2) AS p2p_yoy_growth_pct,
    curr.p2m_volume_mn,
    prev.p2m_volume_mn AS p2m_volume_mn_prior_year,
    ROUND((curr.p2m_volume_mn - prev.p2m_volume_mn) / prev.p2m_volume_mn * 100, 2) AS p2m_yoy_growth_pct
FROM stg_p2p_p2m curr
JOIN stg_p2p_p2m prev
    ON prev.year = curr.year - 1 AND prev.month = curr.month
ORDER BY curr.year, curr.month;


-- ─────────────────────────────────────────────────────────────
-- Block 4c: Growth rate differential — Annual aggregate (2022–2025 ONLY)
-- ─────────────────────────────────────────────────────────────

SELECT
    year,
    COUNT(*) AS month_count,
    SUM(p2p_volume_mn) AS p2p_volume_mn_annual,
    SUM(p2m_volume_mn) AS p2m_volume_mn_annual,
    ROUND(
        (SUM(p2p_volume_mn) - LAG(SUM(p2p_volume_mn)) OVER (ORDER BY year))
        / LAG(SUM(p2p_volume_mn)) OVER (ORDER BY year) * 100, 2
    ) AS p2p_annual_growth_pct,
    ROUND(
        (SUM(p2m_volume_mn) - LAG(SUM(p2m_volume_mn)) OVER (ORDER BY year))
        / LAG(SUM(p2m_volume_mn)) OVER (ORDER BY year) * 100, 2
    ) AS p2m_annual_growth_pct
FROM stg_p2p_p2m
WHERE year BETWEEN 2022 AND 2025
GROUP BY year
ORDER BY year;