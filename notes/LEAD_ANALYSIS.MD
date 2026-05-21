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

When reporting percentage changes, show both:
- **PoP** — current period vs the equivalent immediately prior period.
- **YoY** — current period vs the same calendar window in the prior year.

Do not show only one of PoP or YoY when making a percentage comparison unless the user explicitly asks for a single comparison.

## Fields Used Often in Analysis

| Field | Type | Description |
|---|---|---|
| `created_at` | datetime | When the lead/opportunity record was created. See date-axis guidance above. |
| `contracted_on` | datetime | When the opportunity was contracted (booked). Null for leads that never booked. See date-axis guidance above. |
| `lead_source` | string | `inbound` or `repeat`. See above. |
| `lead_origin` | string | Sub-segmentation of an inbound lead's origin (e.g. `aaespeakers.com`). **Mostly null for `repeat`** — only meaningful for inbound. |
| `lead_status` | string | Disposition of the lead. Values of `doa` or `spam` (case-insensitive) are excluded from **valid leads**. Do not call this filter "qualified"; qualified means stage progression below. |
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

For inbound source-mix analysis, segment by the intersection of **`lead_origin` × `ad_presence`** unless the user asks for only one of those dimensions. This distinguishes website/source effects from ad vs non-ad traffic effects.

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

## Derived Flags (Row-Level)

Use these names carefully. In business-facing analysis, **qualified lead** means the lead progressed to proposal or offer stage. A lead that is merely not DOA/spam is a **valid lead**, not a qualified lead.

- **`valid_lead`** — `1` when `lead_status` is *not* `doa` or `spam`, else `0`. This is the clean top-of-funnel count after junk filtering. Mainly relevant to inbound funnel analysis.
- **`open_lead`** — `1` when `sales_status == "open"`, else `0`. Identifies leads still in the pipeline (not yet won or lost).
- **`assigned_lead`** — `1` when `assigned = 1`, else `0`. Marks leads handed to a sales agent.
- **`active_assigned_unqualified_lead`** — `1` when `assigned = 1`, proposal and offer stage have not been reached, and `sales_status == "open"`, else `0`. Use this to estimate remaining near-term potential in a recent created-date cohort.
- **`stage_qualified_lead`** — `1` when `proposal_stage_started_at IS NOT NULL OR offer_stage_started_at IS NOT NULL`, else `0`. This is the preferred "qualified lead" definition for funnel-quality analysis.
- **`qualified_assigned_lead`** — legacy/historical compatibility flag: `1` when `proposal_stage_started_at IS NOT NULL OR offer_stage_started_at IS NOT NULL OR booked = 1`, else `0`. Use this only when you need booked-row fallback for older records whose stage timestamps are missing; label it explicitly as "qualified + booked fallback."

## Metric Definitions

Standard aggregations sum the row-level flags/amounts above:

| Metric | Definition |
|---|---|
| `raw_inbound_records` | Count of every inbound row created in the period. Bucket by `created_at`. |
| `valid_leads` | Sum of `valid_lead` — inbound leads excluding DOA/spam. Bucket by `created_at`. |
| `open_leads` | Sum of `open_lead` — leads still open in the sales pipeline. |
| `assigned` | Sum of `assigned` flag — leads handed to a sales agent. Bucket by `created_at`. |
| `active_leads` | Sum of `active_assigned_unqualified_lead` — assigned, still-open leads that have not yet reached proposal or offer. Useful for recent periods where qualification may not have matured yet. |
| `qualified_leads` / `stage_qualified_leads` | Sum of `stage_qualified_lead` — leads that reached proposal or offer stage. Bucket by `created_at` (it's a funnel metric). |
| `qualified_assigned` | Sum of `qualified_assigned_lead` — proposal/offer stage reached, with booked fallback for older records. Bucket by `created_at`; label this as "qualified + booked fallback" when reporting. |
| `valid_expected_value` / `valid_ev` | Sum of marketing expected lead value for valid leads only (`marketing_expected_lead_value * valid_lead`). Expected value should not be aggregated or reported for raw records, assigned leads, active leads, qualified leads, booked leads, or open leads. |
| `booked` | Sum of `booked` flag — opportunities that contracted. **Bucket by `contracted_on`.** |
| `commission_fee` | Sum of commission revenue. **Bucket by `contracted_on`.** |
| `gross_fee` | Sum of gross fee revenue. **Bucket by `contracted_on`.** |

### Conversion Rates (inbound funnel)

- **`assigned_rate` = `assigned / valid_leads`** — share of valid, non-DOA/spam inbound leads that get assigned to an agent.
- **`stage_qualification_rate` = `stage_qualified_leads / assigned`** — share of assigned leads that became real opportunities by reaching proposal or offer stage. This is the preferred lead-quality/progression metric.
- **`qualified_assigned_rate` = `qualified_assigned / assigned`** — legacy compatible version of the above that also counts booked rows with missing stage timestamps. Use only when you need the booked fallback, and label it clearly.
- **`booking_rate` = `booked / qualified_assigned`** — share of qualified opportunities (proposal/offer, plus booked fallback where needed) that ultimately book. This is the close rate on real opportunities, not on raw inbound volume — using `valid_leads` as the denominator dilutes it with DOA/spam-filtered-but-never-worked rows. Note: numerator and denominator should be measured against the same cohort (i.e. bucket the cohort by `created_at` and let bookings accrue over time), not against the same calendar window on different date axes.
- **`win_rate` = `booked / (assigned - open_leads)`** — share of *closed* assigned leads that booked. Open leads are removed from the denominator so still-in-progress deals don't deflate the rate. This is the agent-level close rate on resolved opportunities.

Divisions by zero should be filled with `0`.
