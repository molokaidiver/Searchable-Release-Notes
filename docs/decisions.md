# Design decisions & open questions

This prototype makes a handful of deliberate simplifications to get the
ingest → index → search loop working end to end quickly. This doc records
what was decided, why, and what a larger-scale production build should
reconsider. Read this before extending the app — it'll save you from
re-deriving the same tradeoffs.

## 1. Where the PDFs live

**Prototype:** `ingestion/ingest.py --source <folder>` reads local PDFs from
a filesystem path. `data/sample_release_notes/` holds generated fixtures.

**Open question:** where do real release notes actually live — a shared
drive, SharePoint, Confluence attachments, or a release-tooling repo? That
determines whether ingestion stays a filesystem scan or needs an API client
(Microsoft Graph, Confluence REST, etc.) instead.

## 2. Matching release notes to Confluence / Help Center links

**Prototype:** a hand-maintained CSV (`ingestion/config/links.csv`) maps a
release version to a Confluence URL and a Help Center URL. Anything not in
the CSV is indexed without links rather than blocked.

**Production options, roughly in order of effort:**
- Keep the CSV/manual-mapping approach, just owned by whoever publishes a
  release (lowest effort, doesn't scale past a handful of editors).
- Live search against the Confluence REST API and a Help Center API/sitemap
  at ingestion time, matching on release version or product name.
- A convention where the release note itself contains the links (e.g. a
  footer with "Internal: ... / Public: ..."), which ingestion just extracts
  — shifts the matching problem to whoever writes the release note.

## 3. Search technology

**Prototype:** SQLite's built-in [FTS5](https://www.sqlite.org/fts5.html)
extension — zero extra services to run, ships with Python's stdlib
`sqlite3`, and gives BM25 ranking and snippet highlighting for free. This
comfortably handles thousands of documents.

**When to reconsider:** if the corpus grows into the tens of thousands of
documents, if you need typo-tolerant/fuzzy search, faceted filtering (by
product, date range, team), or if the app needs to run across multiple
server instances against one shared index — that's when a hosted engine
(Elasticsearch, OpenSearch, Typesense, Algolia) starts paying for itself.

## 4. Ingestion trigger

**Prototype:** `ingest.py` is a script you run by hand. It's idempotent
(re-running deletes and re-inserts each file's row by filepath), so it's
safe to schedule.

**Production options:** a cron job / Task Scheduler entry running it
periodically is the cheapest real upgrade. A true folder-watcher (e.g.
`watchdog` in Python, or a webhook from wherever the PDFs are uploaded) gets
new releases searchable within seconds instead of on the next scheduled run.

## 5. Access control

**Not implemented in the prototype.** The app has no authentication — it's
built to run locally. Before this goes anywhere multi-user:
- Decide whether internal Confluence links should be hidden or handled
  differently for a user who might paste search results externally.
- Decide whether the tool itself needs SSO/auth, or sits behind something
  that already provides it (VPN, internal network only, reverse proxy with
  auth).

## 6. Metadata-parsing accuracy

**Prototype:** simple regexes for version (`v4.2.0`, `Release 4.2.0`), date
(`March 3, 2026`-style), and fix IDs (`[A-Z]{2,10}-\d{2,6}`, e.g. `FIX-1042`
or `JIRA-2291`). This is intentionally naive — for example the fix-ID regex
will also match incidental strings like `UTC-10` if they appear in the
text. It's a starting point, not a finished parser.

**Before relying on this in production:** tune the regexes against a real
sample of your team's release notes, or — if release notes follow a
consistent template — parse structured sections instead of free text.

## 7. Web framework & deployment

**Prototype:** Flask's built-in development server (`app.run()`), explicitly
not production-safe (Flask prints this warning itself). Fine for local use
and demos.

**Before deploying anywhere real:** run behind a production WSGI server
(gunicorn, waitress) and a reverse proxy, and decide on hosting (internal
server, container, PaaS).
