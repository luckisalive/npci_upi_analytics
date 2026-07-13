# DB Sanity Check Results — 2026-07-14 01:16

Database: `staging\npci_upi.db`

**17 pass · 1 fail · 5 informational**

## Summary

| Check | Status | Note |
| --- | --- | --- |
| 1. Row counts per table | ℹ️ INFO | 3 row(s) returned. |
| 2a. Month coverage — stg_p2p_p2m | ℹ️ INFO | 51 row(s) returned. |
| 2b. Month coverage — stg_upi_apps | ℹ️ INFO | 51 row(s) returned. |
| 2c. Month coverage — stg_top15_psp | ℹ️ INFO | 104 row(s) returned. |
| 2d. Trailing-edge report (per-table latest month) | ℹ️ INFO | 3 row(s) returned. |
| 3a. Missing months — stg_p2p_p2m | ✅ PASS | stg_p2p_p2m missing-month check: no rows returned, as expected. |
| 3b. Missing months — stg_upi_apps | ✅ PASS | 3b. Missing months — stg_upi_apps: exactly the documented case(s) [(2026, 3)]. |
| 3c. Missing months — stg_top15_psp | ✅ PASS | 3c. Missing months — stg_top15_psp: exactly the documented case(s) [(2022, 12, 'payee'), (2026, 4, 'payer')]. |
| 4a. Duplicate months — stg_p2p_p2m | ✅ PASS | stg_p2p_p2m duplicate-month check: no rows returned, as expected. |
| 4b. Row count != 15 per month/type — stg_top15_psp | ✅ PASS | stg_top15_psp count-per-month check: no rows returned, as expected. |
| 4c. Undocumented duplicate app per month — stg_upi_apps | ✅ PASS | stg_upi_apps undocumented-duplicate-app check: no rows returned, as expected. |
| 5a. Consecutive-month identical volume — stg_p2p_p2m | ✅ PASS | p2p_p2m consecutive-identical-volume check: no rows returned, as expected. |
| 5b. Consecutive-month identical volume — stg_upi_apps (app grain) | ✅ PASS | upi_apps consecutive-identical-volume check: no rows returned, as expected. |
| 6a. Null/zero spot check — stg_p2p_p2m | ✅ PASS | stg_p2p_p2m null/zero check: no rows returned, as expected. |
| 6b. Null market_share_pct — stg_upi_apps | ✅ PASS | stg_upi_apps null market_share_pct check: no rows returned, as expected. |
| 6c. Null approved_percent — stg_top15_psp | ✅ PASS | stg_top15_psp null approved_percent check: no rows returned, as expected. |
| 7. Market share sums to ~100% per month — stg_upi_apps | ✅ PASS | stg_upi_apps market-share-sum check: no rows returned, as expected. |
| 8. Percent-sum regression guard — stg_top15_psp | ✅ PASS | percent-sum regression check: no rows returned, as expected. |
| 9. psp_name casing/spelling regression guard | ✅ PASS | psp_name casing regression check: no rows returned, as expected. |
| 10. Name-override collision guard | ❌ FAIL | override-collision check: 1 unexpected row(s) returned. |
| 11. Pre-override legacy name leakage guard | ✅ PASS | legacy-name-leakage check: no rows returned, as expected. |
| 12. Header-leak permanent guard — stg_upi_apps | ✅ PASS | header-leak check: no rows returned, as expected. |
| 13. BD/TD composition anomaly detector | ✅ PASS | 13. BD/TD composition anomaly detector: exactly the documented case(s) [(2023, 6, 'payer')]. |

## Unexpected results — detail

### 10. Name-override collision guard

override-collision check: 1 unexpected row(s) returned.

| year | month | psp_type | psp_name | n |
| --- | --- | --- | --- | --- |
| 2023 | 11 | payee | Indian Bank | 2 |

## Informational output

### 1. Row counts per table

| table_name | row_count |
| --- | --- |
| stg_p2p_p2m | 51 |
| stg_upi_apps | 3789 |
| stg_top15_psp | 1560 |

### 2a. Month coverage — stg_p2p_p2m

| year | month | rows_this_month |
| --- | --- | --- |
| 2022 | 1 | 1 |
| 2022 | 2 | 1 |
| 2022 | 3 | 1 |
| 2022 | 4 | 1 |
| 2022 | 5 | 1 |
| 2022 | 6 | 1 |
| 2022 | 7 | 1 |
| 2022 | 8 | 1 |
| 2022 | 9 | 1 |
| 2022 | 10 | 1 |
| 2022 | 11 | 1 |
| 2022 | 12 | 1 |
| 2023 | 1 | 1 |
| 2023 | 2 | 1 |
| 2023 | 3 | 1 |
| 2023 | 4 | 1 |
| 2023 | 5 | 1 |
| 2023 | 6 | 1 |
| 2023 | 7 | 1 |
| 2023 | 8 | 1 |
| 2023 | 9 | 1 |
| 2023 | 10 | 1 |
| 2023 | 11 | 1 |
| 2023 | 12 | 1 |
| 2024 | 1 | 1 |
| 2024 | 2 | 1 |
| 2024 | 3 | 1 |
| 2024 | 4 | 1 |
| 2024 | 5 | 1 |
| 2024 | 6 | 1 |
| 2024 | 7 | 1 |
| 2024 | 8 | 1 |
| 2024 | 9 | 1 |
| 2024 | 10 | 1 |
| 2024 | 11 | 1 |
| 2024 | 12 | 1 |
| 2025 | 1 | 1 |
| 2025 | 2 | 1 |
| 2025 | 3 | 1 |
| 2025 | 4 | 1 |
| 2025 | 5 | 1 |
| 2025 | 6 | 1 |
| 2025 | 7 | 1 |
| 2025 | 8 | 1 |
| 2025 | 9 | 1 |
| 2025 | 10 | 1 |
| 2025 | 11 | 1 |
| 2025 | 12 | 1 |
| 2026 | 1 | 1 |
| 2026 | 2 | 1 |
| 2026 | 3 | 1 |

### 2b. Month coverage — stg_upi_apps

| year | month | rows_this_month |
| --- | --- | --- |
| 2022 | 1 | 59 |
| 2022 | 2 | 60 |
| 2022 | 3 | 66 |
| 2022 | 4 | 66 |
| 2022 | 5 | 66 |
| 2022 | 6 | 68 |
| 2022 | 7 | 67 |
| 2022 | 8 | 66 |
| 2022 | 9 | 66 |
| 2022 | 10 | 63 |
| 2022 | 11 | 67 |
| 2022 | 12 | 65 |
| 2023 | 1 | 69 |
| 2023 | 2 | 67 |
| 2023 | 3 | 69 |
| 2023 | 4 | 69 |
| 2023 | 5 | 69 |
| 2023 | 6 | 71 |
| 2023 | 7 | 70 |
| 2023 | 8 | 73 |
| 2023 | 9 | 72 |
| 2023 | 10 | 70 |
| 2023 | 11 | 70 |
| 2023 | 12 | 71 |
| 2024 | 1 | 71 |
| 2024 | 2 | 69 |
| 2024 | 3 | 66 |
| 2024 | 4 | 70 |
| 2024 | 5 | 68 |
| 2024 | 6 | 70 |
| 2024 | 7 | 73 |
| 2024 | 8 | 70 |
| 2024 | 9 | 76 |
| 2024 | 10 | 77 |
| 2024 | 11 | 81 |
| 2024 | 12 | 83 |
| 2025 | 1 | 83 |
| 2025 | 2 | 82 |
| 2025 | 3 | 82 |
| 2025 | 4 | 84 |
| 2025 | 5 | 83 |
| 2025 | 6 | 82 |
| 2025 | 7 | 85 |
| 2025 | 8 | 85 |
| 2025 | 9 | 86 |
| 2025 | 10 | 87 |
| 2025 | 11 | 90 |
| 2025 | 12 | 92 |
| 2026 | 1 | 92 |
| 2026 | 2 | 92 |
| 2026 | 4 | 91 |

### 2c. Month coverage — stg_top15_psp

| year | month | psp_type | rows_this_month |
| --- | --- | --- | --- |
| 2022 | 1 | payee | 15 |
| 2022 | 1 | payer | 15 |
| 2022 | 2 | payee | 15 |
| 2022 | 2 | payer | 15 |
| 2022 | 3 | payee | 15 |
| 2022 | 3 | payer | 15 |
| 2022 | 4 | payee | 15 |
| 2022 | 4 | payer | 15 |
| 2022 | 5 | payee | 15 |
| 2022 | 5 | payer | 15 |
| 2022 | 6 | payee | 15 |
| 2022 | 6 | payer | 15 |
| 2022 | 7 | payee | 15 |
| 2022 | 7 | payer | 15 |
| 2022 | 8 | payee | 15 |
| 2022 | 8 | payer | 15 |
| 2022 | 9 | payee | 15 |
| 2022 | 9 | payer | 15 |
| 2022 | 10 | payee | 15 |
| 2022 | 10 | payer | 15 |
| 2022 | 11 | payee | 15 |
| 2022 | 11 | payer | 15 |
| 2022 | 12 | payer | 15 |
| 2023 | 1 | payee | 15 |
| 2023 | 1 | payer | 15 |
| 2023 | 2 | payee | 15 |
| 2023 | 2 | payer | 15 |
| 2023 | 3 | payee | 15 |
| 2023 | 3 | payer | 15 |
| 2023 | 4 | payee | 15 |
| 2023 | 4 | payer | 15 |
| 2023 | 5 | payee | 15 |
| 2023 | 5 | payer | 15 |
| 2023 | 6 | payee | 15 |
| 2023 | 6 | payer | 15 |
| 2023 | 7 | payee | 15 |
| 2023 | 7 | payer | 15 |
| 2023 | 8 | payee | 15 |
| 2023 | 8 | payer | 15 |
| 2023 | 9 | payee | 15 |
| 2023 | 9 | payer | 15 |
| 2023 | 10 | payee | 15 |
| 2023 | 10 | payer | 15 |
| 2023 | 11 | payee | 15 |
| 2023 | 11 | payer | 15 |
| 2023 | 12 | payee | 15 |
| 2023 | 12 | payer | 15 |
| 2024 | 1 | payee | 15 |
| 2024 | 1 | payer | 15 |
| 2024 | 2 | payee | 15 |
| 2024 | 2 | payer | 15 |
| 2024 | 3 | payee | 15 |
| 2024 | 3 | payer | 15 |
| 2024 | 4 | payee | 15 |
| 2024 | 4 | payer | 15 |
| 2024 | 5 | payee | 15 |
| 2024 | 5 | payer | 15 |
| 2024 | 6 | payee | 15 |
| 2024 | 6 | payer | 15 |
| 2024 | 7 | payee | 15 |
| 2024 | 7 | payer | 15 |
| 2024 | 8 | payee | 15 |
| 2024 | 8 | payer | 15 |
| 2024 | 9 | payee | 15 |
| 2024 | 9 | payer | 15 |
| 2024 | 10 | payee | 15 |
| 2024 | 10 | payer | 15 |
| 2024 | 11 | payee | 15 |
| 2024 | 11 | payer | 15 |
| 2024 | 12 | payee | 15 |
| 2024 | 12 | payer | 15 |
| 2025 | 1 | payee | 15 |
| 2025 | 1 | payer | 15 |
| 2025 | 2 | payee | 15 |
| 2025 | 2 | payer | 15 |
| 2025 | 3 | payee | 15 |
| 2025 | 3 | payer | 15 |
| 2025 | 4 | payee | 15 |
| 2025 | 4 | payer | 15 |
| 2025 | 5 | payee | 15 |
| 2025 | 5 | payer | 15 |
| 2025 | 6 | payee | 15 |
| 2025 | 6 | payer | 15 |
| 2025 | 7 | payee | 15 |
| 2025 | 7 | payer | 15 |
| 2025 | 8 | payee | 15 |
| 2025 | 8 | payer | 15 |
| 2025 | 9 | payee | 15 |
| 2025 | 9 | payer | 15 |
| 2025 | 10 | payee | 15 |
| 2025 | 10 | payer | 15 |
| 2025 | 11 | payee | 15 |
| 2025 | 11 | payer | 15 |
| 2025 | 12 | payee | 15 |
| 2025 | 12 | payer | 15 |
| 2026 | 1 | payee | 15 |
| 2026 | 1 | payer | 15 |
| 2026 | 2 | payee | 15 |
| 2026 | 2 | payer | 15 |
| 2026 | 3 | payee | 15 |
| 2026 | 3 | payer | 15 |
| 2026 | 4 | payee | 15 |
| 2026 | 5 | payee | 15 |
| 2026 | 5 | payer | 15 |

### 2d. Trailing-edge report (per-table latest month)

| table_name | latest_yyyymm |
| --- | --- |
| stg_p2p_p2m | 202603 |
| stg_upi_apps | 202604 |
| stg_top15_psp | 202605 |
