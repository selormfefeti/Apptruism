"""
Who belongs in Apptruism, from the IRS Exempt Organizations Business Master
File (EO BMF): the authoritative list of every tax-exempt organization,
refreshed monthly as four regional CSVs.

The target set is the organizations the score can read: 501(c)(3)s that are
required to file a Form 990 or 990-EZ (not the 990-N postcard, which has
no financials) with income of $50,000 or more. Nationally that is about
373,000 organizations, of which roughly 11,000 a year are newly exempt.

    python universe.py                 download the master file and refresh the universe table
    python universe.py --from-dir DIR  use eo1.csv ... eo4.csv already in DIR

Each refresh also marks fetched organizations that no longer appear in the
master file at all as inactive: revoked, merged or dissolved.
"""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
import urllib.request
from pathlib import Path

import db

BMF_URLS = [f"https://www.irs.gov/pub/irs-soi/eo{i}.csv" for i in range(1, 5)]
SUBSECTION_C3 = "03"
FILES_990_OR_EZ = "01"
MIN_INCOME = 50_000


def download(dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for url in BMF_URLS:
        path = dest / url.rsplit("/", 1)[1]
        print(f"downloading {url}", file=sys.stderr)
        req = urllib.request.Request(url, headers={"User-Agent": "apptruism/0.1 (github.com/selormfefeti/Apptruism)"})
        with urllib.request.urlopen(req, timeout=300) as resp, open(path, "wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
        paths.append(path)
    return paths


def read_rows(paths):
    for path in paths:
        with open(path, newline="", encoding="latin-1") as fh:
            yield from csv.DictReader(fh)


def is_target(row) -> bool:
    try:
        income = float(row.get("INCOME_AMT") or 0)
    except ValueError:
        income = 0.0
    return (row.get("SUBSECTION") == SUBSECTION_C3
            and row.get("FILING_REQ_CD") == FILES_990_OR_EZ
            and income >= MIN_INCOME)


def _num(value):
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def refresh(conn, rows, stamp=None) -> dict:
    """
    Rebuild the universe table from master-file rows and mark fetched
    organizations absent from the file as inactive. Returns counts.
    """
    stamp = stamp or db.now()
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS present (ein TEXT PRIMARY KEY)")
    conn.execute("DELETE FROM present")
    seen = targets = 0
    batch, present = [], []

    def flush():
        conn.executemany(
            """INSERT INTO universe (ein, name, city, state, zipcode, ntee_code, subsection, filing_req,
                                     ruling, income_amt, revenue_amt, asset_amt, first_seen, last_seen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(ein) DO UPDATE SET
                 name=excluded.name, city=excluded.city, state=excluded.state, zipcode=excluded.zipcode,
                 ntee_code=excluded.ntee_code, subsection=excluded.subsection, filing_req=excluded.filing_req,
                 ruling=excluded.ruling, income_amt=excluded.income_amt, revenue_amt=excluded.revenue_amt,
                 asset_amt=excluded.asset_amt, last_seen=excluded.last_seen""",
            batch)
        conn.executemany("INSERT OR IGNORE INTO present VALUES (?)", present)
        batch.clear()
        present.clear()

    for row in rows:
        ein = (row.get("EIN") or "").strip().zfill(9)
        if not ein.strip("0"):
            continue
        seen += 1
        present.append((ein,))
        if is_target(row):
            targets += 1
            batch.append((
                ein, db.clean_text(row.get("NAME")), db.clean_text(row.get("CITY")),
                db.clean_text(row.get("STATE")), db.clean_text(row.get("ZIP")),
                db.clean_text(row.get("NTEE_CD")), row.get("SUBSECTION"), row.get("FILING_REQ_CD"),
                db.clean_text(row.get("RULING")), _num(row.get("INCOME_AMT")),
                _num(row.get("REVENUE_AMT")), _num(row.get("ASSET_AMT")), stamp, stamp,
            ))
        if len(batch) >= 5000 or len(present) >= 50000:
            flush()
    flush()

    dropped = conn.execute("DELETE FROM universe WHERE last_seen < ?", (stamp,)).rowcount
    conn.execute("UPDATE orgs SET active = CASE WHEN ein IN (SELECT ein FROM present) THEN 1 ELSE 0 END")
    inactive = conn.execute("SELECT COUNT(*) FROM orgs WHERE active = 0").fetchone()[0]
    conn.commit()
    return {"rows_seen": seen, "in_target": targets, "left_target": dropped, "fetched_now_inactive": inactive}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-dir", help="directory holding eo1.csv to eo4.csv")
    parser.add_argument("--db", default=db.DB_PATH)
    args = parser.parse_args(argv)

    if args.from_dir:
        paths = [Path(args.from_dir) / f"eo{i}.csv" for i in range(1, 5)]
    else:
        paths = download(Path(tempfile.mkdtemp(prefix="bmf-")))
    conn = db.connect(args.db)
    counts = refresh(conn, read_rows(paths))
    print("universe:", counts)
    pending = len(db.pending_eins(conn))
    print(f"organizations in the target set not yet fetched: {pending:,}")


if __name__ == "__main__":
    main()
