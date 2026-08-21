#!/usr/bin/env python3
"""
app/main.py — the "Part 2: End-User Search Workflow" from docs/workflow.md.

A small Flask app that serves a single search page. Typing a keyword hits
/api/search, which runs a SQLite FTS5 query against the index that
ingestion/ingest.py built, and returns ranked results with a highlighted
snippet plus links to the source PDF, the internal Confluence page, and the
external Help Center article.

Run:
    python app/main.py --db ./data/release_notes.db --source ./data/sample_release_notes

Then open http://127.0.0.1:5000
"""

import argparse
import re
import sqlite3
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request, send_from_directory

app = Flask(__name__)

# Populated from CLI args in main() / create_app(); kept simple for an MVP
# rather than wiring up full Flask app-config machinery.
app.config["DB_PATH"] = Path("data/release_notes.db")
app.config["SOURCE_DIR"] = Path("data/sample_release_notes")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DB_PATH"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def build_match_query(raw_query: str) -> str:
    """Turn free-text user input into a safe, forgiving FTS5 MATCH expression.

    - Strips characters FTS5's query syntax treats specially.
    - Adds a trailing '*' to the last token for prefix matching, so typing
      "FIX-104" starts showing results before the user finishes "FIX-1042".
    - Space-separated tokens are implicitly ANDed by FTS5, which is the
      right default for narrowing down a fix ID or feature name.
    """
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-_.]*", raw_query)
    if not tokens:
        return ""
    tokens = [f'"{t}"' for t in tokens[:-1]] + [f'"{tokens[-1]}"*']
    return " ".join(tokens)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search")
def api_search():
    raw_query = (request.args.get("q") or "").strip()
    if not raw_query:
        return jsonify({"query": raw_query, "results": []})

    match_query = build_match_query(raw_query)
    if not match_query:
        return jsonify({"query": raw_query, "results": []})

    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT
                filename, product, version, release_date, fix_ids,
                confluence_url, help_center_url,
                snippet(release_notes, 9, '<mark>', '</mark>', '…', 12) AS snippet,
                bm25(release_notes) AS rank
            FROM release_notes
            WHERE release_notes MATCH ?
            ORDER BY rank
            LIMIT 25
            """,
            (match_query,),
        ).fetchall()
    except sqlite3.OperationalError:
        # Malformed FTS5 query (e.g. an unmatched quote from odd input) —
        # fail soft with no results rather than a 500.
        return jsonify({"query": raw_query, "results": []})

    results = [
        {
            "filename": row["filename"],
            "product": row["product"],
            "version": row["version"],
            "release_date": row["release_date"],
            "fix_ids": row["fix_ids"],
            "confluence_url": row["confluence_url"] or None,
            "help_center_url": row["help_center_url"] or None,
            "snippet": row["snippet"],
            "source_url": f"/files/{row['filename']}",
        }
        for row in rows
    ]
    return jsonify({"query": raw_query, "results": results})


@app.route("/files/<path:filename>")
def serve_source_pdf(filename: str):
    # send_from_directory guards against path traversal (../..) on its own.
    return send_from_directory(app.config["SOURCE_DIR"], filename)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=Path("data/release_notes.db"))
    parser.add_argument("--source", type=Path, default=Path("data/sample_release_notes"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(
            f"No search index found at {args.db}.\n"
            f"Run ingestion first, e.g.:\n"
            f"  python ingestion/ingest.py --source {args.source} --db {args.db}"
        )

    # Resolve to absolute paths: Flask's send_from_directory resolves a
    # relative directory against the app package's root_path (app/), not
    # the process's current working directory, which would silently 404
    # every PDF download if left relative.
    app.config["DB_PATH"] = args.db.resolve()
    app.config["SOURCE_DIR"] = args.source.resolve()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
