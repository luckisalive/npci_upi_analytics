# DECISIONS.md — NPCI UPI Analytics Pipeline

> Running log of significant technical and analytical decisions made during the project.
> Each entry written at decision time, not reconstructed from memory later.
> Used as source material for the final README.

---

## Project Scope

### Decision: Two core analytical questions only

**Date:** Project start

**Decision:** Scope locked to two questions:

1. UPI market concentration — which PSPs/banks dominate transaction volume (HHI metric)
2. P2M vs P2P growth differential — is merchant payment volume outpacing peer transfers

**Rejected scope:**

- State-wise analysis (NPCI doesn't publish state-level transaction data publicly)
- Fraud detection (no labeled transaction-level data available publicly)
- Forecasting (ARIMA/Prophet on ~51 monthly aggregate rows is statistically indefensible)
- 5 dashboards (reduced to 1 focused Tableau dashboard)

**Why:** A project that answers two questions rigorously is stronger than one that gestures at nine questions superficially. Scope creep sourced from a ChatGPT-generated blueprint was explicitly rejected.

---

### Decision: Real data only, no synthetic datasets

**Date:** 01-07-2026

**Decision:** Use only publicly available NPCI/RBI data. No synthetic transaction generators (e.g. PaySim).

**Why:** Synthetic data dressed as real data is a credibility risk in interviews. If asked "where did you get labeled fraud transactions," "I simulated them" without disclosure is a red flag. Since fraud labels don't exist in public NPCI data, the fraud angle was dropped entirely in favor of what the data can actually support.

---

## Data Sources

### Decision: UPI Apps sheet as primary concentration source (not Entity-wise)

**Date:** 01-07-2026

**Decision:** Use NPCI Ecosystem Statistics → UPI Apps tab for HHI and market share analysis, not the Entity-wise volume sheet.

**Why:** UPI Apps sheet contains app-level volume (PhonePe, Google Pay etc.) which maps directly to PSP brand concentration — the business-relevant unit. Entity-wise sheet contains bank names as transaction processors, which is one abstraction layer removed from the consumer-facing PSP story.

**Tradeoff:** UPI Apps sheet is only available as monthly separate downloads, requiring 51 individual files. Accepted as necessary given data source constraints.

### Decision: Date range 2022_01 to 2026_04, with cross-source gaps documented

**Date:** Data collection phase — updated 08-07-2026

**Decision:** Time series covers January 2022 to May 2026 (52 months).

**Cross-source gaps:**

- 2026_03 present in P2P/P2M, absent in UPI Apps — NPCI had not published at time of download
- payee 2022_12 absent from stg_top15_psp — unavailable on NPCI website
- payer 2026_04 absent from stg_top15_psp — unavailable on NPCI website

**Join strategy:** Queries joining across tables must use LEFT JOIN, not INNER JOIN, to avoid silently dropping rows with missing coverage in one source.

**Gap handling:** Not filled or interpolated. All gaps documented here and must be noted explicitly in any trend analysis crossing affected periods.

**Note:** Pre-2022 data exists for some sheets but not consistently across all sources. 2022 chosen as clean start point for cross-source consistency.

---

## File Naming Convention

### Decision: YYYY_MM.xlsx naming standard

**Date:** 01-07-2026

**Decision:** All raw files renamed from NPCI's original verbose filenames (e.g. `Ecosystem-Statistics-UPI-Upi-apps-2025-Apr.xlsx`) to `YYYY_MM.xlsx` (e.g. `2025_04.xlsx`).

**Why:** NPCI's original filenames are inconsistent across years and contain no zero-padded month, making regex extraction unreliable. Since the UPI Apps sheets contain no date column, the filename is the only source of the time dimension. Wrong filename = wrong date on every row in the database. Strict convention enforced at download time, not ETL time.

**Risk:** If any file is named incorrectly, the ETL script fails loudly with a descriptive error rather than loading with wrong dates.

---

## ETL Design

### Decision: Positional column renaming for merged header sheets

**Date:** 02-07-2026

**Decision:** Use positional column assignment (`df.columns = COLUMN_SCHEMA`) instead of string-matching on column names for the UPI Apps sheet.

**Why:** The UPI Apps sheet has a two-row merged header structure. `pd.read_excel()` on merged headers produces `NaN` and `Unnamed: N` columns alongside real names. String matching on `NaN` is unreliable. Positional assignment is deterministic given a confirmed fixed column order.

**Risk:** If NPCI adds or reorders columns, positional assignment silently maps wrong data to wrong column names. Mitigated by: (1) column count validation before assignment, (2) sheet structure logged per file.

### Decision: Sheet loaded by index (position 0), not by name

**Date:** 02-07-2026

**Decision:** `pd.read_excel(filepath, sheet_name=0)` instead of hardcoding a sheet name string.

**Why:** Across 51 files, NPCI used inconsistent sheet tab names ("Sheet1", "Sheet12", and potentially others). Hardcoding "UPI APPS" caused KeyError failures on 2 of the first 2 files tested. Positional loading by index 0 was validated against 10 randomly sampled files across different years — UPI Apps data was consistently the first sheet.

**Risk:** Not all 51 files manually verified. If any file has a different sheet at index 0, wrong data loads without error. Mitigated by logging the actual sheet name read per file.

### Decision: Null insertion for missing On-us columns (2025_01, 2025_02)

**Date:** 03-07-2026

**Decision:** For files with 10 columns instead of 12, insert null columns at positions 8 and 9 (onus_volume_mn, onus_value_cr) before applying COLUMN_SCHEMA.

**Why:** NPCI omitted On-us columns in January and February 2025 only, then included them again (as zeros) from March 2025 onwards. Hard rejection of 10-column files would create a gap in the time series at a critical year boundary. Null insertion preserves row continuity while accurately representing absent data.

**Alternative rejected:** Dropping On-us columns entirely from schema before fixing this — would have masked the schema inconsistency rather than handling it explicitly.

### Decision: Duplicate guard via year/month check before loading

**Date:** 03-07-2026

**Decision:** Before loading any file, query SQLite for existing rows with matching year and month. Skip if found. For stg_top15_psp, guard checks year + month + psp_type since payer and payee are separate files for the same period.

**Why:** Allows re-running the pipeline after fixing individual files without duplicating all previously loaded rows. Without this, every full pipeline re-run doubles the row count silently.

### Decision: 2024_07 duplicate file incident

**Date:** 07-07-2026

**Decision:** 2024_06.xlsx was accidentally downloaded twice and saved as both 2024_06.xlsx and 2024_07.xlsx, causing identical total volumes (13,885.14 Mn) for consecutive months.

**Detection:** Caught by manual inspection of ETL log — identical values across consecutive months in a growing time series flagged as anomalous.

**Fix:** Correct July 2024 file re-downloaded and replaced. Duplicate guard skipped all previously loaded months; only 2024_07 was reprocessed.

**Why documented:** Human errors caught by pipeline validation are worth recording — demonstrates the audit trail works as intended.

### Decision: Top 15 PSP schema fallback — three column variants handled

**Date:** 08-07-2026

**Decision:** etl_top15_psp.py uses a fallback column set strategy to handle three distinct schemas found across 104 files.

**Variants encountered:**

| Variant | Files affected | Key difference |
| --- | --- | --- |
| Standard | Majority | `Sr. No.`, `Payer PSP` / `Payee PSP`, `Total Volume (In Mn)`, `Approved %`, `BD %`, `TD %` |
| Snake case | ~2025_11, 2025_12 payer + others | `payer_psp`, `total_volume_in_mn`, `approved_percent`, `bd_percent`, `td_percent` |
| No period Sr No | ~2025_03 payer + others | `Sr No` instead of `Sr. No.` |

**Implementation:** Parser iterates through three `required_column_sets` and uses the first matching set. Rename map applied per matched variant.

**Risk:** A fourth undiscovered variant would trigger a Missing columns error and log a failure — detectable from the summary line. No silent failures possible.

**Verification:** All 15 rows confirmed present for 2025_03, 2025_11, 2025_12 (payer and payee) via SQL COUNT query post-load.

---

## Schema Decisions

### Decision: onus_volume_mn and onus_value_cr dropped from stg_upi_apps

**Date:** 03-07-2026 — implemented 07-07-2026

**Status:** Implemented in etl_upi_apps.py

**Decision:** On-us columns dropped in ETL script before loading to SQLite. Not present in stg_upi_apps table.

**Why:** 100% zero values from April 2024 onwards. Absent entirely in January and February 2025. NPCI stopped reporting On-us transactions meaningfully. Carrying dead columns into analysis creates confusion without adding signal.

**Implementation note:** Dropped via `df.drop(columns=["onus_volume_mn", "onus_value_cr"])` in parse_upi_apps() before load. GUI-based column drops (DB Browser) explicitly rejected — leaves no audit trail and is overwritten on next ETL run.

---

## Analytical Framing

### Decision: HHI measures app-level concentration, not bank-level

**Date:** 03-07-2026

**Decision:** HHI scores calculated from UPI Apps volume data represent app-level concentration (PhonePe, Google Pay as apps). This is distinct from bank-level or PSP-license-level concentration.

**Why matters for presentation:** In interviews and the README, the distinction must be stated explicitly. "PhonePe dominates" refers to the consumer-facing app, not to Yes Bank (PhonePe's sponsor bank). Conflating these is a factual error that domain-knowledgeable interviewers will catch.

### Decision: MDR policy framing is inferential, not a finding

**Date:** 03-07-2026

**Decision:** Any reference to MDR policy change implications is framed as a conditional inference ("if MDR policy changes, dominant PSPs are structurally positioned to benefit disproportionately"), not as a current finding from the data.

**Why:** Current MDR on UPI P2M is zero by government mandate. Volume concentration without monetization is cost concentration, not profit concentration. Stating "dominant PSPs will capture the most profit" without this qualifier is factually wrong given current policy.

### Decision: P2M crossover documented as structural transition, not gradual drift

**Date:** 07-07-2026

**Observation from P2P/P2M ETL log:** P2M share crossed 50% in September 2022 (52.3%) and has not fallen below 50% since. Grew from 40.3% in January 2022 to 63.7% by June 2025 — a 23 percentage point shift in 3.5 years.

**Counter-trend noted:** P2M share dipped slightly from 63.7% (June 2025) to 62.1% (December 2025) before stabilizing. This counter-trend requires investigation in EDA — do not present a clean upward trend without addressing it.

**Framing decision:** This will be presented as a structural transition (UPI evolving from peer transfer tool to merchant payments infrastructure), not merely "P2M is growing." The September 2022 crossover is a specific, dateable event worth calling out in the dashboard.

---

*Last updated: Top 15 PSP ETL complete — 104 files loaded (52 payer + 52 payee), 0 failures. Three schema variants handled via fallback column sets. Two missing files documented (payee 2022_12, payer 2026_04). All three staging tables complete — pipeline ETL phase closed.*

---

## Analytics Phase — Step 1 Sanity Pass

### Decision: Cross-source trailing-edge mismatch — as-of cutoff required for multi-table analysis

**Date:** 09-07-2026

**Finding:** Sanity pass (Step 1) revealed the three staging tables end on different months: `stg_p2p_p2m` through 2026-03, `stg_upi_apps` through 2026-04, `stg_top15_psp` through 2026-05. This is distinct from the three documented mid-series gaps — it's a download-time publication lag, not a missing file.

**Decision:** Single-table analyses (e.g. HHI from `stg_upi_apps` alone) may use each table's full available range. Any analysis joining or comparing across tables must cap at the earliest common month (currently 2026-03) to avoid implying one series "extends" further than the others.

**Why:** Uncapped cross-table comparison would make it look like data exists where it doesn't, risking a misleading endpoint in trend charts (e.g. P2P/P2M vs PSP approval trend).

---

### Decision: Duplicate app-name-month rows in stg_upi_apps handled via query-time aggregation, not row deletion

**Date:** 09-07-2026

**Finding:** 5 (year, month, app_name) combinations have two rows each — (2023,2,Bajaj Finserv), (2023,11,Mobikwik), (2023,12,Mobikwik), (2024,7,Federal Bank Apps), (2025,8,Others) — with differing `total_volume_mn`/`total_value_cr`, confirmed as two genuine distinct source entries sharing an identical cleaned app name, not a duplicate load.

**Decision:** All app-grain queries (HHI, market share, top-N) must `GROUP BY (year, month, app_name)` and `SUM()` volume before computing share. Raw rows are left untouched.

**Why:** HHI squares shares (`Σ(share%)²`); treating the two rows as separate apps instead of summing first understates concentration for those five app-months, since `(a+b)² > a² + b²`. Aggregating at query time fixes this without needing to identify which underlying entity each row represents.

**Superseded 15-07-2026:** re-investigated following the Paytm entity-lineage finding — 4 of these 5 pairs turned out to be NPCI naming-convention variants, not distinct entities, and were reclassified and physically merged at ETL time. See "stg_upi_apps naming-variant overrides finalized" below.

---

### Decision: 2022-04 header-leak row excluded from analysis

**Date:** 10-07-2026

**Finding:** `stg_upi_apps` contains one row for 2022-04 with `app_name = 'Application Name'` (the literal column header text) and null volume/value — a row-offset parsing artifact in `parse_upi_apps()` for that single file, not a real app entity. Confirmed isolated to this one row via a table-wide scan for known header-label strings and null-volume rows.

**Decision:** Excluded via `WHERE app_name != 'Application Name'` at query time. Root cause (row-offset bug, likely a 3-row header for that file vs. the usual 2-row header) is not fixed in the ETL script since it would require re-running the full pipeline over one row's worth of impact.
> deleted it using `DELETE` function from the `npci_upi.db`.

**Risk:** Not fixed at source, so any future person querying `stg_upi_apps` directly (outside the analysis SQL) must know to filter this row.
 
---
 
### Decision: HHI concentration bands — DOJ/FTC standard thresholds
 
**Date:** 10-07-2026
 
**Decision:** `sql/hhi_monthly.sql` classifies monthly HHI using the US DOJ/FTC Horizontal Merger Guidelines bands:
- HHI < 1,500 → Unconcentrated
- 1,500 ≤ HHI ≤ 2,500 → Moderately Concentrated
- HHI > 2,500 → Highly Concentrated
**Why:** These are the standard, citable thresholds used in competition analysis — not invented for this project. Using a recognized standard rather than an arbitrary cutoff keeps the "competitive/moderate/high" characterization defensible if questioned.
 
**Caveat carried over from the ETL-phase decision above:** these bands were designed for firm-level market concentration in antitrust review. HHI here is computed on **app-level** volume share (PhonePe, Google Pay, etc.), not PSP-license or sponsor-bank level. The bands are a reasonable lens for consumer-facing app concentration but the distinction must be stated explicitly wherever the HHI number is presented, consistent with the existing "HHI measures app-level concentration, not bank-level" decision above.
 
---
 
### Decision: 2024_03 duplicate file incident (stg_upi_apps)
 
**Date:** 10-07-2026
 
**Finding:** `sql/hhi_monthly.sql` block 3 showed a 0.00 HHI change between Feb 2024 and Mar 2024 (3732.33 → 3732.33) — the same fingerprint as the documented 2024_06/07 `stg_p2p_p2m` incident. `sql/qa/HHI_anomaly_check.sql` confirmed every app's `total_volume_mn` was byte-identical between the two months. Direct inspection of the raw files confirmed `2024_03.xlsx` was the February file re-downloaded and saved under the March filename.
 
**Fix:** Correct March 2024 file to be re-downloaded and re-run through `etl_upi_apps.py`. The `already_loaded()` duplicate guard means only 2024-03 needs reprocessing; all other months are untouched.
 
**Why documented:** Second instance of the same human-error pattern already caught once in a different table — worth noting as a recurring risk class (identical-file-under-wrong-name) rather than a one-off, since it suggests the download step, not the ETL step, is where this class of error originates. Consider a file-hash check across all raw files as a future guard.
 
**Status:** Fixed and verified 09-07-2026. Corrected 2024-03 HHI = 3832.78 (was 3732.33, duplicated from Feb). Feb→Mar→Apr now shows a smooth monotonic climb (3732.33 → 3832.78 → 3887.51) instead of a flat step, consistent with the rest of the 2022–May 2024 upward trend. Market leader (PhonePe) unchanged for all months, before and after the fix.

---

## Analytics Phase — Step 3: P2P vs. P2M Growth Differential

### Decision: P2M crossover date corrected to August 2022 — root cause was a log formatting bug, not a data error

**Date:** 12-07-2026

**Finding:** `sql/p2p_p2m_growth.sql` block 2a shows P2M share first reached ≥50% in **August 2022 (50.01%)**, not September 2022 (52.31%) as previously documented ("P2M crossover documented as structural transition" entry, above). The underlying `stg_p2p_p2m` data was correct at all times — August's true value was 50.01%.

**Root cause:** `etl_p2p_p2m.py`'s logging statement used `f"P2M: {df['p2m_share_pct'].iloc[0]:.1f}%"` — one decimal place. This rounded August 2022's 50.01% down to a displayed "50.0%" in `logs/etl_p2p_p2m.log`, which read as "at the threshold" rather than "already past it." September's unambiguous 52.3% was documented as the crossover instead, since the log output for August didn't clearly signal a cross had occurred.

**Fix:** `etl_p2p_p2m.py` logging format changed from `:.1f` to `:.2f`. Historical log files are not regenerated (no data was reloaded — this was a display-layer bug, not a load-layer bug), but any future re-run will log the correct precision.

**Corrected finding:** P2M share crossed 50% in **August 2022 (50.01%)**, then rose to 52.31% in September 2022, and has not fallen below 50% in any month since (confirmed via `sql/p2p_p2m_growth.sql` block 2b — 0 rows on the post-crossover reversion check).

**Why documented:** A third instance of a human-error pattern, but a distinct risk class from the two prior file-naming incidents (2024_06/07, 2024_03 in `stg_upi_apps`) — those were load-time data errors caught by anomaly detection on the data itself. This one was a report/log precision bug that produced a correct database but an incorrect analyst-facing summary, which then propagated into documentation. Worth a standing rule: derived findings quoted from log files during development should be re-verified directly against the database before being written into `DECISIONS.md`, rather than trusted from log output alone.

---

### Decision: Mid-2025 P2M share dip — confirmed as partial, not full, recovery

**Date:** 12-07-2026

**Finding:** `sql/p2p_p2m_growth.sql` block 3 confirms the counter-trend flagged in the earlier P2M crossover entry. P2M share fell from 63.66% (June 2025) to a low of 62.32% (December 2025), then stabilized in the 62.6–62.74% range through March 2026 (62.63%). It has **not** returned to the June 2025 peak — it has plateaued roughly 1 percentage point below it.

**Decision:** Any write-up of this period must use "partial stabilization" or "plateaued below the June 2025 peak," not "recovered." Presenting it as a full recovery overstates the current data.

**Why:** Precision matters here specifically because this counter-trend sits right next to the growth-convergence finding below — an imprecise "recovered" reading would understate how much P2M's momentum has actually slowed.

---

### Decision: P2P and P2M growth rates have converged — reframes the "structural transition" narrative

**Date:** 12-07-2026

**Finding:** `sql/p2p_p2mGrowth.sql` block 4c (annual aggregate, 2022–2025) shows P2M's YoY growth decelerating sharply while P2P's has stayed roughly flat:

| Year | P2P annual growth | P2M annual growth |
| --- | --- | --- |
| 2023 | 28.09% | 93.01% |
| 2024 | 31.01% | 57.59% |
| 2025 | 29.47% | 34.45% |

Block 4b (monthly YoY) confirms the convergence is not a 2025-aggregate artifact: by March 2026, P2P YoY growth (23.69%) and P2M YoY growth (23.73%) are effectively equal.

**Decision:** The existing "structural transition" framing (P2M crossover entry, above) is not wrong but is incomplete on its own — it describes 2022–2023, when P2M was growing at roughly 2–3x P2P's rate. That gap has closed. The updated framing for the README/dashboard: UPI underwent a structural transition from P2P-dominant to P2M-dominant between 2022 and 2023 (driven by triple-digit P2M growth against P2P's steady ~30%), and that transition phase is now largely complete — both rails are growing at a similar, more moderate rate as of early 2026. The mid-2025 P2M share dip (previous entry) is best read as a visible symptom of this deceleration, not an isolated anomaly.

**Caveat:** 2026 annual aggregate is deliberately excluded from the table above — only 3 months of 2026 data are available (`stg_p2p_p2m` trailing edge), and summing a partial year against full prior years would misstate the comparison. Monthly YoY (block 4b) is the correct lens for anything touching 2026.

**Why documented:** This is arguably the more interesting Step 3 finding relative to the original brief ("is merchant payment volume outpacing peer transfers") — the answer is now "it did, decisively, in 2022–2023, but the two are converging toward similar growth rates as of 2026," which is a more nuanced and more defensible claim than a simple "P2M is winning."

---

### Decision: Percent-column scaling bug in stg_top15_psp — magnitude heuristic replaced with presence-of-'%' signal

**Date:** 12-07-2026

**Finding:** `clean_numeric()`'s original percent-scaling logic used a magnitude heuristic (`abs(x) <= 1`) to decide whether a parsed value needed `×100` scaling. This failed for text-form percentage cells that were already small and correctly percent-scale — e.g. `"0.35%"` parses to `0.35` after the `%` is stripped, which the heuristic then incorrectly multiplied to `35`. `technical_decline_percent` is exactly the column where sub-1% values are the normal case for well-performing PSPs, not an edge case, making this column disproportionately affected.

**Detection:** Caught by `sql/psp_reliability.sql` Block 1 (`approved_percent + business_decline_percent + technical_decline_percent ≈ 100` sanity check) — 310 rows returned with `pct_sum` > 100, most attributable to inflated `technical_decline_percent`.

**Fix:** `clean_numeric()` in `etl_top15_psp.py` changed to key the scaling decision off whether the source cell literally contained a `%` sign, not off the resulting value's magnitude:
- Text cells with `%` present → already percent-scale as written, never rescaled regardless of magnitude
- Text cells without `%` present → rescaled only if the parsed value is `≤ 1` (raw decimal-as-text case)
- Numeric-dtype cells → rescaled unconditionally, since a numeric Excel percent-formatted cell is a decimal fraction by definition of that cell format, not something to gate on magnitude

**Why documented:** First round of this fix ("aware of whether a column is a percentage column") was an improvement but incomplete — it narrowed the bug rather than closing it, since it still couldn't distinguish an already-correct small percentage from a raw decimal needing scaling. Worth recording that the fix required two passes, and that a heuristic based on resulting value magnitude is weaker than one based on the original cell's literal format (presence of `%`) wherever that signal is available.

**Verification:** `stg_top15_psp` dropped and fully reloaded via `etl_top15_psp.py` after the fix. `sql/psp_reliability.sql` Block 1 rerun — 0 rows returned (down from 310).

**Status:** Fixed and verified 12-07-2026.

---

### Decision: PSP name casing/suffix normalization — .title() base case-fold with explicit acronym and suffix overrides

**Date:** 12-07-2026

**Finding:** `sql/qa/psp_payer_name_mismatch_check.sql` (drafted while investigating the Oct→Nov 2023 approval-rate step) revealed that `psp_name` casing was inconsistent across source files — NPCI switched to near-total ALL-CAPS naming for roughly Nov 2023–May 2024, reverting afterward. `sql/qa/psp_name_casing_scope_check.sql` scoped the impact: 24 distinct PSPs had 2+ raw spelling variants across the series (e.g. `"ICICI Bank"` / `"ICICI BANK"`, `"Yes Bank Ltd"` / `"YES BANK LTD"` / `"Yes bank Ltd."`), corrupting any exact-string match, join, or GROUP BY on `psp_name` — including the persistent-leader and churn blocks in `sql/psp_reliability.sql`.

**Decision:** `clean_psp_name()` in `etl_top15_psp.py` updated to:
- Base case-fold via `.str.title()` — chosen over a majority-vote canonical-name mapping because it generalizes to casing variants in months not yet loaded, rather than only fixing variants already observed
- Corporate suffixes (`Ltd`, `Ltd.`, `Limited`, `Private Limited`) stripped entirely via regex — not analytically meaningful and inconsistently present across files
- Small explicit override lists layered on top for what `.title()` structurally cannot fix: known acronyms (`Hdfc` → `HDFC`, `Icici` → `ICICI`, etc.), known internal-cap brand names (`Indusind` → `IndusInd`), and one genuine full-wording variant (`India Post Payment Bank` → `India Post Payments Bank`)

**Why `.title()` over canonical-mapping:** A majority-vote mapping built from currently-loaded data would need to be rebuilt on every reload as new months arrive, and could silently reassign a PSP's canonical spelling between reloads — making the join key unstable over time. `.title()` plus a short, explicit exception list (same pattern as `KNOWN_UPI_APPS_GAPS` in `sanityCheck.py`) is deterministic and future-proof, at the cost of needing new exceptions added by hand if an unseen acronym/brand name appears later.

**Verification:** `stg_top15_psp` dropped and fully reloaded. `sql/qa/psp_name_casing_scope_check.sql` QA A rerun — 0 rows (down from 24 PSPs with multiple spellings). `sql/qa/psp_oct_nov_2023_step_check.sql` QA 2 rerun — payer-side stable-PSP match count rose from 2/15 to 14/15.

**Status:** Fixed and verified 12-07-2026.

---

### Decision: Oct→Nov 2023 approval-rate step confirmed genuine, asymmetric between payer and payee

**Date:** 12-07-2026

**Finding:** Following the psp_name casing fix above, `sql/qa/psp_oct_nov_2023_step_check.sql` QA 2 was rerun with working name-matching. Confirmed the ~4-point approval-rate drop flagged by `sql/psp_reliability.sql` Block 2 is genuine PSP-level deterioration, not a top-15 composition change — but the two sides are not equally affected:

| psp_type | PSPs matched | avg Oct 2023 approval % | avg Nov 2023 approval % | avg delta |
| --- | --- | --- | --- | --- |
| payee | 15/15 | 98.71 | 94.16 | −4.55 |
| payer | 14/15 | 98.47 | 96.54 | −1.93 |

**Decision:** Document this as an asymmetric decline — payee-side approval rates fell roughly twice as much as payer-side in this window — rather than a uniform "reliability dropped" statement. The payer-side aggregate figure from Block 2 (−3.79) sits between the stable-PSP average (−1.93) and the payee-side severity, indicating a modest residual composition effect on the payer side (one PSP churned) layered on top of genuine, smaller-magnitude deterioration.

**Why:** The asymmetry is a more specific and more defensible claim than treating both sides as one event, and is worth investigating further (e.g. is this NPCI-methodology-related, given it coincides with the same window where the ALL-CAPS source-file formatting appeared) before finalizing the Step 4 narrative.

---

### Decision: Slice / North East Small Finance Bank merger — entity names consolidated

**Date:** 13-07-2026

**Finding:** `sql/qa/psp_name_casing_scope_check.sql` QA B (run while investigating the casing fix) surfaced 5 distinct raw names across 16 rows, all under `psp_type = 'payer'`: `North East Small Finance Bank Acquirer`, `North East Small Finance Bank`, `Slice Small Finance Bank`, `Slice Small Finance Bank Acquirer`, and `Slice Small Finance Bank Limited(North East Small Finance Bank Limited)`. Unlike the casing issue, this is not a formatting artifact — it reflects a real corporate event. Slice announced its merger with North East Small Finance Bank (NESFB) in October 2023; the merger completed in October 2024; the merged entity was formally renamed Slice Small Finance Bank in May 2025 (per RBI notification, reported by Fortune India). All NESFB/Slice rows in `stg_top15_psp` begin January 2025 — after the merger's October 2024 completion date — confirmed by a direct query showing zero NESFB/Slice rows before 2025-01. NPCI's source files did not consistently use the post-merger name during the Jan 2025–May 2026 transition window, including a two-month reversion to "North East Small Finance Bank" in Feb–Mar 2026 despite the entity being publicly known as Slice Small Finance Bank by then, and two one-off "Acquirer"-suffixed rows appearing nowhere else in the table.

**Decision:** All five raw name variants mapped to a single canonical name, `Slice Small Finance Bank`, via an entity-lineage override in `clean_psp_name()`. Distinct from the casing/suffix normalization above: this is a business-event-driven identity consolidation backed by an external, verifiable fact (the merger), not a mechanical formatting fix. The "Acquirer" suffix is treated as a labeling artifact specific to this entity's transition period — it appears on no other PSP in the table across the full series, so it is not read as a real NPCI reporting category.

**Why:** Since every appearance of this entity in the table postdates the actual merger, all rows represent the same legal entity throughout — consolidating them corrects a labeling inconsistency rather than erasing a pre/post-merger distinction that would otherwise need to be preserved. Leaving the 5 variants unmerged would fragment one PSP's volume and reliability data across 5 names, undercounting it in any `GROUP BY psp_name` analysis (Blocks 3 and 5 of `sql/psp_reliability.sql`) exactly the way the casing bug did.

**Verification:** Confirmed no `North East Small Finance Bank` or `Slice Small Finance Bank` rows exist prior to 2025-01 (pre-merger NESFB never independently appeared in top-15). `stg_top15_psp` dropped and reloaded after adding the override.

**Status:** Fixed and verified 13-07-2026.

---

### Decision: BHIM / NPCI BHIM Services Ltd (NBSL) — entity names consolidated

**Date:** 13-07-2026

**Finding:** `sql/qa/...` (Block 5, churn check) showed `BHIM` present from 2022-01 through 2025-12, followed immediately by `Npci BHIM Services Ltd (Nbsl)` from 2026-01 onward, on both payer and payee sides. NPCI incorporated NPCI BHIM Services Ltd (NBSL) as a wholly-owned subsidiary in August 2024 to operate and promote the BHIM UPI app. The ~16-month gap between incorporation (Aug 2024) and the name's appearance in this table (Jan 2026) reflects NPCI's internal reporting lag adopting the new subsidiary name, not a separate entity.

**Decision:** `Npci BHIM Services Ltd (Nbsl)` mapped to `BHIM` (canonicalizing toward the older, long-running name rather than the newer one, since BHIM has 34-52 months of history in this table vs. NBSL's 3) via `clean_psp_name()` override.

**Why:** Same underlying app/entity throughout; leaving these split would fragment BHIM's already-modest volume and reliability history across two names for no analytical benefit.

**Confidence:** High — subsidiary incorporation date and purpose confirmed via NPCI's own press release.

**Status:** Fixed and verified 13-07-2026.

---

### Decision: IDFC Bank / IDFC First Bank — entity names consolidated (lower confidence)

**Date:** 13-07-2026

**Finding:** `sql/qa/...` (Block 5, churn check) showed `IDFC First Bank` present through 2024-09, immediately followed by `IDFC Bank` from 2024-10 onward, on the payer side. This boundary coincides exactly with IDFC Limited's reverse merger into IDFC First Bank, effective October 1, 2024, in which IDFC First Bank was the surviving legal entity. Confirmed `IDFC Bank` never appears in the table before October 2024, ruling out a genuinely separate, independently-existing "IDFC Bank" entity.

**Complication:** "IDFC Bank" was not the pre-merger parent's name — that entity was called "IDFC Limited" from 2018 onward. "IDFC Bank" was retired as a name in 2018, when it merged with Capital First and became IDFC First Bank. Why NPCI's source file would revert to a name unused for six years, at the exact moment of an unrelated corporate merger, is not explained by any public source found. The same-entity conclusion is well-supported by the timing; the specific mechanism is inferred, not confirmed.

**Decision:** `IDFC Bank` mapped to `IDFC First Bank` (the current, correct legal name) via `clean_psp_name()` override.

**Confidence:** Medium — flagged explicitly lower than the Slice/NESFB and BHIM/NBSL overrides above, which are backed by direct public confirmation of the specific naming transition. If a clearer explanation surfaces later, revisit this entry.

**Status:** Fixed and verified 13-07-2026.

---

### Decision: Payer-side weighted approval decline concentrated in 3 PSPs — decomposition and PhonePe-partner context

**Date:** 13-07-2026

**Finding:** `sql/psp_reliability.sql` Block 2 showed a striking divergence on the payer side: the volume-weighted average approval rate fell 6.16 points (2022 → 2025 full-year comparison), while the simple average across the same top-15 PSPs barely moved. `sql/qa/psp_payer_weighted_decline_decomposition.sql` isolated the cause — for PSPs present in the top-15 in both 2022 and 2025, per-PSP approval-rate change weighted by volume share explains ≈96% of the total weighted-average shift (−5.93 of −6.16; residual attributable to churn, PSPs not present in both years).

Three PSPs — **Yes Bank, Axis Bank, and ICICI Bank** — account for ≈84% of the total decline (−5.18 of −6.16):
- **Yes Bank:** approval rate fell 8.29 points; remained the largest volume-share PSP throughout (36.62% → 29.28%)
- **Axis Bank:** approval rate fell 5.4 points; volume share more than doubled (16.36% → 35.26%), becoming the largest payer-side volume carrier by 2025 — both a genuine reliability decline and a large composition shift compounding in the same direction
- **ICICI Bank:** approval rate fell 7.04 points; volume share held roughly steady (13.75% → 16.12%)

Most other matched PSPs (Federal Bank, India Post Payments Bank, Airtel Payments Bank, IDFC First Bank, Kotak Mahindra Bank, BHIM) showed flat or *improving* approval rates over the same period — the payer-side decline is not broad-based across the top-15, unlike the payee side, where weighted and simple averages move together.

**Contextual note (inference, not a data-derived finding):** PhonePe's confirmed multi-bank UPI partners are Yes Bank (`@ybl`), ICICI Bank (`@ibl`, added 2020), and Axis Bank (`@axl`) — the exact three PSPs identified above. Combined with PhonePe's #1 app-level position in every month of the Step 2 HHI series, this is consistent with the dominant app's banking partners being disproportionately responsible for the payer-side reliability decline. This is stated as a plausible explanatory link, not a proven causal claim — `stg_top15_psp` has no per-app-per-bank transaction attribution, so this dataset cannot directly confirm which app's traffic is driving any individual PSP's volume or approval trend. Framed with the same conditional-inference caution as the existing MDR-policy decision above.

**Why documented:** Reframes the payer-side reliability story from "PSP reliability declined" (a broad claim, and inaccurate given most matched PSPs held flat or improved) to "payer-side decline is concentrated in 3 high-volume PSPs, 2 of which also gained significant volume share" — a materially different and more defensible finding, and one that pairs naturally with the existing HHI/concentration narrative from Step 2 rather than sitting alongside it as an unrelated fact.

**Status:** Verified 13-07-2026.

---

### Decision: June 2023 payer-side BD/TD composition anomaly — confirmed genuine, classification artifact not a reliability event

**Date:** 13-07-2026

**Finding:** `sql/psp_reliability.sql` Block 4 showed payer-side June 2023 with `business_decline_percent` near 0% and `technical_decline_percent` elevated (1.3-5.2%) across all 15 payer PSPs — the inverse of every surrounding month, where `business_decline_percent` runs ~1.3-2.0% and `technical_decline_percent` sits near 0%. `sql/qa/psp_payer_2023_06_bd_td_swap_check.sql` confirmed this is not an ETL-level column swap: values are internally consistent (`approved% + bd% + td% ≈ 100` holds for all 15 rows) and manual inspection of the raw source file ruled out file-level column reordering.

**Context considered:** NPCI recorded a then-record 9.34 billion UPI transactions in June 2023. However, this does not fully explain the anomaly: total failure rate (100 - approved%) for June 2023 payer (98.5%) is in line with May (98.64%) and July (98.38%) — no spike. A genuine traffic-driven infrastructure strain would be expected to raise total failures, not merely reclassify a stable failure rate between business and technical categories. The uniform, symmetric flip across all 15 PSPs simultaneously is more consistent with a one-month change in NPCI's decline-classification methodology or reporting template than a real operational event, though the specific mechanism is not confirmed by any public source found.

**Decision:** Treated as a genuine but unexplained source-data characteristic, not a data quality error requiring a fix, and not a real reliability event. Flagged explicitly in any decline-composition trend chart or write-up; excluded from claims about technical infrastructure performance for that specific month.

**Status:** Investigated and documented 13-07-2026. Root mechanism unresolved — revisit if further evidence surfaces.

---

### Decision: Post-Nov 2023 approval decline attributed to business decline, not technical failure

**Date:** 13-07-2026

**Finding:** `sql/psp_reliability.sql` Block 4 shows `business_decline_percent` jumping from ~0.5% to ~4.8-5% at the Nov 2023 boundary (matching the approval-rate step confirmed genuine in the earlier decision), on both payee and payer simultaneously, and climbing further through the series (reaching ~9-10% by 2026). `technical_decline_percent` remains low and roughly flat throughout the same period, even trending down as a share of total declines (from double digits in 2022 to under 1% by 2026).

**Decision:** The multi-year approval-rate decline is characterized specifically as a rise in business-side declines (bank/account-level transaction rejections, per the existing schema definition), not a decline in NPCI's technical/switch-level infrastructure reliability. Framed this way in any write-up rather than as generic "UPI reliability degraded," which would misattribute the cause.

**Why:** More precise and more defensible than an undifferentiated reliability claim, and consistent with the payer-side concentration finding (Yes Bank/Axis Bank/ICICI Bank decomposition) — those are bank-side approval mechanics, reinforcing that this is a business-decline-driven story centered on specific PSPs, not an ecosystem-wide technical degradation.

**Status:** Verified 13-07-2026.

---

### Decision: sanityCheck refactored to codify Step 2-4 findings as permanent regression guards 

**Date:** 13-07-2026. Both sanityCheck.sql and sanityCheck.py 

**updated:** 
1. fixed a latent bug where a single hardcoded calendar end date conflated each table's natural trailing-edge publication lag with genuine gaps — now each table bounds its own missing-month check to its own MAX(year,month); 
2. added known-exception handling for the 5 confirmed-genuine duplicate app-months; 
3. promoted the percent-sum, psp_name-casing, and header-leak checks from one-time investigation queries to permanent pipeline-health regression guards; 
4. added new guards for name-override collisions and pre-override legacy-name leakage; 
5. added a BD/TD composition anomaly detector with the 2023-06 payer case carved out as documented. 

**Why:** several Step 1 findings and Step 3-4 fixes had no standing regression test — a future reload could silently reintroduce any of these bugs and nothing would catch it until someone noticed by hand during analysis.

**Superseded 15-07-2026:** the known-exception carve-out for the 5 duplicate app-months (point 2) was removed once those duplicates were reclassified as naming variants and physically merged — see entry below. `KNOWN_DUP_APP_MONTHS` reverted to an empty set; `sanityCheck.sql` check 4c reverted to unconditional `expect_empty`.

---

### Decision: Nov 2023 payee-side "Indian Bank" collision resolved as IndusInd Bank source-file mislabel, not a genuine duplicate — with downstream correction to Block 3 persistent-leader threshold

**Date:** 14-07-2026

**Finding:** The sanityCheck refactor's new check 10 (name-override collision guard) flagged its first real case: `(2023, 11, payee, 'Indian Bank')` with 2 rows — id 323 (76.60 Mn, 93.91% approved) and id 329 (21.35 Mn, 92.91% approved). Initial hypothesis was a genuine duplicate, matching the shape of the 5 confirmed `stg_upi_apps` duplicates. This was superseded after two further observations:

1. IndusInd Bank — present at rank 8 in Oct 2023 (69.70 Mn) — was entirely absent from the Nov 2023 payee top-15 and reappeared in Dec 2023 (75.01 Mn), a one-month gap in an otherwise continuous series.
2. Row id 323's volume (76.60 Mn) sits smoothly between IndusInd's Oct and Dec figures, and its reliability profile (93.91 / 5.98 / 0.11 approved/BD/TD) closely matches IndusInd's Dec profile (94.03 / 5.83 / 0.14) — a far tighter match than to Indian Bank's own trend. Row id 329 (21.35 Mn, 92.91%) matches Indian Bank's genuine trajectory, continuing a real decline visible Oct→Dec (99.45 → 92.91 → 92.33), consistent with the already-documented Oct→Nov 2023 payee-side approval step.

**Conclusion:** Row id 323 is IndusInd Bank's genuine Nov 2023 entry, mislabeled as "Indian Bank" at the NPCI source-file level (raw pre-clean strings were "INDIAN Bank" and "Indian Bank" — both correctly normalized by `clean_psp_name()`; the error originates in the source data, not the ETL). Row id 329 is genuine Indian Bank data and required no change. Payer-side check for both names in this window returned empty — neither bank runs payer-side top-15, a scope note rather than a complication.

**Fix:** `sql/qa/fix_2023_11_payee_indusind_mislabel.sql` — one-time `UPDATE` of row id 323's `psp_name` from `Indian Bank` to `IndusInd Bank`, guarded by year/month/psp_type/volume match. Matches the manual-correction precedent set by the 2022-04 header-leak fix (direct DB correction, not an ETL change) rather than the `stg_upi_apps` query-time-aggregation pattern — that pattern is for two rows confirmed to represent the same real-world entity; here the two rows represent two *different* PSPs, so aggregating them would have wrongly attributed IndusInd's volume to Indian Bank and erased IndusInd's genuine one-month presence from the churn record.

**No permanent exception added to `sanityCheck.py`/`.sql`:** unlike the 5 `stg_upi_apps` duplicates or the 2023-06 BD/TD anomaly, this was a one-time source-data error corrected at the row level. Post-fix, check 10 (collision guard) passes with a plain `expect_empty` — no standing carve-out needed.

**Downstream effect — Block 3 (persistent leaders) threshold correction:** Prior to this fix, IndusInd Bank showed 51 of a possible 51 months present (missing Nov 2023 due to the mislabel), landing exactly at the `>= 51` threshold hardcoded in `psp_reliability.sql` at the time. Post-fix, IndusInd is continuously present across all 52 available payee-side months, revealing that the true "fully persistent" count is 52, not 51 — and that the hardcoded `51` had the same staleness risk already fixed once before in `sanityCheck.py`'s `CALENDAR_END`. `psp_reliability.sql` Block 3 updated to derive the threshold dynamically per `psp_type` (`COUNT(DISTINCT year*100+month)` from the data, via an `available_months` CTE) instead of a hardcoded constant, and the filter changed from `>=` to `=` — "persistent leader" now means fully persistent across every available month for that side, a cleaner and non-arbitrary definition.

**Updated Block 3 result — exactly 15 fully-persistent PSPs** (8 payee, 7 payer), each present in literally every month their side's data covers:

*Payee (by avg approval %):* Federal Bank (97.17%), State Bank of India (96.55%), Kotak Mahindra Bank (96.29%), HDFC Bank (96.15%), Axis Bank (96.08%), ICICI Bank (95.80%), IndusInd Bank (95.11%), Yes Bank (94.55%).

*Payer (by avg approval %):* Kotak Mahindra Bank (98.84%), State Bank of India (96.26%), HDFC Bank (96.15%), Axis Bank (95.56%), Airtel Payments Bank (95.19%), ICICI Bank (94.77%), Yes Bank (94.02%).

**Notable pattern:** Yes Bank ranks lowest-reliability among fully-persistent PSPs on *both* sides independently (94.55% payee, 94.02% payer), while simultaneously carrying by far the largest volume on both sides (344,753 Mn payee, 227,191 Mn payer — roughly 3x the next-largest payee PSP and comparable margin on payer). Consistent with, and reinforcing, the existing payer-side weighted-decline decomposition (Yes Bank/Axis Bank/ICICI Bank) and the PhonePe-banking-partner correlational note. Stated as an observed pattern, not a causal claim, per the existing MDR-policy conditional-inference framing.

**Block 5 (churn) also updated as a mechanical consequence:** IndusInd Bank `months_present` +1, Indian Bank `months_present` −1 — correctly reflecting the row-level relabeling, not a genuine churn event for either PSP.

**Verification:** Post-fix, check 10 passes with zero rows. IndusInd Bank's payee-side volume trend now reads Aug 52.28 → Sep 51.09 → Oct 69.70 → Nov 76.60 → Dec 75.01, closing the one-month gap in Block 5's churn table. Block 3 re-run at the corrected dynamic threshold returns exactly 15 PSPs as above.

**Status:** Fixed and verified 14-07-2026.

---

### Decision: PhonePe-partner banks reverse from outperforming to underperforming the payer-side field at the Nov 2023 step — Step 6 cross-table confirmation

**Date:** 15-07-2026

**Finding:** `sql/step6_cross_cutting.sql` Panel B (payer-side approval, PhonePe-partner banks vs. rest-of-field, partners excluded from the baseline) shows the partner banks running consistently above the field average throughout 2022–Oct 2023 (gap ranging +0.55 to +3.89 pts), flipping to consistently below the field average starting Nov 2023 (−2.11 pts) and widening in nearly every subsequent month, reaching −7.66 pts by the latest available month (May 2026). The flip's timing is exact — `Oct 2023` is the last positive month, `Nov 2023` the first negative one — coinciding precisely with the already-documented Oct→Nov 2023 approval-rate step.

**Decision:** Upgrades the existing payer-side weighted-decline decomposition (Yes Bank/Axis Bank/ICICI Bank account for ~84% of the weighted decline) from an annual 2022-vs-2025 snapshot to a monthly-resolution finding: the partner banks' relative underperformance is not a gradual widening from parity, but a sign reversal dated to a specific month, sustained and still deepening as of the latest data. Still framed as correlational, not causal, per the existing PhonePe-partner conditional-inference note — this dataset still cannot attribute volume to a specific app.

**Status:** Verified 15-07-2026 against live query output.

---

### Decision: Payee-side weighted approval decline also concentrated in Yes Bank/Axis Bank/ICICI Bank — independent confirmation of the payer-side pattern

**Date:** 15-07-2026

**Finding:** `sql/step6_payee_decline_decomposition.sql` applied the same matched-PSP weighted-decomposition method used for the payer side (Decision: "Payer-side weighted approval decline concentrated in 3 PSPs," above) to the payee side. Payee-side weighted-average approval fell 7.08 points (2022 → 2025). `Yes Bank`, `Axis Bank`, and `ICICI Bank` — the same three PSPs identified on the payer side — account for ≈90% of the matched-PSP contribution to that decline (−5.45 of −6.04 pts) and ≈77% of the total shift including churn. `Yes Bank` alone drives ≈69% of the matched decline: its approval rate fell 9.02 points while its payee-side volume share grew from 38.77% to 53.32% over the same period, compounding in the same direction — mirroring Axis Bank's payer-side pattern (declining reliability plus rising volume share simultaneously). The remaining 8 matched PSPs show flat-to-small declines or, in one case (BHIM), a slight improvement.

**Decision:** This independently confirms the payer-side finding rather than merely restating the already-documented multi-year decline trend — the same three banks, decomposed the same way, on the opposite side of the transaction. Strengthens (without proving) the existing PhonePe-partner conditional-inference note: PhonePe's three confirmed banking partners are the concentrated driver of the approval-rate decline on both payer and payee sides independently, still stated as correlational — `stg_top15_psp` has no per-app-per-bank attribution, so causality remains unconfirmed.

**Status:** Verified 15-07-2026.

### Decision: stg_upi_apps naming-variant overrides finalized — Paytm, Bajaj Finserv, Federal Bank, Mobikwik, Others reclassified from "genuine duplicates" to NPCI naming conventions; existing duplicate rows physically merged

**Date:** 15-07-2026

**Finding — Paytm:** `Paytm`, `Paytm (OCL)`, `Paytm (OCL )`, `PAYTMWALLET`, and `Paytm Payments Bank App` all trace to one confirmed regulatory event. Paytm's UPI traffic originally ran through Paytm Payments Bank (PPBL). RBI barred PPBL from accepting deposits/top-ups from Jan 31, 2024 (deadline extended to March 15, 2024). NPCI granted One97 Communications Ltd (OCL) — the company that actually operates the Paytm brand — TPAP status on March 14, 2024, and user/merchant migration off `@paytm`→PPBL onto new PSP banks (SBI, Axis, HDFC, Yes Bank) began April 17, 2024. The variant names track this migration; all represent the same consumer-facing app.

**Finding — Bajaj Finserv / Federal Bank / Mobikwik / Others:** Re-examined the 5 pairs previously documented (09-07-2026 entry above) as genuine distinct entries, using two checks not applied the first time: (a) whether the "duplicate" name ever appears independently, outside its collision month, anywhere in the 52-month series; (b) full-series co-occurrence pattern against the main name.
- **Federal Bank Apps → Federal Bank App:** plain spelling variant, no entity ambiguity.
- **Mobikwik PPI → Mobikwik:** "PPI" (Prepaid Payment Instrument) is a regulatory product category, not an organization name — cannot represent a separate company by construction.
- **Other Apps / Others → Other:** NPCI's interchangeably-used low-volume catch-all bucket.
- **Bajaj Finserv PPI / Bajaj Markets / Bajaj Pay Wallet → Bajaj Finserv:** full-series check on all `Bajaj%` rows (2022-01–2026-04) confirmed `Bajaj Finserv` present in nearly every month at meaningfully larger volume, with the three variant names appearing only as small entries in a handful of scattered months, never as the sole Bajaj-labeled row in a month at comparable scale.

**Decision:** `APP_NAME_OVERRIDES` added to `clean_app_name()` in `etl_upi_apps.py`:
```python
APP_NAME_OVERRIDES = {
    "PAYTMWALLET": "Paytm",
    "Paytm (OCL )": "Paytm",
    "Paytm (OCL)": "Paytm",
    "Paytm Payments Bank App": "Paytm",
    "Bajaj Finserv PPI": "Bajaj Finserv",
    "Bajaj Markets": "Bajaj Finserv",
    "Bajaj Pay Wallet": "Bajaj Finserv",
    "Federal Bank Apps": "Federal Bank App",
    "Mobikwik PPI": "Mobikwik",
    "Other Apps": "Other",
    "Others": "Other",
}
```
`stg_upi_apps` reloaded via `etl_upi_apps.py` with the override active. Resulting duplicate (app_name, year, month) rows — created by the override collapsing multiple raw names onto one — merged via `sql/qa/fix_duplicate_app_entries_inSame_month.sql`: metrics summed per group (`MIN(id)` row kept), `avg_ticket_size` recomputed as `SUM(total_value_cr)/SUM(total_volume_mn)*10` rather than summed (summing two ratios is not equivalent to the ratio of the summed totals), residual higher-id rows deleted.

**2023-02 Bajaj Finserv note:** this pair's two rows share the *identical* raw name `Bajaj Finserv` (unlike the other four cases, no second naming convention is involved), so it isn't explained by the reclassification above. Assessed as a suspected reload/re-entry duplicate — same shape as the 2024_06/07 (stg_p2p_p2m) and 2024_03 (stg_upi_apps) file-naming incidents documented earlier — rather than two genuine distinct source entries. Merged by the same generic script (summed, not selectively deleted), consistent with that assessment.

**Downstream updates:**
- `KNOWN_DUP_APP_MONTHS` in `sanityCheck.py` cleared to `set()`.
- `sanityCheck.sql` check 4c reverted from the `NOT IN (...)` carve-out to a plain `expect_empty`.
- Full sanity re-run (`sanity_results_2026_07_15_1353.md`) confirms 18/18 checks pass, 0 fail — check 4c and check 10 both clean.

**Status:** Fixed and verified 15-07-2026.

---

### Decision: PhonePe naming-variant override — Phone Pe / Phonepe consolidated

**Date:** 16-07-2026

**Finding:** `Phone Pe` (15 months) and `Phonepe` (1 month) are casing/spacing variants of `PhonePe` (35 months), spread across the full 51-month series with no month containing more than one variant — confirmed via full-series check before merging. Since each month had exactly one PhonePe row, per-month figures (volume, market_share_pct, HHI contribution) were correct at the time regardless of spelling, and the existing "PhonePe #1 every month" Step 2 finding is unaffected, since rank-by-volume within a month doesn't depend on exact string match.

**Risk identified:** any query trending or grouping specifically on `app_name = 'PhonePe'` across months — as opposed to per-month rank — would have silently dropped the 16 affected months, producing an artificially discontinuous PhonePe time series. Directly relevant to the dashboard's Page 1 "top-5 share stacked area" and "market leader" panels, which need re-verification against the merged data before being trusted as final.

**Decision:** `Phone Pe` and `Phonepe` added to `APP_NAME_OVERRIDES` in `clean_app_name()`, mapped to `PhonePe`. No row merge required — one variant per month means no duplicate (app_name, year, month) rows are created by this override, unlike the Paytm/Bajaj/Federal Bank/Mobikwik/Other case.

**Verification:** confirmed zero month overlap across all three variants prior to reload (15 + 35 + 1 = 51, matching total row count with no double-counted month).

**Status:** Fixed and verified 16-07-2026. Dashboard Page 1 market-leader trend and top-5 stacked area re-checked post-reload — no visible movement in either panel, confirming the pre-merge per-month figures were already correct and this was purely a name-consistency fix, not a volume-correction fix.