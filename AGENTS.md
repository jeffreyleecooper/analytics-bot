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

## Available Documentation

### Notes

- [notes/INBOUND_LEAD_ANALYSIS.MD](notes/INBOUND_LEAD_ANALYSIS.MD) — Reference for analyzing inbound leads from `all-american-entertainment.one_off_opps_review.1_mega_opps_live`. Covers the source table, commonly-used fields, the canonical `std_budget` ordering, derived row-level flags (`qualified_lead`, `open_lead`), metric definitions (`leads`, `assigned`, `booked`, revenue), conversion-rate formulas (`assigned_rate`, `booking_rate`, `win_rate`), and date-axis semantics (created vs. contracted). **Use when:** writing queries or analyses involving inbound leads, lead qualification, sales-agent conversion, booking rates, or budget segmentation.
