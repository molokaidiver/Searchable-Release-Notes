#!/usr/bin/env python3
"""
generate_sample_data.py — creates a handful of realistic-looking release-note
PDFs (and a matching links CSV) so you can run the ingestion + search
pipeline end to end without needing real company data.

Usage:
    python scripts/generate_sample_data.py

Requires reportlab (dev-only dependency — see requirements-dev.txt).
Not meant to be part of the production app; it just seeds data/sample_release_notes/
for local testing and demos.
"""

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_release_notes"
LINKS_CSV = Path(__file__).resolve().parent.parent / "ingestion" / "config" / "links.csv"

RELEASES = [
    {
        "product": "Atlas Sync",
        "version": "4.2.0",
        "date": "March 3, 2026",
        "sections": [
            ("New features", [
                "Added incremental sync mode for workspaces over 50GB.",
                "New audit log export to CSV from Settings > Compliance.",
            ]),
            ("Fixes", [
                "FIX-1042: Resolved a memory leak in the background indexer when "
                "ingesting large batches of PDF attachments.",
                "FIX-1055: Fixed an issue where SSO sessions expired 10 minutes "
                "early for accounts in UTC-10 and UTC-11 timezones.",
                "JIRA-2291: Corrected search relevance ranking so exact version "
                "matches (e.g. \"4.1.0\") now outrank partial matches.",
            ]),
            ("Known issues", [
                "Large file uploads (>2GB) may briefly show an incorrect progress "
                "percentage; the upload itself completes correctly.",
            ]),
        ],
    },
    {
        "product": "Atlas Sync",
        "version": "4.1.0",
        "date": "January 14, 2026",
        "sections": [
            ("New features", [
                "Introduced keyword search across release notes and changelogs.",
            ]),
            ("Fixes", [
                "FIX-988: Fixed a crash on startup when the local cache directory "
                "was on a network-mounted drive.",
                "FIX-1001: Resolved duplicate notification emails sent to shared "
                "mailboxes after a workspace merge.",
            ]),
        ],
    },
    {
        "product": "Beacon Insights",
        "version": "2.0.0",
        "date": "February 20, 2026",
        "sections": [
            ("New features", [
                "Full rewrite of the dashboard rendering engine (2x faster load times).",
                "Added scheduled PDF export of any dashboard.",
            ]),
            ("Fixes", [
                "FIX-771: Fixed incorrect week-over-week percentage change on the "
                "revenue widget when a week had zero data points.",
            ]),
        ],
    },
]

LINKS_HEADER = "version,confluence_url,help_center_url\n"
LINKS_ROWS = {
    "4.2.0": (
        "https://yourcompany.atlassian.net/wiki/spaces/ENG/pages/424200/Atlas-Sync-4.2.0",
        "https://help.yourcompany.com/atlas-sync/release-notes/4-2-0",
    ),
    "4.1.0": (
        "https://yourcompany.atlassian.net/wiki/spaces/ENG/pages/424100/Atlas-Sync-4.1.0",
        "https://help.yourcompany.com/atlas-sync/release-notes/4-1-0",
    ),
    # 2.0.0 intentionally left unmapped to demonstrate the "no links matched,
    # flagged for manual review" path from the ingestion pipeline.
}


def render_pdf(release: dict, out_path: Path) -> None:
    c = canvas.Canvas(str(out_path), pagesize=LETTER)
    width, height = LETTER
    x_margin = 0.9 * inch
    y = height - 1 * inch

    c.setFont("Helvetica-Bold", 16)
    c.drawString(x_margin, y, f"{release['product']} — Release {release['version']}")
    y -= 0.3 * inch

    c.setFont("Helvetica", 11)
    c.drawString(x_margin, y, release["date"])
    y -= 0.4 * inch

    for heading, items in release["sections"]:
        c.setFont("Helvetica-Bold", 13)
        c.drawString(x_margin, y, heading)
        y -= 0.26 * inch
        c.setFont("Helvetica", 10.5)
        for item in items:
            for line in wrap_text(item, 90):
                c.drawString(x_margin + 0.2 * inch, y, line)
                y -= 0.2 * inch
            y -= 0.06 * inch
        y -= 0.15 * inch

    c.showPage()
    c.save()


def wrap_text(text: str, width: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for release in RELEASES:
        filename = f"{release['product'].replace(' ', '_')}_v{release['version']}.pdf"
        out_path = OUT_DIR / filename
        render_pdf(release, out_path)
        print(f"  wrote {out_path.relative_to(OUT_DIR.parent.parent)}")

    LINKS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with LINKS_CSV.open("w", encoding="utf-8") as f:
        f.write(LINKS_HEADER)
        for version, (confluence_url, help_center_url) in LINKS_ROWS.items():
            f.write(f"{version},{confluence_url},{help_center_url}\n")
    print(f"  wrote {LINKS_CSV.relative_to(LINKS_CSV.parent.parent.parent)}")
    print(f"\nGenerated {len(RELEASES)} sample release notes in {OUT_DIR}")


if __name__ == "__main__":
    main()
