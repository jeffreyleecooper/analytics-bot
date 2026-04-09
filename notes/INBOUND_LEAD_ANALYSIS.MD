# BigQuery Data Reference for Inbound Lead Analysis

Reference for the source table, commonly used fields, and the business definitions used to derive lead metrics.

## Source Table

**`all-american-entertainment.one_off_opps_review.1_mega_opps_live`**

## Fields Used Often in Analysis

| Field | Type | Description |
|---|---|---|
| `created_at` | timestamp | When the lead/opportunity record was created. Primary date axis for "by created date" views. |
| `contracted_on` | timestamp | When the opportunity was contracted (booked). Null for leads that never booked.  |
| `lead_source` | string | Origin channel of the lead. Filter to `lead_source == "inbound"` to scope to inbound leads. |
| `lead_origin` | string | Sub-segmentation of the lead's origin. |
| `lead_status` | string | Disposition of the lead. Values of `doa` or `spam` (case-insensitive) are treated as unqualified. |
| `sales_status` | string | Sales pipeline state. A value of `open` (case-insensitive) marks the lead as still in progress. |
| `sales_agent` | string | Sales agent assigned to the opportunity. |
| `std_budget` | string | Standardized client budget bucket. See ordered sequence below. |
| `ad_presence` | string | Whether/how the opportunity was associated with advertising. |
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

- **`qualified_lead`** — `1` when `lead_status` is *not* `doa` or `spam`, else `0`. Anything that isn't dead-on-arrival or spam counts as a real lead.
- **`open_lead`** — `1` when `sales_status == "open"`, else `0`. Identifies leads still in the pipeline (not yet won or lost).

## Metric Definitions

Standard aggregations sum the row-level flags/amounts above:

| Metric | Definition |
|---|---|
| `leads` | Sum of `qualified_lead` — total qualified inbound leads (excludes DOA/spam). |
| `open_leads` | Sum of `open_lead` — leads still open in the sales pipeline. |
| `assigned` | Sum of `assigned` flag — leads handed to a sales agent. |
| `booked` | Sum of `booked` flag — opportunities that contracted. |
| `commission_fee` | Sum of commission revenue. |
| `gross_fee` | Sum of gross fee revenue. |

### Conversion Rates

- **`assigned_rate` = `assigned / leads`** — share of qualified leads that get assigned to an agent.
- **`booking_rate` = `booked / leads`** — share of qualified leads that ultimately book. Top-of-funnel close rate.
- **`win_rate` = `booked / (assigned - open_leads)`** — share of *closed* assigned leads that booked. Open leads are removed from the denominator so still-in-progress deals don't deflate the rate. This is the agent-level close rate on resolved opportunities.

Divisions by zero should be filled with `0`.
