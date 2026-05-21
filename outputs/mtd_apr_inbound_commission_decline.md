# MTD April 2026 vs 2025 — Why is volume up but commission down?

**Window:** April 1–28 each year, bucketed by `contracted_on` (revenue side). Funnel volumes use `created_at` and are inbound-only.

## Headline

| | 2025 MTD | 2026 MTD | Δ | YoY |
|---|---:|---:|---:|---:|
| Bookings | 147 | 154 | +7 | +4.8% |
| Gross fee | $5,691,005 | $5,086,000 | -$605,005 | -10.6% |
| **Commission** | **$1,536,703** | **$1,261,310** | **-$275,393** | **-17.9%** |

Volume up, commission down — confirmed. The decline lives entirely on **inbound**; **repeat is up**.

## 1. Repeat vs Inbound — repeat is healthy, inbound is the problem

| Source | Bookings 25→26 | Commission 25→26 | Δ Commission | Avg comm/booking 25→26 |
|---|---:|---:|---:|---:|
| **Repeat** | 68 → 75 (+10%) | $676,500 → $752,285 | **+$75,785 (+11%)** | $9,949 → $10,030 (~flat) |
| **Inbound** | 79 → 79 (flat) | $860,203 → $509,025 | **-$351,178 (-41%)** | **$10,889 → $6,443 (-41%)** |

Inbound booked the **same number of deals** but each one is worth ~40% less in commission. So this is a **revenue-per-deal / mix problem**, not a volume problem.

## 2. Within Inbound — the damage is in the high-end / unknown-budget brackets

| Budget bucket | Booked 25→26 | Commission 25→26 | Δ Commission | Avg comm 25→26 |
|---|---:|---:|---:|---:|
| $5K or less | 1 → 1 | $2,500 → $2,500 | $0 | flat |
| $5K–10K | 19 → 15 | $55,375 → $45,025 | -$10,350 | flat (~$3K) |
| $10K–20K | 15 → **22** | $72,750 → $95,750 | **+$23,000** | flat (~$4.5K) |
| $20K–30K | 7 → **14** | $48,250 → $103,625 | **+$55,375** | flat (~$7.4K) |
| $30K–50K | 3 → **7** | $27,500 → $66,175 | **+$38,675** | flat (~$9.4K) |
| $50K–100K | 1 → 2 | $12,500 → $21,500 | +$9,000 | flat |
| **$100K+** | **3 → 1** | **$95,375 → $5,000** | **-$90,375** | $31,792 → $5,000 |
| Unsure | 20 → 14 | $161,453 → $106,950 | -$54,503 | flat (~$8K) |
| **Unknown** | **10 → 3** | **$384,500 → $62,500** | **-$322,000** | $38,450 → $20,833 |

Mid-tier ($10K–$50K) is **growing nicely** — +$117K commission, +18 bookings, with stable unit economics. The bleed is entirely in two buckets:

- **"Unknown" budget**: -$322K (was the single biggest commission contributor in 2025).
- **"$100K and above"**: -$90K (only 1 booking and at a $5K commission, vs. an avg of $32K last year).

Together those two buckets are -$412K — more than the entire $351K inbound decline. The "Unsure" bucket adds another -$54K.

In short: **we are losing the big-fish inbound deals**, and the mid-tier growth isn't enough to offset.

### Demand-side check — these leads are still arriving

By `created_at`, **inbound leads in the high-end buckets actually grew YoY**:

| Budget bucket | Leads 25→26 | Qualified leads 25→26 | Assigned 25→26 |
|---|---:|---:|---:|
| $100K+ | 237 → **393** (+66%) | 69 → 60 | 54 → 48 |
| Unknown | 50 → **75** (+50%) | 35 → 23 | 35 → 23 |
| Unsure | 616 → **751** (+22%) | 277 → 363 | 243 → 298 |

The funnel is bringing in **more** high-end demand, but qualified-and-assigned counts are flat or down, and bookings (contracted side) collapsed. The top of the funnel is fine — **the close is broken at the high end.**

> Side note: `$30K–50K` shows 2,310 raw rows with only 120 qualified — a ~95% DOA/spam rate, vs. ~50% normal. Something funky in intake for that bucket; flag for separate look.

## 3. Within Inbound — the damage is concentrated in 2 agents

Worst commission deltas (April 1–28 YoY, inbound only):

| Agent | Bookings 25→26 | Commission 25→26 | Δ Commission |
|---|---:|---:|---:|
| **Sawyer Panara** | 16 → 10 | $345,750 → $54,200 | **-$291,550 (-84%)** |
| **Jessica Brown** | 14 → 6 | $176,000 → $37,925 | **-$138,075 (-78%)** |
| Jasmine Mansfield | 7 → 10 | $102,500 → $61,750 | -$40,750 (-40%) |
| Amanda Miller | 13 → 10 | $80,500 → $61,400 | -$19,100 (-24%) |
| Ryan Finnerty | 7 → 3 | $25,625 → $10,000 | -$15,625 (-61%) |
| Dylan Kirkpatrick | 8 → 12 | $41,703 → $49,000 | +$7,297 |
| Katie Carson | 5 → 7 | $16,250 → $49,000 | **+$32,750** |
| Sarah Angry | 5 → 10 | $46,000 → $85,500 | **+$39,500** |
| Mandy Lubrano | 4 → 11 | $25,875 → $100,250 | **+$74,375** |

**Sawyer alone is -$292K** — that's 83% of the $351K inbound commission decline.
**Sawyer + Jessica = -$430K**, which is more than the entire inbound shortfall (the other agents are net +$80K).

### Why Sawyer / Jessica fell — they lost their high-end mix

Cross-tabbing those two (and Amanda) by budget:

| | 2025 | 2026 |
|---|---|---|
| **Unknown-budget bookings** | **8 deals, $362K commission** | **0 deals, $0** |
| Unsure-budget bookings | 10 deals, $104K | 6 deals, $39K |
| Mid-tier ($5K–$50K) | 24 deals, $124K | 20 deals, $115K (~flat) |

In 2025 Sawyer + Jessica + Amanda closed **8 "Unknown"-budget inbound deals worth $362K in commission**. In 2026 they've closed **zero**. Their mid-tier work is roughly stable — they are not collapsing across the board, they have specifically stopped converting the big-fish opportunities. The "Unknown" budget bucket historically averaged $38K commission/booking (the highest of any bucket); these are the deals that move the number.

Meanwhile, Mandy Lubrano (+$74K), Sarah Angry (+$40K), Katie Carson (+$33K) picked up some big-end deals — Mandy's "Unknown"-budget booking ($30K commission) and Sarah's two "Unknown" bookings ($32.5K) are exactly the type Sawyer used to win.

## Bottom line

1. **Repeat business is up YoY (+11% commission).** Not a problem.
2. **Inbound bookings are flat (79=79); commission is down 41%** because revenue-per-booking dropped 41%. This is a mix shift, not a volume drop.
3. **The mix shift is concentrated in 2 buckets**: "$100K+" (-$90K) and "Unknown budget" (-$322K). Mid-tier ($10K–$50K) is actually growing.
4. **The mix shift is concentrated in 2 agents**: Sawyer Panara (-$292K) and Jessica Brown (-$138K). Together they explain more than 100% of the inbound decline. Specifically, **they have closed zero "Unknown"-budget inbound deals** in April 2026 vs. 8 worth $362K in April 2025.
5. **The lead funnel is bringing in more high-end demand, not less** — $100K+ leads +66%, Unknown +50%. So the issue isn't intake; it's conversion of premium leads to bookings, by specific agents.

### What to look at next
- Pull the Sawyer / Jessica large-deal pipeline as of today: are these deals stalled in proposal/offer, or never assigned, or losing to competitors?
- Check whether high-end leads in April 2026 are being routed to the agents who can close them (Mandy/Sarah/Katie are the ones actually winning that segment now).
- Sanity check the `$30K–50K` lead intake — 2,310 rows in 4 weeks vs. 187 last year, with a 95% DOA/spam rate, suggests an intake-quality regression worth a separate look.
