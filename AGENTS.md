This project is for data analysis of lead and sales data for AAE. It contains scripts for easy access to requirements installation and querying the data source. It also has reference notes for understand data schema and metrics.

## Setup

Install Python dependencies from the root `requirements.txt`:

```bash
python scripts/setup.py
```

## Running BigQuery Queries

Use `scripts/run_query.py` to execute a BigQuery SQL string. Authentication is read automatically from `GOOGLE_CREDENTIALS_JSON` in the root `.env` (base64-encoded service-account JSON) — no extra setup needed.

CLI — pretty-print results, optionally write a CSV:

```bash
python scripts/run_query.py "SELECT lead_source, COUNT(*) AS n FROM \`all-american-entertainment.one_off_opps_review.1_mega_opps_live\` GROUP BY 1"
python scripts/run_query.py "SELECT ..." --csv notes/out.csv
```

Importable from other scripts:

```python
from scripts.run_query import run_query
df = run_query("SELECT 1 AS x")
```

Notes:
- The query argument must be an inline SQL string. Quote table names with backticks (escape them in shell as `\``).
- `run_query` returns a `pandas.DataFrame`; the CLI prints the full frame and only writes CSV when `--csv PATH` is supplied.

## Standard Analysis (start here for ~every inquiry)

Most lead / booking / commission questions want the **same matrix**: revenue (booked / commission / gross / avg per booking) by `contracted_on` across lead_source (inbound vs repeat), agent, lead_origin, ad_presence, and budget tier; plus the inbound funnel (total_leads / workable_leads / assigned / SQL + the conversion rates) by `created_at`. `scripts/standard_report.py` produces all of it — **tables only, no narrative** — for any set of date windows, honoring the analysis defaults below. Don't rebuild these queries by hand.

Run it (writes one CSV per table + a tables-only HTML data pack to `outputs/`):

```bash
python -m scripts.standard_report \
    --window current=2026-05-13:2026-06-11 \
    --window prior=2026-04-13:2026-05-12
```

The first `--window` is primary; relative changes are computed primary-vs-each-other-window. Add more windows for MTD / YoY framings (e.g. a third `--window ly=2025-05-13:2025-06-11`).

To assemble the **final report**, import the same tables and wrap them with your bespoke interpretation, then write raw HTML (see Outputs):

```python
from scripts.standard_report import build, parse_window
from scripts.report import write_report, html_table

tables = build([parse_window("current=2026-05-13:2026-06-11"),
                parse_window("prior=2026-04-13:2026-05-12")])
body  = "<h1>Inbound — 30d vs prior</h1>"
body += "<p>Bespoke read: commission −8% while gross +11% — mix shifted to larger, lower-take deals…</p>"
body += html_table(tables["rev_source"], "lead_source", [
    ("commission_fee__current", "Comm cur", "money"),
    ("commission_fee__prior",   "Comm prior", "money"),
    ("commission_fee__vs_prior", "Δ%", "pct")])
write_report("inbound_30d_vs_prior", body)
```

Table keys: `rev_source`, `rev_agent`, `rev_origin`, `rev_ad`, `rev_budget`, `fun_total`, `fun_agent`, `fun_origin`, `fun_ad`, `fun_budget`. Reach for fully custom SQL only when the question falls outside this matrix.

## Custom Analysis Scratch File

`scripts/analysis.py` is a scratch file for analyses that fall outside the standard matrix, or for the glue that assembles a bespoke report (import `build`, add notes, `write_report`). Use it freely for multi-step DataFrame work — overwrite its contents between tasks; it is not intended to hold durable code. Run with `python scripts/analysis.py`.

## Outputs

Save persisted analysis artifacts (CSV result sets, the final report, charts) under `outputs/`. When using `run_query.py --csv`, point it at `outputs/<name>.csv`. Keep file names descriptive of the analysis they came from.

**The report format is HTML, and only HTML.** Author the report as **raw HTML** and write it with the shared shell helper — there is no markdown intermediate and no `.md` deliverable:

```python
from scripts.report import write_report, html_table
body = "<h1>Inbound — 30d vs prior</h1><p>your bespoke notes…</p>"
body += html_table(df, "lead_source", [("commission_fee__current", "Comm cur", "money")])
write_report("inbound_30d_vs_prior", body)   # -> outputs/inbound_30d_vs_prior.html
```

`scripts/report.py` provides `write_report` (styled standalone HTML shell), `html_table` (DataFrame → HTML table fragment), and the `money` / `integer` / `pct` / `percent` formatters. (`scripts/md_to_html.py` remains only for the rare case of rendering a pre-existing `.md` with the same styling; it is **not** the default path.)

**Reset analysis state before starting a fresh analysis.** Stale CSVs and markdown from a previous run can be confused with current results, and old files often encode prior (sometimes wrong) methodology. At the start of any new analysis task, run `python scripts/reset.py` to (a) delete the existing contents of `outputs/` (the directory itself is kept) and (b) reset `scripts/analysis.py` back to its scratch shell. If the user is iterating on an in-progress analysis, do **not** run this — only clear files belonging to that same analysis manually.

## Analysis Defaults — Read Before Writing Queries

These defaults apply to any analysis against `1_mega_opps_live`. Violating them silently produces results that will not reconcile with the business dashboards.

1. **Include both `inbound` and `repeat` lead sources by default.** `lead_source` has two values: `inbound` (~88% of rows) and `repeat` (~12% of rows but ~half of commission revenue). Filtering to one without a stated reason understates the business by roughly 50%. Only scope to a single source when the question is explicitly funnel-shaped (inbound only) or explicitly about repeat clients.

2. **Bucket booked / revenue metrics by `contracted_on`, not `created_at`.** The table has two date columns:
   - `created_at` — when the lead/opportunity record was created. Use this only for **funnel metrics** (`total_leads`, `workable_leads`, `assigned`, SQL, lead-source mix, intake quality). It measures *when demand arrived*.
   - `contracted_on` — when the opportunity contracted. **Use this for `booked`, `gross_fee`, `commission_fee`, and any "performance / revenue" question.** It measures *when revenue was earned* and is the axis the business dashboards key on.

   A lead created in Q4 that contracts in Q1 is Q1 *revenue* but Q4 *demand*. Bucketing bookings by `created_at` makes recent periods look artificially weak because their pipeline hasn't closed yet. Repeat business in particular has no meaningful funnel and should always be bucketed by `contracted_on`.

3. **A self-consistent quarterly analysis usually splits into two views:**
   - **Revenue view** — `booked` / `gross_fee` / `commission_fee` by `contracted_on`, both sources, optionally split inbound vs repeat.
   - **Funnel view** — `total_leads` / `workable_leads` / `assigned` / SQL / conversion rates by `created_at`, inbound only.

4. **Sanity-check headline numbers against the business dashboards before publishing takeaways.** If your Q1 booked count or commission total disagrees with the dashboard by more than rounding, something is wrong with the methodology — stop and reconcile before drawing conclusions.

Full field reference, metric definitions, and budget ordering: [notes/LEAD_ANALYSIS.MD](notes/LEAD_ANALYSIS.MD).

## Available Documentation

### Notes

- [notes/LEAD_ANALYSIS.MD](notes/LEAD_ANALYSIS.MD) — Reference for analyzing leads and sales from `all-american-entertainment.one_off_opps_review.1_mega_opps_live`. Covers **both inbound and repeat** business, the source table, commonly-used fields, the canonical `std_budget` ordering, the funnel ladder (Total → Workable → Assigned → SQL → Booked), derived row-level flags (`workable_lead`, `open_lead`, `qualified_assigned_lead`), metric definitions (`total_leads`, `workable_leads`, `assigned`, `qualified_assigned`/SQL, `booked`, revenue), conversion-rate formulas (`assigned_rate`, `qualified_assigned_rate`, `booking_rate`, `win_rate`), and the **two date axes** — `created_at` for funnel metrics, `contracted_on` for booked/revenue metrics. **Use when:** writing queries or analyses involving leads, sales-agent performance, booking rates, revenue trends, or budget segmentation. **Default to including both `inbound` and `repeat`** unless the question is explicitly funnel-only; **always bucket booked/revenue metrics by `contracted_on`**, not `created_at`.
