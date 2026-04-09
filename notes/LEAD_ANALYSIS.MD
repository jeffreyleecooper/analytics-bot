# BigQuery Data Reference for Lead & Sales Analysis

Reference for the source table, commonly used fields, and the business definitions used to derive lead and sales metrics. Covers **both inbound and repeat** business — do not silently restrict to one without a reason.

## Source Table

**`all-american-entertainment.one_off_opps_review.1_mega_opps_live`**

## Lead Sources

`lead_source` has two values:

| value | what it is | typical share |
|---|---|---|
| `inbound` | New leads from web/phone/etc. that enter the top of the sales funnel. | ~88% of rows |
| `repeat` | Repeat business from existing clients. No marketing-funnel stage — these come back directly. | ~12% of rows, but ~half of commission revenue. |

**Default behavior: include both.** Any analysis that scopes to a single `lead_source` should be doing so deliberately and should say so explicitly. Reporting on "the business" without `repeat` understates revenue by roughly 50%.

## Date Axes — pick the right one for the metric

The table has **two date columns** and they answer different questions. Using the wrong one will produce nonsense numbers.

| column | type | meaning | use it for |
|---|---|---|---|
| `created_at` | DATETIME | When the lead/opportunity record was created. | **Top-of-funnel metrics**: `leads`, `assigned`, lead-source mix, lead-origin trends, intake quality. Bucketing by `created_at` measures *when demand arrived*. |
| `contracted_on` | DATETIME | When the opportunity was contracted (booked). Null for leads that never booked. | **Booked / revenue metrics**: `booked`, `gross_fee`, `commission_fee`, win rate. Bucketing by `contracted_on` measures *when revenue was earned* and is the axis the business dashboards use. |

**Why this matters:** a lead created in Q4 2025 that contracts in Q1 2026 is Q1 2026 *revenue* but Q4 2025 *demand*. If you bucket bookings by `created_at`, recent periods look artificially weak because their pipeline hasn't closed yet. **Always bucket revenue by `contracted_on` when comparing periods.** Repeat business especially has no meaningful `created_at`-vs-`contracted_on` distinction at the funnel level — it should always be bucketed by `contracted_on`.

A self-consistent quarterly analysis typically reports:
- **Funnel metrics** (`leads`, `assigned`, conversion rates) by `created_at`, **inbound only** (repeat has no funnel).
- **Booked/revenue metrics** (`booked`, `gross_fee`, `commission_fee`) by `contracted_on`, **all sources**, optionally split inbound vs repeat.

## Fields Used Often in Analysis

| Field | Type | Description |
|---|---|---|
| `created_at` | datetime | When the lead/opportunity record was created. See date-axis guidance above. |
| `contracted_on` | datetime | When the opportunity was contracted (booked). Null for leads that never booked. See date-axis guidance above. |
| `lead_source` | string | `inbound` or `repeat`. See above. |
| `lead_origin` | string | Sub-segmentation of an inbound lead's origin (e.g. `aaespeakers.com`). **Mostly null for `repeat`** — only meaningful for inbound. |
| `lead_status` | string | Disposition of the lead. Values of `doa` or `spam` (case-insensitive) are treated as unqualified. |
| `sales_status` | string | Sales pipeline state. A value of `open` (case-insensitive) marks the lead as still in progress. |
| `sales_agent` | string | Sales agent assigned to the opportunity. Populated for ~95% of repeat rows and ~25% of inbound rows. |
| `std_budget` | string | Standardized client budget bucket. **Mostly null for `repeat`** — only meaningful for inbound. See ordered sequence below. |
| `ad_presence` | string | Whether/how the opportunity was associated with advertising. Populated for both sources, but `repeat` is overwhelmingly `non-ad` by definition. |
| `assigned` | numeric (0/1) | Flag indicating the lead was assigned to a sales agent. Sum to count assignments. |
| `booked` | numeric (0/1) | Flag indicating the opportunity was booked/contracted. Sum to count bookings. |
| `commission_fee` | numeric | Commission revenue on the opportunity. |
| `gross_fee` | numeric | Gross fee (talent + commission) on the opportunity. |

When aggregating, numeric columns should be coerced to numbers and null-filled with `0`. String segment columns should be null-filled with `"Unknown"` so groupby operations don't drop rows.

## Budget Ordering

`std_budget` values, in their canonical low-to-high order:

1. I am looking for Talent to donate their time
2. $5,000 or less
3. $5,000 - $10,000
4. $10,000 - $20,000
5. $20,000 - $30,000
6. $30,000 - $50,000
7. $50,000 - $100,000
8. $100,000 and above
9. I have a budget, but I am unsure of what it is
10. Unknown

## Derived Flags (Row-Level)

- **`qualified_lead`** — `1` when `lead_status` is *not* `doa` or `spam`, else `0`. Anything that isn't dead-on-arrival or spam counts as a real lead. Mainly relevant to inbound funnel analysis.
- **`open_lead`** — `1` when `sales_status == "open"`, else `0`. Identifies leads still in the pipeline (not yet won or lost).

## Metric Definitions

Standard aggregations sum the row-level flags/amounts above:

| Metric | Definition |
|---|---|
| `leads` | Sum of `qualified_lead` — total qualified inbound leads (excludes DOA/spam). Bucket by `created_at`. |
| `open_leads` | Sum of `open_lead` — leads still open in the sales pipeline. |
| `assigned` | Sum of `assigned` flag — leads handed to a sales agent. Bucket by `created_at`. |
| `booked` | Sum of `booked` flag — opportunities that contracted. **Bucket by `contracted_on`.** |
| `commission_fee` | Sum of commission revenue. **Bucket by `contracted_on`.** |
| `gross_fee` | Sum of gross fee revenue. **Bucket by `contracted_on`.** |

### Conversion Rates (inbound funnel)

- **`assigned_rate` = `assigned / leads`** — share of qualified leads that get assigned to an agent.
- **`booking_rate` = `booked / leads`** — share of qualified leads that ultimately book. Top-of-funnel close rate. Note: numerator and denominator should be measured against the same lead cohort (i.e. bucket the cohort by `created_at` and let bookings accrue over time), not against the same calendar window on different date axes.
- **`win_rate` = `booked / (assigned - open_leads)`** — share of *closed* assigned leads that booked. Open leads are removed from the denominator so still-in-progress deals don't deflate the rate. This is the agent-level close rate on resolved opportunities.

Divisions by zero should be filled with `0`.
