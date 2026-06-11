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


def render_report(title: str, body_html: str) -> str:
    """Wrap a raw-HTML body in the styled standalone document shell."""
    return TEMPLATE.format(title=title, css=CSS, body=body_html)


def write_report(name: str, body_html: str, title: str | None = None) -> Path:
    """Write a raw-HTML body to `outputs/<name>.html` (HTML is the only output).

    `name` may include or omit the `.html` suffix. `title` defaults to `name`.
    """
    OUT.mkdir(exist_ok=True)
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


def html_table(df: pd.DataFrame, label_col: str, columns: list[tuple[str, str, str]],
               title: str | None = None) -> str:
    """Render `df` as an HTML table fragment.

    `label_col` is the left-hand label column (rendered as text). `columns` is an
    ordered list of `(df_column, header, kind)` where kind is one of
    money / int / pct / percent / str. Numeric kinds are right-aligned.
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
            cells.append(f"<td{cls}>{fmt(row[col])}</td>")
        parts.append("<tr>" + "".join(cells) + "</tr>")
    parts.append("</table>")
    return "\n".join(parts)
