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

## Custom Analysis Scratch File

`scripts/analysis.py` is a scratch file for building ad-hoc analyses on top of `run_query`. Use it freely when a task calls for multi-step DataFrame work that doesn't fit on a single CLI line — overwrite its contents between tasks; it is not intended to hold durable code. Run with `python scripts/analysis.py`.

## Outputs

Save any persisted analysis artifacts (CSV result sets, markdown writeups, charts, etc.) under `outputs/`. When using `run_query.py --csv`, point it at `outputs/<name>.csv`. When summarizing findings as markdown, write the file to `outputs/<name>.md`. Keep file names descriptive of the analysis they came from.

**Always also produce an HTML version of any markdown writeup.** After writing `outputs/<name>.md`, render `outputs/<name>.html` alongside it using the helper:

```bash
python -m scripts.md_to_html outputs/<name>.md
```

Or from Python:

```python
from scripts.md_to_html import md_to_html
md_to_html("outputs/<name>.md")
```

The two files should always travel together — markdown for editing/source-of-truth, HTML for sharing/viewing in a browser.

**Clear `outputs/` before starting a fresh analysis.** Stale CSVs and markdown from a previous run can be confused with current results, and old files often encode prior (sometimes wrong) methodology. At the start of any new analysis task, run `python scripts/clear_outputs.py` to delete the existing contents of `outputs/` (the directory itself is kept). If the user is iterating on an in-progress analysis, do **not** run this — only clear files belonging to that same analysis manually.

## Analysis Defaults — Read Before Writing Queries

These defaults apply to any analysis against `1_mega_opps_live`. Violating them silently produces results that will not reconcile with the business dashboards.

1. **Include both `inbound` and `repeat` lead sources by default.** `lead_source` has two values: `inbound` (~88% of rows) and `repeat` (~12% of rows but ~half of commission revenue). Filtering to one without a stated reason understates the business by roughly 50%. Only scope to a single source when the question is explicitly funnel-shaped (inbound only) or explicitly about repeat clients.

2. **Bucket booked / revenue metrics by `contracted_on`, not `created_at`.** The table has two date columns:
   - `created_at` — when the lead/opportunity record was created. Use this only for **funnel metrics** (`leads`, `assigned`, lead-source mix, intake quality). It measures *when demand arrived*.
   - `contracted_on` — when the opportunity contracted. **Use this for `booked`, `gross_fee`, `commission_fee`, and any "performance / revenue" question.** It measures *when revenue was earned* and is the axis the business dashboards key on.

   A lead created in Q4 that contracts in Q1 is Q1 *revenue* but Q4 *demand*. Bucketing bookings by `created_at` makes recent periods look artificially weak because their pipeline hasn't closed yet. Repeat business in particular has no meaningful funnel and should always be bucketed by `contracted_on`.

3. **A self-consistent quarterly analysis usually splits into two views:**
   - **Revenue view** — `booked` / `gross_fee` / `commission_fee` by `contracted_on`, both sources, optionally split inbound vs repeat.
   - **Funnel view** — `leads` / `assigned` / conversion rates by `created_at`, inbound only.

4. **Sanity-check headline numbers against the business dashboards before publishing takeaways.** If your Q1 booked count or commission total disagrees with the dashboard by more than rounding, something is wrong with the methodology — stop and reconcile before drawing conclusions.

Full field reference, metric definitions, and budget ordering: [notes/LEAD_ANALYSIS.MD](notes/LEAD_ANALYSIS.MD).

## Available Documentation

### Notes

- [notes/LEAD_ANALYSIS.MD](notes/LEAD_ANALYSIS.MD) — Reference for analyzing leads and sales from `all-american-entertainment.one_off_opps_review.1_mega_opps_live`. Covers **both inbound and repeat** business, the source table, commonly-used fields, the canonical `std_budget` ordering, derived row-level flags (`qualified_lead`, `open_lead`), metric definitions (`leads`, `assigned`, `booked`, revenue), conversion-rate formulas (`assigned_rate`, `booking_rate`, `win_rate`), and the **two date axes** — `created_at` for funnel metrics, `contracted_on` for booked/revenue metrics. **Use when:** writing queries or analyses involving leads, sales-agent performance, booking rates, revenue trends, or budget segmentation. **Default to including both `inbound` and `repeat`** unless the question is explicitly funnel-only; **always bucket booked/revenue metrics by `contracted_on`**, not `created_at`.
