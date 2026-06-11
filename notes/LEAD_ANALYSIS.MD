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
| `created_at` | DATETIME | When the lead/opportunity record was created. | **Top-of-funnel metrics**: `total_leads`, `workable_leads`, `assigned`, lead-source mix, lead-origin trends, intake quality. Bucketing by `created_at` measures *when demand arrived*. |
| `contracted_on` | DATETIME | When the opportunity was contracted (booked). Null for leads that never booked. | **Booked / revenue metrics**: `booked`, `gross_fee`, `commission_fee`, win rate. Bucketing by `contracted_on` measures *when revenue was earned*. |

**Why this matters:** a lead created in Q4 2025 that contracts in Q1 2026 is Q1 2026 *revenue* but Q4 2025 *demand*. If you bucket bookings by `created_at`, recent periods look artificially weak because their pipeline hasn't closed yet. **Always bucket revenue by `contracted_on` when comparing periods.** Repeat business especially has no meaningful `created_at`-vs-`contracted_on` distinction at the funnel level — it should always be bucketed by `contracted_on`.

A self-consistent quarterly analysis typically reports:
- **Funnel metrics** (`total_leads`, `workable_leads`, `assigned`, conversion rates) by `created_at`, **inbound only** (repeat has no funnel).
- **Booked/revenue metrics** (`booked`, `gross_fee`, `commission_fee`) by `contracted_on`, **all sources**, optionally split inbound vs repeat.

## Fields Used Often in Analysis

| Field | Type | Description |
|---|---|---|
| `created_at` | datetime | When the lead/opportunity record was created. See date-axis guidance above. |
| `contracted_on` | datetime | When the opportunity was contracted (booked). Null for leads that never booked. See date-axis guidance above. |
| `lead_source` | string | `inbound` or `repeat`. See above. |
| `lead_origin` | string | Sub-segmentation of an inbound lead's origin (e.g. `aaespeakers.com`). **Mostly null for `repeat`** — only meaningful for inbound. |
| `lead_status` | string | Disposition of the lead. Observed values: `doa`, `spam`, `duplicate`, `closed`, `open`, or null. See the funnel ladder below for how each is treated. |
| `machine_doa` | numeric (0/1) | `1` = the lead was auto-DOA'd by an automated/machine filter; `0` = not machine-flagged (includes human-marked DOAs). Only meaningful when `lead_status = 'doa'`. |
| `doa_reason` | string | Why a lead was DOA'd: `No/Low Budget`, `Not Viable`, `Weak Opportunity`, `Marketing Request`, or null. Populated on both machine and human DOAs — **not** a machine signal by itself. |
| `sales_status` | string | Sales pipeline state. A value of `open` (case-insensitive) marks the lead as still in progress. |
| `sales_agent` | string | Sales agent assigned to the opportunity. Populated for ~95% of repeat rows and ~25% of inbound rows. |
| `std_budget` | string | Standardized client budget bucket. **Mostly null for `repeat`** — only meaningful for inbound. See ordered sequence below. |
| `ad_presence` | string | Whether/how the opportunity was associated with advertising. Populated for both sources, but `repeat` is overwhelmingly `non-ad` by definition. |
| `assigned` | numeric (0/1) | Flag indicating the lead was assigned to a sales agent. Sum to count assignments. |
| `booked` | numeric (0/1) | Flag indicating the opportunity was booked/contracted. Sum to count bookings. |
| `commission_fee` | numeric | Commission revenue on the opportunity. |
| `gross_fee` | numeric | Gross fee (talent + commission) on the opportunity. |
| `proposal_stage_started_at` | datetime | When the opportunity entered the proposal stage. NULL if the stage was never reached. **Use this — not `proposal_stage_basis` — to detect that proposal was hit.** |
| `offer_stage_started_at` | datetime | When the opportunity entered the offer stage. NULL if the stage was never reached. Some opps skip proposal and go straight assigned → offer. **Use this — not `offer_stage_basis` — to detect that offer was hit.** |

When aggregating, numeric columns should be coerced to numbers and null-filled with `0`. String segment columns should be null-filled with `"Unknown"` so groupby operations don't drop rows.

For inbound source-mix analysis, segment by the intersection of **`lead_origin` × `ad_presence`** unless the user asks for only one of those dimensions. This separates website/source effects from ad vs non-ad traffic effects.

**Aside on `*_basis` columns:** the table also has `proposal_stage_basis`, `offer_stage_basis`, etc. These are populated on 100% of rows — they equal the corresponding `*_started_at` when the stage was hit, and fall back to a default timestamp (≈ `created_at`) otherwise. They are *not* the "stage was reached" signal. Always use `*_stage_started_at IS NOT NULL` for that.

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

## Funnel Ladder (canonical stages)

Inbound only — `repeat` has no funnel. Each stage is (roughly) a subset of the one above; bucket all of these by `created_at`.

1. **Total leads** — every lead row, regardless of `lead_status`. The raw top of funnel.
2. **Workable leads** — leads with no *credible* evidence they're dead. Excludes `spam`, `duplicate`, and the DOA reasons we trust as genuinely dead (`doa` with no reason, `Marketing Request`, or `Not Viable`). **Deliberately retains** `doa` rows flagged `Weak Opportunity` or `No/Low Budget`, because those dispositions are subjective and not always trustworthy — they may be real leads dismissed prematurely.
3. **Assigned lead** — reached the assigned stage (handed to a sales agent). Flag `assigned`.
4. **SQL (Sales Qualified Opp)** — reached the proposal or offer stage. Flag `qualified_assigned_lead`.
5. **Booked** — contracted / won. Flag `booked`. Feeds the revenue and rate definitions below.

### Row-Level Flags

- **`workable_lead`** (Workable leads) — `0` when `lead_status` is `spam` or `duplicate`, or when `lead_status = 'doa'` AND (`doa_reason` is null OR in `Marketing Request`, `Not Viable`); else `1`.
- **`open_lead`** — `1` when `sales_status == "open"`, else `0`. Identifies leads still in the pipeline (not yet won or lost).
- **`qualified_assigned_lead`** (SQL) — `1` when `proposal_stage_started_at IS NOT NULL OR offer_stage_started_at IS NOT NULL OR booked = 1`, else `0`. Marks an assigned lead that progressed to a real opportunity stage (proposal, offer, or already booked). The `booked = 1` clause covers ~1,200 inbound + ~900 repeat older bookings whose stage timestamps are not populated, so `SQL ≥ booked` always holds.

## Metric Definitions

Standard aggregations sum the row-level flags/amounts above:

| Metric | Definition |
|---|---|
| `total_leads` | Count of all inbound lead rows, any `lead_status`. Bucket by `created_at`. |
| `workable_leads` | Sum of `workable_lead` — the credible top of funnel (excludes spam, duplicates, and trusted-dead DOAs; keeps `Weak Opportunity` / `No/Low Budget`). Bucket by `created_at`. |
| `open_leads` | Sum of `open_lead` — leads still open in the sales pipeline. |
| `assigned` | Sum of `assigned` flag — leads handed to a sales agent. Bucket by `created_at`. |
| `qualified_assigned` (SQL) | Sum of `qualified_assigned_lead` — assigned leads that reached proposal, offer, or booked. Bucket by `created_at` (it's a funnel metric). |
| `booked` | Sum of `booked` flag — opportunities that contracted. **Bucket by `contracted_on`.** |
| `commission_fee` | Sum of commission revenue. **Bucket by `contracted_on`.** |
| `gross_fee` | Sum of gross fee revenue. **Bucket by `contracted_on`.** |

### Conversion Rates (inbound funnel)

- **`assigned_rate` = `assigned / workable_leads`** — share of workable leads that get assigned to an agent.
- **`qualified_assigned_rate` = `qualified_assigned / assigned`** — share of assigned leads that became real opportunities (reached proposal/offer or booked). Inbound runs ~49%; repeat ~22%, since most repeat work is informal and never logs a proposal stage. A useful "did we actually do sales work on this" gate, sitting between `assigned_rate` and `booking_rate`. Bucket by `created_at`.
- **`booking_rate` = `booked / qualified_assigned`** — share of *qualified* opportunities (those that reached proposal/offer or booked) that ultimately book. This is the close rate on real opportunities, not on raw inbound volume — using `workable_leads` as the denominator dilutes it with rows that were never worked. Note: numerator and denominator should be measured against the same cohort (i.e. bucket the cohort by `created_at` and let bookings accrue over time), not against the same calendar window on different date axes.
- **`win_rate` = `booked / (assigned - open_leads)`** — share of *closed* assigned leads that booked. Open leads are removed from the denominator so still-in-progress deals don't deflate the rate. This is the agent-level close rate on resolved opportunities.

Divisions by zero should be filled with `0`.
