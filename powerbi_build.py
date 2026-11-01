#!/usr/bin/env python3
"""
powerbi_build.py — NPCI UPI Analytics: Power BI Project builder
"""

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("staging/npci_upi.db")
OUT_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("powerbi")
DATA_DIR = OUT_DIR / "data"

PARTNERS = ["Yes Bank", "Axis Bank", "ICICI Bank"]
DRIVER_YEARS = (2022, 2025)

# Text definitions for all pages
PAGE_TEXTS = {
    "page1": (
        "HHI measures app-level concentration (PhonePe and Google Pay as apps), "
        "not bank or PSP-licence level. Bands use DOJ/FTC thresholds (1,500 / 2,500). "
        "2026-03 is missing at source."
    ),
    "page2": (
        "P2M share first reached 50% or more in Aug 2022 (50.01%). Annual growth P2P/P2M "
        "was 28.1%/93.0% in 2023, 31.0%/57.6% in 2024 and 29.5%/34.5% in 2025. "
        "By Mar-26, monthly YoY is 23.69% vs 23.73%. P2M share peaked at 63.66% in Jun-25 "
        "and has plateaued near 62.6%, below the peak (not recovered)."
    ),
    "page3": (
        "Decline is business-side (bank or account rejections), not technical, and the chart "
        "averages payer and payee. The payer-side weighted decline is concentrated in Yes Bank, "
        "Axis and ICICI, PhonePe’s banking partners. This is correlational, since the data has "
        "no per-app-per-bank attribution. Missing source months: payee 2022-12, payer 2026-04."
    ),
    "page4_compounding": (
        "Payee: Yes Bank’s approval fell 9.02 pts while its volume share rose from 38.77% to 53.32%. "
        "Payer: Axis Bank’s approval fell 5.4 pts while its share rose from 16.36% to 35.26%. "
        "Yes Bank’s payer share fell, from 36.62% to 29.28%."
    ),
    "page4_footnote": (
        "Series are capped at the earliest common month across the tables, and gaps are not "
        "interpolated (missing: stg_upi_apps 2026-03, payee 2022-12, payer 2026-04). "
        "The partner gap is correlational. The 15 Oct 2026 UPI MDR postdates this data."
    )
}

# ═════════════════════════════════════════════════════════════
# PART 1 — DATA TRANSFORMATION & CSV EXPORT
# ═════════════════════════════════════════════════════════════

def month_date(df):
    return pd.to_datetime(pd.DataFrame({"year": df["year"], "month": df["month"], "day": 1})).dt.strftime("%Y-%m-%d")

def hhi_band(h):
    if h < 1500:
        return "Unconcentrated"
    if h <= 2500:
        return "Moderately Concentrated"
    return "Highly Concentrated"

def export_csvs():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    apps = pd.read_sql(
        "SELECT year, month, app_name, SUM(total_volume_mn) AS vol FROM stg_upi_apps "
        "WHERE app_name != 'Application Name' AND total_volume_mn IS NOT NULL "
        "GROUP BY year, month, app_name", conn)
    p2p = pd.read_sql(
        "SELECT year, month, p2p_volume_mn, p2m_volume_mn, p2p_share_pct, p2m_share_pct FROM stg_p2p_p2m", conn)
    psp = pd.read_sql(
        "SELECT psp_name, psp_type, total_volume_mn AS vol, approved_percent AS appr, "
        "business_decline_percent AS bd, technical_decline_percent AS td, year, month FROM stg_top15_psp", conn)
    conn.close()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = {}

    # Page 1: Concentration
    apps["share"] = apps["vol"] / apps.groupby(["year", "month"])["vol"].transform("sum") * 100
    hhi = apps.assign(sq=apps["share"] ** 2).groupby(["year", "month"], as_index=False)["sq"].sum().rename(columns={"sq": "hhi"})
    hhi["month_date"] = month_date(hhi)
    long_rows = []
    for _, r in hhi.iterrows():
        long_rows += [
            (r["month_date"], "HHI (app-level)", round(r["hhi"], 2)),
            (r["month_date"], "Moderately concentrated floor (1,500)", 1500.0),
            (r["month_date"], "Highly concentrated floor (2,500)", 2500.0),
        ]
    out["tb_hhi_trend"] = pd.DataFrame(long_rows, columns=["month_date", "series", "hhi_value"])

    top5 = apps.groupby("app_name")["vol"].sum().nlargest(5).index.tolist()
    apps["app_group"] = np.where(apps["app_name"].isin(top5), apps["app_name"], "All other apps")
    shares = apps.groupby(["year", "month", "app_group"], as_index=False)["share"].sum()
    shares["month_date"] = month_date(shares)
    out["tb_app_shares"] = shares.rename(columns={"share": "market_share_pct"})[["month_date", "app_group", "market_share_pct"]].round(4)

    idx = apps.groupby(["year", "month"])["share"].idxmax()
    leader = apps.loc[idx, ["year", "month", "app_name", "share"]].rename(columns={"app_name": "leader_name", "share": "leader_share_pct"})
    leader["month_date"] = month_date(leader)
    out["tb_leader"] = leader[["month_date", "leader_name", "leader_share_pct"]].round(4)

    last = hhi.sort_values(["year", "month"]).iloc[-1]
    lead_last = leader[(leader["year"] == last["year"]) & (leader["month"] == last["month"])].iloc[0]
    out["tb_snapshot"] = pd.DataFrame([{
        "as_of": f"{int(last['year'])}-{int(last['month']):02d}",
        "latest_hhi": round(last["hhi"], 2),
        "hhi_band": hhi_band(last["hhi"]),
        "leader_name": lead_last["leader_name"],
        "leader_share_pct": round(lead_last["leader_share_pct"], 2),
    }])

    # Page 2: P2P vs P2M
    p2p = p2p.sort_values(["year", "month"]).copy()
    prev = p2p[["year", "month", "p2p_volume_mn", "p2m_volume_mn"]].copy()
    prev["year"] += 1
    p2p = p2p.merge(prev, on=["year", "month"], how="left", suffixes=("", "_prev"))
    rows = []
    for rail, share, vol in (("P2P", "p2p_share_pct", "p2p_volume_mn"), ("P2M", "p2m_share_pct", "p2m_volume_mn")):
        d = pd.DataFrame({
            "month_date": month_date(p2p),
            "rail": rail,
            "share_pct": p2p[share],
            "yoy_pct": (p2p[vol] / p2p[vol + "_prev"] - 1) * 100,
            "volume_mn": p2p[vol],
        })
        rows.append(d)
    out["tb_p2p_p2m_long"] = pd.concat(rows, ignore_index=True).round(4)

    # Page 3: PSP reliability
    for c in ("appr", "bd", "td"):
        psp["w_" + c] = psp[c] * psp["vol"]
    m = psp.groupby(["year", "month", "psp_type"], as_index=False).agg(
        vol=("vol", "sum"), w_appr=("w_appr", "sum"), w_bd=("w_bd", "sum"), w_td=("w_td", "sum"), approved_simple=("appr", "mean"))
    m["approved_weighted"] = m["w_appr"] / m["vol"]
    m["weighted_minus_simple"] = m["approved_weighted"] - m["approved_simple"]
    m["month_date"] = month_date(m)
    out["tb_psp_monthly"] = m[["month_date", "psp_type", "approved_weighted", "approved_simple", "weighted_minus_simple"]].round(4)

    mix = []
    for comp, col in (("Business decline", "w_bd"), ("Technical decline", "w_td")):
        mix.append(pd.DataFrame({
            "month_date": m["month_date"],
            "psp_type": m["psp_type"],
            "component": comp,
            "pct_weighted": m[col] / m["vol"]
        }))
    out["tb_psp_mix"] = pd.concat(mix, ignore_index=True).round(4)

    psp["ym"] = psp["year"] * 100 + psp["month"]
    avail = psp.groupby("psp_type")["ym"].nunique()
    per = psp.groupby(["psp_type", "psp_name"], as_index=False).agg(
        months_present=("ym", "nunique"), avg_approved=("appr", "mean"), total_volume_mn=("vol", "sum"))
    per = per[per["months_present"] == per["psp_type"].map(avail)]
    per = per.sort_values("avg_approved", ascending=False)
    out["tb_psp_persistent"] = per.round(4)

    y0, y1 = DRIVER_YEARS
    yr = psp[psp["year"].isin(DRIVER_YEARS)].groupby(["psp_type", "psp_name", "year"], as_index=False).agg(
        vol=("vol", "sum"), w_appr=("w_appr", "sum"))
    yr["approved"] = yr["w_appr"] / yr["vol"]
    yr["share"] = yr["vol"] / yr.groupby(["psp_type", "year"])["vol"].transform("sum") * 100
    a = yr.pivot_table(index=["psp_type", "psp_name"], columns="year", values=["approved", "share"])
    a.columns = [f"{v}_{y}" for v, y in a.columns]
    a = a.dropna().reset_index()
    drv = pd.DataFrame({
        "psp_type": a["psp_type"], "psp_name": a["psp_name"],
        "approved_2022": a[f"approved_{y0}"], "approved_2025": a[f"approved_{y1}"],
        "delta_pts": a[f"approved_{y1}"] - a[f"approved_{y0}"],
        "share_2022_pct": a[f"share_{y0}"], "share_2025_pct": a[f"share_{y1}"],
        "phonepe_partner": np.where(a["psp_name"].isin(PARTNERS), "PhonePe partner bank", "Other PSP"),
    }).sort_values("delta_pts", ascending=False)
    out["tb_decline_drivers"] = drv.round(4)

    # Page 4: Cross-cutting
    gap = psp.assign(is_partner=psp["psp_name"].isin(PARTNERS)).groupby(
        ["year", "month", "psp_type", "is_partner"])["appr"].mean().unstack("is_partner")
    for col in (True, False):
        if col not in gap.columns:
            gap[col] = np.nan
    gap = gap.rename(columns={True: "partner_approved", False: "rest_approved"}).reset_index()
    gap["gap_pts"] = gap["partner_approved"] - gap["rest_approved"]
    gap["month_date"] = month_date(gap)
    out["tb_partner_gap"] = gap[["month_date", "psp_type", "partner_approved", "rest_approved", "gap_pts"]].round(4)

    cutoff = min(p2p.eval("year*100+month").max(), (apps["year"] * 100 + apps["month"]).max(), psp["ym"].max())
    cal = pd.DataFrame([(y, mo) for y in range(2022, cutoff // 100 + 1) for mo in range(1, 13) if y * 100 + mo <= cutoff],
                       columns=["year", "month"])
    cal = cal.merge(hhi[["year", "month", "hhi"]], how="left", on=["year", "month"])
    cal = cal.merge(p2p[p2p["year"].notna()][["year", "month", "p2m_share_pct"]], how="left", on=["year", "month"])
    cal["month_date"] = month_date(cal)
    out["tb_cross_timeline"] = cal[["month_date", "hhi", "p2m_share_pct"]].round(4)

    for name, df in out.items():
        df.to_csv(DATA_DIR / f"{name}.csv", index=False)
        print(f"  wrote {name}.csv ({len(df)} rows)")

# ═════════════════════════════════════════════════════════════
# PART 2 — POWER BI PROJECT (.PBIP) GENERATOR
# ═════════════════════════════════════════════════════════════

DS_SCHEMA = {
    "tb_hhi_trend": [("month_date", "date"), ("series", "string"), ("hhi_value", "real")],
    "tb_app_shares": [("month_date", "date"), ("app_group", "string"), ("market_share_pct", "real")],
    "tb_leader": [("month_date", "date"), ("leader_name", "string"), ("leader_share_pct", "real")],
    "tb_snapshot": [("as_of", "string"), ("latest_hhi", "real"), ("hhi_band", "string"), ("leader_name", "string"), ("leader_share_pct", "real")],
    "tb_p2p_p2m_long": [("month_date", "date"), ("rail", "string"), ("share_pct", "real"), ("yoy_pct", "real"), ("volume_mn", "real")],
    "tb_psp_monthly": [("month_date", "date"), ("psp_type", "string"), ("approved_weighted", "real"), ("approved_simple", "real"), ("weighted_minus_simple", "real")],
    "tb_psp_mix": [("month_date", "date"), ("psp_type", "string"), ("component", "string"), ("pct_weighted", "real")],
    "tb_psp_persistent": [("psp_type", "string"), ("psp_name", "string"), ("months_present", "integer"), ("avg_approved", "real"), ("total_volume_mn", "real")],
    "tb_decline_drivers": [("psp_type", "string"), ("psp_name", "string"), ("approved_2022", "real"), ("approved_2025", "real"), ("delta_pts", "real"),
                           ("share_2022_pct", "real"), ("share_2025_pct", "real"), ("phonepe_partner", "string")],
    "tb_cross_timeline": [("month_date", "date"), ("hhi", "real"), ("p2m_share_pct", "real")],
    "tb_partner_gap": [("month_date", "date"), ("psp_type", "string"), ("partner_approved", "real"), ("rest_approved", "real"), ("gap_pts", "real")],
}

TYPE_MAP_BIM = {"date": "dateTime", "string": "string", "real": "double", "integer": "int64"}
TYPE_MAP_M = {"date": "type date", "string": "type text", "real": "type number", "integer": "Int64.Type"}

def _make_container(x, y, w, h, visual_type, projections, select_items, title=None, extra_vc_objects=None, order_by=None):
    config = {
        "name": f"vis_{x}_{y}",
        "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": w, "height": h}}],
        "singleVisual": {
            "visualType": visual_type,
            "projections": projections,
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": "t", "Entity": select_items[0]["table"], "Type": 0}],
                "Select": [item["select"] for item in select_items]
            },
            "vcObjects": {}
        }
    }
    if order_by:
        config["singleVisual"]["prototypeQuery"]["OrderBy"] = order_by

    if title:
        config["singleVisual"]["vcObjects"]["title"] = [{
            "properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": f"'{title}'"}}}
            }
        }]
    if extra_vc_objects:
        config["singleVisual"]["vcObjects"].update(extra_vc_objects)

    return {
        "x": x, "y": y, "z": 0, "width": w, "height": h,
        "config": json.dumps(config)
    }

def make_card(table, col, is_numeric, x, y, w, h, display_title):
    func = 0 if is_numeric else 3
    agg_name = "Sum" if is_numeric else "Min"
    q_ref = f"{agg_name}({table}.{col})"

    select_item = {
        "table": table,
        "select": {
            "Aggregation": {
                "Expression": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": col}},
                "Function": func
            },
            "Name": q_ref
        }
    }
    extra = {
        "categoryAxis": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}],
        "labels": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}],
        "categoryLabels": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}]
    }
    return _make_container(
        x, y, w, h, "card",
        projections={"Values": [{"queryRef": q_ref, "displayName": display_title}]},
        select_items=[select_item],
        title=display_title,
        extra_vc_objects=extra
    )

def make_line_chart(table, x_col, y_col, series_col, x, y, w, h, title):
    y_ref = f"Sum({table}.{y_col})"
    x_ref = f"{table}.{x_col}"
    select_items = [
        {"table": table, "select": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": x_col}, "Name": x_ref}},
        {"table": table, "select": {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": y_col}}, "Function": 0}, "Name": y_ref}}
    ]
    projections = {"Category": [{"queryRef": x_ref}], "Y": [{"queryRef": y_ref}]}

    if series_col:
        s_ref = f"{table}.{series_col}"
        select_items.append({"table": table, "select": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": series_col}, "Name": s_ref}})
        projections["Series"] = [{"queryRef": s_ref}]

    return _make_container(x, y, w, h, "lineChart", projections, select_items, title=title)

def make_stacked_area_chart(table, x_col, y_col, series_col, x, y, w, h, title):
    y_ref = f"Sum({table}.{y_col})"
    x_ref = f"{table}.{x_col}"
    s_ref = f"{table}.{series_col}"
    select_items = [
        {"table": table, "select": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": x_col}, "Name": x_ref}},
        {"table": table, "select": {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": y_col}}, "Function": 0}, "Name": y_ref}},
        {"table": table, "select": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": series_col}, "Name": s_ref}}
    ]
    projections = {"Category": [{"queryRef": x_ref}], "Y": [{"queryRef": y_ref}], "Series": [{"queryRef": s_ref}]}
    return _make_container(x, y, w, h, "stackedAreaChart", projections, select_items, title=title)

def make_mix_chart(table, x_col, y_col, series_col, x, y, w, h, title):
    y_ref = f"Avg({table}.{y_col})"
    x_ref = f"{table}.{x_col}"
    s_ref = f"{table}.{series_col}"
    select_items = [
        {"table": table, "select": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": x_col}, "Name": x_ref}},
        {"table": table, "select": {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": y_col}}, "Function": 1}, "Name": y_ref}},
        {"table": table, "select": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": series_col}, "Name": s_ref}}
    ]
    projections = {"Category": [{"queryRef": x_ref}], "Y": [{"queryRef": y_ref}], "Series": [{"queryRef": s_ref}]}
    return _make_container(x, y, w, h, "lineChart", projections, select_items, title=title)

def make_bar_chart(table, cat_col, val_col, series_col, x, y, w, h, title):
    val_ref = f"Sum({table}.{val_col})"
    cat_ref = f"{table}.{cat_col}"
    s_ref = f"{table}.{series_col}"
    select_items = [
        {"table": table, "select": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": cat_col}, "Name": cat_ref}},
        {"table": table, "select": {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": val_col}}, "Function": 0}, "Name": val_ref}},
        {"table": table, "select": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": series_col}, "Name": s_ref}}
    ]
    projections = {"Category": [{"queryRef": cat_ref}], "Y": [{"queryRef": val_ref}], "Series": [{"queryRef": s_ref}]}
    return _make_container(x, y, w, h, "clusteredBarChart", projections, select_items, title=title)

def make_table(table, cols, x, y, w, h, title, sort_col=None):
    select_items = [
        {"table": table, "select": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": c}, "Name": f"{table}.{c}"}}
        for c in cols
    ]
    order_by = None
    if sort_col:
        order_by = [{
            "Direction": 2,
            "Expression": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": sort_col}}
        }]
    return _make_container(
        x, y, w, h, "tableEx",
        projections={"Values": [{"queryRef": f"{table}.{c}"} for c in cols]},
        select_items=select_items,
        title=title,
        order_by=order_by
    )

def make_textbox(text, x, y, w, h, font_size="9pt", is_callout=False):
    paragraphs = []
    for line in text.strip().split("\n"):
        if line.strip():
            paragraphs.append({
                "textRuns": [{
                    "value": line.strip(),
                    "textStyle": {
                        "fontSize": font_size,
                        "fontFamily": "Segoe UI",
                        "color": {"solid": {"color": "#1A202C" if is_callout else "#4A5568"}}
                    }
                }]
            })
    config = {
        "name": f"tb_{x}_{y}",
        "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": w, "height": h}}],
        "singleVisual": {
            "visualType": "textbox",
            "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]}
        }
    }
    return {"x": x, "y": y, "z": 0, "width": w, "height": h, "config": json.dumps(config)}

def generate_sections():
    return [
        {
            "name": "Page1",
            "displayName": "1 Market Concentration",
            "width": 1280,
            "height": 720,
            "visualContainers": [
                make_card("tb_snapshot", "as_of", False, 20, 15, 220, 85, "As Of"),
                make_card("tb_snapshot", "latest_hhi", True, 260, 15, 240, 85, "Latest HHI"),
                make_card("tb_snapshot", "hhi_band", False, 520, 15, 240, 85, "Concentration Band"),
                make_card("tb_snapshot", "leader_name", False, 780, 15, 240, 85, "Market Leader"),
                make_card("tb_snapshot", "leader_share_pct", True, 1040, 15, 220, 85, "Leader Share %"),
                make_line_chart("tb_hhi_trend", "month_date", "hhi_value", "series", 20, 115, 610, 520, "HHI Trend & DOJ Thresholds"),
                make_stacked_area_chart("tb_app_shares", "month_date", "market_share_pct", "app_group", 650, 115, 610, 520, "Top 5 App Market Share (%)"),
                make_textbox(PAGE_TEXTS["page1"], 20, 645, 1240, 60)
            ]
        },
        {
            "name": "Page2",
            "displayName": "2 P2P vs P2M",
            "width": 1280,
            "height": 720,
            "visualContainers": [
                make_line_chart("tb_p2p_p2m_long", "month_date", "share_pct", "rail", 20, 15, 610, 305, "Volume Share % (P2P vs P2M)"),
                make_line_chart("tb_p2p_p2m_long", "month_date", "volume_mn", "rail", 650, 15, 610, 305, "Total Volume (Mn)"),
                make_line_chart("tb_p2p_p2m_long", "month_date", "yoy_pct", "rail", 20, 330, 1240, 290, "YoY Growth Rate (%) by Rail"),
                make_textbox(PAGE_TEXTS["page2"], 20, 630, 1240, 75)
            ]
        },
        {
            "name": "Page3",
            "displayName": "3 PSP Reliability",
            "width": 1280,
            "height": 720,
            "visualContainers": [
                make_line_chart("tb_psp_monthly", "month_date", "approved_weighted", "psp_type", 20, 15, 610, 305, "Weighted Approval Rate (%) by Type"),
                make_mix_chart("tb_psp_mix", "month_date", "pct_weighted", "component", 650, 15, 610, 305, "Decline Reason Breakdown (%) — Payer & Payee Average"),
                make_table("tb_psp_persistent", ["psp_name", "psp_type", "months_present", "avg_approved", "total_volume_mn"], 20, 330, 610, 295, "Persistent PSP Stability (Sorted by Avg Approved)", sort_col="avg_approved"),
                make_bar_chart("tb_decline_drivers", "psp_name", "delta_pts", "phonepe_partner", 650, 330, 610, 295, "2022 vs 2025 Delta Points by PSP (PhonePe Partner Breakdown)"),
                make_textbox(PAGE_TEXTS["page3"], 20, 635, 1240, 70)
            ]
        },
        {
            "name": "Page4",
            "displayName": "4 Cross-Cutting Narrative",
            "width": 1280,
            "height": 900,  # Custom canvas height
            "visualContainers": [
                # 3 Timelines (each h=120)
                make_line_chart("tb_cross_timeline", "month_date", "hhi", None, 20, 15, 1240, 120, "1. HHI Index (Ecosystem Concentration)"),
                make_line_chart("tb_cross_timeline", "month_date", "p2m_share_pct", None, 20, 150, 1240, 120, "2. P2M Volume Share (%)"),
                make_line_chart("tb_psp_monthly", "month_date", "approved_weighted", "psp_type", 20, 285, 1240, 120, "3. Weighted Approval Rate (%) — Payer vs Payee Direct Comparison"),
                # Gap Chart below timelines with 20px buffer (y=425, h=225)
                make_line_chart("tb_partner_gap", "month_date", "gap_pts", "psp_type", 20, 425, 1240, 225, "Partner Bank Approval Gap (pts) — Payer-side evidence only (payee turns positive in 2026)"),
                # Compounding Callout Textbox from DECISIONS.md
                make_textbox(PAGE_TEXTS["page4_compounding"], 20, 665, 1240, 75, font_size="9.5pt", is_callout=True),
                # Methodology Footnote Textbox
                make_textbox(PAGE_TEXTS["page4_footnote"], 20, 755, 1240, 125, font_size="9pt")
            ]
        }
    ]

def build_pbip(out_dir: Path, data_dir: Path):
    proj_name = "UPI_Analytics"
    rep_dir = out_dir / f"{proj_name}.Report"
    sem_dir = out_dir / f"{proj_name}.SemanticModel"
    rep_dir.mkdir(parents=True, exist_ok=True)
    sem_dir.mkdir(parents=True, exist_ok=True)

    pbip_json = {"version": "1.0", "artifacts": [{"report": {"path": f"{proj_name}.Report"}}]}
    (out_dir / f"{proj_name}.pbip").write_text(json.dumps(pbip_json, indent=2), encoding="utf-8")

    pbir_json = {
        "version": "1.0",
        "datasetReference": {"byPath": {"path": f"../{proj_name}.SemanticModel"}, "byConnection": None}
    }
    (rep_dir / "definition.pbir").write_text(json.dumps(pbir_json, indent=2), encoding="utf-8")

    report_json = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/reportVersion/1.1.0/schema.json",
        "themeCollection": {"baseTheme": {"name": "CY24SU02", "version": "5.56", "type": 2}},
        "sections": generate_sections()
    }
    (rep_dir / "report.json").write_text(json.dumps(report_json, indent=2), encoding="utf-8")

    (sem_dir / "definition.pbism").write_text(json.dumps({"version": "1.0"}, indent=2), encoding="utf-8")

    tables = []
    for tbl_name, cols in DS_SCHEMA.items():
        csv_file_path = str((data_dir / f"{tbl_name}.csv").resolve()).replace("\\", "/")
        type_transform_list = ", ".join([f'{{"{c}", {TYPE_MAP_M[t]}}}' for c, t in cols])
        
        m_expression = [
            "let",
            f'    Source = Csv.Document(File.Contents("{csv_file_path}"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.None]),',
            '    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
            f'    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers", {{{type_transform_list}}})',
            "in",
            '    #"Changed Type"'
        ]

        table_cols = []
        for c, t in cols:
            col_def = {
                "name": c,
                "dataType": TYPE_MAP_BIM[t],
                "sourceColumn": c,
                "summarizeBy": "none" if t in ("string", "date") else "sum"
            }
            if t == "date":
                col_def["formatString"] = "yyyy-mm-dd"
            table_cols.append(col_def)

        tables.append({
            "name": tbl_name,
            "columns": table_cols,
            "partitions": [{
                "name": tbl_name,
                "mode": "import",
                "source": {"type": "m", "expression": m_expression}
            }]
        })

    model_bim = {
        "compatibilityLevel": 1600,
        "model": {
            "culture": "en-US",
            "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "sourceQueryCulture": "en-US",
            "tables": tables
        }
    }
    (sem_dir / "model.bim").write_text(json.dumps(model_bim, indent=2), encoding="utf-8")
    print(f"Generated Power BI Project: {(out_dir / f'{proj_name}.pbip').resolve()}")


if __name__ == "__main__":
    if not DB_PATH.exists():
        sys.exit(f"ERROR: database not found at {DB_PATH.resolve()}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Exporting CSVs...")
    export_csvs()
    print("Building Power BI project...")
    build_pbip(OUT_DIR, DATA_DIR)