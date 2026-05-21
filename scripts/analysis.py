"""April 1-29 2026 vs March 1-29 2026 (last month, same # of days)
vs April 1-29 2025 (last year, same # of days).

Bookings bucketed by `contracted_on`; assigned bucketed by `created_at`.
Both inbound + repeat. Cuts by lead_source, sales_agent, and source x agent.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

from scripts.run_query import run_query

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

TBL = "`all-american-entertainment.one_off_opps_review.1_mega_opps_live`"

WINDOWS = [
    ("apr_2026", "2026-04-01", "2026-04-29"),
    ("mar_2026", "2026-03-01", "2026-03-29"),
    ("apr_2025", "2025-04-01", "2025-04-29"),
]
WIN_ORDER = ["apr_2026", "mar_2026", "apr_2025"]

UNASSIGNED = "(unassigned)"


def window_case(date_col: str) -> str:
    parts = [
        f"WHEN DATE({date_col}) BETWEEN DATE('{s}') AND DATE('{e}') THEN '{name}'"
        for name, s, e in WINDOWS
    ]
    return "CASE " + " ".join(parts) + " END"


def window_filter(date_col: str) -> str:
    parts = [
        f"DATE({date_col}) BETWEEN DATE('{s}') AND DATE('{e}')"
        for _, s, e in WINDOWS
    ]
    return "(" + " OR ".join(parts) + ")"


# ---------- 1) Bookings (by contracted_on) ----------
sql_book = f"""
SELECT
  {window_case('contracted_on')} AS win_label,
  lead_source,
  COALESCE(sales_agent, '{UNASSIGNED}') AS sales_agent,
  SUM(COALESCE(booked, 0))         AS booked,
  SUM(COALESCE(gross_fee, 0))      AS gross_fee,
  SUM(COALESCE(commission_fee, 0)) AS commission_fee
FROM {TBL}
WHERE contracted_on IS NOT NULL
  AND {window_filter('contracted_on')}
GROUP BY 1, 2, 3
"""
book = run_query(sql_book)
book = book.rename(columns={"win_label": "window"})
for c in ("booked", "gross_fee", "commission_fee"):
    book[c] = book[c].astype(float)


# ---------- 2) Funnel (by created_at): leads + assigned ----------
sql_funnel = f"""
SELECT
  {window_case('created_at')} AS win_label,
  lead_source,
  COALESCE(sales_agent, '{UNASSIGNED}') AS sales_agent,
  SUM(CASE WHEN LOWER(IFNULL(lead_status,'')) IN ('doa','spam') THEN 0 ELSE 1 END) AS leads,
  SUM(COALESCE(assigned, 0)) AS assigned
FROM {TBL}
WHERE created_at IS NOT NULL
  AND {window_filter('created_at')}
GROUP BY 1, 2, 3
"""
fun = run_query(sql_funnel)
fun = fun.rename(columns={"win_label": "window"})
for c in ("leads", "assigned"):
    fun[c] = fun[c].astype(float)


# ---------- helpers ----------
def pivot_windows(df: pd.DataFrame, group_cols: list[str], metrics: list[str]) -> pd.DataFrame:
    """Aggregate to (group_cols x window) and pivot windows to columns,
    one column per (metric, window). Adds vs_lm and vs_ly delta columns."""
    g = df.groupby(group_cols + ["window"], dropna=False)[metrics].sum().reset_index()
    p = g.pivot_table(index=group_cols, columns="window", values=metrics, fill_value=0.0)
    rows = []
    for k, row in p.iterrows():
        rec = dict(zip(group_cols, k if isinstance(k, tuple) else (k,)))
        for m in metrics:
            v_apr26 = float(row.get((m, "apr_2026"), 0))
            v_mar26 = float(row.get((m, "mar_2026"), 0))
            v_apr25 = float(row.get((m, "apr_2025"), 0))
            rec[f"{m}__apr_2026"] = v_apr26
            rec[f"{m}__mar_2026"] = v_mar26
            rec[f"{m}__apr_2025"] = v_apr25
            rec[f"{m}__vs_lm"] = v_apr26 - v_mar26
            rec[f"{m}__vs_ly"] = v_apr26 - v_apr25
        rows.append(rec)
    out = pd.DataFrame(rows)
    return out


def add_total_row(df: pd.DataFrame, group_cols: list[str], label_col: str, label: str = "TOTAL") -> pd.DataFrame:
    num_cols = [c for c in df.columns if c not in group_cols]
    total = {c: df[c].sum() for c in num_cols}
    for c in group_cols:
        total[c] = label if c == label_col else ""
    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)


# ---------- 3) Source-only cuts ----------
book_src = pivot_windows(book, ["lead_source"], ["booked", "gross_fee", "commission_fee"])
book_src = book_src.sort_values("commission_fee__apr_2026", ascending=False).reset_index(drop=True)
book_src = add_total_row(book_src, ["lead_source"], "lead_source")

fun_src = pivot_windows(fun, ["lead_source"], ["leads", "assigned"])
fun_src = fun_src.sort_values("assigned__apr_2026", ascending=False).reset_index(drop=True)
fun_src = add_total_row(fun_src, ["lead_source"], "lead_source")

# ---------- 4) Agent-only cuts ----------
book_ag = pivot_windows(book, ["sales_agent"], ["booked", "gross_fee", "commission_fee"])
book_ag = book_ag.sort_values("commission_fee__apr_2026", ascending=False).reset_index(drop=True)
book_ag = add_total_row(book_ag, ["sales_agent"], "sales_agent")

fun_ag = pivot_windows(fun, ["sales_agent"], ["leads", "assigned"])
fun_ag = fun_ag.sort_values("assigned__apr_2026", ascending=False).reset_index(drop=True)
fun_ag = add_total_row(fun_ag, ["sales_agent"], "sales_agent")

# ---------- 5) Source x Agent ----------
book_sa = pivot_windows(book, ["lead_source", "sales_agent"], ["booked", "gross_fee", "commission_fee"])
book_sa = book_sa.sort_values(
    ["lead_source", "commission_fee__apr_2026"], ascending=[True, False]
).reset_index(drop=True)

fun_sa = pivot_windows(fun, ["lead_source", "sales_agent"], ["leads", "assigned"])
fun_sa = fun_sa.sort_values(
    ["lead_source", "assigned__apr_2026"], ascending=[True, False]
).reset_index(drop=True)


# ---------- 6) Print + write ----------
def show(name: str, df: pd.DataFrame) -> None:
    print(f"\n=== {name} ===")
    with pd.option_context("display.max_columns", None, "display.width", 220):
        print(df.to_string(index=False))


show("Bookings — by lead_source",            book_src)
show("Bookings — by sales_agent",            book_ag)
show("Bookings — by lead_source x agent",    book_sa)
show("Funnel (leads/assigned) — by source",          fun_src)
show("Funnel (leads/assigned) — by sales_agent",     fun_ag)
show("Funnel (leads/assigned) — by source x agent",  fun_sa)


book_src.to_csv(OUT / "apr_v_lm_v_ly_bookings_by_source.csv", index=False)
book_ag .to_csv(OUT / "apr_v_lm_v_ly_bookings_by_agent.csv", index=False)
book_sa .to_csv(OUT / "apr_v_lm_v_ly_bookings_by_source_x_agent.csv", index=False)
fun_src .to_csv(OUT / "apr_v_lm_v_ly_funnel_by_source.csv", index=False)
fun_ag  .to_csv(OUT / "apr_v_lm_v_ly_funnel_by_agent.csv", index=False)
fun_sa  .to_csv(OUT / "apr_v_lm_v_ly_funnel_by_source_x_agent.csv", index=False)


# ---------- 7) Markdown summary ----------
def fmt_money(x: float) -> str:
    return f"${x:,.0f}"

def fmt_int(x: float) -> str:
    return f"{int(round(x)):,}"

def fmt_pct(curr: float, base: float) -> str:
    if base == 0:
        return "n/a"
    return f"{(curr - base) / base * 100:+.0f}%"


def src_row_for(df: pd.DataFrame, src: str, metric: str) -> tuple[float, float, float]:
    r = df[df["lead_source"] == src].iloc[0]
    return (r[f"{metric}__apr_2026"], r[f"{metric}__mar_2026"], r[f"{metric}__apr_2025"])


def total_for(df: pd.DataFrame, label_col: str, metric: str) -> tuple[float, float, float]:
    r = df[df[label_col] == "TOTAL"].iloc[0]
    return (r[f"{metric}__apr_2026"], r[f"{metric}__mar_2026"], r[f"{metric}__apr_2025"])


lines: list[str] = []
lines.append("# April 1-29 2026 vs March 1-29 2026 vs April 1-29 2025\n")
lines.append("Same number of days (29) in every window. "
             "Bookings bucketed by `contracted_on`, funnel by `created_at`. "
             "Both inbound + repeat included.\n")

# headline totals
b_apr26, b_mar26, b_apr25 = total_for(book_src, "lead_source", "booked")
c_apr26, c_mar26, c_apr25 = total_for(book_src, "lead_source", "commission_fee")
g_apr26, g_mar26, g_apr25 = total_for(book_src, "lead_source", "gross_fee")
l_apr26, l_mar26, l_apr25 = total_for(fun_src,  "lead_source", "leads")
a_apr26, a_mar26, a_apr25 = total_for(fun_src,  "lead_source", "assigned")

lines.append("## Headline\n")
lines.append("| Metric | Apr 1-29 2026 | Mar 1-29 2026 | vs LM | Apr 1-29 2025 | vs LY |")
lines.append("|---|---:|---:|---:|---:|---:|")
lines.append(f"| Bookings (count) | {fmt_int(b_apr26)} | {fmt_int(b_mar26)} | {fmt_pct(b_apr26, b_mar26)} | {fmt_int(b_apr25)} | {fmt_pct(b_apr26, b_apr25)} |")
lines.append(f"| Commission | {fmt_money(c_apr26)} | {fmt_money(c_mar26)} | {fmt_pct(c_apr26, c_mar26)} | {fmt_money(c_apr25)} | {fmt_pct(c_apr26, c_apr25)} |")
lines.append(f"| Gross fee | {fmt_money(g_apr26)} | {fmt_money(g_mar26)} | {fmt_pct(g_apr26, g_mar26)} | {fmt_money(g_apr25)} | {fmt_pct(g_apr26, g_apr25)} |")
lines.append(f"| Leads (created) | {fmt_int(l_apr26)} | {fmt_int(l_mar26)} | {fmt_pct(l_apr26, l_mar26)} | {fmt_int(l_apr25)} | {fmt_pct(l_apr26, l_apr25)} |")
lines.append(f"| Assigned (created) | {fmt_int(a_apr26)} | {fmt_int(a_mar26)} | {fmt_pct(a_apr26, a_mar26)} | {fmt_int(a_apr25)} | {fmt_pct(a_apr26, a_apr25)} |")
lines.append("")

# ---------- What's driving the miss (data-derived) ----------
inb_b = book_src[book_src["lead_source"] == "inbound"].iloc[0]
rep_b = book_src[book_src["lead_source"] == "repeat"].iloc[0]
inb_f = fun_src[fun_src["lead_source"] == "inbound"].iloc[0]
rep_f = fun_src[fun_src["lead_source"] == "repeat"].iloc[0]

avg_book_apr26 = c_apr26 / b_apr26 if b_apr26 else 0
avg_book_apr25 = c_apr25 / b_apr25 if b_apr25 else 0
avg_book_mar26 = c_mar26 / b_mar26 if b_mar26 else 0

lines.append("## What's driving the April miss\n")
lines.append(
    "- **Top of funnel is healthy.** Inbound leads "
    f"{fmt_int(inb_f['leads__apr_2026'])} vs {fmt_int(inb_f['leads__apr_2025'])} LY "
    f"({fmt_pct(inb_f['leads__apr_2026'], inb_f['leads__apr_2025'])}); "
    f"inbound assigned {fmt_int(inb_f['assigned__apr_2026'])} vs {fmt_int(inb_f['assigned__apr_2025'])} LY "
    f"({fmt_pct(inb_f['assigned__apr_2026'], inb_f['assigned__apr_2025'])}). "
    "Demand isn't the problem."
)
lines.append(
    "- **Repeat volume is down materially.** "
    f"{fmt_int(rep_f['assigned__apr_2026'])} repeat opps vs "
    f"{fmt_int(rep_f['assigned__apr_2025'])} LY "
    f"({fmt_pct(rep_f['assigned__apr_2026'], rep_f['assigned__apr_2025'])}) and "
    f"{fmt_int(rep_f['assigned__apr_2026'])} vs {fmt_int(rep_f['assigned__apr_2025'])} LM "
    f"({fmt_pct(rep_f['assigned__apr_2026'], rep_f['assigned__mar_2026'])}). "
    "Yet repeat commission is still up YoY "
    f"({fmt_money(rep_b['commission_fee__apr_2026'])} vs {fmt_money(rep_b['commission_fee__apr_2025'])}, "
    f"{fmt_pct(rep_b['commission_fee__apr_2026'], rep_b['commission_fee__apr_2025'])}) — "
    "fewer but larger repeat deals are landing."
)
lines.append(
    "- **The miss is concentrated in inbound revenue.** Inbound commission "
    f"{fmt_money(inb_b['commission_fee__apr_2026'])} vs "
    f"{fmt_money(inb_b['commission_fee__apr_2025'])} LY "
    f"({fmt_pct(inb_b['commission_fee__apr_2026'], inb_b['commission_fee__apr_2025'])}) on "
    f"{fmt_int(inb_b['booked__apr_2026'])} bookings vs {fmt_int(inb_b['booked__apr_2025'])} LY "
    f"({fmt_pct(inb_b['booked__apr_2026'], inb_b['booked__apr_2025'])}) — "
    "more bookings, less revenue, so deal size has compressed."
)
lines.append(
    f"- **Average $/booking dropped.** Apr-26 ${avg_book_apr26:,.0f} vs "
    f"Apr-25 ${avg_book_apr25:,.0f} ({fmt_pct(avg_book_apr26, avg_book_apr25)}), "
    f"Mar-26 ${avg_book_mar26:,.0f} ({fmt_pct(avg_book_apr26, avg_book_mar26)})."
)

# Agent-level YoY swings (commission)
ag_yoy = book_ag[book_ag["sales_agent"] != "TOTAL"][["sales_agent", "commission_fee__apr_2026", "commission_fee__apr_2025", "commission_fee__vs_ly"]].copy()
ag_yoy_down = ag_yoy.sort_values("commission_fee__vs_ly").head(3)
ag_yoy_up = ag_yoy.sort_values("commission_fee__vs_ly", ascending=False).head(3)
losers = ", ".join(
    f"{r['sales_agent']} ({fmt_money(r['commission_fee__apr_2026'])} vs {fmt_money(r['commission_fee__apr_2025'])}, {fmt_pct(r['commission_fee__apr_2026'], r['commission_fee__apr_2025'])})"
    for _, r in ag_yoy_down.iterrows()
)
winners = ", ".join(
    f"{r['sales_agent']} ({fmt_money(r['commission_fee__apr_2026'])} vs {fmt_money(r['commission_fee__apr_2025'])}, {fmt_pct(r['commission_fee__apr_2026'], r['commission_fee__apr_2025'])})"
    for _, r in ag_yoy_up.iterrows()
)
lines.append(f"- **Biggest agent-level commission drops YoY:** {losers}.")
lines.append(f"- **Biggest agent-level commission gains YoY:** {winners}.")

# Lead-routing shifts: inbound assigned changes
inb_sa = fun_sa[fun_sa["lead_source"] == "inbound"].copy()
inb_sa["delta_ly"] = inb_sa["assigned__vs_ly"]
routing_down = inb_sa.sort_values("delta_ly").head(3)
routing_up = inb_sa.sort_values("delta_ly", ascending=False).head(3)
r_down = ", ".join(
    f"{r['sales_agent']} ({fmt_int(r['assigned__apr_2026'])} vs {fmt_int(r['assigned__apr_2025'])} LY)"
    for _, r in routing_down.iterrows() if r['sales_agent'] != UNASSIGNED
)
r_up = ", ".join(
    f"{r['sales_agent']} ({fmt_int(r['assigned__apr_2026'])} vs {fmt_int(r['assigned__apr_2025'])} LY)"
    for _, r in routing_up.iterrows() if r['sales_agent'] != UNASSIGNED
)
lines.append(f"- **Inbound routing shifts (YoY assigned counts):** down to {r_down}; up to {r_up}.")
lines.append("")


def section(title: str, df: pd.DataFrame, label_col: str, metrics: list[tuple[str, str, str]]) -> None:
    """metrics: list of (column, header, fmt) — fmt one of 'money'|'int'."""
    lines.append(f"## {title}\n")
    header_cells = [label_col]
    for _, h, _ in metrics:
        header_cells += [
            f"{h} Apr-26", f"{h} Mar-26", f"{h} vs LM",
            f"{h} Apr-25", f"{h} vs LY",
        ]
    lines.append("| " + " | ".join(header_cells) + " |")
    lines.append("|" + "|".join(["---"] + ["---:"] * (len(header_cells) - 1)) + "|")
    for _, r in df.iterrows():
        cells = [str(r[label_col])]
        for col, _, kind in metrics:
            v_apr26 = r[f"{col}__apr_2026"]
            v_mar26 = r[f"{col}__mar_2026"]
            v_apr25 = r[f"{col}__apr_2025"]
            f = fmt_money if kind == "money" else fmt_int
            cells += [
                f(v_apr26), f(v_mar26), fmt_pct(v_apr26, v_mar26),
                f(v_apr25), fmt_pct(v_apr26, v_apr25),
            ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")


# Source breakdowns
section(
    "Bookings by lead_source",
    book_src.drop(columns=[c for c in book_src.columns if c.startswith("gross_fee")]),
    "lead_source",
    [("booked", "Booked", "int"), ("commission_fee", "Comm.", "money")],
)
section(
    "Funnel by lead_source",
    fun_src,
    "lead_source",
    [("leads", "Leads", "int"), ("assigned", "Assigned", "int")],
)

# Agent breakdowns — top 12 by current commission / assigned (excluding TOTAL row sorted to bottom)
def head_keep_total(df: pd.DataFrame, label_col: str, n: int) -> pd.DataFrame:
    body = df[df[label_col] != "TOTAL"].head(n)
    total = df[df[label_col] == "TOTAL"]
    return pd.concat([body, total], ignore_index=True)

section(
    "Top agents by Apr 2026 commission (bookings)",
    head_keep_total(book_ag, "sales_agent", 12),
    "sales_agent",
    [("booked", "Booked", "int"), ("commission_fee", "Comm.", "money")],
)
section(
    "Top agents by Apr 2026 assigned (funnel)",
    head_keep_total(fun_ag, "sales_agent", 12),
    "sales_agent",
    [("leads", "Leads", "int"), ("assigned", "Assigned", "int")],
)

# Source x Agent — top per source
def top_per_source(df: pd.DataFrame, sort_col: str, n: int = 8) -> pd.DataFrame:
    out_pieces = []
    for src in ["inbound", "repeat"]:
        chunk = df[df["lead_source"] == src].head(n)
        out_pieces.append(chunk)
    return pd.concat(out_pieces, ignore_index=True)

def top_per_source_with_source(df: pd.DataFrame, n: int = 8) -> pd.DataFrame:
    out_pieces = []
    for src in ["inbound", "repeat"]:
        chunk = df[df["lead_source"] == src].head(n).copy()
        chunk["sales_agent"] = chunk["lead_source"] + " · " + chunk["sales_agent"]
        out_pieces.append(chunk)
    return pd.concat(out_pieces, ignore_index=True)

section(
    "Source x Agent — bookings (top 8 per source by Apr 2026 commission)",
    top_per_source_with_source(book_sa),
    "sales_agent",
    [("booked", "Booked", "int"), ("commission_fee", "Comm.", "money")],
)
section(
    "Source x Agent — funnel (top 8 per source by Apr 2026 assigned)",
    top_per_source_with_source(fun_sa),
    "sales_agent",
    [("leads", "Leads", "int"), ("assigned", "Assigned", "int")],
)


lines.append("## Files\n")
lines.append("- `outputs/apr_v_lm_v_ly_bookings_by_source.csv`")
lines.append("- `outputs/apr_v_lm_v_ly_bookings_by_agent.csv`")
lines.append("- `outputs/apr_v_lm_v_ly_bookings_by_source_x_agent.csv`")
lines.append("- `outputs/apr_v_lm_v_ly_funnel_by_source.csv`")
lines.append("- `outputs/apr_v_lm_v_ly_funnel_by_agent.csv`")
lines.append("- `outputs/apr_v_lm_v_ly_funnel_by_source_x_agent.csv`")
lines.append("")

md_path = OUT / "apr_v_lm_v_ly_summary.md"
md_path.write_text("\n".join(lines), encoding="utf-8")
print(f"\nwrote {md_path}")

from scripts.md_to_html import md_to_html
md_to_html(str(md_path))
print(f"wrote {md_path.with_suffix('.html')}")
