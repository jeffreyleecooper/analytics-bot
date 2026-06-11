"""Standard AAE lead / booking / commission analysis — the default for ~all inquiries.

Runs the canonical dimension matrix against `1_mega_opps_live` for one or more date
windows and returns **tables only** (no narrative). Honors the project analysis
defaults: revenue by `contracted_on` (both sources), funnel by `created_at` (inbound
only), new `workable_leads` taxonomy. See notes/LEAD_ANALYSIS.MD.

Dimension matrix
----------------
Revenue view  (metrics: booked, commission_fee, gross_fee, avg_commission/booking)
  rev_source  — by lead_source (inbound vs repeat) + TOTAL
  rev_agent   — by sales_agent (both sources) + TOTAL
  rev_agent_source — by sales_agent x lead_source (both sources) + TOTAL
  rev_origin  — inbound by lead_origin + TOTAL
  rev_origin_ad — inbound by lead_origin x ad_presence (website x ad/non-ad) + TOTAL
  rev_ad      — inbound by ad_presence + TOTAL
  rev_budget  — inbound by std_budget tier (canonical order) + TOTAL

Funnel view  (metrics: total_leads, workable_leads, assigned, qualified_assigned [SQL];
              rates: assigned_rate, qualified_assigned_rate, booking_rate, win_rate)
  fun_total   — inbound, single row
  fun_agent   — inbound by sales_agent
  fun_origin  — inbound by lead_origin
  fun_origin_ad — inbound by lead_origin x ad_presence
  fun_ad      — inbound by ad_presence
  fun_budget  — inbound by std_budget tier (canonical order)

Each table has, per metric, one value column per window (`<metric>__<window>`) plus a
relative-change column of the primary (first) window vs every other window
(`<metric>__vs_<window>`).

Default comparison framing: PoP + YoY. Give `--period START:END` and the report
auto-derives three windows — `current`, `prior` (immediately preceding equal-length
period), and `yoy` (same calendar window a year earlier) — so every table carries
both a `__vs_prior` and a `__vs_yoy` change column. Use `--compare pop|yoy` to keep
only one, or `--window` for full manual control.

CLI — writes every table to outputs/<name>_<table>.csv and a tables-only HTML pack:
    python -m scripts.standard_report --period 2026-04-01:2026-06-30          # Q2: current + PoP + YoY
    python -m scripts.standard_report --period 2026-04-01:2026-06-30 --compare yoy
    python -m scripts.standard_report --window a=2026-04-01:2026-06-30 --window b=2025-04-01:2025-06-30

Importable — embed the same tables in a bespoke raw-HTML report:
    from scripts.standard_report import build, derive_periods
    tables = build(derive_periods("2026-04-01", "2026-06-30"))   # current / prior / yoy
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from typing import NamedTuple

import pandas as pd

from scripts.run_query import run_query
from scripts.report import OUT, write_report, html_table

TBL = "`all-american-entertainment.one_off_opps_review.1_mega_opps_live`"
UNK = "Unknown"
UNASSIGNED = "(unassigned)"

# Canonical std_budget order (low to high); see notes/LEAD_ANALYSIS.MD.
BUDGET_ORDER = [
    "I am looking for Talent to donate their time",
    "$5,000 or less",
    "$5,000 - $10,000",
    "$10,000 - $20,000",
    "$20,000 - $30,000",
    "$30,000 - $50,000",
    "$50,000 - $100,000",
    "$100,000 and above",
    "I have a budget, but I am unsure of what it is",
    UNK,
]


class Window(NamedTuple):
    name: str
    start: str  # 'YYYY-MM-DD'
    end: str    # 'YYYY-MM-DD' inclusive


def parse_window(spec: str) -> Window:
    """Parse a CLI window spec 'name=YYYY-MM-DD:YYYY-MM-DD'."""
    try:
        name, span = spec.split("=", 1)
        start, end = span.split(":", 1)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"bad --window {spec!r}; expected name=YYYY-MM-DD:YYYY-MM-DD"
        )
    return Window(name.strip(), start.strip(), end.strip())


def _shift_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # Feb 29 in a non-leap target year
        return d.replace(year=d.year + years, day=28)


def derive_periods(start: str, end: str, compare: str = "both") -> list[Window]:
    """Build the default analysis windows from a single period.

    Returns `current` (start..end) plus, per `compare`:
      - `prior` (PoP) — the immediately preceding equal-length window, and/or
      - `yoy`        — the same calendar window one year earlier.
    `compare` is one of 'both' (default), 'pop', 'yoy'. `current` is always primary,
    so every table gets a `__vs_prior` and/or `__vs_yoy` change column.
    """
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    if e < s:
        raise ValueError(f"period end {end} precedes start {start}")
    span = (e - s).days  # inclusive length is span + 1 days
    windows = [Window("current", s.isoformat(), e.isoformat())]
    if compare in ("both", "pop"):
        pe = s - timedelta(days=1)
        ps = pe - timedelta(days=span)
        windows.append(Window("prior", ps.isoformat(), pe.isoformat()))
    if compare in ("both", "yoy"):
        windows.append(Window("yoy", _shift_years(s, -1).isoformat(), _shift_years(e, -1).isoformat()))
    return windows


def _window_case(date_col: str, windows: list[Window]) -> str:
    parts = [
        f"WHEN DATE({date_col}) BETWEEN DATE('{w.start}') AND DATE('{w.end}') THEN '{w.name}'"
        for w in windows
    ]
    return "CASE " + " ".join(parts) + " END"


def _window_filter(date_col: str, windows: list[Window]) -> str:
    parts = [f"DATE({date_col}) BETWEEN DATE('{w.start}') AND DATE('{w.end}')" for w in windows]
    return "(" + " OR ".join(parts) + ")"


# ---------- base datasets ----------
def _revenue_df(windows: list[Window]) -> pd.DataFrame:
    sql = f"""
    SELECT
      {_window_case('contracted_on', windows)} AS win_label,
      lead_source,
      COALESCE(sales_agent, '{UNASSIGNED}') AS sales_agent,
      COALESCE(lead_origin, '{UNK}')        AS lead_origin,
      COALESCE(ad_presence, '{UNK}')        AS ad_presence,
      COALESCE(std_budget, '{UNK}')         AS std_budget,
      SUM(COALESCE(booked, 0))         AS booked,
      SUM(COALESCE(commission_fee, 0)) AS commission_fee,
      SUM(COALESCE(gross_fee, 0))      AS gross_fee
    FROM {TBL}
    WHERE contracted_on IS NOT NULL AND {_window_filter('contracted_on', windows)}
    GROUP BY 1, 2, 3, 4, 5, 6
    """
    df = run_query(sql).rename(columns={"win_label": "window"})
    for c in ("booked", "commission_fee", "gross_fee"):
        df[c] = df[c].astype(float)
    return df


def _funnel_df(windows: list[Window]) -> pd.DataFrame:
    sql = f"""
    SELECT
      {_window_case('created_at', windows)} AS win_label,
      lead_source,
      COALESCE(sales_agent, '{UNASSIGNED}') AS sales_agent,
      COALESCE(lead_origin, '{UNK}')        AS lead_origin,
      COALESCE(ad_presence, '{UNK}')        AS ad_presence,
      COALESCE(std_budget, '{UNK}')         AS std_budget,
      COUNT(*) AS total_leads,
      SUM(CASE WHEN LOWER(IFNULL(lead_status,'')) IN ('spam','duplicate') THEN 0
               WHEN LOWER(IFNULL(lead_status,'')) = 'doa'
                    AND (doa_reason IS NULL OR doa_reason IN ('Marketing Request','Not Viable')) THEN 0
               ELSE 1 END) AS workable_leads,
      SUM(COALESCE(assigned, 0)) AS assigned,
      SUM(CASE WHEN proposal_stage_started_at IS NOT NULL
                 OR offer_stage_started_at IS NOT NULL
                 OR COALESCE(booked, 0) = 1 THEN 1 ELSE 0 END) AS qualified_assigned,
      SUM(CASE WHEN LOWER(IFNULL(sales_status,'')) = 'open' THEN 1 ELSE 0 END) AS open_leads,
      SUM(COALESCE(booked, 0)) AS booked
    FROM {TBL}
    WHERE created_at IS NOT NULL AND {_window_filter('created_at', windows)}
    GROUP BY 1, 2, 3, 4, 5, 6
    """
    df = run_query(sql).rename(columns={"win_label": "window"})
    for c in ("total_leads", "workable_leads", "assigned", "qualified_assigned", "open_leads", "booked"):
        df[c] = df[c].astype(float)
    return df


def _open_now_df() -> pd.DataFrame:
    """Point-in-time count of currently-open leads (sales_status='open') per segment.

    No date filter — this is a pipeline snapshot ('what's in flight right now'),
    independent of the comparison windows. Used as booking-count context in the
    revenue tables, where open leads have no contracted_on to bucket by.
    """
    sql = f"""
    SELECT
      lead_source,
      COALESCE(sales_agent, '{UNASSIGNED}') AS sales_agent,
      COALESCE(lead_origin, '{UNK}')        AS lead_origin,
      COALESCE(ad_presence, '{UNK}')        AS ad_presence,
      COALESCE(std_budget, '{UNK}')         AS std_budget,
      COUNT(*) AS open_now
    FROM {TBL}
    WHERE LOWER(IFNULL(sales_status, '')) = 'open'
    GROUP BY 1, 2, 3, 4, 5
    """
    df = run_query(sql)
    df["open_now"] = df["open_now"].astype(float)
    return df


def _attach_open_now(t: pd.DataFrame, groups: list[str], open_df: pd.DataFrame) -> pd.DataFrame:
    """Left-merge the open-now snapshot onto a revenue table by its group column(s).

    The TOTAL row gets the sum of the visible (non-TOTAL) rows so the column foots.
    """
    agg = open_df.groupby(groups, dropna=False)["open_now"].sum().reset_index()
    merged = t.merge(agg, on=groups, how="left")
    merged["open_now"] = merged["open_now"].fillna(0.0)
    is_total = merged[groups[0]] == "TOTAL"
    merged.loc[is_total, "open_now"] = merged.loc[~is_total, "open_now"].sum()
    return merged


# ---------- pivot / decorate ----------
def _pivot(df: pd.DataFrame, group_cols: list[str], metrics: list[str],
           windows: list[Window]) -> pd.DataFrame:
    """Aggregate to group x window and spread each metric to one column per window."""
    g = df.groupby(group_cols + ["window"], dropna=False)[metrics].sum().reset_index()
    p = g.pivot_table(index=group_cols, columns="window", values=metrics, fill_value=0.0)
    rows = []
    for k, row in p.iterrows():
        rec = dict(zip(group_cols, k if isinstance(k, tuple) else (k,)))
        for m in metrics:
            for w in windows:
                rec[f"{m}__{w.name}"] = float(row.get((m, w.name), 0.0))
        rows.append(rec)
    return pd.DataFrame(rows)


def _add_total(df: pd.DataFrame, label_col: str, value_cols: list[str], label="TOTAL") -> pd.DataFrame:
    total = {c: df[c].sum() for c in value_cols}
    total[label_col] = label
    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)


def _safe_div(a: float, b: float) -> float:
    return a / b if b else float("nan")


def _decorate(df: pd.DataFrame, windows: list[Window], base_metrics: list[str],
              ratios: list[tuple[str, str, str]]) -> pd.DataFrame:
    """Add relative-change cols for base metrics and derived ratio cols (+ their change).

    `ratios` is a list of (name, numerator_metric, denominator_metric); the
    denominator may be the special token 'closed_assigned' (= assigned - open_leads).
    Primary window is windows[0]; change is primary vs each other window.
    """
    primary = windows[0].name
    others = [w.name for w in windows[1:]]

    # closed_assigned helper columns (for win_rate)
    if any(den == "closed_assigned" for _, _, den in ratios):
        for w in windows:
            df[f"closed_assigned__{w.name}"] = df[f"assigned__{w.name}"] - df[f"open_leads__{w.name}"]

    for m in base_metrics:
        for w in others:
            df[f"{m}__vs_{w}"] = [
                _safe_div(cur - base, base) * 100
                for cur, base in zip(df[f"{m}__{primary}"], df[f"{m}__{w}"])
            ]

    for name, num, den in ratios:
        for w in [primary, *others]:
            df[f"{name}__{w}"] = [
                _safe_div(n, d) for n, d in zip(df[f"{num}__{w}"], df[f"{den}__{w}"])
            ]
        for w in others:
            df[f"{name}__vs_{w}"] = [
                _safe_div(cur - base, base) * 100
                for cur, base in zip(df[f"{name}__{primary}"], df[f"{name}__{w}"])
            ]
    return df


def _sort_budget(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["std_budget"] = pd.Categorical(df["std_budget"], categories=BUDGET_ORDER, ordered=True)
    return df.sort_values("std_budget").reset_index(drop=True)


# ---------- build ----------
REV_BASE = ["booked", "commission_fee", "gross_fee"]
REV_RATIOS = [("avg_commission", "commission_fee", "booked")]
FUN_BASE = ["total_leads", "workable_leads", "assigned", "qualified_assigned", "open_leads", "booked"]
FUN_RATIOS = [
    ("assigned_rate", "assigned", "workable_leads"),
    ("qualified_assigned_rate", "qualified_assigned", "assigned"),
    ("booking_rate", "booked", "qualified_assigned"),
    ("win_rate", "booked", "closed_assigned"),
]


def _rev_table(rev: pd.DataFrame, group: str, windows: list[Window], sort_by: str) -> pd.DataFrame:
    t = _pivot(rev, [group], REV_BASE, windows)
    value_cols = [c for c in t.columns if c != group]
    t = _add_total(t, group, value_cols)
    t = _decorate(t, windows, REV_BASE, REV_RATIOS)
    body = t[t[group] != "TOTAL"].sort_values(sort_by, ascending=False)
    return pd.concat([body, t[t[group] == "TOTAL"]], ignore_index=True)


def _rev_table2(rev: pd.DataFrame, groups: list[str], windows: list[Window], sort_by: str) -> pd.DataFrame:
    """Revenue table cross-segmented by two dimensions (e.g. agent x source).

    Both `groups` are kept as separate columns. Rows are **grouped by the first
    dimension** so its values stay adjacent (e.g. an agent's inbound and repeat rows
    sit together): the first dimension is ordered by its total of `sort_by`, and rows
    within each first-dimension value are ordered by `sort_by`. A grand TOTAL row is
    appended last.
    """
    t = _pivot(rev, groups, REV_BASE, windows)
    value_cols = [c for c in t.columns if c not in groups]
    total = {c: t[c].sum() for c in value_cols}
    for g in groups:
        total[g] = "TOTAL"
    t = pd.concat([t, pd.DataFrame([total])], ignore_index=True)
    t = _decorate(t, windows, REV_BASE, REV_RATIOS)
    body = t[t[groups[0]] != "TOTAL"].copy()
    order = body.groupby(groups[0])[sort_by].sum().sort_values(ascending=False).index
    body[groups[0]] = pd.Categorical(body[groups[0]], categories=order, ordered=True)
    body = body.sort_values([groups[0], sort_by], ascending=[True, False])
    body[groups[0]] = body[groups[0]].astype(str)
    return pd.concat([body, t[t[groups[0]] == "TOTAL"]], ignore_index=True)


def _fun_table(fun_in: pd.DataFrame, group: str, windows: list[Window], sort_by: str) -> pd.DataFrame:
    t = _pivot(fun_in, [group], FUN_BASE, windows)
    t = _decorate(t, windows, FUN_BASE, FUN_RATIOS)
    return t.sort_values(sort_by, ascending=False).reset_index(drop=True)


def _fun_table2(fun_in: pd.DataFrame, groups: list[str], windows: list[Window], sort_by: str) -> pd.DataFrame:
    """Funnel table cross-segmented by two dimensions (e.g. origin x ad_presence).

    Both `groups` are kept as separate columns and rows are **grouped by the first
    dimension** (ordered by its total of `sort_by`; rows within each ordered by
    `sort_by`), matching `_rev_table2`. No TOTAL row (funnel totals live in fun_total).
    """
    t = _pivot(fun_in, groups, FUN_BASE, windows)
    t = _decorate(t, windows, FUN_BASE, FUN_RATIOS)
    order = t.groupby(groups[0])[sort_by].sum().sort_values(ascending=False).index
    t[groups[0]] = pd.Categorical(t[groups[0]], categories=order, ordered=True)
    t = t.sort_values([groups[0], sort_by], ascending=[True, False])
    t[groups[0]] = t[groups[0]].astype(str)
    return t.reset_index(drop=True)


def build(windows: list[Window]) -> dict[str, pd.DataFrame]:
    """Run the full standard matrix and return {table_name: DataFrame}."""
    if not windows:
        raise ValueError("at least one window is required")
    primary = windows[0].name

    rev = _revenue_df(windows)
    fun = _funnel_df(windows)
    rev_in = rev[rev["lead_source"] == "inbound"].copy()
    fun_in = fun[fun["lead_source"] == "inbound"].copy()

    pc = f"commission_fee__{primary}"
    pa = f"assigned__{primary}"

    tables: dict[str, pd.DataFrame] = {}

    # revenue
    open_all = _open_now_df()
    open_in = open_all[open_all["lead_source"] == "inbound"].copy()

    tables["rev_source"] = _attach_open_now(
        _rev_table(rev, "lead_source", windows, pc), ["lead_source"], open_all)
    tables["rev_agent"] = _attach_open_now(
        _rev_table(rev, "sales_agent", windows, pc), ["sales_agent"], open_all)
    tables["rev_agent_source"] = _attach_open_now(
        _rev_table2(rev, ["sales_agent", "lead_source"], windows, pc),
        ["sales_agent", "lead_source"], open_all)
    tables["rev_origin"] = _attach_open_now(
        _rev_table(rev_in, "lead_origin", windows, pc), ["lead_origin"], open_in)
    tables["rev_origin_ad"] = _attach_open_now(
        _rev_table2(rev_in, ["lead_origin", "ad_presence"], windows, pc),
        ["lead_origin", "ad_presence"], open_in)
    tables["rev_ad"] = _attach_open_now(
        _rev_table(rev_in, "ad_presence", windows, pc), ["ad_presence"], open_in)
    rev_budget = _attach_open_now(
        _rev_table(rev_in, "std_budget", windows, pc), ["std_budget"], open_in)
    tables["rev_budget"] = _sort_budget(rev_budget)

    # funnel (inbound) — single-row inbound total via a constant group key
    fi = fun_in.copy()
    fi["_all"] = "inbound"
    total_tbl = _pivot(fi, ["_all"], FUN_BASE, windows)
    total_tbl = _decorate(total_tbl, windows, FUN_BASE, FUN_RATIOS).rename(columns={"_all": "scope"})
    tables["fun_total"] = total_tbl

    tables["fun_agent"] = _fun_table(fun_in, "sales_agent", windows, pa)
    tables["fun_origin"] = _fun_table(fun_in, "lead_origin", windows, f"workable_leads__{primary}")
    tables["fun_origin_ad"] = _fun_table2(fun_in, ["lead_origin", "ad_presence"], windows, f"workable_leads__{primary}")
    tables["fun_ad"] = _fun_table(fun_in, "ad_presence", windows, f"workable_leads__{primary}")
    tables["fun_budget"] = _sort_budget(_fun_table(fun_in, "std_budget", windows, f"workable_leads__{primary}"))

    return tables


# ---------- CLI: dump CSVs + tables-only HTML data pack ----------
def _rev_columns(windows: list[Window]) -> list[tuple[str, str, str]]:
    """Revenue columns, COUNT-first: bookings + Open-now context, then commission,
    avg commission/booking, then gross. Reading volume before revenue keeps a channel
    from being misjudged as 'down' on a commission dip when booking volume is up."""
    cols: list[tuple[str, str, str]] = []

    def add(m: str, label: str, kind: str) -> None:
        for w in windows:
            cols.append((f"{m}__{w.name}", f"{label} {w.name}", kind))
        for w in windows[1:]:
            cols.append((f"{m}__vs_{w.name}", f"{label} Δ%{w.name}", "pct"))

    add("booked", "Bookings", "int")
    cols.append(("open_now", "Open now", "int"))   # point-in-time pipeline context
    add("commission_fee", "Comm", "money")
    add("avg_commission", "Avg comm/bkg", "money")
    add("gross_fee", "Gross", "money")
    return cols


def _fun_columns(windows: list[Window]) -> list[tuple[str, str, str]]:
    cols: list[tuple[str, str, str]] = []
    counts = [("total_leads", "Total", "int"), ("workable_leads", "Workable", "int"),
              ("assigned", "Assigned", "int"), ("qualified_assigned", "SQL", "int")]
    rates = [("assigned_rate", "Asgn%", "percent"), ("qualified_assigned_rate", "SQL%", "percent"),
             ("booking_rate", "Book%", "percent"), ("win_rate", "Win%", "percent")]
    for m, label, kind in counts:
        for w in windows:
            cols.append((f"{m}__{w.name}", f"{label} {w.name}", kind))
        for w in windows[1:]:
            cols.append((f"{m}__vs_{w.name}", f"{label} Δ%{w.name}", "pct"))
    # open leads still in the pipeline, per window (no delta — prior/yoy are largely resolved)
    for w in windows:
        cols.append((f"open_leads__{w.name}", f"Open {w.name}", "int"))
    for m, label, kind in rates:
        for w in windows:
            cols.append((f"{m}__{w.name}", f"{label} {w.name}", kind))
    return cols


def _data_pack(tables: dict[str, pd.DataFrame], windows: list[Window]) -> str:
    rc = _rev_columns(windows)
    fc = _fun_columns(windows)
    spec = [
        ("Revenue — by source (inbound vs repeat)", "rev_source", "lead_source", rc),
        ("Revenue — by agent", "rev_agent", "sales_agent", rc),
        ("Revenue — by agent x source", "rev_agent_source", "sales_agent", [("lead_source", "source", "str")] + rc),
        ("Revenue — inbound by lead_origin", "rev_origin", "lead_origin", rc),
        ("Revenue — inbound by lead_origin x ad_presence", "rev_origin_ad", "lead_origin", [("ad_presence", "ad", "str")] + rc),
        ("Revenue — inbound by ad_presence", "rev_ad", "ad_presence", rc),
        ("Revenue — inbound by budget tier", "rev_budget", "std_budget", rc),
        ("Funnel — inbound total", "fun_total", "scope", fc),
        ("Funnel — inbound by agent", "fun_agent", "sales_agent", fc),
        ("Funnel — inbound by lead_origin", "fun_origin", "lead_origin", fc),
        ("Funnel — inbound by lead_origin x ad_presence", "fun_origin_ad", "lead_origin", [("ad_presence", "ad", "str")] + fc),
        ("Funnel — inbound by ad_presence", "fun_ad", "ad_presence", fc),
        ("Funnel — inbound by budget tier", "fun_budget", "std_budget", fc),
    ]
    win_desc = ", ".join(f"<b>{w.name}</b> {w.start}→{w.end}" for w in windows)
    body = ["<h1>Standard report — data pack</h1>",
            f"<p>Windows: {win_desc}. Revenue by <code>contracted_on</code> (both sources); "
            "funnel by <code>created_at</code> (inbound only). Tables only — no interpretation.</p>"]
    for title, key, label_col, cols in spec:
        body.append(f"<h2>{title}</h2>")
        body.append(html_table(tables[key], label_col, cols))
    return "\n".join(body)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run the standard AAE analysis matrix.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--period", metavar="YYYY-MM-DD:YYYY-MM-DD",
                     help="Analyze this window with PoP + YoY auto-derived (current / prior / yoy). "
                          "The default way to run a report.")
    src.add_argument("--window", action="append", dest="windows", type=parse_window,
                     metavar="name=YYYY-MM-DD:YYYY-MM-DD",
                     help="Explicit window(s) for full manual control; the FIRST is primary, "
                          "changes are computed vs the rest. Repeatable.")
    p.add_argument("--compare", choices=["both", "pop", "yoy"], default="both",
                   help="With --period: which comparisons to include (default: both).")
    p.add_argument("--name", default="standard_report", help="Output basename (default: standard_report).")
    args = p.parse_args(argv)

    if args.period:
        try:
            start, end = args.period.split(":", 1)
        except ValueError:
            p.error(f"bad --period {args.period!r}; expected YYYY-MM-DD:YYYY-MM-DD")
        windows = derive_periods(start.strip(), end.strip(), args.compare)
    else:
        windows = args.windows

    tables = build(windows)
    OUT.mkdir(exist_ok=True)
    for key, df in tables.items():
        df.to_csv(OUT / f"{args.name}_{key}.csv", index=False)
    html_path = write_report(args.name, _data_pack(tables, windows), title="Standard report — data pack")
    print(f"Wrote {len(tables)} tables as CSVs + {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
