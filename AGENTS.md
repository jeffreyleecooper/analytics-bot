This is a directory of documentation to orient you with completing technical tasks.

When a task touches one of the domains below, read the corresponding file before proposing changes or running queries — these documents capture business definitions and conventions that are not derivable from raw schemas alone.

## Available Documentation

### BigQuery

- [bigquery/INBOUND_LEAD_ANALYSIS.MD](bigquery/INBOUND_LEAD_ANALYSIS.MD) — Reference for analyzing inbound leads from `all-american-entertainment.one_off_opps_review.1_mega_opps_live`. Covers the source table, commonly-used fields, the canonical `std_budget` ordering, derived row-level flags (`qualified_lead`, `open_lead`), metric definitions (`leads`, `assigned`, `booked`, revenue), conversion-rate formulas (`assigned_rate`, `booking_rate`, `win_rate`), and date-axis semantics (created vs. contracted). **Use when:** writing queries or analyses involving inbound leads, lead qualification, sales-agent conversion, booking rates, or budget segmentation.
