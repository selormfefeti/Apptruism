"""
Mission text, program spending and officers, from the IRS e-file XML.

The IRS publishes every e-filed 990 as XML in monthly zips of about 500 MB,
with an index per year mapping each return to its EIN, tax period, form
and zip. ProPublica's extract carries none of the text and not the program
expense line, so this module reads the returns themselves: it picks the
newest 990 or 990-EZ per organization from the index, streams each zip
once, keeps a dozen fields per return, and throws the rest away.

    python irsxml.py --plan                 what the index says is still to fetch
    python irsxml.py --max-minutes 300      ingest zips until the time budget runs out
    python irsxml.py --years 2026           limit to one index year
    python irsxml.py --parse FILE.xml       print what the parser sees in one return
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import struct
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections import defaultdict
from pathlib import Path

import inflate64

import db

INDEX_URL = "https://apps.irs.gov/pub/epostcard/990/xml/{year}/index_{year}.csv"
ZIP_URL = "https://apps.irs.gov/pub/epostcard/990/xml/{year}/{batch}.zip"
DEFAULT_YEARS = (2026, 2025)
WANTED_FORMS = ("990", "990EZ")
NS = "{http://www.irs.gov/efile}"
USER_AGENT = "apptruism/0.1 (github.com/selormfefeti/Apptruism)"


# ------------------------------------------------------------------ parsing

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_text(root, *names) -> str | None:
    wanted = set(names)
    for el in root.iter():
        if _local(el.tag) in wanted and el.text and el.text.strip():
            return el.text.strip()
    return None


def _all_text(root, name) -> list[str]:
    return [el.text.strip() for el in root.iter() if _local(el.tag) == name and el.text and el.text.strip()]


def _num(value):
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def parse_return(xml_bytes: bytes) -> dict | None:
    """The fields Apptruism keeps from one return, or None if it is not a 990/990-EZ."""
    root = ET.fromstring(xml_bytes)
    data = root.find(f"{NS}ReturnData")
    if data is None:
        return None
    if data.find(f"{NS}IRS990") is not None:
        form, body = "990", data.find(f"{NS}IRS990")
    elif data.find(f"{NS}IRS990EZ") is not None:
        form, body = "990EZ", data.find(f"{NS}IRS990EZ")
    else:
        return None
    header = root.find(f"{NS}ReturnHeader")

    programs = []
    for el in body.iter():
        name = _local(el.tag)
        if name.startswith("ProgSrvcAccomActy") or name == "ProgramSrvcAccomplishmentGrp":
            programs += _all_text(el, "Desc") + _all_text(el, "DescriptionProgramSrvcAccomTxt")
    officers = []
    for el in body.iter():
        if _local(el.tag) in ("Form990PartVIISectionAGrp", "OfficerDirectorTrusteeEmplGrp"):
            person = _first_text(el, "PersonNm", "BusinessNameLine1Txt")
            if person:
                officers.append({"name": person, "title": _first_text(el, "TitleTxt"),
                                 "pay": _num(_first_text(el, "ReportableCompFromOrgAmt", "CompensationAmt"))})

    return {
        "form": form,
        "ein": (_first_text(header, "EIN") or "").zfill(9) if header is not None else None,
        "tax_period_end": _first_text(header, "TaxPeriodEndDt") if header is not None else None,
        "name": _first_text(header, "BusinessNameLine1Txt") if header is not None else None,
        "mission": _first_text(body, "ActivityOrMissionDesc", "MissionDesc", "PrimaryExemptPurposeTxt"),
        "programs": "\n".join(dict.fromkeys(programs)) or None,
        "program_expenses": _num(_first_text(body, "TotalProgramServiceExpensesAmt")),
        "total_expenses": _num(_first_text(body, "TotalExpensesAmt"))
        if form == "990EZ" else _num(_first_text(body, "CYTotalExpensesAmt")),
        "website": _first_text(body, "WebsiteAddressTxt"),
        "employees": _num(_first_text(body, "TotalEmployeeCnt")),
        "volunteers": _num(_first_text(body, "TotalVolunteersCnt")),
        "officers": officers[:15],
    }


# ------------------------------------------------------------------ the index

def _open(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=600)


def read_index(year: int):
    with _open(INDEX_URL.format(year=year)) as resp:
        text = io.TextIOWrapper(resp, encoding="latin-1", newline="")
        for row in csv.DictReader(text):
            if row.get("RETURN_TYPE") in WANTED_FORMS:
                yield row


def plan(conn, years=DEFAULT_YEARS) -> dict[str, list[dict]]:
    """
    {batch: [index rows]} for the newest 990/990-EZ per organization we track
    that is not already in the returns table. Later index years win ties.
    """
    tracked = {r[0] for r in conn.execute("SELECT ein FROM orgs UNION SELECT ein FROM universe UNION SELECT ein FROM seed")}
    have = {r[0]: r[1] for r in conn.execute("SELECT ein, object_id FROM returns")}
    missing = {r[0] for r in conn.execute("SELECT object_id FROM xml_missing")}
    best: dict[str, dict] = {}
    for year in years:
        for row in read_index(year):
            ein = row["EIN"].zfill(9)
            if ein not in tracked:
                continue
            key = (row["TAX_PERIOD"], row["SUB_DATE"], row["RETURN_ID"])
            cur = best.get(ein)
            if cur is None or key > (cur["TAX_PERIOD"], cur["SUB_DATE"], cur["RETURN_ID"]):
                row = dict(row, EIN=ein, YEAR=year)
                best[ein] = row
    by_batch: dict[str, list[dict]] = defaultdict(list)
    for ein, row in best.items():
        if have.get(ein) != row["OBJECT_ID"] and row["OBJECT_ID"] not in missing:
            by_batch[row["XML_BATCH_ID"]].append(row)
    return dict(sorted(by_batch.items(), key=lambda kv: -len(kv[1])))


# ------------------------------------------------------------------ zip reading

def read_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    """
    One member's bytes. The IRS zips use Deflate64 (method 9), which
    Python's zipfile refuses, so read the raw data ourselves and inflate.
    """
    fp = zf.fp
    fp.seek(info.header_offset)
    header = fp.read(30)
    name_len, extra_len = struct.unpack("<HH", header[26:30])
    fp.seek(info.header_offset + 30 + name_len + extra_len)
    raw = fp.read(info.compress_size)
    if info.compress_type == 9:
        return inflate64.Inflater().inflate(raw)
    if info.compress_type == 8:
        return zlib.decompress(raw, -15)
    return raw


# ------------------------------------------------------------------ ingest

def _download(url: str, path: Path) -> bool:
    """False when the file does not exist (404)."""
    try:
        with _open(url) as resp, open(path, "wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def _scan(conn, zip_path: Path, name: str, wanted: dict[str, dict]) -> dict:
    counts = dict(found=0, matched=0, unreadable=0, other_form=0, members=0)
    stamp = db.now()
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            counts["members"] += 1
            object_id = Path(info.filename).name.split("_")[0]
            row = wanted.get(object_id)
            if row is None:
                continue
            counts["matched"] += 1
            try:
                parsed = parse_return(read_member(zf, info))
            except (ET.ParseError, zlib.error, ValueError):
                counts["unreadable"] += 1
                continue
            if not parsed:
                counts["other_form"] += 1
                continue
            conn.execute(
                """INSERT OR REPLACE INTO returns
                   (ein, object_id, batch, tax_period, form, mission, programs, program_expenses,
                    total_expenses, website, employees, volunteers, officers, ingested_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (row["EIN"], object_id, name, row["TAX_PERIOD"], parsed["form"], parsed["mission"],
                 parsed["programs"], parsed["program_expenses"], parsed["total_expenses"], parsed["website"],
                 parsed["employees"], parsed["volunteers"], json.dumps(parsed["officers"]), stamp))
            counts["found"] += 1
            del wanted[object_id]
    conn.execute("INSERT OR REPLACE INTO xml_zips VALUES (?,?,?)", (name, counts["members"], stamp))
    conn.commit()
    return counts


def ingest_batch(conn, batch: str, rows: list[dict], workdir: Path) -> int:
    """
    The index names one zip per month, but the IRS splits busy months into
    several (05A, 05B, ...). Scan the named zip and its siblings until one
    does not exist, skipping zips already scanned on an earlier run. Returns
    the index rows still not found afterwards get noted so the plan stops
    asking for them.
    """
    year = rows[0]["YEAR"]
    wanted = {r["OBJECT_ID"]: r for r in rows}
    scanned = {r[0] for r in conn.execute("SELECT name FROM xml_zips")}
    stem = batch[:-1]
    found = 0
    for letter in "ABCDEFGH":
        if not wanted:
            break
        name = stem + letter
        if name in scanned:
            continue
        path = workdir / f"{name}.zip"
        print(f"downloading {name} ({len(wanted):,} returns wanted)", file=sys.stderr, flush=True)
        if not _download(ZIP_URL.format(year=year, batch=name), path):
            break
        counts = _scan(conn, path, name, wanted)
        path.unlink(missing_ok=True)
        found += counts["found"]
        print(f"  {name}: {counts['found']:,} ingested of {counts['members']:,} members "
              f"(unreadable {counts['unreadable']}, not a 990/EZ {counts['other_form']})", file=sys.stderr, flush=True)
    if wanted:
        stamp = db.now()
        conn.executemany("INSERT OR IGNORE INTO xml_missing VALUES (?,?,?)",
                         [(oid, batch, stamp) for oid in wanted])
        conn.commit()
        print(f"  {len(wanted):,} returns listed under {batch} were in none of its zips; noted", file=sys.stderr, flush=True)
    return found


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan", action="store_true", help="show what is left, fetch nothing")
    parser.add_argument("--max-minutes", type=float, default=None)
    parser.add_argument("--max-batches", type=int, default=None)
    parser.add_argument("--years", type=int, nargs="+", default=list(DEFAULT_YEARS))
    parser.add_argument("--parse", metavar="FILE", help="parse one XML file and print the result")
    parser.add_argument("--db", default=db.DB_PATH)
    args = parser.parse_args(argv)

    if args.parse:
        print(json.dumps(parse_return(Path(args.parse).read_bytes()), indent=2))
        return

    conn = db.connect(args.db)
    todo = plan(conn, args.years)
    total = sum(len(v) for v in todo.values())
    print(f"returns still to fetch: {total:,} across {len(todo)} zip files")
    if args.plan or not todo:
        for batch, rows in list(todo.items())[:30]:
            print(f"  {batch}: {len(rows):,}")
        return

    start = time.monotonic()
    done_batches = ingested = 0
    workdir = Path(tempfile.mkdtemp(prefix="irsxml-"))
    for batch, rows in todo.items():
        if args.max_batches and done_batches >= args.max_batches:
            break
        if args.max_minutes and (time.monotonic() - start) / 60 >= args.max_minutes:
            print(f"time budget of {args.max_minutes:g} minutes reached", flush=True)
            break
        ingested += ingest_batch(conn, batch, rows, workdir)
        done_batches += 1
    left = total - sum(len(rows) for rows in list(todo.values())[:done_batches])
    print(f"done: {ingested:,} returns from {done_batches} zip files | about {left:,} left in the queue")


if __name__ == "__main__":
    main()
