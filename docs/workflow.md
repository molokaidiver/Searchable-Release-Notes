# Workflow

How a keyword search finds the right release note fast, and hands the user a direct link to the internal Confluence page or the external Help Center article — instead of opening PDFs one by one.

The system has two halves: a background ingestion pipeline that indexes release-note PDFs, and the end-user search experience built on top of that index.

```mermaid
flowchart TD
    subgraph ING["Part 1 · Content ingestion pipeline (automated / admin)"]
        A1["New / updated release-note PDF\nadded to source location"] --> A2["Ingestion job detects the file\n(folder watcher or scheduled run)"]
        A2 --> A3["Extract text from the PDF\n(OCR fallback for scanned pages)"]
        A3 --> A4["Parse metadata: release version,\nproduct, date, fix / ticket IDs"]
        A4 --> A5["Look up matching Confluence page\n& Help Center article"]
        A5 --> A6{"Matching link(s)\nfound?"}
        A6 -->|yes| A7["Attach links to the record"]
        A6 -->|no / partial| A8["Flag for manual\nlinking / review"]
        A8 --> A7
        A7 --> A9["Write full text + metadata + links\ninto the search index"]
        A9 --> A10["Release note is now\nsearchable in the app"]
    end

    subgraph SRCH["Part 2 · End-user search workflow"]
        B1["User opens the app"] --> B2["User types a keyword\n(fix ID, error text, feature, version)"]
        B2 --> B3["App queries the search index"]
        B3 --> B4{"Any matches\nfound?"}
        B4 -->|no| B5["Show 'no results' +\nspelling / broader-term suggestions"]
        B5 -.-> B2
        B4 -->|yes| B6["Display ranked results: version,\ndate, matching snippet highlighted"]
        B6 --> B7["User selects a result"]
        B7 --> B8["Detail view: full excerpt + links to\nsource PDF, Confluence, Help Center"]
        B8 --> B9{"What does the\nuser need?"}
        B9 -->|internal follow-up| B10["Open Confluence link"]
        B9 -->|customer-facing| B11["Copy / open Help Center link"]
        B10 --> B12["Done — fix identified,\nready to reference or share"]
        B11 --> B12
    end

    A10 -. feeds the live index .-> B3
```

A higher-resolution rendered version of this diagram is in [`docs/assets/workflow-diagram.svg`](assets/workflow-diagram.svg).

## Part 1 — Content ingestion pipeline

Runs in the background with no user involvement, implemented today as [`ingestion/ingest.py`](../ingestion/ingest.py):

1. **Detect** — the script scans a source folder for `.pdf` files (currently run by hand or on a schedule; a real folder-watcher/cron job is a later step — see [decisions](decisions.md)).
2. **Extract text** — [pypdf](https://pypi.org/project/pypdf/) pulls text out of each PDF.
3. **Parse metadata** — regexes pull a release version, a date, and any fix/ticket IDs (e.g. `FIX-1042`, `JIRA-2291`) out of the extracted text, falling back to the filename for the product/version if nothing was found in the body.
4. **Match links** — the parsed version is looked up against a manual CSV mapping ([`ingestion/config/links.csv`](../ingestion/config/links.csv)) to attach a Confluence URL and a Help Center URL. Anything that doesn't match is indexed anyway, just without links — visible in search results as "no linked resources yet" rather than silently dropped.
5. **Index** — the text, metadata, and links get written into a SQLite [FTS5](https://www.sqlite.org/fts5.html) full-text-search table (`data/release_notes.db`), which the app queries at search time.

## Part 2 — End-user search workflow

What the person searching actually sees, implemented today as [`app/main.py`](../app/main.py) + [`app/templates/index.html`](../app/templates/index.html):

1. User opens the app and types a keyword — a fix ID, an error string, a feature name, or a version number.
2. Each keystroke (debounced) hits `/api/search`, which runs a `MATCH` query against the FTS5 index and ranks results by [BM25](https://www.sqlite.org/fts5.html#the_bm25_function) relevance.
3. Results show the product, version, release date, and a snippet with the matched term highlighted.
4. Selecting a result reveals the source PDF link, the Confluence link (if matched), and the Help Center link (if matched) — so the person can either dig into internal context or hand a customer the public article directly.

## Current implementation vs. the target design

The `ingestion/` and `app/` code in this repo is a working prototype of the diagram above, built to prove out the mechanics end to end — not the production system. See [`docs/decisions.md`](decisions.md) for what's simplified and what a larger-scale implementation would need to change.
