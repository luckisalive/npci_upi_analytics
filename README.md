# NPCI UPI Analytics Pipeline

A full-stack analytics pipeline analyzing India's UPI (Unified Payments Interface) ecosystem using NPCI's public statistics — from raw Excel ingestion through ETL, SQL analysis, and a multi-page Tableau dashboard.

**52 months of data (Jan 2022 – May 2026) · 3 data sources · 155+ raw files · 18 automated data-quality checks**

---

## Table of Contents

- [NPCI UPI Analytics Pipeline](#npci-upi-analytics-pipeline)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Analytical Questions](#analytical-questions)
  - [Architecture](#architecture)
  - [Data Sources](#data-sources)
  - [Tech Stack](#tech-stack)
  - [Repository Structure](#repository-structure)
  - [Key Findings](#key-findings)
    - [1. Market concentration (HHI)](#1-market-concentration-hhi)
    - [2. P2P vs. P2M dynamics](#2-p2p-vs-p2m-dynamics)
    - [3. PSP reliability](#3-psp-reliability)
  - [Data Quality \& Engineering Highlights](#data-quality--engineering-highlights)
  - [Dashboard](#dashboard)
  - [Audit Trail — DECISIONS.md](#audit-trail--decisionsmd)
  - [How to Reproduce](#how-to-reproduce)
  - [Known Limitations](#known-limitations)

---

## Overview

UPI processes billions of transactions a month across a fragmented ecosystem of consumer-facing apps (PhonePe, Google Pay, Paytm) and the sponsor banks that actually settle those transactions (PSPs). NPCI publishes this data monthly as disconnected Excel exports with no consistent schema, no shared naming convention, and no built-in way to trace a bank or app across a corporate rename, a regulatory transition, or a formatting change.

This project builds a reproducible pipeline that turns 52 months of that raw data into three analytical answers, with every non-trivial judgment call — data anomalies, entity-lineage decisions, framing choices — logged in [`DECISIONS.md`](./DECISIONS.md) at the time it was made, not reconstructed after the fact.

## Analytical Questions

The project scope was deliberately locked to two core questions (see *Project Scope* in `DECISIONS.md`), later extended with a third cross-cutting one once both were independently validated:

1. **Market concentration** — Which apps dominate UPI transaction volume, and is that concentration rising or falling? (HHI methodology)
2. **P2P vs. P2M dynamics** — Is merchant payment volume (P2M) structurally overtaking peer-to-peer transfers (P2P), and has that shift stabilized?
3. **PSP reliability** — Which banks/PSPs are most reliable, where are declines concentrated, and does reliability correlate with market concentration?

Explicitly **out of scope**: state-wise analysis (not published), fraud detection (no labeled data exists publicly), and forecasting (~51 monthly rows is too short a series to model responsibly). Scope creep from an early AI-generated project blueprint was deliberately rejected in favor of depth over breadth.

## Architecture

```
NPCI Excel exports (155+ files)
        │
        ▼
┌─────────────────────────────────────────────┐
│  ETL Layer (Python / pandas)                 │
│  etl_upi_apps.py · etl_p2p_p2m.py            │
│  etl_top15_psp.py                            │
│  → schema validation, entity-name            │
│    normalization, numeric cleaning           │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  SQLite staging DB (staging/npci_upi.db)     │
│  stg_upi_apps · stg_p2p_p2m · stg_top15_psp  │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  Automated sanity checks                     │
│  sanityCheck.py / sanityCheck.sql            │
│  18 pass/fail regression guards              │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  Analytical SQL (sql/)                       │
│  HHI · P2P/P2M growth · PSP reliability      │
│  · cross-cutting narrative                   │
│  QA/diagnostic queries kept separate          │
│  (sql/qa/) as evidence of the process         │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  CSV exports (sql/exports/)                  │
│  → Tableau — 4-page dashboard                │
└─────────────────────────────────────────────┘
```

## Data Sources

All data is sourced from NPCI's publicly available **Ecosystem Statistics** reports. No synthetic or simulated data is used anywhere in the project — a deliberate call recorded early in `DECISIONS.md`, since fraud-style synthetic data dressed as real data is a credibility risk that doesn't hold up under interview scrutiny.

| Table | Source sheet | Grain | Coverage |
| --- | --- | --- | --- |
| `stg_upi_apps` | UPI Apps tab | app × month | 2022-01 → 2026-04 (2026-03 gap, not yet published) |
| `stg_p2p_p2m` | P2P/P2M summary | month | 2022-01 → 2026-03 |
| `stg_top15_psp` | Top-15 PSP (payer & payee) | PSP × type × month | 2022-01 → 2026-05 (payee 2022-12 and payer 2026-04 unavailable) |

Files were renamed at download time from NPCI's inconsistent original names to a strict `YYYY_MM.xlsx` convention, since the filename is the *only* source of the time dimension — the sheets themselves carry no date column. The three tables end on different months because of NPCI's own publication lag, not missing files; any cross-table analysis caps at the earliest common month rather than implying one series extends further than it does.

## Tech Stack

- **Python / pandas** — ETL, schema validation, entity-name normalization
- **SQLite** — staging database, three tables, ~150K+ rows
- **SQL** — all analytical logic (HHI, growth rates, weighted decomposition, cross-cutting joins)
- **Tableau** — 4-page interactive dashboard, fed by CSV exports
- **Git** — daily commit discipline across the full build

## Repository Structure

```
├── dashboard/
├── logs/                      # Per-ETL-run logs
├── raw/                       # Source Excel files (upi_apps/, p2p_p2m/, top15_psp/{payer,payee}/)
│   ├── p2p_p2m/
│   ├── top15_psp/
│   │   ├── payee/
│   │   ├── payer/
│   ├── upi_apps/
├── scripts
│   ├── etl_upi_apps.py
│   ├── etl_p2p_p2m.py 
│   ├── etl_top15_psp.py
│   └── sanityCheck.py              # Automated pass/fail runner              
├── sql/
│   ├── cross_cutting.sql
│   ├── HHImonthly.sql
│   ├── p2p_p2mGrowth.sql
│   ├── psp_reliability.sql
│   ├── payee_decline_decomposition.sql
│   ├── sanityCheck.sql             # Standalone version of the same checks
│   ├── qa/                    # Diagnostic/investigation queries (published as evidence)
│   └── exports/                # CSV exports feeding Tableau
├── staging/
│   └── npci_upi.db            # SQLite staging database
├── DECISIONS.md                # Full project audit trail
└── README.md
```

## Key Findings

### 1. Market concentration (HHI)

- App-level concentration is **Highly Concentrated** under DOJ/FTC HHI bands (HHI > 2,500) throughout the series, climbing to a peak around May 2024 before declining.
- **PhonePe holds the #1 position by volume in every single month** of the 52-month series.
- HHI here measures *app-level* concentration (PhonePe, Google Pay as consumer brands), which is explicitly distinct from bank-level or PSP-license-level concentration — a distinction that matters because "PhonePe dominates" refers to the app, not to Yes Bank, PhonePe's sponsor bank.

### 2. P2P vs. P2M dynamics

- P2M (merchant payments) share crossed 50% in **August 2022 (50.01%)**, not September as an early log-precision bug had suggested — corrected after re-verifying directly against the database rather than trusting a rounded log line.
- P2M share rose from 40.3% (Jan 2022) to a peak of 63.7% (Jun 2025), then **plateaued roughly 1 point below that peak** through early 2026 rather than fully recovering.
- P2P and P2M annual growth rates, which were 2–3x apart in 2022–2023 (P2M growing at 93% YoY vs. P2P's 28%), have **converged to near-parity by March 2026** (23.7% vs. 23.7% YoY) — the "P2M is winning" narrative is more precisely "P2M won decisively in 2022–23, and the transition phase is now largely complete."

### 3. PSP reliability

- A ~4-point approval-rate step-decline occurred at the **Oct→Nov 2023** boundary, confirmed genuine (not a top-15 composition artifact) and **asymmetric**: payee-side fell ~2x more (−4.55 pts) than payer-side (−1.93 pts).
- The multi-year approval decline is driven by rising **business declines** (bank/account-level rejections), not technical/infrastructure failures — technical decline rates stayed flat-to-falling across the same period.
- On the payer side, **Yes Bank, Axis Bank, and ICICI Bank** account for ~84% of the weighted-average approval decline (2022→2025); the same three banks independently account for ~90% of the payee-side decline. These are PhonePe's three confirmed banking partners — stated as a plausible correlational link, not a proven causal one, since the dataset has no per-app-per-bank transaction attribution.
- Exactly **15 PSPs** (8 payee, 7 payer) were present in literally every available month for their side — the "fully persistent leaders." Yes Bank ranks lowest-reliability among them on both sides while simultaneously carrying by far the largest volume, a pattern consistent with (not proof of) the PhonePe-partner link above.
- A monthly cross-cutting check confirmed the partner-bank underperformance is a **sign reversal dated to a specific month** (Oct→Nov 2023), not a gradual drift — the partner banks ran *above* the field average every month before that boundary and *below* it, and widening, every month after.

## Data Quality & Engineering Highlights

This project treats data-quality investigation as a first-class deliverable, not an afterthought — `sql/qa/` is published alongside the analytical SQL specifically as evidence of the verification process.

**Notable incidents caught and fixed:**

| Issue | Detection method | Fix |
| --- | --- | --- |
| Duplicate file uploaded under wrong month (2024_06/07, 2024_03) | Consecutive-month identical-volume fingerprint | Correct file re-downloaded, reprocessed via idempotent duplicate guard |
| Percent-scaling bug inflating `technical_decline_percent` | `approved% + BD% + TD% ≈ 100` sanity check (310 failing rows) | Scaling logic keyed off literal `%` presence in source cell, not resulting magnitude |
| 24 PSPs with inconsistent name casing (NPCI's ALL-CAPS period, Nov 2023–May 2024) | Casing-normalization regression guard | `.title()` case-fold + explicit acronym/suffix override dictionary |
| Multi-name entity fragmentation (Slice/NESFB merger, BHIM→NBSL subsidiary, IDFC Bank/IDFC First Bank, Paytm's PPBL→OCL regulatory migration) | Cross-referenced against real corporate/regulatory events (RBI notifications, NPCI press releases) | Entity-lineage overrides in a single `PSP_NAME_OVERRIDES` / `APP_NAME_OVERRIDES` dict, each backed by a dated external event |
| "Indian Bank" collision, Nov 2023 payee | Name-override collision guard + volume/reliability-profile cross-check | Traced to a genuine IndusInd Bank source-file mislabel; corrected via targeted row-level `UPDATE`, not query-time workaround |
| Header row leaking into data (2022-04) | Header-string + null-volume scan | Row excluded at query time (and later deleted at source) |

**Standing regression suite:** `sanityCheck.py` runs 18 automated checks (row counts, missing-month detection with per-table dynamic cutoffs, duplicate detection, percent-sum validation, casing regressions, override-collision guards, BD/TD anomaly detection) and writes a timestamped pass/fail report — so any future data reload that reintroduces a previously-fixed bug is caught automatically rather than rediscovered by hand.

**Engineering principles applied throughout** (see [`DECISIONS.md`](./DECISIONS.md) for the full rationale on each):
- Fix data-quality issues at the root (ETL/schema) — never paper over them in analytical queries, with one documented exception for two rows confirmed to represent the same real-world entity
- One-time source-data errors get surgical, targeted fixes — not permanent exception-handling logic
- Cutoffs and thresholds are computed dynamically from the data (`CTE`s), never hardcoded, since a hardcoded date silently goes stale
- Every judgment call is logged with date, finding, decision, and rationale *at decision time*

## Dashboard

A 4-page Tableau dashboard built directly on top of the analytical SQL:

1. **Market Concentration** — HHI trend with DOJ/FTC band shading and 3-phase annotation, market-leader/top-5 share stacked area, snapshot cards
2. **P2P vs. P2M Dynamics** — share crossover chart with Aug-2022 marker, YoY growth convergence lines, mid-2025 plateau callout
3. **PSP Reliability** — approval-rate trend with the Nov-2023 step annotated, BD/TD composition mix with the Jun-2023 anomaly flagged, decline-driver decomposition, persistent-leader list
4. **Cross-Cutting Narrative** — unified multi-axis timeline (HHI + P2M share + approval rate, capped at the earliest common as-of cutoff), concentration × reliability decomposition (PhonePe-partner banks vs. field), methodology footnote linking back to `DECISIONS.md`

Dashboard annotations are written to faithfully match the documented findings rather than a looser paraphrase — e.g. "plateaued below peak," not "recovered"; crossover dated to August, not September — since the annotation *is* the finding being communicated.

## Audit Trail — DECISIONS.md

[`DECISIONS.md`](./DECISIONS.md) is the permanent decision log for this project: every data anomaly, entity-lineage call, analytical framing choice, and annotation-wording decision is recorded with date, finding, decision, and rationale, written at the time the decision was made. It's the source material for this README and the intended proof of process for anyone reviewing the project — showing not just the final numbers, but how each one was arrived at and verified.

## How to Reproduce

```bash
# 1. Run ETL scripts (idempotent — safe to re-run, skips already-loaded months)
python etl_upi_apps.py
python etl_p2p_p2m.py
python etl_top15_psp.py

# 2. Run the automated sanity suite
python sanityCheck.py staging/npci_upi.db sql/qualityAnalysis/results

# 3. Run analytical SQL against the staging DB
sqlite3 staging/npci_upi.db < sql/HHImonthly.sql
sqlite3 staging/npci_upi.db < sql/p2p_p2mGrowth.sql
sqlite3 staging/npci_upi.db < sql/psp_reliability.sql
sqlite3 staging/npci_upi.db < sql/cross_cutting.sql

# 4. Export CSVs for Tableau (bash heredoc pattern)
sqlite3 staging/npci_upi.db <<'EOF'
.headers on
.mode csv
.once sql/exports/HHImonthly.csv
SELECT * FROM ...;
EOF
```

## Known Limitations

- **No per-app-per-bank attribution.** The PhonePe-banking-partner correlational finding (Yes Bank/Axis Bank/ICICI Bank driving the reliability decline) cannot be confirmed as causal with this dataset — NPCI's public data doesn't break down which app's traffic runs through which PSP.
- **App-level HHI ≠ firm-level HHI.** The concentration metric uses the standard DOJ/FTC bands, but those bands were designed for firm-level antitrust review, not consumer-app-level analysis — a reasonable lens, explicitly caveated rather than presented as a strict antitrust reading.
- **Zero MDR on UPI P2M.** Any statement about "who benefits" from volume concentration is a conditional, policy-contingent inference, not a current profit-capture finding, since UPI P2M currently carries zero merchant discount rate by government mandate.
- **2026 data is partial.** Annual growth-rate comparisons exclude 2026 to avoid comparing a 3-month partial year against full prior years; monthly YoY is used instead for anything touching the most recent months.
- **June 2023 payer-side BD/TD anomaly** remains genuine but structurally unexplained — flagged and excluded from technical-infrastructure claims for that month, not silently smoothed over.