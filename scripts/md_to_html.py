"""Convert a markdown analysis writeup to a styled, standalone HTML file.

Usage:
    python -m scripts.md_to_html outputs/some_analysis.md
    # writes outputs/some_analysis.html

Importable:
    from scripts.md_to_html import md_to_html
    md_to_html("outputs/some_analysis.md")
"""
from __future__ import annotations

import sys
from pathlib import Path

import markdown

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


def md_to_html(md_path: str | Path, html_path: str | Path | None = None) -> Path:
    """Render `md_path` as a styled standalone HTML file. Returns the html path."""
    md_path = Path(md_path)
    if html_path is None:
        html_path = md_path.with_suffix(".html")
    html_path = Path(html_path)

    text = md_path.read_text(encoding="utf-8")
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])

    # Use the first H1 (or filename) as <title>
    title = md_path.stem
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    html = TEMPLATE.format(title=title, css=CSS, body=body)
    html_path.write_text(html, encoding="utf-8")
    return html_path


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m scripts.md_to_html <markdown-file>", file=sys.stderr)
        return 2
    out = md_to_html(sys.argv[1])
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
