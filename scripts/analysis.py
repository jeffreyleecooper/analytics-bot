"""Scratch file for ad-hoc lead/sales analysis.

Use this file to build, iterate on, and run custom queries or DataFrame
transformations. Overwrite freely between tasks — it is not meant to hold
durable code.

Example:
    from scripts.run_query import run_query

    df = run_query('''
        SELECT lead_source, COUNT(*) AS n
        FROM `all-american-entertainment.one_off_opps_review.1_mega_opps_live`
        GROUP BY 1
    ''')
    print(df)
"""
from scripts.run_query import run_query  # noqa: F401


if __name__ == "__main__":
    pass
