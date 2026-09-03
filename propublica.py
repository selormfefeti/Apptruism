"""
Thin client for the ProPublica Nonprofit Explorer API v2.

    https://projects.propublica.org/nonprofits/api/

Free, no key, one JSON document per EIN with the organization's IRS master
file record and a financial extract for every e-filed 990, 990-EZ and 990-PF
on record. That single endpoint replaces both the AWS index and the HTML
scrape the 2020 version depended on.

The API publishes no rate limit. This client keeps a polite gap between
requests and backs off on 429s and server errors, which is enough to pull the
whole seed list in an hour or two without bothering anyone.
"""

from __future__ import annotations

import time

import requests

BASE = "https://projects.propublica.org/nonprofits/api/v2"
ORG_PAGE = "https://projects.propublica.org/nonprofits/organizations/{ein}"
FORM_NAMES = {0: "990", 1: "990EZ", 2: "990PF"}
USER_AGENT = "apptruism/0.1 (research prototype; github.com/selormfefeti/Apptruism)"


class FetchError(Exception):
    pass


class Client:
    def __init__(self, min_interval=0.25, retries=4, session=None):
        self.min_interval = min_interval
        self.retries = retries
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._last = 0.0

    def _throttle(self) -> None:
        gap = self.min_interval - (time.monotonic() - self._last)
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()

    def _get(self, url, params=None):
        last_error = "no attempts"
        for attempt in range(self.retries):
            self._throttle()
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except requests.RequestException as exc:
                last_error = str(exc)
                time.sleep(2 ** attempt)
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code == 200:
                return resp.json()
            last_error = f"HTTP {resp.status_code}"
            time.sleep((2 ** attempt) * (5 if resp.status_code == 429 else 1))
        raise FetchError(f"{url}: {last_error}")

    def organization(self, ein) -> dict | None:
        """Full record for one EIN, or None if ProPublica has never seen it."""
        return self._get(f"{BASE}/organizations/{int(ein)}.json")

    def search(self, q, state=None, ntee=None, page=0) -> dict:
        params = {"q": q, "page": page}
        if state:
            params["state[id]"] = state
        if ntee:
            params["ntee[id]"] = ntee
        return self._get(f"{BASE}/search.json", params) or {}


def _first(record, *keys):
    for key in keys:
        value = record.get(key)
        if value is not None:
            return value
    return None


def normalize_org(payload) -> dict:
    o = payload["organization"]
    return {
        "ein": str(o["ein"]).zfill(9),
        "name": o.get("name"),
        "city": o.get("city"),
        "state": o.get("state"),
        "zipcode": o.get("zipcode"),
        "ntee_code": o.get("ntee_code"),
        "subsection_code": o.get("subsection_code"),
        "ruling_date": o.get("ruling_date"),
        "latest_tax_period": o.get("tax_period"),
    }


def normalize_filing(f) -> dict | None:
    """
    Map ProPublica's extract columns onto one vocabulary. Form 990 and 990-EZ
    name the same line differently (totcntrbgfts vs totcntrbs), and the EZ
    has no officer compensation or professional fundraising line at all.
    Private foundations (990-PF) are skipped: their extract is a different
    shape and they are not who a donor is choosing between.
    """
    form = FORM_NAMES.get(f.get("formtype"))
    if form not in ("990", "990EZ"):
        return None
    return {
        "tax_period": f.get("tax_prd"),
        "tax_year": f.get("tax_prd_yr"),
        "form": form,
        "revenue": _first(f, "totrevenue", "totrevnue"),
        "expenses": _first(f, "totfuncexpns", "totexpns"),
        "contributions": _first(f, "totcntrbgfts", "totcntrbs"),
        "program_revenue": _first(f, "totprgmrevnue", "prgmservrev"),
        "assets": f.get("totassetsend"),
        "liabilities": f.get("totliabend"),
        "net_assets": _first(f, "totnetassetend", "totnetassetsend"),
        "officer_comp": f.get("compnsatncurrofcr") if form == "990" else None,
        "fundraising_expense": f.get("profndraising") if form == "990" else None,
        "fundraising_net": f.get("netincfndrsng"),
        "pdf_url": f.get("pdf_url"),
        "updated": f.get("updated") or "",
    }


def normalize_filings(payload) -> list[dict]:
    """
    Filings in ascending (tax period, updated) order, so that when an amended
    return shares a period with the original, the newer one lands last and
    wins the INSERT OR REPLACE.
    """
    out = []
    for raw in payload.get("filings_with_data", []):
        f = normalize_filing(raw)
        if f and f["tax_period"]:
            out.append(f)
    out.sort(key=lambda f: (f["tax_period"], f["updated"]))
    return out
