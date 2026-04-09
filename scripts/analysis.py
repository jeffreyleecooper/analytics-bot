"""Q1 2026 vs trailing 7 quarters — systematic 8-quarter trend analysis.

Methodology:
- Revenue/booked metrics bucketed by `contracted_on`, BOTH inbound and repeat.
- Funnel metrics bucketed by `created_at`, INBOUND only.
- 8 quarters: Q2 2024 .. Q1 2026.
"""
from __future__ import annotations

import pandas as pd

from scripts.run_query import run_query

TABLE = "`all-american-entertainment.one_off_opps_review.1_mega_opps_live`"

# 8 quarters in chronological order (oldest -> newest)
PERIODS: list[tuple[str, str, str]] = [
    ("Q2_2024", "2024-04-01", "2024-07-01"),
    ("Q3_2024", "2024-07-01", "2024-10-01"),
    ("Q4_2024", "2024-10-01", "2025-01-01"),
    ("Q1_2025", "2025-01-01", "2025-04-01"),
    ("Q2_2025", "2025-04-01", "2025-07-01"),
    ("Q3_2025", "2025-07-01", "2025-10-01"),
    ("Q4_2025", "2025-10-01", "2026-01-01"),
    ("Q1_2026", "2026-01-01", "2026-04-01"),
]
PERIOD_NAMES = [p[0] for p in PERIODS]
CURRENT = "Q1_2026"
PRIOR_Q = "Q4_2025"
PRIOR_Y = "Q1_2025"
TRAILING_7 = [p for p in PERIOD_NAMES if p != CURRENT]


def period_case(date_col: str) -> str:
    parts = [
        f"WHEN {date_col} >= DATETIME('{s}') AND {date_col} < DATETIME('{e}') THEN '{n}'"
        for n, s, e in PERIODS
    ]
    return "CASE " + " ".join(parts) + " ELSE NULL END"


# ---------- Revenue side: bucket by contracted_on, ALL sources ---------- #

REVENUE_BASE = f"""
WITH base AS (
  SELECT
    contracted_on,
    LOWER(IFNULL(lead_source, 'unknown'))   AS lead_source,
    COALESCE(lead_origin, 'Unknown')        AS lead_origin,
    COALESCE(sales_agent, 'Unknown')        AS sales_agent,
    COALESCE(std_budget, 'Unknown')         AS std_budget,
    COALESCE(ad_presence, 'Unknown')        AS ad_presence,
    IFNULL(SAFE_CAST(booked   AS NUMERIC), 0)       AS booked,
    IFNULL(SAFE_CAST(commission_fee AS NUMERIC), 0) AS commission_fee,
    IFNULL(SAFE_CAST(gross_fee AS NUMERIC), 0)      AS gross_fee
  FROM {TABLE}
  WHERE contracted_on IS NOT NULL
)
"""


def q_rev_overall() -> pd.DataFrame:
    sql = f"""
    {REVENUE_BASE}
    SELECT
      {period_case('contracted_on')} AS period,
      lead_source,
      SUM(booked) AS booked,
      SUM(commission_fee) AS commission_fee,
      SUM(gross_fee) AS gross_fee
    FROM base
    WHERE {period_case('contracted_on')} IS NOT NULL
    GROUP BY period, lead_source
    """
    return run_query(sql)


def q_rev_dim(dim: str, source_filter: str | None = None) -> pd.DataFrame:
    where = f"AND lead_source = '{source_filter}'" if source_filter else ""
    sql = f"""
    {REVENUE_BASE}
    SELECT
      {period_case('contracted_on')} AS period,
      {dim} AS {dim},
      SUM(booked) AS booked,
      SUM(commission_fee) AS commission_fee,
      SUM(gross_fee) AS gross_fee
    FROM base
    WHERE {period_case('contracted_on')} IS NOT NULL
      {where}
    GROUP BY period, {dim}
    """
    return run_query(sql)


def q_rev_agent_x_source() -> pd.DataFrame:
    sql = f"""
    {REVENUE_BASE}
    SELECT
      {period_case('contracted_on')} AS period,
      sales_agent,
      lead_source,
      SUM(booked) AS booked,
      SUM(commission_fee) AS commission_fee,
      SUM(gross_fee) AS gross_fee
    FROM base
    WHERE {period_case('contracted_on')} IS NOT NULL
    GROUP BY period, sales_agent, lead_source
    """
    return run_query(sql)


def q_rev_origin_x_budget() -> pd.DataFrame:
    sql = f"""
    {REVENUE_BASE}
    SELECT
      {period_case('contracted_on')} AS period,
      lead_origin,
      std_budget,
      SUM(booked) AS booked,
      SUM(commission_fee) AS commission_fee,
      SUM(gross_fee) AS gross_fee
    FROM base
    WHERE {period_case('contracted_on')} IS NOT NULL
      AND lead_source = 'inbound'
    GROUP BY period, lead_origin, std_budget
    """
    return run_query(sql)


# ---------- Funnel side: bucket by created_at, INBOUND only ---------- #

FUNNEL_BASE = f"""
WITH base AS (
  SELECT
    created_at,
    COALESCE(lead_origin, 'Unknown') AS lead_origin,
    COALESCE(std_budget, 'Unknown')  AS std_budget,
    COALESCE(ad_presence, 'Unknown') AS ad_presence,
    CASE WHEN LOWER(IFNULL(lead_status,'')) IN ('doa','spam') THEN 0 ELSE 1 END AS qualified_lead,
    CASE WHEN LOWER(IFNULL(sales_status,'')) = 'open' THEN 1 ELSE 0 END         AS open_lead,
    IFNULL(SAFE_CAST(assigned AS NUMERIC), 0) AS assigned
  FROM {TABLE}
  WHERE LOWER(IFNULL(lead_source,'')) = 'inbound'
)
"""


def q_funnel_overall() -> pd.DataFrame:
    sql = f"""
    {FUNNEL_BASE}
    SELECT
      {period_case('created_at')} AS period,
      SUM(qualified_lead) AS leads,
      SUM(open_lead)      AS open_leads,
      SUM(assigned)       AS assigned
    FROM base
    WHERE {period_case('created_at')} IS NOT NULL
    GROUP BY period
    """
    return run_query(sql)


def q_funnel_dim(dim: str) -> pd.DataFrame:
    sql = f"""
    {FUNNEL_BASE}
    SELECT
      {period_case('created_at')} AS period,
      {dim} AS {dim},
      SUM(qualified_lead) AS leads,
      SUM(open_lead)      AS open_leads,
      SUM(assigned)       AS assigned
    FROM base
    WHERE {period_case('created_at')} IS NOT NULL
    GROUP BY period, {dim}
    """
    return run_query(sql)


# ---------- Helpers ---------- #

def pivot_periods(df: pd.DataFrame, dim: str, value: str) -> pd.DataFrame:
    """Pivot to wide format with one column per quarter, ordered chronologically."""
    df = df.copy()
    df[value] = pd.to_numeric(df[value], errors="coerce").astype(float)
    p = df.pivot_table(index=dim, columns="period", values=value, aggfunc="sum").fillna(0.0)
    # Ensure all 8 columns present and in order
    for c in PERIOD_NAMES:
        if c not in p.columns:
            p[c] = 0
    p = p[PERIOD_NAMES]
    return p


def add_change_cols(p: pd.DataFrame) -> pd.DataFrame:
    """Add comparison vs Q4_2025 (QoQ), Q1_2025 (YoY), and trailing-7-avg."""
    out = p.copy()
    out["QoQ_abs"] = out[CURRENT] - out[PRIOR_Q]
    out["QoQ_pct"] = (out[CURRENT] - out[PRIOR_Q]) / out[PRIOR_Q].replace(0, pd.NA) * 100
    out["YoY_abs"] = out[CURRENT] - out[PRIOR_Y]
    out["YoY_pct"] = (out[CURRENT] - out[PRIOR_Y]) / out[PRIOR_Y].replace(0, pd.NA) * 100
    out["T7_avg"] = out[TRAILING_7].mean(axis=1)
    out["vs_T7_pct"] = (out[CURRENT] - out["T7_avg"]) / out["T7_avg"].replace(0, pd.NA) * 100
    return out


def fmt(df: pd.DataFrame) -> str:
    with pd.option_context(
        "display.max_rows", None, "display.max_columns", None,
        "display.width", 260, "display.float_format", lambda x: f"{x:,.0f}",
    ):
        return df.to_string()


def banner(s: str) -> None:
    print()
    print("=" * 100)
    print(s)
    print("=" * 100)


def main() -> None:
    out_prefix = "outputs/q1_2026_8q"

    # ---------- Overall revenue trend ---------- #
    banner("REVENUE OVERALL — 8 quarters by lead_source")
    rev = q_rev_overall()
    rev.to_csv(f"{out_prefix}_revenue_by_source.csv", index=False)
    for metric in ["booked", "commission_fee", "gross_fee"]:
        print(f"\n-- {metric} --")
        p = pivot_periods(rev, "lead_source", metric)
        print(fmt(p))
        # totals row
        tot = p.sum(axis=0).to_frame().T
        tot.index = ["TOTAL"]
        print(fmt(add_change_cols(tot)))

    # Save totals separately
    rev_num = rev.copy()
    for c in ["booked", "commission_fee", "gross_fee"]:
        rev_num[c] = pd.to_numeric(rev_num[c], errors="coerce").astype(float)
    totals = (
        rev_num.groupby("period")[["booked", "commission_fee", "gross_fee"]].sum()
        .reindex(PERIOD_NAMES).fillna(0.0)
    )
    totals.to_csv(f"{out_prefix}_totals.csv")
    banner("TOTALS BY QUARTER (both sources)")
    print(fmt(totals))
    print("\nDeal-size derivatives:")
    der = pd.DataFrame({
        "avg_gross_per_booking": totals["gross_fee"] / totals["booked"].replace(0, pd.NA),
        "avg_comm_per_booking":  totals["commission_fee"] / totals["booked"].replace(0, pd.NA),
        "comm_take_rate_pct":    totals["commission_fee"] / totals["gross_fee"].replace(0, pd.NA) * 100,
    })
    print(fmt(der))
    der.to_csv(f"{out_prefix}_deal_size.csv")

    # ---------- Sales agents ---------- #
    for src in [None, "inbound", "repeat"]:
        label = "all" if src is None else src
        banner(f"SALES AGENT — {label.upper()} — commission_fee 8q")
        d = q_rev_dim("sales_agent", src)
        d.to_csv(f"{out_prefix}_agent_{label}.csv", index=False)
        for metric in ["commission_fee", "booked", "gross_fee"]:
            print(f"\n-- {metric} --")
            piv = add_change_cols(pivot_periods(d, "sales_agent", metric))
            piv = piv.sort_values(CURRENT, ascending=False).head(15)
            print(fmt(piv))

    # Agent x source pivot
    banner("AGENT × SOURCE — commission, Q1 2025 vs Q1 2026 vs T7 avg")
    ax = q_rev_agent_x_source()
    ax.to_csv(f"{out_prefix}_agent_x_source.csv", index=False)

    # ---------- Lead origin ---------- #
    banner("LEAD ORIGIN — INBOUND — 8q")
    d = q_rev_dim("lead_origin", "inbound")
    d.to_csv(f"{out_prefix}_origin_inbound.csv", index=False)
    for metric in ["commission_fee", "booked", "gross_fee"]:
        print(f"\n-- {metric} --")
        piv = add_change_cols(pivot_periods(d, "lead_origin", metric))
        piv = piv.sort_values(CURRENT, ascending=False).head(10)
        print(fmt(piv))

    # ---------- Budget tier ---------- #
    banner("STD_BUDGET — INBOUND — 8q")
    d = q_rev_dim("std_budget", "inbound")
    d.to_csv(f"{out_prefix}_budget_inbound.csv", index=False)
    for metric in ["commission_fee", "booked", "gross_fee"]:
        print(f"\n-- {metric} --")
        piv = add_change_cols(pivot_periods(d, "std_budget", metric))
        print(fmt(piv.sort_values(CURRENT, ascending=False)))

    # ---------- Ad presence ---------- #
    banner("AD_PRESENCE — INBOUND — 8q")
    d = q_rev_dim("ad_presence", "inbound")
    d.to_csv(f"{out_prefix}_ad_inbound.csv", index=False)
    for metric in ["commission_fee", "booked", "gross_fee"]:
        print(f"\n-- {metric} --")
        piv = add_change_cols(pivot_periods(d, "ad_presence", metric))
        print(fmt(piv))

    # ---------- Origin × budget combo ---------- #
    banner("ORIGIN × BUDGET — INBOUND — top combos by Q1 2026 commission")
    ob = q_rev_origin_x_budget()
    ob.to_csv(f"{out_prefix}_origin_x_budget_inbound.csv", index=False)
    ob["combo"] = ob["lead_origin"] + " | " + ob["std_budget"]
    piv = add_change_cols(pivot_periods(ob, "combo", "commission_fee"))
    print(fmt(piv.sort_values(CURRENT, ascending=False).head(20)))

    # ---------- Funnel ---------- #
    banner("INBOUND FUNNEL OVERALL — 8q")
    f = q_funnel_overall()
    for c in ["leads", "open_leads", "assigned"]:
        f[c] = pd.to_numeric(f[c], errors="coerce").astype(float)
    f = f.set_index("period").reindex(PERIOD_NAMES).fillna(0.0)
    f.to_csv(f"{out_prefix}_funnel_overall.csv")
    f["assigned_rate_pct"] = f["assigned"] / f["leads"].replace(0, pd.NA) * 100
    print(fmt(f))

    banner("FUNNEL — leads by origin (top 10) — 8q")
    d = q_funnel_dim("lead_origin")
    d.to_csv(f"{out_prefix}_funnel_origin.csv", index=False)
    piv = add_change_cols(pivot_periods(d, "lead_origin", "leads"))
    print(fmt(piv.sort_values(CURRENT, ascending=False).head(10)))

    banner("FUNNEL — leads by std_budget — 8q")
    d = q_funnel_dim("std_budget")
    d.to_csv(f"{out_prefix}_funnel_budget.csv", index=False)
    piv = add_change_cols(pivot_periods(d, "std_budget", "leads"))
    print(fmt(piv.sort_values(CURRENT, ascending=False)))


if __name__ == "__main__":
    main()
