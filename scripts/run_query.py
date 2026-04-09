"""Run a BigQuery SQL query and return / display the results.

Importable:
    from scripts.run_query import run_query
    df = run_query("SELECT 1 AS x")

CLI:
    python scripts/run_query.py "SELECT 1 AS x"
    python scripts/run_query.py "SELECT ..." --csv out.csv
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _client() -> bigquery.Client:
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not raw:
        raise RuntimeError(
            "GOOGLE_CREDENTIALS_JSON is not set. Add it to .env at the project root."
        )
    # Value is base64-encoded service-account JSON.
    info = json.loads(base64.b64decode(raw))
    creds = service_account.Credentials.from_service_account_info(info)
    return bigquery.Client(credentials=creds, project=info.get("project_id"))


def run_query(sql: str) -> pd.DataFrame:
    """Execute `sql` against BigQuery and return the result as a DataFrame."""
    return _client().query(sql).to_dataframe()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run a BigQuery SQL query.")
    p.add_argument("sql", help="Inline SQL string to execute.")
    p.add_argument(
        "--csv",
        metavar="PATH",
        help="Optional path to write results as CSV (in addition to pretty print).",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    df = run_query(args.sql)

    with pd.option_context(
        "display.max_rows", None,
        "display.max_columns", None,
        "display.width", None,
    ):
        print(df.to_string(index=False))

    if args.csv:
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        print(f"\nWrote {len(df)} rows to {out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
