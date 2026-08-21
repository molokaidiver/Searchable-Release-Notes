# Searchable Release Notes

Find out which software release fixed a given bug — by keyword — instead of
opening release-note PDFs one by one and searching each by hand.

Type a fix ID, an error message, a feature name, or a version number and get
back the release notes that mention it, ranked by relevance, each with a
direct link to the source PDF, the related internal Confluence page, and the
external Help Center article to hand a customer.

See [`docs/workflow.md`](docs/workflow.md) for the full workflow diagram and
walkthrough of both halves of the system (background ingestion + the search
UI), and [`docs/decisions.md`](docs/decisions.md) for what's simplified in
this prototype versus what a larger-scale build should reconsider.

## Status

Working prototype: PDF ingestion, a SQLite full-text search index, and a
Flask search UI, all running locally. Not yet connected to real Confluence /
Help Center data, not authenticated, and not deployed anywhere — see
[`docs/decisions.md`](docs/decisions.md) for the list of what's next.

## Quick start

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Optional — only needed to (re)generate the sample PDFs used below:
pip install -r requirements-dev.txt
python scripts/generate_sample_data.py

# Ingest the sample release notes into a local search index
python ingestion/ingest.py --source ./data/sample_release_notes --db ./data/release_notes.db

# Run the search app
python app/main.py --db ./data/release_notes.db --source ./data/sample_release_notes
```

Then open **http://127.0.0.1:5000** and try searching `FIX-1042`, `memory
leak`, or `4.2.0`.

### Using your own release notes

```bash
python ingestion/ingest.py --source /path/to/your/release-note-pdfs --db ./data/release_notes.db
```

Copy [`ingestion/config/links.example.csv`](ingestion/config/links.example.csv)
to `ingestion/config/links.csv` and fill in the Confluence / Help Center URL
for each release version you want linked. Anything not in that file still
gets indexed and shows up in search — just without links attached yet.

## Project layout

```
ingestion/          PDF -> text -> metadata -> search-index pipeline
  ingest.py
  config/
    links.example.csv   template for the version -> URL mapping
app/                 the search web app
  main.py
  templates/, static/
scripts/
  generate_sample_data.py   generates fixture PDFs for local testing
data/
  sample_release_notes/     generated sample PDFs (checked in as fixtures)
docs/
  workflow.md        the workflow diagram + walkthrough
  decisions.md        open questions and what a production build should reconsider
```

## Contributing / picking this up

If you're taking this over: start with [`docs/workflow.md`](docs/workflow.md)
for the intended end-to-end flow, then [`docs/decisions.md`](docs/decisions.md)
for exactly where this prototype cuts corners and what to weigh before
building past them.
