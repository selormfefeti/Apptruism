"""
Storage for Apptruism.

Everything sits in SQLite so the whole thing runs from a laptop. Four tables:

  seed     the ~20k organizations hand-tagged in the 2019 spreadsheets, with
           the category each one was given. This is the reusable asset from
           the original project and the starting universe for fetching.
  orgs     one row per EIN as ProPublica describes it today, plus a fetch
           status so a long pull can stop and resume.
  filings  one row per (EIN, tax period) holding the handful of financial
           fields the score needs, normalized across Form 990 and 990-EZ.
  scores   the computed score and its components, refreshed by score.py.
"""

from __future__ import annotations

import csv
import gzip
import json
import shutil
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "apptruism.db"
SEED_PATH = Path(__file__).parent / "seed" / "seed_orgs_2019.csv"

# The refresh-data workflow rebuilds the database monthly and publishes it
# gzipped as a GitHub release asset. A fresh checkout, including the hosted
# app, downloads it from here instead of spending an hour on the API.
DATA_URL = "https://github.com/selormfefeti/Apptruism/releases/download/data/apptruism.db.gz"

# The categories the 2019 spreadsheets were tagged with, spelled the way the
# Categories sheet spells them. Rows were tagged by hand so the casing drifts.
CATEGORIES = [
    "Animal Rights",
    "Educational Institutions and Related Activities",
    "Environmental",
    "Human Rights",
    "Human Services",
    "Labor/Workers' Rights",
    "Medical Research",
    "Military and Veterans Organization",
    "Other",
    "Recreation, Sports, Leisure, Athletics",
    "Religious Organization",
    "Trade Development",
]
UNCATEGORIZED = "Uncategorized"
_CANON = {c.lower(): c for c in CATEGORIES}

SCHEMA = """
CREATE TABLE IF NOT EXISTS seed (
    ein TEXT PRIMARY KEY,
    name TEXT,
    form_type TEXT,
    category TEXT,
    subcategory TEXT,
    mission TEXT,
    website TEXT,
    zip TEXT
);
CREATE TABLE IF NOT EXISTS orgs (
    ein TEXT PRIMARY KEY,
    name TEXT,
    city TEXT,
    state TEXT,
    zipcode TEXT,
    ntee_code TEXT,
    subsection_code INTEGER,
    ruling_date TEXT,
    latest_tax_period TEXT,
    fetch_status TEXT,
    fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS filings (
    ein TEXT NOT NULL,
    tax_period INTEGER NOT NULL,
    tax_year INTEGER,
    form TEXT,
    revenue REAL,
    expenses REAL,
    contributions REAL,
    program_revenue REAL,
    assets REAL,
    liabilities REAL,
    net_assets REAL,
    officer_comp REAL,
    fundraising_expense REAL,
    fundraising_net REAL,
    pdf_url TEXT,
    PRIMARY KEY (ein, tax_period)
);
CREATE INDEX IF NOT EXISTS filings_ein ON filings (ein);
CREATE TABLE IF NOT EXISTS scores (
    ein TEXT PRIMARY KEY,
    score REAL,
    confidence REAL,
    components TEXT,
    latest_year INTEGER,
    latest_revenue REAL,
    years_on_file INTEGER,
    size_band TEXT,
    computed_at TEXT,
    cause_rank INTEGER,
    cause_total INTEGER,
    cause_pct REAL
);
"""

# Columns added after the first version. connect() adds any that are missing
# so an existing database keeps working.
MIGRATIONS = [
    ("scores", "cause_rank", "INTEGER"),
    ("scores", "cause_total", "INTEGER"),
    ("scores", "cause_pct", "REAL"),
]

FILING_COLUMNS = [
    "ein", "tax_period", "tax_year", "form", "revenue", "expenses",
    "contributions", "program_revenue", "assets", "liabilities", "net_assets",
    "officer_comp", "fundraising_expense", "fundraising_net", "pdf_url",
]

ORG_COLUMNS = [
    "ein", "name", "city", "state", "zipcode", "ntee_code", "subsection_code",
    "ruling_date", "latest_tax_period",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_database(path=DB_PATH, url=DATA_URL) -> bool:
    """
    Download the published database if there is none at path. Returns True
    when a database is present afterwards. Failure is not fatal: the app
    just starts empty and says so.
    """
    path = Path(path)
    if path.exists() and path.stat().st_size > 0:
        if _has_scores(path):
            return True
        # An empty schema from an earlier start that could not download.
        path.unlink()
    partial = path.with_suffix(".db.download")
    try:
        print(f"downloading {url}", file=sys.stderr)
        with urllib.request.urlopen(url, timeout=120) as resp, gzip.GzipFile(fileobj=resp) as gz, \
                open(partial, "wb") as out:
            shutil.copyfileobj(gz, out)
        partial.replace(path)
        return True
    except Exception as exc:  # noqa: BLE001 - any failure means "start empty"
        print(f"could not download database: {exc}", file=sys.stderr)
        partial.unlink(missing_ok=True)
        return False


def _has_scores(path) -> bool:
    try:
        with sqlite3.connect(str(path)) as probe:
            return probe.execute("SELECT COUNT(*) FROM scores").fetchone()[0] > 0
    except sqlite3.Error:
        return False


def connect(path=DB_PATH) -> sqlite3.Connection:
    # Streamlit calls into the same connection from different threads, and
    # nothing here writes from the app, so the same-thread check is safe off.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL lets the app read while a long fetch is writing.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    for table, column, kind in MIGRATIONS:
        present = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in present:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
    return conn


def clean_text(raw) -> str | None:
    if raw is None:
        return None
    text = str(raw).replace("\xa0", " ").strip()
    return text or None


def clean_category(raw) -> str:
    text = clean_text(raw)
    if not text:
        return UNCATEGORIZED
    return _CANON.get(text.lower(), text)


def load_seed(conn, csv_path=SEED_PATH) -> int:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = [
            (
                r["ein"].strip().zfill(9),
                clean_text(r["name"]),
                clean_text(r["form_type"]),
                clean_category(r["category"]),
                clean_text(r["subcategory"]),
                clean_text(r["mission"]),
                clean_text(r["website"]),
                clean_text(r["zip"]),
            )
            for r in csv.DictReader(fh)
        ]
    conn.executemany("INSERT OR REPLACE INTO seed VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return len(rows)


def pending_eins(conn, category=None, retry_errors=False, limit=None) -> list[str]:
    """Seed EINs that have not been fetched yet, oldest tag first."""
    status = "o.fetch_status IS NULL"
    if retry_errors:
        status += " OR o.fetch_status = 'error'"
    sql = (
        "SELECT s.ein FROM seed s LEFT JOIN orgs o ON o.ein = s.ein "
        f"WHERE ({status})"
    )
    params: list = []
    if category:
        sql += " AND s.category = ?"
        params.append(category)
    sql += " ORDER BY s.ein"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return [row["ein"] for row in conn.execute(sql, params)]


def save_org(conn, ein, org, filings, status) -> None:
    """Write one fetch result. Does not commit; the caller batches that."""
    if org is None:
        conn.execute(
            "INSERT OR REPLACE INTO orgs (ein, fetch_status, fetched_at) VALUES (?,?,?)",
            (ein, status, now()),
        )
        return
    values = [org.get(c) for c in ORG_COLUMNS] + [status, now()]
    conn.execute(
        f"INSERT OR REPLACE INTO orgs ({', '.join(ORG_COLUMNS)}, fetch_status, fetched_at) "
        f"VALUES ({', '.join('?' * (len(ORG_COLUMNS) + 2))})",
        values,
    )
    conn.execute("DELETE FROM filings WHERE ein = ?", (ein,))
    conn.executemany(
        f"INSERT OR REPLACE INTO filings ({', '.join(FILING_COLUMNS)}) "
        f"VALUES ({', '.join('?' * len(FILING_COLUMNS))})",
        [[ein] + [f.get(c) for c in FILING_COLUMNS[1:]] for f in filings],
    )


def filings_for(conn, ein) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM filings WHERE ein = ? ORDER BY tax_period", (ein,)
    )
    return [dict(r) for r in rows]


def all_filings(conn) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for r in conn.execute("SELECT * FROM filings ORDER BY ein, tax_period"):
        grouped.setdefault(r["ein"], []).append(dict(r))
    return grouped


def save_scores(conn, results: dict[str, dict]) -> None:
    stamp = now()
    conn.executemany(
        "INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                ein, s["score"], s["confidence"], json.dumps(s["components"]),
                s["latest_year"], s["latest_revenue"], s["years_on_file"],
                s["size_band"], stamp, s.get("cause_rank"), s.get("cause_total"),
                s.get("cause_pct"),
            )
            for ein, s in results.items()
        ],
    )
    conn.commit()


def categories_by_ein(conn) -> dict[str, str]:
    return {r["ein"]: r["category"] for r in conn.execute("SELECT ein, category FROM seed")}


def ranking_rows(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.ein, COALESCE(o.name, s.name) AS name, s.category, s.subcategory,
               s.mission, s.website, o.city, o.state, o.ntee_code,
               o.subsection_code, sc.score, sc.confidence, sc.components, sc.latest_year,
               sc.latest_revenue, sc.years_on_file, sc.size_band,
               sc.cause_rank, sc.cause_total, sc.cause_pct
        FROM scores sc
        JOIN seed s ON s.ein = sc.ein
        LEFT JOIN orgs o ON o.ein = sc.ein
        WHERE sc.score IS NOT NULL
        ORDER BY sc.score DESC, sc.confidence DESC
        """
    )
    return [dict(r) for r in rows]


def scores_stamp(conn) -> str:
    """When the scores table was last written. Cheap, and a good cache key."""
    row = conn.execute("SELECT MAX(computed_at) FROM scores").fetchone()
    return row[0] or ""


def counts(conn) -> dict:
    one = lambda sql: conn.execute(sql).fetchone()[0]
    return {
        "seed": one("SELECT COUNT(*) FROM seed"),
        "fetched": one("SELECT COUNT(*) FROM orgs WHERE fetch_status = 'ok'"),
        "not_found": one("SELECT COUNT(*) FROM orgs WHERE fetch_status = 'not_found'"),
        "errors": one("SELECT COUNT(*) FROM orgs WHERE fetch_status = 'error'"),
        "filings": one("SELECT COUNT(*) FROM filings"),
        "scored": one("SELECT COUNT(*) FROM scores WHERE score IS NOT NULL"),
    }
