#!/usr/bin/env python3
"""
ingest.py — scans a folder of release-note PDFs, extracts text + metadata,
and writes everything into a SQLite full-text-search index that app/main.py
queries at search time.

This is the "Part 1: Content Ingestion Pipeline" step from docs/workflow.md,
implemented as a script you run by hand or on a schedule (cron / Task
Scheduler / a CI job) rather than a folder-watcher daemon. That's a
deliberate MVP simplification — see docs/decisions.md for the tradeoff.

Usage:
    python ingestion/ingest.py --source ./data/sample_release_notes --db ./data/release_notes.db
    python ingestion/ingest.py --source ./data/sample_release_notes --links ./ingestion/config/links.csv

What it does, per PDF:
  1. Extract raw text (pypdf).
  2. Parse metadata out of the text with regexes: release version, a date,
     and any fix/ticket IDs mentioned (e.g. JIRA-1234, FIX-42).
  3. Look up a matching Confluence / Help Center URL from a manual mapping
     CSV (see ingestion/config/links.example.csv) — this stands in for the
     "auto-search Confluence & Help Center" step in the workflow diagram
     until that integration is built (see docs/decisions.md, item 2).
  4. Upsert one row per file into a SQLite FTS5 table so app/main.py can run
     keyword search with snippet highlighting and BM25 ranking.

Re-running this script is safe: each file's previous row (matched by
filepath) is deleted and re-inserted, so you can re-ingest after fixing a
PDF or updating the links mapping.
"""

import argparse
import csv
import hashlib
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

# --- metadata extraction heuristics -----------------------------------
# These are intentionally simple regexes tuned for typical release-note
# phrasing ("Release 4.2.0", "v4.2.0", "March 3, 2026", "JIRA-1234").
# Real-world release notes will need these tuned per your team's format —
# see docs/decisions.md, item 6.

VERSION_RE = re.compile(
    r"\b(?:v(?:ersion)?\.?\s*|release\s+)(\d+\.\d+(?:\.\d+)?)\b", re.IGNORECASE
)
DATE_RE = re.compile(
    r"\b((?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},?\s+\d{4})\b"
)
FIX_ID_RE = re.compile(r"\b([A-Z]{2,10}-\d{2,6})\b")


def extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def parse_metadata(text: str, filename: str) -> dict:
    version_match = VERSION_RE.search(text)
    date_match = DATE_RE.search(text)
    fix_ids = sorted(set(FIX_ID_RE.findall(text)))

    version = version_match.group(1) if version_match else None
    release_date = date_match.group(1) if date_match else None

    # Fall back to filename for product/version if we couldn't parse one
    # out of the body text — better a rough guess than a blank field. Strip
    # a trailing version-looking token (e.g. "_v4.2.0") so the product name
    # doesn't end up duplicating the version shown alongside it in the UI.
    product_guess = re.sub(r"[_\-]+", " ", Path(filename).stem).strip()
    product_guess = re.sub(r"\s+v?\d+\.\d+(?:\.\d+)?$", "", product_guess, flags=re.IGNORECASE).strip()

    return {
        "product": product_guess,
        "version": version,
        "release_date": release_date,
        "fix_ids": ", ".join(fix_ids),
    }


def load_links_map(links_csv: Path | None) -> dict:
    """Load a manual version -> (confluence_url, help_center_url) mapping.

    Expected CSV columns: version,confluence_url,help_center_url
    See ingestion/config/links.example.csv for the format.
    """
    if not links_csv or not links_csv.exists():
        return {}
    mapping = {}
    with links_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            version = (row.get("version") or "").strip()
            if not version:
                continue
            mapping[version] = {
                "confluence_url": (row.get("confluence_url") or "").strip(),
                "help_center_url": (row.get("help_center_url") or "").strip(),
            }
    return mapping


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS release_notes USING fts5(
            filename,
            filepath UNINDEXED,
            product,
            version,
            release_date UNINDEXED,
            fix_ids,
            confluence_url UNINDEXED,
            help_center_url UNINDEXED,
            content_hash UNINDEXED,
            full_text
        );
        """
    )
    conn.commit()


def upsert_document(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute("DELETE FROM release_notes WHERE filepath = ?", (row["filepath"],))
    conn.execute(
        """
        INSERT INTO release_notes
            (filename, filepath, product, version, release_date, fix_ids,
             confluence_url, help_center_url, content_hash, full_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["filename"],
            row["filepath"],
            row["product"],
            row["version"],
            row["release_date"],
            row["fix_ids"],
            row["confluence_url"],
            row["help_center_url"],
            row["content_hash"],
            row["full_text"],
        ),
    )


def ingest(source_dir: Path, db_path: Path, links_csv: Path | None, verbose: bool = True) -> int:
    links_map = load_links_map(links_csv)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)

    pdf_paths = sorted(source_dir.rglob("*.pdf"))
    if not pdf_paths:
        print(f"No PDFs found under {source_dir}", file=sys.stderr)

    count = 0
    for pdf_path in pdf_paths:
        text = extract_text(pdf_path)
        meta = parse_metadata(text, pdf_path.name)
        links = links_map.get(meta["version"], {}) if meta["version"] else {}
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

        row = {
            "filename": pdf_path.name,
            "filepath": str(pdf_path.resolve()),
            "product": meta["product"],
            "version": meta["version"] or "",
            "release_date": meta["release_date"] or "",
            "fix_ids": meta["fix_ids"],
            "confluence_url": links.get("confluence_url", ""),
            "help_center_url": links.get("help_center_url", ""),
            "content_hash": content_hash,
            "full_text": text,
        }
        upsert_document(conn, row)
        count += 1
        if verbose:
            flag = "" if (row["confluence_url"] or row["help_center_url"]) else "  [no links matched]"
            print(f"  indexed: {pdf_path.name}  (version={row['version'] or '?'}){flag}")

    conn.commit()
    conn.close()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=Path("data/sample_release_notes"),
                         help="Folder to scan for release-note PDFs (default: data/sample_release_notes)")
    parser.add_argument("--db", type=Path, default=Path("data/release_notes.db"),
                         help="SQLite database file to write the search index into")
    parser.add_argument("--links", type=Path, default=Path("ingestion/config/links.csv"),
                         help="Optional CSV mapping release versions to Confluence/Help Center URLs")
    args = parser.parse_args()

    if not args.source.exists():
        print(f"Source folder does not exist: {args.source}", file=sys.stderr)
        sys.exit(1)

    print(f"Ingesting PDFs from {args.source} -> {args.db}")
    started = datetime.now()
    count = ingest(args.source, args.db, args.links if args.links.exists() else None)
    elapsed = (datetime.now() - started).total_seconds()
    print(f"Done. Indexed {count} file(s) in {elapsed:.2f}s.")


if __name__ == "__main__":
    main()
