"""
Turn a few years of filings into one number a donor can compare across
organizations, and keep the arithmetic simple enough to explain on a screen.

The 2020 pitch promised a ranking on donor retention, donor growth, pledge
fulfilment and financials. Form 990 carries no donor counts and no pledges,
so the score uses what the public filings actually contain:

  donor_growth   compound annual growth of contributions across the years
                 on file. The closest public proxy for a growing donor base.
                 Needs two years of at least $1,000 each.
  margin         (revenue - expenses) / revenue, the median of the last three
                 years so one unusual year does not decide it. Small surpluses
                 are healthy; large deficits and very large surpluses both
                 score lower.
  reserves       months of expenses covered by net assets. Six to twenty-four
                 months is the comfortable band.
  officer_comp   officer and director compensation as a share of expenses.
                 Form 990 only; the EZ has no such line. A reported zero at
                 an organization spending $500k or more is treated as
                 unknown rather than as perfect.

The full 990 and the 990-EZ each have their own weights summing to one, so
filing the short form is not itself a penalty. Each component maps to
0-100 through a piecewise-linear curve, and the score is the weighted mean
of whichever components are available.

Confidence says how far to trust that number. It is the product of five
factors between 0 and 1:

  coverage        share of the formula's weight that could be computed
  depth           years of data: 0.4 for one, rising to 1.0 at five
  recency         1.0 while the newest return is three years old or less,
                  since returns lag the tax year; then 0.7, 0.4, 0.2
  stability       whether the latest margin is typical of the last three
                  years; can cost at most 30%
  reconciliation  whether revenue minus expenses matches the change in net
                  assets year to year; can cost at most 30%

A food pantry and a university should not be compared on one number, so
every organization also gets a rank and percentile among the others tagged
with the same cause.

    python score.py            recompute the scores table for every org
"""

from __future__ import annotations

from datetime import date

import db

COMPONENTS = ["donor_growth", "margin", "reserves", "officer_comp"]

WEIGHTS = {
    "990": {"donor_growth": 0.30, "margin": 0.25, "reserves": 0.25, "officer_comp": 0.20},
    "990EZ": {"donor_growth": 0.35, "margin": 0.30, "reserves": 0.35},
}

# (raw value, score) knots. Outside the first and last knot the score is flat.
CURVES = {
    "donor_growth": [(-0.30, 0), (0.00, 50), (0.15, 90), (0.30, 100)],
    "margin": [(-0.25, 0), (-0.05, 40), (0.00, 65), (0.05, 90), (0.15, 100),
               (0.30, 80), (0.60, 50)],
    "reserves": [(0, 0), (3, 70), (6, 100), (24, 100), (48, 60), (96, 30)],
    "officer_comp": [(0.00, 100), (0.05, 100), (0.15, 50), (0.30, 0)],
}

LABELS = {
    "donor_growth": ("Donor growth", "pct"),
    "margin": ("Operating margin", "pct"),
    "reserves": ("Reserves", "months"),
    "officer_comp": ("Officer pay share", "pct"),
}

FACTOR_LABELS = {
    "coverage": "Coverage of the formula",
    "depth": "Years of data",
    "recency": "Age of newest return",
    "stability": "Latest year typical",
    "reconciliation": "Numbers add up",
}

MIN_CONTRIBUTIONS = 1_000
ZERO_PAY_SUSPECT_EXPENSES = 500_000
MARGIN_YEARS = 3
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


def one_per_year(filings) -> list[dict]:
    """Usable filings, one per tax year (the latest period wins), oldest first."""
    by_year: dict[int, dict] = {}
    for f in sorted(filings, key=lambda f: f["tax_period"]):
        if f.get("form") in SCORED_FORMS and f.get("tax_year"):
            by_year[f["tax_year"]] = f
    return [by_year[y] for y in sorted(by_year)]


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


def margin(filing) -> float | None:
    revenue, expenses = filing.get("revenue"), filing.get("expenses")
    if not revenue or revenue <= 0 or expenses is None:
        return None
    return (revenue - expenses) / revenue


def recent_margins(filings) -> list[float]:
    return [m for m in (margin(f) for f in filings[-MARGIN_YEARS:]) if m is not None]


def median_margin(filings) -> float | None:
    ms = sorted(recent_margins(filings))
    return ms[len(ms) // 2] if ms else None


def reserve_months(latest) -> float | None:
    net_assets, expenses = latest.get("net_assets"), latest.get("expenses")
    if net_assets is None or not expenses or expenses <= 0:
        return None
    return max(net_assets, 0) / (expenses / 12)


def officer_pay_share(latest) -> float | None:
    value = share(latest.get("officer_comp"), latest.get("expenses"))
    if value == 0 and (latest.get("expenses") or 0) >= ZERO_PAY_SUSPECT_EXPENSES:
        return None  # nobody runs a $500k organization for free; the line was left blank
    return value


def stability(filings) -> float:
    """1.0 when the latest margin sits within five points of the recent average."""
    ms = recent_margins(filings)
    latest = margin(filings[-1])
    if latest is None or len(ms) < 2:
        return 0.8
    return piecewise(abs(latest - sum(ms) / len(ms)),
                     [(0.05, 1.0), (0.15, 0.8), (0.30, 0.6), (0.50, 0.4)])


def reconciliation(filings) -> float:
    """
    Revenue minus expenses should roughly equal the change in net assets
    from one year to the next. Investment gains break this for endowed
    organizations, so the factor runs from 1.0 down to only 0.7.
    """
    checks = misses = 0
    for prev, cur in zip(filings, filings[1:]):
        if cur["tax_year"] != prev["tax_year"] + 1:
            continue
        if None in (prev.get("net_assets"), cur.get("net_assets"), cur.get("revenue"), cur.get("expenses")):
            continue
        expected = cur["revenue"] - cur["expenses"]
        actual = cur["net_assets"] - prev["net_assets"]
        tolerance = max(0.25 * abs(cur["expenses"]), 25_000)
        checks += 1
        if abs(expected - actual) > tolerance:
            misses += 1
    return 1.0 if not checks else 1.0 - 0.3 * misses / checks


def depth(years: int) -> float:
    return piecewise(years, [(1, 0.4), (2, 0.6), (3, 0.8), (5, 1.0)])


def recency(gap_years: int) -> float:
    return piecewise(gap_years, [(3, 1.0), (4, 0.7), (5, 0.4), (6, 0.2)])


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
    usable = one_per_year(filings)
    if not usable:
        return None
    latest = usable[-1]
    weights = WEIGHTS[latest["form"]]

    raw = {
        "donor_growth": donor_growth(usable),
        "margin": median_margin(usable),
        "reserves": reserve_months(latest),
        "officer_comp": officer_pay_share(latest) if latest["form"] == "990" else None,
    }
    components = {}
    for name, weight in weights.items():
        value = raw[name]
        points = None if value is None else piecewise(value, CURVES[name])
        components[name] = {"value": value, "score": points, "weight": weight}

    available = [(c["score"], c["weight"]) for c in components.values() if c["score"] is not None]
    got = sum(w for _, w in available)
    composite = sum(s * w for s, w in available) / got if got else None

    factors = {
        "coverage": round(got / sum(weights.values()), 2),
        "depth": depth(len(usable)),
        "recency": recency(current_year - latest["tax_year"]),
        "stability": round(stability(usable), 2),
        "reconciliation": round(reconciliation(usable), 2),
    }
    confidence = (factors["coverage"] * factors["depth"] * factors["recency"]
                  * (0.7 + 0.3 * factors["stability"]) * (0.7 + 0.3 * factors["reconciliation"]))

    return {
        "score": round(composite, 1) if composite is not None else None,
        "confidence": round(confidence, 2),
        "components": components,
        "confidence_factors": factors,
        "latest_year": latest["tax_year"],
        "latest_revenue": latest.get("revenue"),
        "years_on_file": len(usable),
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
    for ein, filings in db.iter_filings(conn):
        result = score(filings)
        if result:
            results[ein] = result
    ranks = cause_percentiles({e: r["score"] for e, r in results.items()},
                              db.causes_by_ein(conn))
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
