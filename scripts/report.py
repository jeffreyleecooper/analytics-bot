"""HTML report assembly — the project's single output format.

Reports are authored as **raw HTML**: build a body string (your bespoke notes
plus any standard tables) and call `write_report`. There is no markdown
intermediate — the only persisted artifact is `outputs/<name>.html`.

Typical use inside a scratch `analysis.py`:

    from scripts.report import write_report, html_table, money, integer, pct, percent
    from scripts.standard_report import build, WINDOWS_DEFAULT

    tables = build(WINDOWS_DEFAULT)          # dict[str, DataFrame] of standard breakdowns
    body = "<h1>Inbound — last 30d vs prior</h1>"
    body += "<p>My bespoke read of the numbers...</p>"
    body += html_table(tables["rev_source"], "lead_source", [
        ("commission_fee__current", "Comm cur", "money"),
        ("commission_fee__prior",   "Comm prior", "money"),
        ("commission_fee__vs_prior","Δ%", "pct"),
    ])
    write_report("inbound_30d_vs_prior", body)   # -> outputs/inbound_30d_vs_prior.html
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"

# Shared styling for every report. md_to_html imports these too, so all HTML
# the project emits looks the same.
CSS = """
:root { color-scheme: light; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
       max-width: 980px; margin: 2rem auto; padding: 0 1.25rem; color: #1f2328; line-height: 1.55; }
h1, h2, h3, h4 { line-height: 1.25; }
h1 { border-bottom: 1px solid #d0d7de; padding-bottom: .3em; }
h2 { border-bottom: 1px solid #d0d7de; padding-bottom: .3em; margin-top: 2em; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: .92em; }
th, td { border: 1px solid #d0d7de; padding: 6px 10px; text-align: left; }
th { background: #f6f8fa; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr:nth-child(even) td { background: #f9fafb; }
code { background: #eff1f3; padding: .15em .35em; border-radius: 4px; font-size: .9em; }
pre { background: #f6f8fa; padding: 1em; border-radius: 6px; overflow-x: auto; }
blockquote { border-left: 4px solid #d0d7de; margin: 1em 0; padding: .25em 1em; color: #57606a;
             background: #f6f8fa; }
a { color: #0969da; text-decoration: none; }
a:hover { text-decoration: underline; }
hr { border: 0; border-top: 1px solid #d0d7de; margin: 2em 0; }
"""

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""


# Canonical metric glossary appended to every report so a shared file is
# self-explanatory. Definitions track notes/LEAD_ANALYSIS.MD.
METRIC_GLOSSARY: list[tuple[str, str]] = [
    ("Bookings (booked)", "Count of opportunities that contracted. Bucketed by <code>contracted_on</code>."),
    ("Commission (commission_fee)", "Commission revenue on booked opportunities. Bucketed by <code>contracted_on</code>."),
    ("Gross (gross_fee)", "Gross fee (talent + commission) on booked opportunities. Bucketed by <code>contracted_on</code>."),
    ("Avg comm/booking", "Commission ÷ bookings — average commission per booked deal (a deal-size measure)."),
    ("Open now", "Point-in-time count of leads currently open in the pipeline (<code>sales_status = open</code>) for the segment. <b>Not windowed</b> — context for in-window booking counts, since a low count may just mean deals are still in flight."),
    ("Total leads", "All inbound lead rows, any status — the raw top of funnel. Bucketed by <code>created_at</code>."),
    ("Workable leads", "Credible leads: excludes spam, duplicates, and trusted-dead DOAs (no reason / Marketing Request / Not Viable); keeps Weak Opportunity &amp; No/Low Budget. Bucketed by <code>created_at</code>."),
    ("Assigned", "Leads handed to a sales agent. Bucketed by <code>created_at</code>."),
    ("SQL (qualified_assigned)", "Assigned leads that reached proposal or offer stage (or already booked). Bucketed by <code>created_at</code>."),
    ("Open leads (funnel)", "Leads from the window still open in the pipeline (<code>sales_status = open</code>), by <code>created_at</code>."),
    ("Asgn% (assigned_rate)", "assigned ÷ workable_leads — share of workable leads handed to an agent."),
    ("SQL% (qualified_assigned_rate)", "qualified_assigned ÷ assigned — share of assigned leads that became real opportunities."),
    ("Book% (booking_rate)", "booked ÷ qualified_assigned — close rate on real (qualified) opportunities."),
    ("Win% (win_rate)", "booked ÷ (assigned − open_leads) — close rate on resolved (non-open) assigned leads."),
]

CONVENTIONS = (
    'Revenue metrics (bookings, commission, gross, avg comm/booking) are bucketed by '
    '<code>contracted_on</code> and include <b>both</b> inbound and repeat. Funnel metrics '
    '(leads, workable, assigned, SQL, rates) are bucketed by <code>created_at</code>, '
    'inbound only. <b>Δ%</b> columns show the primary window\'s change vs the named '
    'comparison window — <span style="color:#1a7f37">green</span> up, '
    '<span style="color:#cf222e">red</span> down.'
)


def glossary_html() -> str:
    """Render the standard metric glossary + reading conventions as an HTML fragment."""
    rows = "\n".join(
        f"<tr><td>{term}</td><td>{definition}</td></tr>" for term, definition in METRIC_GLOSSARY
    )
    return (
        '\n<hr>\n<h2>Metric definitions</h2>\n'
        f'<p>{CONVENTIONS}</p>\n'
        '<table>\n<tr><th>Metric</th><th>Definition</th></tr>\n'
        f'{rows}\n</table>'
    )


def render_report(title: str, body_html: str) -> str:
    """Wrap a raw-HTML body in the styled standalone document shell."""
    return TEMPLATE.format(title=title, css=CSS, body=body_html)


def write_report(name: str, body_html: str, title: str | None = None,
                 include_glossary: bool = True) -> Path:
    """Write a raw-HTML body to `outputs/<name>.html` (HTML is the only output).

    `name` may include or omit the `.html` suffix. `title` defaults to `name`.
    A standard metric-definitions glossary is appended to every report so a shared
    file is self-explanatory; pass `include_glossary=False` only for fragments that
    are not standalone deliverables.
    """
    OUT.mkdir(exist_ok=True)
    if include_glossary:
        body_html = body_html + glossary_html()
    stem = name[:-5] if name.endswith(".html") else name
    path = OUT / f"{stem}.html"
    path.write_text(render_report(title or stem, body_html), encoding="utf-8")
    return path


# ---------- value formatting ----------
def _isnan(x) -> bool:
    return isinstance(x, float) and x != x


def money(x: float) -> str:
    if x is None or _isnan(x):
        return "n/a"
    return f"${x:,.0f}"


def integer(x: float) -> str:
    if x is None or _isnan(x):
        return "n/a"
    return f"{int(round(x)):,}"


def pct(x: float) -> str:
    """Relative change, e.g. -9% (used for `__vs_<window>` delta columns)."""
    if x is None or _isnan(x):
        return "n/a"
    return f"{x:+.0f}%"


def percent(x: float) -> str:
    """A rate in 0..1 rendered as a percentage, e.g. 0.49 -> 49% (rate columns)."""
    if x is None or _isnan(x):
        return "n/a"
    return f"{x * 100:.0f}%"


_FMT = {"money": money, "int": integer, "pct": pct, "percent": percent, "str": str}

# Green/red palette for signed change cells (matches the CSS link/neutral tones).
_POS_COLOR = "#1a7f37"
_NEG_COLOR = "#cf222e"


def _delta_style(value) -> str:
    """Inline color style for a signed change value: green up, red down, none otherwise.

    Returns the ` style="..."` attribute fragment (with leading space) or "".
    """
    if value is None or _isnan(value) or not isinstance(value, (int, float)):
        return ""
    if value > 0:
        return f' style="color:{_POS_COLOR}"'
    if value < 0:
        return f' style="color:{_NEG_COLOR}"'
    return ""


# Distinct line colors for charts (matches the report's link/green/red palette tones).
_CHART_COLORS = ["#0969da", "#cf222e", "#1a7f37", "#9a6700", "#8250df", "#0550ae", "#bc4c00"]


def _nice_top(v: float) -> float:
    """Round an axis maximum up to a clean 1/2/2.5/5/10 × 10ⁿ value."""
    if v <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(v))
    return next(m * mag for m in (1, 2, 2.5, 5, 10) if v <= m * mag)


def line_chart_svg(x_labels: list[str], series: dict[str, list[float]], *,
                   width: int = 880, height: int = 380, title: str | None = None,
                   colors: list[str] | None = None) -> str:
    """Self-contained inline-SVG multi-line chart (no JS / external deps).

    `x_labels` are the evenly-spaced x categories; `series` maps each line's name to its
    y-values (same length as `x_labels`). Y axis starts at 0. Renders gridlines, rotated
    x labels, point markers, and a legend — safe to embed directly in a report body.
    """
    colors = colors or _CHART_COLORS
    n = len(x_labels)
    left, right, top, bot = 56, 150, 40 if title else 20, 58
    pw, ph = width - left - right, height - (40 if title else 20) - bot
    vmax = max((v for vs in series.values() for v in vs), default=1) or 1
    ytop = _nice_top(vmax)

    def X(i: int) -> float:
        return left + (pw * i / (n - 1) if n > 1 else pw / 2)

    def Y(v: float) -> float:
        return top + ph - (v / ytop) * ph

    p: list[str] = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
                    f'style="max-width:{width}px;font:12px -apple-system,Segoe UI,sans-serif" '
                    f'role="img" xmlns="http://www.w3.org/2000/svg">']
    if title:
        p.append(f'<text x="{left}" y="20" font-weight="600" fill="#1f2328">{title}</text>')
    # horizontal gridlines + y labels
    for t in range(5):
        yv = ytop * t / 4
        y = Y(yv)
        p.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + pw}" y2="{y:.1f}" stroke="#e1e4e8"/>')
        p.append(f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" fill="#57606a">{yv:,.0f}</text>')
    # x labels (rotated)
    for i, lbl in enumerate(x_labels):
        x = X(i)
        p.append(f'<text x="{x:.1f}" y="{top + ph + 14:.1f}" text-anchor="end" fill="#57606a" '
                 f'transform="rotate(-40 {x:.1f} {top + ph + 14:.1f})">{lbl}</text>')
    # series lines + markers
    for j, (name, vals) in enumerate(series.items()):
        c = colors[j % len(colors)]
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
        p.append(f'<polyline fill="none" stroke="{c}" stroke-width="2" points="{pts}"/>')
        for i, v in enumerate(vals):
            p.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="2.5" fill="{c}"/>')
        ly = top + 4 + j * 18
        p.append(f'<rect x="{left + pw + 18}" y="{ly}" width="12" height="12" fill="{c}"/>')
        p.append(f'<text x="{left + pw + 34}" y="{ly + 11}" fill="#1f2328">{name}</text>')
    p.append("</svg>")
    return "".join(p)


def html_table(df: pd.DataFrame, label_col: str, columns: list[tuple[str, str, str]],
               title: str | None = None) -> str:
    """Render `df` as an HTML table fragment.

    `label_col` is the left-hand label column (rendered as text). `columns` is an
    ordered list of `(df_column, header, kind)` where kind is one of
    money / int / pct / percent / str. Numeric kinds are right-aligned. `pct` cells
    (signed change columns) are auto color-coded green for positive / red for negative.
    """
    parts: list[str] = []
    if title:
        parts.append(f"<h3>{title}</h3>")
    parts.append("<table>")
    head = [f"<th>{label_col}</th>"] + [
        f'<th class="num">{h}</th>' if kind != "str" else f"<th>{h}</th>"
        for _, h, kind in columns
    ]
    parts.append("<tr>" + "".join(head) + "</tr>")
    for _, row in df.iterrows():
        cells = [f"<td>{row[label_col]}</td>"]
        for col, _, kind in columns:
            fmt = _FMT.get(kind, str)
            cls = "" if kind == "str" else ' class="num"'
            style = _delta_style(row[col]) if kind == "pct" else ""
            cells.append(f"<td{cls}{style}>{fmt(row[col])}</td>")
        parts.append("<tr>" + "".join(cells) + "</tr>")
    parts.append("</table>")
    return "\n".join(parts)
