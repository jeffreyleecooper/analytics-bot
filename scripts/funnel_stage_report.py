"""Standard report #2 — funnel stage-entry flow by month (throughput over time).

Answers: "how many opps moved INTO each sales stage each month?" — i.e. funnel
throughput / velocity over time. This uses the per-stage entry timestamps, which are
reliably recorded (unlike stage *exits* / loss timing, which are not — so a point-in-time
"who is sitting in each stage" reconstruction is not supported by this data; see the repo
notes). Each opp contributes to a stage's count in the month it entered that stage.

Stages (entered when…):
    Assigned    assigned_at
    Qualifying  qualifying_stage_started_at
    Proposed    proposal_stage_started_at
    Firm offer  offer_stage_started_at
    Booked      contracted_on            (canonical booked date; both sources)

Note this is a *flow* by calendar month, not a strict cohort funnel — an opp entering
Proposed in May may have been Assigned in an earlier month. The final month is
partial (month-to-date) and labelled accordingly.

CLI — writes outputs/<name>_stage_flow.csv + a styled HTML report:
    python -m scripts.funnel_stage_report                      # trailing 18 months, both sources
    python -m scripts.funnel_stage_report --months 12 --source inbound
    python -m scripts.funnel_stage_report --asof 2026-06-11     # override "today"

Importable:
    from scripts.funnel_stage_report import build, derive_months
    table = build(derive_months(date.today(), 18), source="both")
"""
from __future__ import annotations

import argparse
from datetime import date

import pandas as pd

from scripts.run_query import run_query
from scripts.report import OUT, write_report, html_table, line_chart_svg

TBL = "`all-american-entertainment.one_off_opps_review.1_mega_opps_live`"

# Reported stage -> (display label, entry-timestamp column)
STAGES = [
    ("assigned",   "Assigned",   "assigned_at"),
    ("qualifying", "Qualifying", "qualifying_stage_started_at"),
    ("proposed",   "Proposed",   "proposal_stage_started_at"),
    ("firm_offer", "Firm offer", "offer_stage_started_at"),
    ("booked",     "Booked",     "contracted_on"),
]
TS_COLS = [c for _, _, c in STAGES]


def derive_months(asof: date, months: int) -> list[tuple[str, bool]]:
    """Trailing `months` calendar months ending with asof's month (oldest→newest).

    Returns (label 'YYYY-MM', is_partial) — the final (current) month is partial/MTD.
    """
    out: list[tuple[str, bool]] = []
    y, m = asof.year, asof.month
    for _ in range(months):
        out.append((f"{y:04d}-{m:02d}", False))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    out.reverse()
    out[-1] = (out[-1][0], True)   # current month is month-to-date
    return out


def _pull(source: str) -> pd.DataFrame:
    # Real opportunities only — exclude ~21k inert records (assigned_at only, blank
    # status, stage 'None') that never entered the pipeline and would inflate "Assigned".
    where = (
        "assigned_at IS NOT NULL AND ("
        "qualifying_stage_started_at IS NOT NULL OR proposal_stage_started_at IS NOT NULL "
        "OR offer_stage_started_at IS NOT NULL OR contracted_on IS NOT NULL "
        "OR closed_stage_started_at IS NOT NULL OR completed_stage_started_at IS NOT NULL "
        "OR LOWER(IFNULL(sales_status,'')) = 'open')"
    )
    if source in ("inbound", "repeat"):
        where += f" AND lead_source = '{source}'"
    sql = f"""
    SELECT lead_source, assigned_at, qualifying_stage_started_at,
           proposal_stage_started_at, offer_stage_started_at, contracted_on
    FROM {TBL}
    WHERE {where}
    """
    df = run_query(sql)
    for c in TS_COLS:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def build(months: list[tuple[str, bool]], source: str = "both") -> pd.DataFrame:
    """Return stage-entry flow: one row per stage, one column per month label."""
    df = _pull(source)
    labels = [lbl for lbl, _ in months]
    entered = {key: df[col].dt.strftime("%Y-%m").value_counts() for key, _, col in STAGES}
    out = pd.DataFrame({"stage": [lbl for _, lbl, _ in STAGES]})
    for label in labels:
        out[label] = [int(entered[key].get(label, 0)) for key, _, _ in STAGES]
    return out


# ---------- report ----------
_DEFS = """
<hr>
<h2>How to read this</h2>
<p>Each cell is the number of opps that <b>entered that stage during that month</b> —
funnel throughput, from the reliably-recorded stage-entry timestamps. It is a flow by
calendar month, <b>not a cohort funnel</b>: an opp that entered Proposed in May may have
been Assigned in an earlier month, so columns don't sum top-to-bottom. The final month is
<b>month-to-date</b> (partial).</p>
<p><b>Why flow, not 'opps currently in each stage'?</b> Stage <i>entry</i> times are
reliable but stage <i>exit</i> / loss times are not (loss timestamps are often backfilled
to an earlier date), so a trustworthy point-in-time "who is sitting in each stage on date
X" cannot be reconstructed from this data. Entry flow is the robust view of funnel
activity over time.</p>
<p><b>Scope:</b> real opportunities only — reached <code>assigned</code> with a downstream
signal or currently open; ~21k inert records excluded.</p>
<table>
<tr><th>Stage</th><th>Counted in the month the opp…</th></tr>
<tr><td>Assigned</td><td>was assigned to an agent (<code>assigned_at</code>).</td></tr>
<tr><td>Qualifying</td><td>entered qualifying (<code>qualifying_stage_started_at</code>).</td></tr>
<tr><td>Proposed</td><td>entered proposal (<code>proposal_stage_started_at</code>).</td></tr>
<tr><td>Firm offer</td><td>entered offer (<code>offer_stage_started_at</code>).</td></tr>
<tr><td>Booked</td><td>contracted (<code>contracted_on</code>) — both inbound &amp; repeat.</td></tr>
</table>
"""


def _report_html(table: pd.DataFrame, months: list[tuple[str, bool]], source: str) -> str:
    cols = [(lbl, f"{lbl} (MTD)" if partial else lbl, "int") for lbl, partial in months]
    scope = {"both": "both inbound + repeat", "inbound": "inbound only",
             "repeat": "repeat only"}[source]
    # chart uses completed months only, so the partial current month isn't a false cliff
    completed = [lbl for lbl, partial in months if not partial]
    series = {row["stage"]: [int(row[lbl]) for lbl in completed] for _, row in table.iterrows()}
    chart = line_chart_svg(completed, series, title="Opps entering each stage per month")
    body = [
        "<h1>Funnel stage-entry flow by month</h1>",
        f"<p>Opps that <i>entered</i> each sales stage per month ({scope}) — funnel "
        f"throughput over time. The final table column is month-to-date; the chart shows "
        f"completed months only.</p>",
        chart,
        html_table(table, "stage", cols),
    ]
    return "\n".join(body) + _DEFS


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Funnel stage-entry flow by month.")
    p.add_argument("--months", type=int, default=18, help="Number of trailing months (default 18).")
    p.add_argument("--source", choices=["both", "inbound", "repeat"], default="both")
    p.add_argument("--asof", default=None, help="Override 'today' (YYYY-MM-DD); default today.")
    p.add_argument("--name", default="funnel_stage", help="Output basename (default: funnel_stage).")
    args = p.parse_args(argv)

    asof = date.fromisoformat(args.asof) if args.asof else date.today()
    months = derive_months(asof, args.months)
    table = build(months, args.source)

    OUT.mkdir(exist_ok=True)
    table.to_csv(OUT / f"{args.name}_stage_flow.csv", index=False)
    # report defines its own (stage) glossary, so skip the standard metric glossary
    path = write_report(args.name, _report_html(table, months, args.source),
                        title="Funnel stage-entry flow by month", include_glossary=False)
    print(f"Wrote {OUT / f'{args.name}_stage_flow.csv'} + {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
