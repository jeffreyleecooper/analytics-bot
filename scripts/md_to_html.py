"""Convert a markdown file to a styled, standalone HTML file.

NOTE: The project's default output path is **raw HTML via `scripts.report`** — see
`report.write_report`. This helper remains for the occasional case where a source
markdown file already exists and you want it rendered with the same styling.

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

from scripts.report import CSS, TEMPLATE  # single source of styling


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
