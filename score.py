"""
Turn a few years of filings into one number a donor can compare across
organizations, and keep the arithmetic simple enough to explain on a screen.

The 2020 pitch promised a ranking on donor retention, donor growth, pledge
fulfilment and financials. Form 990 carries no donor counts and no pledges,
so this first version uses what the public filings actually contain:

  donor_growth        compound annual growth of contributions across the
                      years on file. The closest public proxy for a growing
                      donor base. Needs two years of at least $1,000 each.
  margin              (revenue - expenses) / revenue in the latest year.
                      Small surpluses are healthy. Large deficits and very
                      large surpluses both score lower.
  reserves            months of expenses covered by net assets. Six to
                      twenty-four months is the comfortable band.
  officer_comp        officer and director compensation as a share of
                      expenses. Form 990 only; the EZ has no such line.
  fundraising_cost    professional fundraising fees as a share of
                      contributions. Form 990 only, and narrow: it misses
                      in-house fundraising staff.
  filing_consistency  how many of the last five fileable years have a
                      return on record, and how recent the newest one is.

A food pantry and a university should not be compared on one number, so
every organization also gets a rank and percentile among the others tagged
with the same cause. The percentile is the share of peers it scores at or
above.

Each component maps to 0-100 through a piecewise-linear curve. The score is
the weighted mean of whichever components are available, and confidence is
the share of total weight that was available. A 990-EZ filer with two years
of data is visibly less certain than a 990 filer with five.

    python score.py            recompute the scores table for every org
"""

from __future__ import annotations

from datetime import date

import db

WEIGHTS = {
    "donor_growth": 0.25,
    "filing_consistency": 0.20,
    "margin": 0.15,
    "reserves": 0.15,
    "officer_comp": 0.15,
    "fundraising_cost": 0.10,
}

# (raw value, score) knots. Outside the first and last knot the score is flat.
CURVES = {
    "donor_growth": [(-0.30, 0), (0.00, 50), (0.15, 90), (0.30, 100)],
    "margin": [(-0.25, 0), (-0.05, 40), (0.00, 65), (0.05, 90), (0.15, 100),
               (0.30, 80), (0.60, 50)],
    "reserves": [(0, 0), (3, 70), (6, 100), (24, 100), (48, 60), (96, 30)],
    "officer_comp": [(0.00, 100), (0.05, 100), (0.15, 50), (0.30, 0)],
    "fundraising_cost": [(0.00, 100), (0.10, 100), (0.25, 50), (0.50, 0)],
}

LABELS = {
    "donor_growth": ("Donor growth", "pct"),
    "filing_consistency": ("Filing consistency", "score"),
    "margin": ("Operating margin", "pct"),
    "reserves": ("Reserves", "months"),
    "officer_comp": ("Officer pay share", "pct"),
    "fundraising_cost": ("Fundraising cost", "pct"),
}

MIN_CONTRIBUTIONS = 1_000
SCORED_FORMS = ("990", "990EZ")


def piecewise(x: float, knots) -> float:
    if x <= knots[0][0]:
        return float(knots[0][1])
    if x >= knots[-1][0]:
        return float(knots[-1][1])
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return float(knots[-1][1])


def share(part, whole):
    if part is None or not whole or whole <= 0:
        return None
    return max(part, 0) / whole


def donor_growth(filings) -> float | None:
    by_year: dict[int, float] = {}
    for f in filings:
        amount = f.get("contributions") or 0
        if f.get("tax_year") and amount >= MIN_CONTRIBUTIONS:
            by_year[f["tax_year"]] = amount
    if len(by_year) < 2:
        return None
    first, last = min(by_year), max(by_year)
    span = last - first
    if span < 1:
        return None
    return (by_year[last] / by_year[first]) ** (1 / span) - 1


def margin(latest) -> float | None:
    revenue, expenses = latest.get("revenue"), latest.get("expenses")
    if not revenue or revenue <= 0 or expenses is None:
        return None
    return (revenue - expenses) / revenue


def reserve_months(latest) -> float | None:
    net_assets, expenses = latest.get("net_assets"), latest.get("expenses")
    if net_assets is None or not expenses or expenses <= 0:
        return None
    return max(net_assets, 0) / (expenses / 12)


def filing_consistency(filings, current_year) -> float:
    """
    Filings lag the tax year by a year or more, so the window is the five
    years ending two years ago. Coverage is worth 60 points, recency 40.
    """
    years = {f["tax_year"] for f in filings if f.get("tax_year")}
    window = set(range(current_year - 6, current_year - 1))
    coverage = len(years & window) / len(window)
    gap = current_year - max(years)
    recency = {0: 100, 1: 100, 2: 100, 3: 60, 4: 30}.get(gap, 0)
    return 60 * coverage + 40 * recency / 100


def size_band(revenue) -> str:
    if revenue is None:
        return "Unknown"
    if revenue < 100_000:
        return "Under $100k"
    if revenue < 1_000_000:
        return "$100k to $1M"
    if revenue < 10_000_000:
        return "$1M to $10M"
    return "Over $10M"


def score(filings, current_year=None) -> dict | None:
    """Score one organization from its list of filing dicts. None if no usable filing."""
    current_year = current_year or date.today().year
    usable = sorted(
        (f for f in filings if f.get("form") in SCORED_FORMS and f.get("tax_year")),
        key=lambda f: f["tax_period"],
    )
    if not usable:
        return None
    latest = usable[-1]
    is_990 = latest["form"] == "990"

    raw = {
        "donor_growth": donor_growth(usable),
        "filing_consistency": filing_consistency(usable, current_year),
        "margin": margin(latest),
        "reserves": reserve_months(latest),
        "officer_comp": share(latest.get("officer_comp"), latest.get("expenses")) if is_990 else None,
        "fundraising_cost": share(latest.get("fundraising_expense"), latest.get("contributions")) if is_990 else None,
    }

    components = {}
    for name, weight in WEIGHTS.items():
        value = raw[name]
        if value is None:
            points = None
        elif name == "filing_consistency":
            points = value
        else:
            points = piecewise(value, CURVES[name])
        components[name] = {"value": value, "score": points, "weight": weight}

    available = [(c["score"], c["weight"]) for c in components.values() if c["score"] is not None]
    total_weight = sum(w for _, w in available)
    composite = sum(s * w for s, w in available) / total_weight if total_weight else None

    return {
        "score": round(composite, 1) if composite is not None else None,
        "confidence": round(total_weight, 2),
        "components": components,
        "latest_year": latest["tax_year"],
        "latest_revenue": latest.get("revenue"),
        "years_on_file": len({f["tax_year"] for f in usable}),
        "size_band": size_band(latest.get("revenue")),
    }


def cause_percentiles(scores: dict[str, float], causes: dict[str, str]) -> dict[str, tuple]:
    """
    {ein: (rank, total, percentile)} within each cause. Rank 1 is the best.
    Organizations with no cause on record are ranked among themselves.
    """
    groups: dict[str, list] = {}
    for ein, value in scores.items():
        if value is not None:
            groups.setdefault(causes.get(ein, ""), []).append((ein, value))
    out = {}
    for members in groups.values():
        members.sort(key=lambda m: m[1], reverse=True)
        total = len(members)
        for rank, (ein, _) in enumerate(members, 1):
            out[ein] = (rank, total, round(100 * (total - rank + 1) / total, 1))
    return out


def main() -> None:
    conn = db.connect()
    results = {}
    for ein, filings in db.all_filings(conn).items():
        result = score(filings)
        if result:
            results[ein] = result
    ranks = cause_percentiles({e: r["score"] for e, r in results.items()},
                              db.categories_by_ein(conn))
    for ein, (rank, total, pct) in ranks.items():
        results[ein].update(cause_rank=rank, cause_total=total, cause_pct=pct)
    db.save_scores(conn, results)
    scored = [r["score"] for r in results.values() if r["score"] is not None]
    print(f"scored {len(results)} organizations")
    if scored:
        scored.sort()
        print(f"score range {scored[0]} to {scored[-1]}, median {scored[len(scored) // 2]}")


if __name__ == "__main__":
    main()
