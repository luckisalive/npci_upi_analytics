#!/usr/bin/env python3
"""
mdr_scenario.py — UPI P2M MDR: scenario model (NOT a measured-impact study)

The MDR was due to start 15 Oct 2026; on 13 Oct 2026 NPCI deferred it to "immediately
post Diwali, at a date to be notified separately" (no new date, no rate change announced
as of 1 Nov 2026). The staging DB has no post-policy observations either way, so
everything here is a parametric what-if built from pre-policy volumes/values.
Every output is labelled "scenario"; nothing is a finding.

Reads  : staging/npci_upi.db  (stg_p2p_p2m, stg_upi_apps)
Writes : <out_dir>/mdr_inputs.csv         parameter register (value, status, note)
         <out_dir>/mdr_pool_grid.csv      notional annual pool by p x cap-scenario, split by party
         <out_dir>/mdr_app_allocation.csv app-side pool allocated by VALUE share

Usage:  python mdr_scenario.py [db_path] [out_dir]
        defaults: staging/npci_upi.db   mdr/

Status tags used in the parameter register
    NEWS-REPORTED : stated consistently by news coverage of the NPCI FAQ (15 Sep 2026);
                    confirm against the primary PDF before publishing
    VERIFY        : reported as proposed / single-source / not yet confirmed
    ASSUMPTION    : modelling choice with no data source — vary it, don't defend it
    DERIVED       : computed from the staging DB
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("staging/npci_upi.db")
OUT_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("mdr")

# ── Policy parameters ───────────────────────────────────────
RATE = 0.004            # 0.4% on P2M above the threshold
THRESHOLD = 2000        # Rs
CAP = 300               # Rs per transaction
CAP_TXN = 75000         # Rs; cap binds at/above this (0.4% x 75,000 = 300)
SPLIT = {"issuer": 0.40, "app": 0.30, "acquirer": 0.30}   # proposed
FUND_SHARE = 0.05       # proposed: % of collections to a small-merchant fund
VOL_SHARE_BELOW = 0.95  # reported share of P2M *volume* at or below Rs 2,000

# ── Modelling assumptions (no data source) ──────────────────
P_MAX = 0.80            # ceiling for p, share of P2M VALUE above the threshold
N_STEPS = 10
BIG_MEAN_TICKET = 150000  # assumed mean ticket of transactions >= Rs 75,000
EXEMPT_SHARE = 0.0        # share of taxable value exempt (micro-merchant QR); 0 = ignore
CAP_SCENARIOS = {         # share of taxable value sitting in transactions >= Rs 75,000
    "cap-light (0%)": 0.0,
    "cap-moderate (20%)": 0.20,
    "cap-heavy (40%)": 0.40,
}


def load():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    p2p = pd.read_sql("SELECT year, month, p2m_volume_mn, p2m_value_cr FROM stg_p2p_p2m", conn)
    apps = pd.read_sql(
        "SELECT year, month, app_name, SUM(total_value_cr) AS val, SUM(total_volume_mn) AS vol "
        "FROM stg_upi_apps WHERE app_name != 'Application Name' "
        "AND total_value_cr IS NOT NULL GROUP BY year, month, app_name", conn)
    conn.close()
    return p2p, apps


def trailing_window(p2p, apps):
    """Last 12 calendar months ending at the earliest common latest month of both tables."""
    ym = lambda d: (d["year"] * 100 + d["month"])
    cutoff = int(min(ym(p2p).max(), ym(apps).max()))
    y, m = cutoff // 100, cutoff % 100
    months = []
    for _ in range(12):
        months.append(y * 100 + m)
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return cutoff, sorted(months)


def hhi(shares_pct):
    return float((np.asarray(shares_pct) ** 2).sum())


def main():
    if not DB_PATH.exists():
        sys.exit(f"ERROR: database not found at {DB_PATH.resolve()}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p2p, apps = load()

    cutoff, months = trailing_window(p2p, apps)
    w2 = p2p[(p2p["year"] * 100 + p2p["month"]).isin(months)]
    if len(w2) < 12:
        have = sorted((w2["year"] * 100 + w2["month"]).tolist())
        sys.exit(f"ERROR: stg_p2p_p2m has {len(w2)}/12 months in window {months[0]}-{months[-1]}: {have}")
    wa = apps[(apps["year"] * 100 + apps["month"]).isin(months)]
    apps_months = sorted((wa["year"] * 100 + wa["month"]).unique().tolist())
    missing_apps = sorted(set(months) - set(apps_months))

    annual_value_cr = float(w2["p2m_value_cr"].sum())
    annual_volume_mn = float(w2["p2m_volume_mn"].sum())
    avg_ticket = annual_value_cr * 10 / annual_volume_mn  # Rs per txn (crore / million * 10)

    # p lower bound: if VOL_SHARE_BELOW of volume is <= Rs 2,000, the rest each carry >= Rs 2,000
    p_min = (1 - VOL_SHARE_BELOW) * THRESHOLD / avg_ticket
    if p_min >= P_MAX:
        sys.exit(f"ERROR: p_min={p_min:.3f} >= P_MAX={P_MAX}. Check VOL_SHARE_BELOW / avg ticket ({avg_ticket:.0f}).")
    p_grid = np.linspace(p_min, P_MAX, N_STEPS)

    big_rate = min(RATE, CAP / BIG_MEAN_TICKET)
    rows = []
    for scen, b in CAP_SCENARIOS.items():
        eff_rate = (1 - b) * RATE + b * big_rate
        for p in p_grid:
            taxable = annual_value_cr * p * (1 - EXEMPT_SHARE)
            pool = taxable * eff_rate
            rows.append({
                "cap_scenario": scen, "p_pct": round(p * 100, 2),
                "taxable_value_cr": round(taxable, 1),
                "effective_rate_on_taxable_pct": round(eff_rate * 100, 4),
                "pool_cr": round(pool, 1),
                "pool_as_pct_of_total_p2m_value": round(pool / annual_value_cr * 100, 4),
                "issuer_cr": round(pool * SPLIT["issuer"], 1),
                "app_side_cr": round(pool * SPLIT["app"], 1),
                "acquirer_cr": round(pool * SPLIT["acquirer"], 1),
                "fund_cr_if_applied_to_gross": round(pool * FUND_SHARE, 1),
            })
    grid = pd.DataFrame(rows)

    # App allocation by VALUE share (a fee on value follows value, not volume)
    by_app = wa.groupby("app_name", as_index=False).agg(val=("val", "sum"), vol=("vol", "sum"))
    by_app["value_share_pct"] = by_app["val"] / by_app["val"].sum() * 100
    by_app["volume_share_pct"] = by_app["vol"] / by_app["vol"].sum() * 100
    top = by_app.nlargest(5, "value_share_pct")["app_name"].tolist()
    by_app["app_group"] = np.where(by_app["app_name"].isin(top), by_app["app_name"], "All other apps")
    grp = by_app.groupby("app_group", as_index=False)[["value_share_pct", "volume_share_pct"]].sum()
    alloc = grid[["cap_scenario", "p_pct", "app_side_cr"]].merge(grp, how="cross")
    alloc["app_pool_cr"] = (alloc["app_side_cr"] * alloc["value_share_pct"] / 100).round(1)
    alloc = alloc[["cap_scenario", "p_pct", "app_group", "value_share_pct", "volume_share_pct", "app_pool_cr"]].round(4)

    hhi_val, hhi_vol = hhi(by_app["value_share_pct"]), hhi(by_app["volume_share_pct"])

    inputs = pd.DataFrame([
        ("rate", f"{RATE:.1%}", "NEWS-REPORTED", "on P2M above threshold"),
        ("threshold_rs", THRESHOLD, "NEWS-REPORTED", ""),
        ("cap_rs_at_or_above_75000", CAP, "NEWS-REPORTED", "0.4% x 75,000 = 300"),
        ("effective_date", "TBA (post-Diwali)", "NEWS-REPORTED", "was 2026-10-15; NPCI deferred 2026-10-13, new date to be notified; re-check before publishing"),
        ("payer", "merchant", "NEWS-REPORTED", "not the consumer; P2P stays free"),
        ("split_issuer_app_acquirer", "40/30/30", "VERIFY", "reported as proposed"),
        ("small_merchant_fund_share", FUND_SHARE, "VERIFY", "shown separately, not netted from the split"),
        ("flat_rs5_sectors", "excluded from model", "VERIFY", "railways/fuel etc. reported; confirm in PDF"),
        ("vol_share_below_threshold", VOL_SHARE_BELOW, "VERIFY", "reported share of VOLUME, not value"),
        ("window_months", f"{months[0]}..{months[-1]}", "DERIVED", f"earliest common month {cutoff}"),
        ("apps_months_missing_in_window", str(missing_apps), "DERIVED", "app shares use available months only"),
        ("annual_p2m_value_cr", round(annual_value_cr, 1), "DERIVED", "trailing 12 months"),
        ("avg_p2m_ticket_rs", round(avg_ticket, 1), "DERIVED", "value_cr*10/volume_mn"),
        ("p_min", round(p_min, 4), "DERIVED", "= (1-0.95)*2000/avg_ticket; floor on value share above threshold"),
        ("p_max", P_MAX, "ASSUMPTION", "no value-band source; vary freely"),
        ("big_ticket_mean_rs", BIG_MEAN_TICKET, "ASSUMPTION", "for cap effect"),
        ("exempt_share", EXEMPT_SHARE, "ASSUMPTION", "micro-merchant exemption not modelled by default"),
        ("cap_scenarios", str(CAP_SCENARIOS), "ASSUMPTION", "share of taxable value in txns >= Rs 75,000"),
        ("app_shares_basis", "total UPI value (P2P+P2M)", "ASSUMPTION", "stg_upi_apps has no P2M-only split"),
    ], columns=["parameter", "value", "status", "note"])

    inputs.to_csv(OUT_DIR / "mdr_inputs.csv", index=False)
    grid.to_csv(OUT_DIR / "mdr_pool_grid.csv", index=False)
    alloc.to_csv(OUT_DIR / "mdr_app_allocation.csv", index=False)

    mid = grid[(grid["cap_scenario"] == "cap-moderate (20%)")].iloc[N_STEPS // 2]
    print("SCENARIO MODEL — not a measured result")
    print(f"  window {months[0]}..{months[-1]} | annual P2M value Rs {annual_value_cr:,.0f} cr | avg ticket Rs {avg_ticket:,.0f}")
    print(f"  p floor {p_min:.1%}  (sweep {p_min:.1%} to {P_MAX:.0%}, assumption)")
    lo, hi = grid["pool_cr"].min(), grid["pool_cr"].max()
    print(f"  notional annual pool: Rs {lo:,.0f} cr to Rs {hi:,.0f} cr across the grid")
    print(f"  mid case (p={mid['p_pct']}%, cap-moderate): pool Rs {mid['pool_cr']:,.0f} cr = "
          f"{mid['pool_as_pct_of_total_p2m_value']:.3f}% of total P2M value (vs 0.4% headline)")
    print(f"  app-level HHI over window: value-based {hhi_val:,.0f} vs volume-based {hhi_vol:,.0f}")
    if missing_apps:
        print(f"  NOTE: stg_upi_apps missing {missing_apps} inside window")
    print(f"Wrote 3 CSVs to {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()