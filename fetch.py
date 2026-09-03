"""
Pull organizations and filings from ProPublica into the local database.

    python fetch.py --load-seed              load seed/seed_orgs_2019.csv
    python fetch.py --limit 300              fetch the next 300 unfetched orgs
    python fetch.py --category "Animal Rights"
    python fetch.py --ein 454824300          one org, handy for spot checks
    python fetch.py --retry-errors           revisit orgs that errored

Resumable: every EIN gets a status of ok, not_found or error in orgs, and a
plain run only visits EINs with no status yet. Run score.py afterwards.
"""

from __future__ import annotations

import argparse
import time
from collections import Counter

import db
import propublica


def fetch_one(client, conn, ein) -> str:
    try:
        payload = client.organization(ein)
    except propublica.FetchError as exc:
        print(f"  {ein}: {exc}")
        db.save_org(conn, ein, None, [], "error")
        return "error"
    if payload is None:
        db.save_org(conn, ein, None, [], "not_found")
        return "not_found"
    db.save_org(
        conn, ein,
        propublica.normalize_org(payload),
        propublica.normalize_filings(payload),
        "ok",
    )
    return "ok"


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--load-seed", action="store_true")
    parser.add_argument("--ein")
    parser.add_argument("--category")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--db", default=db.DB_PATH)
    args = parser.parse_args(argv)

    conn = db.connect(args.db)
    if args.load_seed:
        print(f"seed: {db.load_seed(conn)} organizations loaded")

    if args.ein:
        eins = [args.ein.replace("-", "").zfill(9)]
    else:
        eins = db.pending_eins(conn, args.category, args.retry_errors, args.limit)
    if not eins:
        print("nothing to fetch")
        return

    client = propublica.Client()
    tally: Counter = Counter()
    start = time.monotonic()
    print(f"fetching {len(eins)} organizations")
    for i, ein in enumerate(eins, 1):
        tally[fetch_one(client, conn, ein)] += 1
        if i % 25 == 0:
            conn.commit()
        if i % 100 == 0 or i == len(eins):
            rate = i / max(time.monotonic() - start, 1e-6)
            left = (len(eins) - i) / rate / 60
            print(f"{i}/{len(eins)}  ok={tally['ok']} not_found={tally['not_found']} "
                  f"error={tally['error']}  {rate:.1f}/s  ~{left:.0f} min left", flush=True)
    conn.commit()
    print("done:", dict(tally))


if __name__ == "__main__":
    main()
