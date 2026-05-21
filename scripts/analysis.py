"""Inbound lead volume/value comparison for May 1-20 windows."""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
import re
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_query import run_query


TABLE = "`all-american-entertainment.one_off_opps_review.1_mega_opps_live`"
COLUMNS_TABLE = "`all-american-entertainment.one_off_opps_review.INFORMATION_SCHEMA.COLUMNS`"
OUT = ROOT / "outputs"

PERIODS = [
    {
        "period": "Current May 1-20 2026",
        "comparison_label": "current",
        "start": "2026-05-01",
        "end": "2026-05-20",
        "sort_order": 1,
    },
    {
        "period": "Prior 20 days Apr 11-30 2026",
        "comparison_label": "prior_20_days",
        "start": "2026-04-11",
        "end": "2026-04-30",
        "sort_order": 2,
    },
    {
        "period": "Last year May 1-20 2025",
        "comparison_label": "last_year_same_dates",
        "start": "2025-05-01",
        "end": "2025-05-20",
        "sort_order": 3,
    },
]

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
    "Unknown",
]
BUDGET_RANK = {label: i for i, label in enumerate(BUDGET_ORDER, start=1)}


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def discover_expected_value_column() -> str:
    sql = f"""
    SELECT column_name, data_type
    FROM {COLUMNS_TABLE}
    WHERE table_name = '1_mega_opps_live'
    ORDER BY ordinal_position
    """
    columns = run_query(sql)
    columns["norm_name"] = columns["column_name"].map(norm)

    preferred = [
        "marketing_expected_lead_value",
        "marketing_expected_value",
        "expected_lead_value",
        "mktg_expected_lead_value",
        "lead_value_marketing_expected",
    ]
    for name in preferred:
        match = columns.loc[columns["norm_name"] == name, "column_name"]
        if not match.empty:
            return str(match.iloc[0])

    tokens = {"marketing", "expected", "lead", "value"}

    def score(name: str) -> tuple[int, int]:
        pieces = set(name.split("_"))
        return len(tokens & pieces), len(name)

    candidates = columns[
        columns["norm_name"].str.contains("expected", na=False)
        & columns["norm_name"].str.contains("value|lead", regex=True, na=False)
    ].copy()
    if not candidates.empty:
        candidates[["token_score", "name_length"]] = candidates["norm_name"].apply(
            lambda x: pd.Series(score(x))
        )
        candidates = candidates.sort_values(
            ["token_score", "name_length"], ascending=[False, True]
        )
        return str(candidates.iloc[0]["column_name"])

    interesting = columns[
        columns["norm_name"].str.contains(
            "marketing|expected|value|budget", regex=True, na=False
        )
    ][["column_name", "data_type"]]
    raise RuntimeError(
        "Could not identify a marketing expected lead value column. "
        "Matching columns were:\n"
        + interesting.to_string(index=False)
    )


def quote_identifier(column_name: str) -> str:
    return "`" + column_name.replace("`", "") + "`"


def periods_cte() -> str:
    rows = []
    for p in PERIODS:
        rows.append(
            "SELECT "
            f"'{p['period']}' AS period, "
            f"'{p['comparison_label']}' AS comparison_label, "
            f"DATE '{p['start']}' AS start_date, "
            f"DATE '{p['end']}' AS end_date, "
            f"{p['sort_order']} AS period_sort"
        )
    return "\nUNION ALL\n".join(rows)


def fetch_rows(expected_value_column: str) -> pd.DataFrame:
    expected_col = quote_identifier(expected_value_column)
    sql = f"""
    WITH periods AS (
      {periods_cte()}
    )
    SELECT
      p.period,
      p.comparison_label,
      p.start_date,
      p.end_date,
      p.period_sort,
      DATE(t.created_at) AS created_date,
      DATE_DIFF(DATE(t.created_at), p.start_date, DAY) + 1 AS day_number,
      COALESCE(NULLIF(CAST(t.std_budget AS STRING), ''), 'Unknown') AS std_budget,
      COALESCE(NULLIF(CAST(t.lead_origin AS STRING), ''), 'Unknown') AS lead_origin,
      COALESCE(NULLIF(CAST(t.ad_presence AS STRING), ''), 'Unknown') AS ad_presence,
      CASE
        WHEN LOWER(COALESCE(CAST(t.lead_status AS STRING), '')) IN ('doa', 'spam')
          THEN 0
        ELSE 1
      END AS valid_lead,
      CASE
        WHEN SAFE_CAST(t.assigned AS INT64) = 1 THEN 1
        ELSE 0
      END AS assigned_lead,
      CASE
        WHEN LOWER(COALESCE(CAST(t.sales_status AS STRING), '')) = 'open'
          THEN 1
        ELSE 0
      END AS open_lead,
      CASE
        WHEN t.proposal_stage_started_at IS NOT NULL
          OR t.offer_stage_started_at IS NOT NULL
          THEN 1
        ELSE 0
      END AS stage_qualified_lead,
      CASE
        WHEN t.proposal_stage_started_at IS NOT NULL
          OR t.offer_stage_started_at IS NOT NULL
          OR SAFE_CAST(t.booked AS INT64) = 1
          THEN 1
        ELSE 0
      END AS stage_or_booked_qualified_lead,
      CASE
        WHEN SAFE_CAST(t.assigned AS INT64) = 1
          AND t.proposal_stage_started_at IS NULL
          AND t.offer_stage_started_at IS NULL
          AND LOWER(COALESCE(CAST(t.sales_status AS STRING), '')) = 'open'
          THEN 1
        ELSE 0
      END AS active_assigned_unqualified_lead,
      SAFE_CAST(t.{expected_col} AS FLOAT64) AS marketing_expected_lead_value
    FROM {TABLE} AS t
    JOIN periods AS p
      ON DATE(t.created_at) BETWEEN p.start_date AND p.end_date
    WHERE LOWER(COALESCE(CAST(t.lead_source AS STRING), '')) = 'inbound'
    """
    df = run_query(sql)
    df["created_date"] = pd.to_datetime(df["created_date"]).dt.date
    df["marketing_expected_lead_value"] = pd.to_numeric(
        df["marketing_expected_lead_value"], errors="coerce"
    ).fillna(0.0)
    count_cols = [
        "valid_lead",
        "assigned_lead",
        "open_lead",
        "stage_qualified_lead",
        "stage_or_booked_qualified_lead",
        "active_assigned_unqualified_lead",
    ]
    for col in count_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["raw_inbound_records"] = 1
    value_cols = {
        "valid_marketing_expected_lead_value": "valid_lead",
    }
    for value_col, flag_col in value_cols.items():
        df[value_col] = df["marketing_expected_lead_value"] * df[flag_col]
    return df


def aggregate_periods(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby(
            ["period_sort", "period", "comparison_label", "start_date", "end_date"],
            as_index=False,
        )
        .agg(
            raw_inbound_records=("raw_inbound_records", "sum"),
            valid_leads=("valid_lead", "sum"),
            assigned_leads=("assigned_lead", "sum"),
            active_leads=("active_assigned_unqualified_lead", "sum"),
            stage_qualified_leads=("stage_qualified_lead", "sum"),
            stage_or_booked_qualified_leads=(
                "stage_or_booked_qualified_lead",
                "sum",
            ),
            valid_marketing_expected_lead_value=(
                "valid_marketing_expected_lead_value",
                "sum",
            ),
        )
        .sort_values("period_sort")
    )
    grouped["doa_spam_records"] = (
        grouped["raw_inbound_records"] - grouped["valid_leads"]
    )
    grouped["avg_expected_value_per_valid_lead"] = safe_div(
        grouped["valid_marketing_expected_lead_value"],
        grouped["valid_leads"],
    )
    return grouped


def aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(
            [
                "period_sort",
                "period",
                "comparison_label",
                "created_date",
                "day_number",
            ],
            as_index=False,
        )
        .agg(
            raw_inbound_records=("raw_inbound_records", "sum"),
            valid_leads=("valid_lead", "sum"),
            assigned_leads=("assigned_lead", "sum"),
            active_leads=("active_assigned_unqualified_lead", "sum"),
            stage_qualified_leads=("stage_qualified_lead", "sum"),
            stage_or_booked_qualified_leads=(
                "stage_or_booked_qualified_lead",
                "sum",
            ),
            valid_marketing_expected_lead_value=(
                "valid_marketing_expected_lead_value",
                "sum",
            ),
        )
        .sort_values(["period_sort", "created_date"])
    )


def aggregate_budget(df: pd.DataFrame) -> pd.DataFrame:
    budget = (
        df.groupby(
            ["period_sort", "period", "comparison_label", "std_budget"],
            as_index=False,
        )
        .agg(
            raw_inbound_records=("raw_inbound_records", "sum"),
            valid_leads=("valid_lead", "sum"),
            assigned_leads=("assigned_lead", "sum"),
            active_leads=("active_assigned_unqualified_lead", "sum"),
            stage_qualified_leads=("stage_qualified_lead", "sum"),
            stage_or_booked_qualified_leads=(
                "stage_or_booked_qualified_lead",
                "sum",
            ),
            valid_marketing_expected_lead_value=(
                "valid_marketing_expected_lead_value",
                "sum",
            ),
        )
    )
    budget["budget_order"] = budget["std_budget"].map(BUDGET_RANK).fillna(99).astype(int)
    period_totals = budget.groupby("period", as_index=False).agg(
        period_valid_leads=("valid_leads", "sum"),
        period_assigned_leads=("assigned_leads", "sum"),
        period_active_leads=("active_leads", "sum"),
        period_stage_qualified_leads=("stage_qualified_leads", "sum"),
        period_valid_marketing_expected_lead_value=(
            "valid_marketing_expected_lead_value",
            "sum",
        ),
    )
    budget = budget.merge(period_totals, on="period", how="left")
    budget["valid_lead_share"] = safe_div(
        budget["valid_leads"], budget["period_valid_leads"]
    )
    budget["assigned_lead_share"] = safe_div(
        budget["assigned_leads"], budget["period_assigned_leads"]
    )
    budget["active_lead_share"] = safe_div(
        budget["active_leads"], budget["period_active_leads"]
    )
    budget["stage_qualified_lead_share"] = safe_div(
        budget["stage_qualified_leads"], budget["period_stage_qualified_leads"]
    )
    budget["valid_expected_value_share"] = safe_div(
        budget["valid_marketing_expected_lead_value"],
        budget["period_valid_marketing_expected_lead_value"],
    )
    return budget.sort_values(["period_sort", "budget_order", "std_budget"])


def aggregate_source(df: pd.DataFrame) -> pd.DataFrame:
    source = (
        df.groupby(
            ["period_sort", "period", "comparison_label", "lead_origin", "ad_presence"],
            as_index=False,
        )
        .agg(
            raw_inbound_records=("raw_inbound_records", "sum"),
            valid_leads=("valid_lead", "sum"),
            assigned_leads=("assigned_lead", "sum"),
            active_leads=("active_assigned_unqualified_lead", "sum"),
            stage_qualified_leads=("stage_qualified_lead", "sum"),
            stage_or_booked_qualified_leads=(
                "stage_or_booked_qualified_lead",
                "sum",
            ),
            valid_marketing_expected_lead_value=(
                "valid_marketing_expected_lead_value",
                "sum",
            ),
        )
    )
    source["source_segment"] = source["lead_origin"] + " / " + source["ad_presence"]
    period_totals = source.groupby("period", as_index=False).agg(
        period_valid_leads=("valid_leads", "sum"),
        period_assigned_leads=("assigned_leads", "sum"),
        period_active_leads=("active_leads", "sum"),
        period_stage_qualified_leads=("stage_qualified_leads", "sum"),
        period_valid_marketing_expected_lead_value=(
            "valid_marketing_expected_lead_value",
            "sum",
        ),
    )
    source = source.merge(period_totals, on="period", how="left")
    source["valid_lead_share"] = safe_div(
        source["valid_leads"], source["period_valid_leads"]
    )
    source["assigned_lead_share"] = safe_div(
        source["assigned_leads"], source["period_assigned_leads"]
    )
    source["active_lead_share"] = safe_div(
        source["active_leads"], source["period_active_leads"]
    )
    source["stage_qualified_lead_share"] = safe_div(
        source["stage_qualified_leads"], source["period_stage_qualified_leads"]
    )
    source["valid_expected_value_share"] = safe_div(
        source["valid_marketing_expected_lead_value"],
        source["period_valid_marketing_expected_lead_value"],
    )

    current_rank = (
        source[source["comparison_label"] == "current"]
        .sort_values(
            ["valid_leads", "stage_qualified_leads", "source_segment"],
            ascending=[False, False, True],
        )[["source_segment"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    current_rank["source_order"] = current_rank.index + 1
    source = source.merge(current_rank, on="source_segment", how="left")
    source["source_order"] = source["source_order"].fillna(9999).astype(int)
    return source.sort_values(["source_order", "period_sort", "source_segment"])


def safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace({0: pd.NA})
    return (numerator / denominator).fillna(0)


def build_period_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "raw_inbound_records",
        "valid_leads",
        "assigned_leads",
        "active_leads",
        "stage_qualified_leads",
        "stage_or_booked_qualified_leads",
        "valid_marketing_expected_lead_value",
        "avg_expected_value_per_valid_lead",
    ]
    current = summary[summary["comparison_label"] == "current"].iloc[0]
    rows = []
    for _, base in summary[summary["comparison_label"] != "current"].iterrows():
        row = {
            "comparison": f"Current vs {base['period']}",
            "baseline_period": base["period"],
        }
        for metric in metrics:
            current_value = current[metric]
            baseline_value = base[metric]
            row[f"current_{metric}"] = current_value
            row[f"baseline_{metric}"] = baseline_value
            row[f"delta_{metric}"] = current_value - baseline_value
            row[f"pct_delta_{metric}"] = (
                0 if baseline_value == 0 else (current_value / baseline_value) - 1
            )
        rows.append(row)
    return pd.DataFrame(rows)


def build_budget_comparison(budget: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "raw_inbound_records",
        "valid_leads",
        "assigned_leads",
        "active_leads",
        "stage_qualified_leads",
        "valid_marketing_expected_lead_value",
        "valid_lead_share",
        "assigned_lead_share",
        "active_lead_share",
        "stage_qualified_lead_share",
        "valid_expected_value_share",
    ]
    current = budget[budget["comparison_label"] == "current"][
        ["std_budget", "budget_order", *metrics]
    ].rename(columns={m: f"current_{m}" for m in metrics})

    frames = []
    for label in ["prior_20_days", "last_year_same_dates"]:
        baseline = budget[budget["comparison_label"] == label][
            ["std_budget", *metrics]
        ].rename(columns={m: f"baseline_{m}" for m in metrics})
        comp = current.merge(baseline, on="std_budget", how="outer").fillna(0)
        comp["comparison_label"] = label
        comp["budget_order"] = comp["budget_order"].replace({0: 99}).astype(int)
        for metric in metrics:
            comp[f"delta_{metric}"] = comp[f"current_{metric}"] - comp[
                f"baseline_{metric}"
            ]
            comp[f"pct_delta_{metric}"] = comp.apply(
                lambda r, m=metric: 0
                if r[f"baseline_{m}"] == 0
                else (r[f"current_{m}"] / r[f"baseline_{m}"]) - 1,
                axis=1,
            )
        frames.append(comp)
    return pd.concat(frames, ignore_index=True).sort_values(
        ["comparison_label", "budget_order", "std_budget"]
    )


def build_source_comparison(source: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "raw_inbound_records",
        "valid_leads",
        "assigned_leads",
        "active_leads",
        "stage_qualified_leads",
        "valid_marketing_expected_lead_value",
        "valid_lead_share",
        "assigned_lead_share",
        "active_lead_share",
        "stage_qualified_lead_share",
        "valid_expected_value_share",
    ]
    current = source[source["comparison_label"] == "current"][
        ["source_segment", "lead_origin", "ad_presence", "source_order", *metrics]
    ].rename(columns={m: f"current_{m}" for m in metrics})

    frames = []
    for label in ["prior_20_days", "last_year_same_dates"]:
        baseline = source[source["comparison_label"] == label][
            ["source_segment", *metrics]
        ].rename(columns={m: f"baseline_{m}" for m in metrics})
        comp = current.merge(baseline, on="source_segment", how="outer")
        for col in ["lead_origin", "ad_presence"]:
            comp[col] = comp[col].fillna("Unknown")
        comp["source_order"] = comp["source_order"].fillna(9999).astype(int)
        metric_cols = [
            col for col in comp.columns if col.startswith("current_") or col.startswith("baseline_")
        ]
        comp[metric_cols] = comp[metric_cols].fillna(0)
        comp["comparison_label"] = label
        for metric in metrics:
            comp[f"delta_{metric}"] = comp[f"current_{metric}"] - comp[
                f"baseline_{metric}"
            ]
            comp[f"pct_delta_{metric}"] = comp.apply(
                lambda r, m=metric: 0
                if r[f"baseline_{m}"] == 0
                else (r[f"current_{m}"] / r[f"baseline_{m}"]) - 1,
                axis=1,
            )
        frames.append(comp)
    return pd.concat(frames, ignore_index=True).sort_values(
        ["comparison_label", "source_order", "source_segment"]
    )


def fmt_int(value: float) -> str:
    return f"{value:,.0f}"


def fmt_money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def fmt_pct(value: float) -> str:
    return f"{value:+.1%}"


def fmt_change(delta: float, pct_delta: float, baseline: float, formatter) -> str:
    if float(baseline) == 0:
        return f"{formatter(delta)} (n/a; baseline 0)"
    return f"{formatter(delta)} ({fmt_pct(pct_delta)})"


def fmt_pct_or_na(pct_delta: float, baseline: float) -> str:
    if float(baseline) == 0:
        return "n/a; baseline 0"
    return fmt_pct(pct_delta)


def pct(value: float) -> str:
    return f"{value:.1%}"


def html_table(rows: list[dict[str, str]], columns: list[str]) -> str:
    head = "".join(f"<th>{escape(col)}</th>" for col in columns)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{escape(str(row.get(col, '')))}</td>" for col in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def period_short(period: str) -> str:
    return (
        period.replace("Current ", "")
        .replace("Prior 20 days ", "")
        .replace("Last year ", "")
    )


def short_text(value: str, limit: int = 42) -> str:
    value = str(value)
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def metric_period_bar_svg(
    title: str,
    df: pd.DataFrame,
    metrics: list[tuple[str, str, str]],
    value_formatter,
) -> str:
    width = 980
    height = 360
    left = 70
    right = 26
    top = 42
    bottom = 78
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_value = max(float(df[col].max()) for col, _, _ in metrics) or 1
    group_w = plot_w / len(metrics)
    bar_w = min(34, group_w / (len(df) + 1.6))
    gap = bar_w * 0.22
    period_colors = ["#1d4ed8", "#f59e0b", "#64748b"]

    parts = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{escape(title)}'>",
        f"<text x='{left}' y='24' class='chart-title'>{escape(title)}</text>",
    ]
    for frac in [0, 0.25, 0.5, 0.75, 1.0]:
        y = top + plot_h - (plot_h * frac)
        value = max_value * frac
        parts.append(f"<line x1='{left}' y1='{y:.1f}' x2='{width - right}' y2='{y:.1f}' class='grid' />")
        parts.append(f"<text x='{left - 10}' y='{y + 4:.1f}' text-anchor='end' class='axis-label'>{escape(value_formatter(value))}</text>")

    for i, (col, label, _) in enumerate(metrics):
        group_x = left + i * group_w + group_w * 0.18
        for j, (_, row) in enumerate(df.iterrows()):
            value = float(row[col])
            h = 0 if max_value == 0 else value / max_value * plot_h
            x = group_x + j * (bar_w + gap)
            y = top + plot_h - h
            color = period_colors[j % len(period_colors)]
            parts.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{bar_w:.1f}' height='{h:.1f}' fill='{color}' rx='3' />")
            parts.append(f"<text x='{x + bar_w / 2:.1f}' y='{y - 5:.1f}' text-anchor='middle' class='bar-value'>{escape(value_formatter(value))}</text>")
        parts.append(f"<text x='{left + i * group_w + group_w / 2:.1f}' y='{height - 38}' text-anchor='middle' class='axis-label'>{escape(label)}</text>")

    legend_x = left
    legend_y = height - 16
    for j, (_, row) in enumerate(df.iterrows()):
        color = period_colors[j % len(period_colors)]
        label = period_short(str(row["period"]))
        parts.append(f"<rect x='{legend_x}' y='{legend_y - 10}' width='10' height='10' fill='{color}' rx='2' />")
        parts.append(f"<text x='{legend_x + 16}' y='{legend_y}' class='legend'>{escape(label)}</text>")
        legend_x += 185

    parts.append("</svg>")
    return "".join(parts)


def segment_period_series_svg(
    title: str,
    data: pd.DataFrame,
    metric: str,
    label_col: str,
    order_col: str,
    value_formatter,
) -> str:
    width = 980
    row_h = 48
    top = 48
    left = 286
    right = 32
    chart_w = width - left - right
    period_colors = ["#1d4ed8", "#f59e0b", "#64748b"]
    periods = list(
        data[["period_sort", "period"]]
        .drop_duplicates()
        .sort_values("period_sort")
        .itertuples(index=False)
    )
    segment_order = (
        data[[label_col, order_col]]
        .drop_duplicates()
        .sort_values([order_col, label_col])
    )
    height = top + len(segment_order) * row_h + 52
    max_value = float(data[metric].max()) or 1
    parts = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{escape(title)}'>",
        f"<text x='{left}' y='24' class='chart-title'>{escape(title)}</text>",
    ]
    for i, row in enumerate(segment_order.itertuples(index=False)):
        label_value = getattr(row, label_col)
        y = top + i * row_h
        parts.append(f"<text x='{left - 12}' y='{y + 20}' text-anchor='end' class='budget-label'>{escape(short_text(label_value))}</text>")
        for j, period_row in enumerate(periods):
            period_sort = period_row.period_sort
            match = data[
                (data[label_col] == label_value)
                & (data["period_sort"] == period_sort)
            ]
            value = 0 if match.empty else float(match.iloc[0][metric])
            w = 0 if max_value == 0 else value / max_value * chart_w
            color = period_colors[j % len(period_colors)]
            offset = j * 12
            parts.append(f"<rect x='{left}' y='{y + offset}' width='{w:.1f}' height='8' fill='{color}' rx='3' />")
            parts.append(f"<text x='{left + w + 6:.1f}' y='{y + offset + 8}' class='bar-value'>{escape(value_formatter(value))}</text>")
    legend_x = left
    legend_y = height - 18
    for j, period_row in enumerate(periods):
        color = period_colors[j % len(period_colors)]
        label = period_short(str(period_row.period))
        parts.append(f"<rect x='{legend_x}' y='{legend_y - 10}' width='10' height='10' fill='{color}' rx='2' />")
        parts.append(f"<text x='{legend_x + 16}' y='{legend_y}' class='legend'>{escape(label)}</text>")
        legend_x += 185
    parts.append("</svg>")
    return "".join(parts)


REPORT_CSS = """
:root {
  color-scheme: light;
  --ink: #172033;
  --muted: #5b6475;
  --line: #d9dee8;
  --panel: #f7f9fc;
  --accent: #2563eb;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  max-width: 1120px;
  margin: 28px auto;
  padding: 0 22px 44px;
  color: var(--ink);
  line-height: 1.5;
  background: #ffffff;
}
h1 { margin: 0 0 4px; font-size: 30px; line-height: 1.2; }
h2 { margin: 34px 0 12px; font-size: 20px; border-bottom: 1px solid var(--line); padding-bottom: 7px; }
p, li { color: var(--muted); }
.subtitle { margin: 0 0 22px; color: var(--muted); }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 20px 0 26px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }
.card .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
.card .value { font-size: 25px; font-weight: 700; margin-top: 4px; }
.card .note { color: var(--muted); font-size: 13px; margin-top: 4px; }
.chart { border: 1px solid var(--line); border-radius: 8px; padding: 10px; margin: 14px 0 18px; overflow-x: auto; }
svg { width: 100%; min-width: 820px; display: block; }
.chart-title { font-size: 16px; font-weight: 700; fill: var(--ink); }
.axis-label, .legend, .bar-value, .budget-label { font-size: 12px; fill: var(--muted); }
.bar-value { fill: var(--ink); }
.budget-label { fill: var(--ink); }
.grid { stroke: #e9edf4; stroke-width: 1; }
.zero-line { stroke: #8791a3; stroke-width: 1.2; }
table { border-collapse: collapse; width: 100%; margin: 12px 0 22px; font-size: 13px; }
th, td { border: 1px solid var(--line); padding: 7px 9px; text-align: left; vertical-align: top; }
th { background: var(--panel); color: #30394b; }
tr:nth-child(even) td { background: #fbfcfe; }
code { background: #eef2f7; border-radius: 4px; padding: 1px 4px; }
.callout { background: #fff8e6; border: 1px solid #f1d28a; border-radius: 8px; padding: 12px 14px; color: #4b3a05; }
"""


def write_report(
    summary: pd.DataFrame,
    period_comparison: pd.DataFrame,
    budget: pd.DataFrame,
    budget_comparison: pd.DataFrame,
    source: pd.DataFrame,
    source_comparison: pd.DataFrame,
    expected_value_column: str,
) -> Path:
    current = summary[summary["comparison_label"] == "current"].iloc[0]
    prior_comp = period_comparison[
        period_comparison["baseline_period"].str.contains("Prior 20 days", na=False)
    ].iloc[0]
    last_year_comp = period_comparison[
        period_comparison["baseline_period"].str.contains("Last year", na=False)
    ].iloc[0]

    period_rows = []
    for _, row in summary.iterrows():
        period_rows.append(
            {
                "Period": row["period"],
                "Raw inbound records": fmt_int(row["raw_inbound_records"]),
                "Valid leads": fmt_int(row["valid_leads"]),
                "DOA/spam": fmt_int(row["doa_spam_records"]),
                "Assigned": fmt_int(row["assigned_leads"]),
                "Active": fmt_int(row["active_leads"]),
                "Qualified leads": fmt_int(row["stage_qualified_leads"]),
                "Qualified + booked fallback": fmt_int(
                    row["stage_or_booked_qualified_leads"]
                ),
                "Valid expected value": fmt_money(
                    row["valid_marketing_expected_lead_value"]
                ),
                "Valid EV / valid lead": fmt_money(
                    row["avg_expected_value_per_valid_lead"]
                ),
            }
        )

    comparison_metrics = [
        ("Valid leads", "valid_leads", fmt_int),
        ("Assigned", "assigned_leads", fmt_int),
        ("Active", "active_leads", fmt_int),
        ("Qualified leads", "stage_qualified_leads", fmt_int),
        ("Valid expected value", "valid_marketing_expected_lead_value", fmt_money),
        ("Valid EV / valid lead", "avg_expected_value_per_valid_lead", fmt_money),
    ]
    comparison_rows = []
    for label, metric, formatter in comparison_metrics:
        comparison_rows.append(
            {
                "Metric": label,
                "Current": formatter(current[metric]),
                "Prior period": formatter(prior_comp[f"baseline_{metric}"]),
                "PoP delta": fmt_change(
                    prior_comp[f"delta_{metric}"],
                    prior_comp[f"pct_delta_{metric}"],
                    prior_comp[f"baseline_{metric}"],
                    formatter,
                ),
                "Last year": formatter(last_year_comp[f"baseline_{metric}"]),
                "YoY delta": fmt_change(
                    last_year_comp[f"delta_{metric}"],
                    last_year_comp[f"pct_delta_{metric}"],
                    last_year_comp[f"baseline_{metric}"],
                    formatter,
                ),
            }
        )

    budget_detail_rows = []
    current_budget = budget[budget["comparison_label"] == "current"].sort_values(
        ["budget_order", "std_budget"]
    )
    for _, row in current_budget.iterrows():
        budget_detail_rows.append(
            {
                "Budget": row["std_budget"],
                "Raw records": fmt_int(row["raw_inbound_records"]),
                "Valid leads": fmt_int(row["valid_leads"]),
                "Assigned": fmt_int(row["assigned_leads"]),
                "Active": fmt_int(row["active_leads"]),
                "Qualified leads": fmt_int(row["stage_qualified_leads"]),
                "Qualified share": f"{row['stage_qualified_lead_share']:.1%}",
                "Valid expected value": fmt_money(
                    row["valid_marketing_expected_lead_value"]
                ),
                "Valid EV share": f"{row['valid_expected_value_share']:.1%}",
            }
        )

    prior_budget_comp = budget_comparison[
        budget_comparison["comparison_label"] == "prior_20_days"
    ].set_index("std_budget")
    last_year_budget_comp = budget_comparison[
        budget_comparison["comparison_label"] == "last_year_same_dates"
    ].set_index("std_budget")
    budget_delta_rows = []
    for _, row in current_budget.iterrows():
        budget_name = row["std_budget"]
        prior_row = prior_budget_comp.loc[budget_name]
        last_year_row = last_year_budget_comp.loc[budget_name]
        budget_delta_rows.append(
            {
                "Budget": budget_name,
                "Valid PoP": fmt_change(prior_row["delta_valid_leads"], prior_row["pct_delta_valid_leads"], prior_row["baseline_valid_leads"], fmt_int),
                "Valid YoY": fmt_change(last_year_row["delta_valid_leads"], last_year_row["pct_delta_valid_leads"], last_year_row["baseline_valid_leads"], fmt_int),
                "Active PoP": fmt_change(prior_row["delta_active_leads"], prior_row["pct_delta_active_leads"], prior_row["baseline_active_leads"], fmt_int),
                "Active YoY": fmt_change(last_year_row["delta_active_leads"], last_year_row["pct_delta_active_leads"], last_year_row["baseline_active_leads"], fmt_int),
                "Qualified PoP": fmt_change(prior_row["delta_stage_qualified_leads"], prior_row["pct_delta_stage_qualified_leads"], prior_row["baseline_stage_qualified_leads"], fmt_int),
                "Qualified YoY": fmt_change(last_year_row["delta_stage_qualified_leads"], last_year_row["pct_delta_stage_qualified_leads"], last_year_row["baseline_stage_qualified_leads"], fmt_int),
                "Valid EV PoP": fmt_change(prior_row["delta_valid_marketing_expected_lead_value"], prior_row["pct_delta_valid_marketing_expected_lead_value"], prior_row["baseline_valid_marketing_expected_lead_value"], fmt_money),
                "Valid EV YoY": fmt_change(last_year_row["delta_valid_marketing_expected_lead_value"], last_year_row["pct_delta_valid_marketing_expected_lead_value"], last_year_row["baseline_valid_marketing_expected_lead_value"], fmt_money),
            }
        )

    current_source = source[source["comparison_label"] == "current"].sort_values(
        ["source_order", "source_segment"]
    )
    top_source_segments = current_source["source_segment"].head(12).tolist()
    source_top = source[source["source_segment"].isin(top_source_segments)].sort_values(
        ["source_order", "period_sort", "source_segment"]
    )
    current_source_top = current_source[
        current_source["source_segment"].isin(top_source_segments)
    ]
    source_detail_rows = []
    for _, row in current_source_top.iterrows():
        source_detail_rows.append(
            {
                "Lead source / ad presence": row["source_segment"],
                "Raw records": fmt_int(row["raw_inbound_records"]),
                "Valid leads": fmt_int(row["valid_leads"]),
                "Assigned": fmt_int(row["assigned_leads"]),
                "Active": fmt_int(row["active_leads"]),
                "Qualified leads": fmt_int(row["stage_qualified_leads"]),
                "Qualified share": f"{row['stage_qualified_lead_share']:.1%}",
                "Valid expected value": fmt_money(
                    row["valid_marketing_expected_lead_value"]
                ),
                "Valid EV share": f"{row['valid_expected_value_share']:.1%}",
            }
        )

    prior_source_comp = source_comparison[
        source_comparison["comparison_label"] == "prior_20_days"
    ].set_index("source_segment")
    last_year_source_comp = source_comparison[
        source_comparison["comparison_label"] == "last_year_same_dates"
    ].set_index("source_segment")
    source_delta_rows = []
    for segment in top_source_segments:
        prior_row = prior_source_comp.loc[segment]
        last_year_row = last_year_source_comp.loc[segment]
        source_delta_rows.append(
            {
                "Lead source / ad presence": segment,
                "Valid PoP": fmt_change(prior_row["delta_valid_leads"], prior_row["pct_delta_valid_leads"], prior_row["baseline_valid_leads"], fmt_int),
                "Valid YoY": fmt_change(last_year_row["delta_valid_leads"], last_year_row["pct_delta_valid_leads"], last_year_row["baseline_valid_leads"], fmt_int),
                "Active PoP": fmt_change(prior_row["delta_active_leads"], prior_row["pct_delta_active_leads"], prior_row["baseline_active_leads"], fmt_int),
                "Active YoY": fmt_change(last_year_row["delta_active_leads"], last_year_row["pct_delta_active_leads"], last_year_row["baseline_active_leads"], fmt_int),
                "Qualified PoP": fmt_change(prior_row["delta_stage_qualified_leads"], prior_row["pct_delta_stage_qualified_leads"], prior_row["baseline_stage_qualified_leads"], fmt_int),
                "Qualified YoY": fmt_change(last_year_row["delta_stage_qualified_leads"], last_year_row["pct_delta_stage_qualified_leads"], last_year_row["baseline_stage_qualified_leads"], fmt_int),
                "Valid EV PoP": fmt_change(prior_row["delta_valid_marketing_expected_lead_value"], prior_row["pct_delta_valid_marketing_expected_lead_value"], prior_row["baseline_valid_marketing_expected_lead_value"], fmt_money),
                "Valid EV YoY": fmt_change(last_year_row["delta_valid_marketing_expected_lead_value"], last_year_row["pct_delta_valid_marketing_expected_lead_value"], last_year_row["baseline_valid_marketing_expected_lead_value"], fmt_money),
            }
        )

    counts_chart = metric_period_bar_svg(
        "Lead Progression by Metric",
        summary,
        [
            ("valid_leads", "Valid", "#4b5563"),
            ("assigned_leads", "Assigned", "#2563eb"),
            ("active_leads", "Active", "#0d9488"),
            ("stage_qualified_leads", "Qualified", "#16a34a"),
        ],
        fmt_int,
    )
    value_chart = metric_period_bar_svg(
        "Valid Expected Value by Period",
        summary,
        [
            ("valid_marketing_expected_lead_value", "Valid EV", "#0d9488"),
        ],
        fmt_money,
    )
    budget_valid_chart = segment_period_series_svg(
        "Valid Leads by Budget Range",
        budget,
        "valid_leads",
        "std_budget",
        "budget_order",
        fmt_int,
    )
    budget_qualified_chart = segment_period_series_svg(
        "Qualified Leads by Budget Range",
        budget,
        "stage_qualified_leads",
        "std_budget",
        "budget_order",
        fmt_int,
    )
    source_valid_chart = segment_period_series_svg(
        "Valid Leads by Lead Source / Ad Presence",
        source_top,
        "valid_leads",
        "source_segment",
        "source_order",
        fmt_int,
    )
    source_qualified_chart = segment_period_series_svg(
        "Qualified Leads by Lead Source / Ad Presence",
        source_top,
        "stage_qualified_leads",
        "source_segment",
        "source_order",
        fmt_int,
    )

    scope_items = [
        "Source: inbound only.",
        "Date axis: created_at.",
        "Current window: 2026-05-01 through 2026-05-20.",
        "Comparison windows: 2026-04-11 through 2026-04-30 and 2025-05-01 through 2025-05-20.",
        "Raw inbound records include every inbound row created in the window.",
        "Valid leads exclude lead_status values of doa and spam; this is not the sales-qualified metric.",
        "Assigned leads use the assigned flag.",
        "Active leads are assigned, not yet proposal/offer-qualified, and still open.",
        "Qualified leads mean proposal or offer stage reached.",
        "Qualified + booked fallback is shown as a diagnostic for rows that booked without populated proposal/offer timestamps.",
        "Lead source segmentation crosses lead_origin with ad_presence.",
        "Current-window qualified counts may be immature because newly created leads have had little time to reach proposal or offer.",
        f"Valid EV uses {expected_value_column} after applying the valid-lead filter.",
    ]
    scope_html = "".join(f"<li>{escape(item)}</li>" for item in scope_items)

    cards = [
        (
            "Valid leads",
            fmt_int(current["valid_leads"]),
            f"PoP {fmt_pct_or_na(prior_comp['pct_delta_valid_leads'], prior_comp['baseline_valid_leads'])}; YoY {fmt_pct_or_na(last_year_comp['pct_delta_valid_leads'], last_year_comp['baseline_valid_leads'])}",
        ),
        (
            "Assigned",
            fmt_int(current["assigned_leads"]),
            f"PoP {fmt_pct_or_na(prior_comp['pct_delta_assigned_leads'], prior_comp['baseline_assigned_leads'])}; YoY {fmt_pct_or_na(last_year_comp['pct_delta_assigned_leads'], last_year_comp['baseline_assigned_leads'])}",
        ),
        (
            "Active",
            fmt_int(current["active_leads"]),
            f"PoP {fmt_pct_or_na(prior_comp['pct_delta_active_leads'], prior_comp['baseline_active_leads'])}; YoY {fmt_pct_or_na(last_year_comp['pct_delta_active_leads'], last_year_comp['baseline_active_leads'])}",
        ),
        (
            "Qualified",
            fmt_int(current["stage_qualified_leads"]),
            f"PoP {fmt_pct_or_na(prior_comp['pct_delta_stage_qualified_leads'], prior_comp['baseline_stage_qualified_leads'])}; YoY {fmt_pct_or_na(last_year_comp['pct_delta_stage_qualified_leads'], last_year_comp['baseline_stage_qualified_leads'])}",
        ),
        (
            "Valid EV",
            fmt_money(current["valid_marketing_expected_lead_value"]),
            f"PoP {fmt_pct_or_na(prior_comp['pct_delta_valid_marketing_expected_lead_value'], prior_comp['baseline_valid_marketing_expected_lead_value'])}; YoY {fmt_pct_or_na(last_year_comp['pct_delta_valid_marketing_expected_lead_value'], last_year_comp['baseline_valid_marketing_expected_lead_value'])}",
        ),
    ]
    cards_html = "".join(
        "<div class='card'>"
        f"<div class='label'>{escape(label)}</div>"
        f"<div class='value'>{escape(value)}</div>"
        f"<div class='note'>{escape(note)}</div>"
        "</div>"
        for label, value, note in cards
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Inbound Lead Volume and Valid EV: May 1-20</title>
<style>{REPORT_CSS}</style>
</head>
<body>
<h1>Inbound Lead Volume and Valid EV: May 1-20</h1>
<p class="subtitle">Generated {escape(datetime.now().strftime('%Y-%m-%d %H:%M'))}. Current window is compared to the prior 20 days and the same dates last year.</p>

<div class="cards">{cards_html}</div>

<div class="callout">
  Valid lead volume is {escape(fmt_pct_or_na(prior_comp['pct_delta_valid_leads'], prior_comp['baseline_valid_leads']))} PoP and {escape(fmt_pct_or_na(last_year_comp['pct_delta_valid_leads'], last_year_comp['baseline_valid_leads']))} YoY. Active assigned/not-yet-qualified leads total {escape(fmt_int(current['active_leads']))}. Proposal/offer-stage qualification is {escape(fmt_pct_or_na(prior_comp['pct_delta_stage_qualified_leads'], prior_comp['baseline_stage_qualified_leads']))} PoP and {escape(fmt_pct_or_na(last_year_comp['pct_delta_stage_qualified_leads'], last_year_comp['baseline_stage_qualified_leads']))} YoY. Qualified counts for the current window should be read with some maturity caution because these leads are newly created.
</div>

<h2>Definitions and Scope</h2>
<ul>{scope_html}</ul>

<h2>Charts</h2>
<div class="chart">{counts_chart}</div>
<div class="chart">{value_chart}</div>
<div class="chart">{budget_valid_chart}</div>
<div class="chart">{budget_qualified_chart}</div>
<div class="chart">{source_valid_chart}</div>
<div class="chart">{source_qualified_chart}</div>

<h2>Period Summary</h2>
{html_table(period_rows, [
    "Period",
    "Raw inbound records",
    "Valid leads",
    "DOA/spam",
    "Assigned",
    "Active",
    "Qualified leads",
    "Qualified + booked fallback",
    "Valid expected value",
    "Valid EV / valid lead",
])}

<h2>Current Window Comparison</h2>
{html_table(comparison_rows, [
    "Metric",
    "Current",
    "Prior period",
    "PoP delta",
    "Last year",
    "YoY delta",
])}

<h2>Current Budget Mix</h2>
{html_table(budget_detail_rows, [
    "Budget",
    "Raw records",
    "Valid leads",
    "Assigned",
    "Active",
    "Qualified leads",
    "Qualified share",
    "Valid expected value",
    "Valid EV share",
])}

<h2>Budget-Range Changes</h2>
{html_table(budget_delta_rows, [
    "Budget",
    "Valid PoP",
    "Valid YoY",
    "Active PoP",
    "Active YoY",
    "Qualified PoP",
    "Qualified YoY",
    "Valid EV PoP",
    "Valid EV YoY",
])}

<h2>Current Lead Source / Ad Presence Mix</h2>
{html_table(source_detail_rows, [
    "Lead source / ad presence",
    "Raw records",
    "Valid leads",
    "Assigned",
    "Active",
    "Qualified leads",
    "Qualified share",
    "Valid expected value",
    "Valid EV share",
])}

<h2>Lead Source / Ad Presence Changes</h2>
{html_table(source_delta_rows, [
    "Lead source / ad presence",
    "Valid PoP",
    "Valid YoY",
    "Active PoP",
    "Active YoY",
    "Qualified PoP",
    "Qualified YoY",
    "Valid EV PoP",
    "Valid EV YoY",
])}
</body>
</html>
"""

    out_path = OUT / "inbound_may_1_20_lead_volume_expected_value.html"
    out_path.write_text(html, encoding="utf-8")

    stale_md = OUT / "inbound_may_1_20_lead_volume_expected_value.md"
    if stale_md.exists():
        stale_md.unlink()

    return out_path


def main() -> None:
    OUT.mkdir(exist_ok=True)
    expected_value_column = discover_expected_value_column()
    rows = fetch_rows(expected_value_column)

    summary = aggregate_periods(rows)
    daily = aggregate_daily(rows)
    budget = aggregate_budget(rows)
    source = aggregate_source(rows)
    period_comparison = build_period_comparison(summary)
    budget_comparison = build_budget_comparison(budget)
    source_comparison = build_source_comparison(source)

    summary.to_csv(OUT / "inbound_may_1_20_period_summary.csv", index=False)
    period_comparison.to_csv(
        OUT / "inbound_may_1_20_period_comparison.csv", index=False
    )
    daily.to_csv(OUT / "inbound_may_1_20_daily.csv", index=False)
    budget.to_csv(OUT / "inbound_may_1_20_budget.csv", index=False)
    budget_comparison.to_csv(
        OUT / "inbound_may_1_20_budget_comparison.csv", index=False
    )
    source.to_csv(OUT / "inbound_may_1_20_source_ad_presence.csv", index=False)
    source_comparison.to_csv(
        OUT / "inbound_may_1_20_source_ad_presence_comparison.csv", index=False
    )
    report = write_report(
        summary,
        period_comparison,
        budget,
        budget_comparison,
        source,
        source_comparison,
        expected_value_column,
    )
    print(f"Wrote analysis outputs under {OUT}")
    print(f"Report: {report}")


if __name__ == "__main__":
    main()
