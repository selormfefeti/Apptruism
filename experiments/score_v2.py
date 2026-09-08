"""
Pressure test for a second version of the score.

What changes against score.py, each switchable so its effect can be isolated:

  form-specific weights   the 990 and the 990-EZ each get a formula whose
                          weights sum to one, so filing the short form no
                          longer caps confidence.
  consistency moved out   filing consistency stops being a merit component
                          and becomes part of confidence.
  averaged margin         operating margin is the mean of the last three
                          years, not the latest year alone.
  demoted zeros           zero officer pay at an organization spending
                          $500k or more counts as unknown, not as perfect.
  fundraising dropped     professional fundraising fees are zero for 78% of
                          990 filers; the component is dropped by default.

Confidence becomes coverage x depth x recency x stability x reconciliation,
each between 0 and 1, instead of coverage alone.

    python experiments/score_v2.py          prints the comparison, writes experiments/v2_comparison.xlsx
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd

import db
import score as v1

CURRENT_YEAR = 2026
W990 = {"donor_growth": 0.30, "margin": 0.25, "reserves": 0.25, "officer_comp": 0.20}
WEZ = {"donor_growth": 0.35, "margin": 0.30, "reserves": 0.35}
ZERO_PAY_SUSPECT_EXPENSES = 500_000
PARENT_GROUP = re.compile(r"booster|\bpta\b|\bpto\b|parent|athletic|\bband\b", re.I)

FULL = dict(margin_stat="mean", demote_zeros=True, keep_fundraising=False, consistency_in_score=False,
            soft_confidence=False)
VARIANTS = {
    "v2 full": FULL,
    "v2 latest-year margin": {**FULL, "margin_stat": "latest"},
    "v2 median margin": {**FULL, "margin_stat": "median"},
    "v2 zeros kept": {**FULL, "demote_zeros": False},
    "v2 fundraising kept": {**FULL, "keep_fundraising": True},
    "v2 consistency in score": {**FULL, "consistency_in_score": True},
    "v2b median + soft confidence": {**FULL, "margin_stat": "median", "soft_confidence": True},
}


def margins(filings, n=3):
    return [m for m in (v1.margin(f) for f in filings[-n:]) if m is not None]


def reconciliation(filings) -> float:
    """
    Revenue minus expenses should roughly equal the change in net assets
    from one year to the next. Investment gains break this for endowed
    organizations, so the penalty is mild: 1.0 down to 0.7.
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


def score_v2(filings, opts) -> dict | None:
    usable = sorted((f for f in filings if f.get("form") in v1.SCORED_FORMS and f.get("tax_year")),
                    key=lambda f: f["tax_period"])
    if not usable:
        return None
    by_year = {}
    for f in usable:
        by_year[f["tax_year"]] = f
    years = sorted(by_year)
    fl = [by_year[y] for y in years]
    latest = fl[-1]
    is_990 = latest["form"] == "990"

    weights = dict(W990 if is_990 else WEZ)
    if opts["keep_fundraising"] and is_990:
        weights["fundraising_cost"] = 0.10
    if opts["consistency_in_score"]:
        weights["filing_consistency"] = 0.20

    raw = {"donor_growth": v1.donor_growth(fl), "reserves": v1.reserve_months(latest)}
    ms = margins(fl)
    if opts["margin_stat"] == "latest" or not ms:
        raw["margin"] = v1.margin(latest)
    elif opts["margin_stat"] == "median":
        raw["margin"] = sorted(ms)[len(ms) // 2]
    else:
        raw["margin"] = sum(ms) / len(ms)
    if is_990:
        value = v1.share(latest.get("officer_comp"), latest.get("expenses"))
        if opts["demote_zeros"] and value == 0 and (latest.get("expenses") or 0) >= ZERO_PAY_SUSPECT_EXPENSES:
            value = None
        raw["officer_comp"] = value
        if "fundraising_cost" in weights:
            raw["fundraising_cost"] = v1.share(latest.get("fundraising_expense"), latest.get("contributions"))
    if "filing_consistency" in weights:
        raw["filing_consistency"] = v1.filing_consistency(fl, CURRENT_YEAR)

    points = {}
    for name in weights:
        value = raw.get(name)
        if value is None:
            points[name] = None
        elif name == "filing_consistency":
            points[name] = value
        else:
            points[name] = v1.piecewise(value, v1.CURVES[name])
    available = [(points[k], w) for k, w in weights.items() if points[k] is not None]
    got = sum(w for _, w in available)
    total = sum(weights.values())
    composite = sum(p * w for p, w in available) / got if got else None

    coverage = got / total
    depth = v1.piecewise(len(years), [(1, 0.4), (2, 0.6), (3, 0.8), (5, 1.0)])
    if opts["soft_confidence"]:
        # Returns lag the tax year by a year or more, so a 2023 return in 2026 is normal.
        recency = v1.piecewise(CURRENT_YEAR - years[-1], [(3, 1.0), (4, 0.7), (5, 0.4), (6, 0.2)])
    else:
        recency = v1.piecewise(CURRENT_YEAR - years[-1], [(2, 1.0), (3, 0.7), (4, 0.4), (5, 0.2)])
    latest_margin = v1.margin(latest)
    if latest_margin is None or len(ms) < 2:
        stability = 0.8
    else:
        stability = v1.piecewise(abs(latest_margin - sum(ms) / len(ms)),
                                 [(0.05, 1.0), (0.15, 0.8), (0.30, 0.6), (0.50, 0.4)])
    recon = reconciliation(fl)
    if opts["soft_confidence"]:
        # Stability and reconciliation are hints, not gates: each can cost at most 30%.
        confidence = coverage * depth * recency * (0.7 + 0.3 * stability) * (0.7 + 0.3 * recon)
    else:
        confidence = coverage * depth * recency * stability * recon
    return {
        "score": None if composite is None else round(composite, 1),
        "confidence": round(confidence, 2),
        "available": ",".join(k for k, v in points.items() if v is not None),
        "points": {k: (None if v is None else round(v)) for k, v in points.items()},
        "coverage": coverage, "depth": depth, "recency": recency, "stability": stability, "recon": recon,
        "form": latest["form"], "latest_year": years[-1], "years": len(years),
        "officer_comp_raw": raw.get("officer_comp"),
    }


def within_cause_pct(frame, col):
    ranks = v1.cause_percentiles(dict(zip(frame["ein"], frame[col])), dict(zip(frame["ein"], frame["category"])))
    return frame["ein"].map(lambda e: ranks.get(e, (None, None, None))[2])


LEAD = sys.argv[1] if len(sys.argv) > 1 else "v2 full"


def main() -> None:
    conn = db.connect()
    base = pd.DataFrame(db.ranking_rows(conn)).set_index("ein")
    filings = db.all_filings(conn)

    runs = {}
    for label, opts in VARIANTS.items():
        rows = {ein: r for ein, fl in filings.items() if (r := score_v2(fl, opts))}
        runs[label] = pd.DataFrame.from_dict(rows, orient="index")

    full = runs[LEAD]
    df = base.join(full[["score", "confidence", "coverage", "depth", "recency", "stability", "recon",
                         "form", "years", "officer_comp_raw", "available", "points"]].add_prefix("v2_"), how="inner")
    df.index.name = "ein"
    df = df.reset_index()
    comp = df["components"].map(json.loads)
    df["v1_officer_comp"] = comp.map(lambda c: c["officer_comp"]["value"])

    # Same population for every comparison: 501(c)(3), a return since 2023.
    pop = df[(df["subsection_code"] == 3) & (df["latest_year"] >= CURRENT_YEAR - 3)].copy()
    pop["v1_pct"] = within_cause_pct(pop, "score")
    pop["v2_pct"] = within_cause_pct(pop, "v2_score")
    pop["pct_shift"] = pop["v2_pct"] - pop["v1_pct"]

    out = []
    p = out.append
    p(f"LEAD VARIANT: {LEAD}")
    p(f"organizations compared (501(c)(3), filed since {CURRENT_YEAR - 3}): {len(pop):,}")
    p(f"rank correlation v1 vs v2 (Spearman): {pop[['score', 'v2_score']].corr(method='spearman').iloc[0, 1]:.3f}")
    p(f"moved more than 10 points of score: {(abs(pop['v2_score'] - pop['score']) > 10).mean():.0%}")
    p(f"moved more than 20 percentile points within their cause: {(abs(pop['pct_shift']) > 20).mean():.0%}")

    p("\nCONFIDENCE, by form")
    for form in ("990", "990EZ"):
        sub = pop[pop["v2_form"] == form]
        p(f"  {form:6s} n={len(sub):6,}  v1 mean {sub['confidence'].mean():.2f}  v2 mean {sub['v2_confidence'].mean():.2f}"
          f"  | share below 0.5: v1 {(sub['confidence'] < 0.5).mean():.0%}  v2 {(sub['v2_confidence'] < 0.5).mean():.0%}")
    p("  v2 confidence factors, mean: " + ", ".join(
        f"{k} {pop['v2_' + k].mean():.2f}" for k in ("coverage", "depth", "recency", "stability", "recon")))
    p(f"  reconciliation failed at least once: {(pop['v2_recon'] < 1).mean():.0%} of organizations")

    p("\nSCORE BY SIZE BAND (mean)")
    for band, g in pop.groupby("size_band"):
        p(f"  {band:14s} n={len(g):6,}  v1 {g['score'].mean():5.1f}  v2 {g['v2_score'].mean():5.1f}")
    p("\nSCORE BY FORM (mean)")
    for form, g in pop.groupby("v2_form"):
        p(f"  {form:6s} n={len(g):6,}  v1 {g['score'].mean():5.1f}  v2 {g['v2_score'].mean():5.1f}")

    zeros = pop[(pop["v2_form"] == "990") & (pop["v1_officer_comp"] == 0) & (pop["latest_revenue"] >= ZERO_PAY_SUSPECT_EXPENSES)]
    p(f"\nLARGE 990 FILERS REPORTING ZERO OFFICER PAY: {len(zeros):,}")
    p(f"  mean v1 score {zeros['score'].mean():.1f} -> v2 {zeros['v2_score'].mean():.1f}; "
      f"mean within-cause percentile {zeros['v1_pct'].mean():.0f} -> {zeros['v2_pct'].mean():.0f}")

    p("\nPARENT-GROUP-LIKE NAMES IN THE TOP 100 OF EDUCATION (booster, PTA, PTO, parent, athletic, band)")
    edu = pop[pop["category"] == "Educational Institutions and Related Activities"]
    for label, col, conf in (("v1", "score", "confidence"), ("v2", "v2_score", "v2_confidence")):
        top = edu[edu[conf] >= 0.5].sort_values(col, ascending=False).head(100)
        p(f"  {label}: {top['name'].str.contains(PARENT_GROUP).sum()} of 100 "
          f"(size mix: {top['size_band'].value_counts().to_dict()})")

    p("\nCONFIDENCE DISTRIBUTION (lead variant)")
    p("  " + pop["v2_confidence"].describe()[["min", "25%", "50%", "75%", "max"]].round(2).to_dict().__repr__())
    p(f"  share at or above 0.6: {(pop['v2_confidence'] >= 0.6).mean():.0%}")

    p("\nMARGIN POINTS BY SIZE BAND (mean), to see whether the margin statistic punishes small organizations")
    for label, frame in runs.items():
        if label not in ("v2 latest-year margin", "v2 full", "v2 median margin"):
            continue
        merged = pop[["ein", "size_band"]].merge(frame[["points"]], left_on="ein", right_index=True)
        merged["m"] = merged["points"].map(lambda d: d.get("margin"))
        p(f"  {label:24s} " + "  ".join(f"{b}: {g['m'].mean():4.0f}" for b, g in merged.groupby("size_band")))

    p("\nABLATIONS: rank correlation of each variant with the lead variant, on the same population")
    for label, frame in runs.items():
        if label == LEAD:
            continue
        merged = pop[["ein", "v2_score"]].merge(frame[["score"]], left_on="ein", right_index=True)
        rho = merged[["v2_score", "score"]].corr(method="spearman").iloc[0, 1]
        p(f"  {label:26s} rho {rho:.3f}")

    def mover(r):
        return (f"  {r['pct_shift']:+4.0f}  {r['name'][:40]:40s} {r['size_band']:13s} {r['v2_form']:5s} yrs {r['v2_years']:2d} "
                f"v1 {r['score']:5.1f} -> v2 {r['v2_score']:5.1f}  conf {r['confidence']:.2f}->{r['v2_confidence']:.2f}  "
                f"points {r['v2_points']}")
    p("\nBIGGEST CLIMBERS (within-cause percentile), with v2 component points")
    for _, r in pop.sort_values("pct_shift", ascending=False).head(6).iterrows():
        p(mover(r))
    p("\nBIGGEST FALLERS")
    for _, r in pop.sort_values("pct_shift").head(6).iterrows():
        p(mover(r))

    report = "\n".join(out)
    print(report)
    cols = ["ein", "name", "category", "state", "size_band", "v2_form", "latest_year", "latest_revenue",
            "score", "confidence", "v1_pct", "v2_score", "v2_confidence", "v2_pct", "pct_shift",
            "v2_coverage", "v2_depth", "v2_recency", "v2_stability", "v2_recon", "v1_officer_comp"]
    path = pathlib.Path(__file__).parent / "v2_comparison.xlsx"
    with pd.ExcelWriter(path) as xl:
        pd.DataFrame({"report": report.split("\n")}).to_excel(xl, sheet_name="summary", index=False)
        pop.sort_values("pct_shift", ascending=False).head(300)[cols].to_excel(xl, sheet_name="climbers", index=False)
        pop.sort_values("pct_shift").head(300)[cols].to_excel(xl, sheet_name="fallers", index=False)
        for cause in ("Educational Institutions and Related Activities", "Human Services", "Animal Rights"):
            sub = pop[pop["category"] == cause]
            t1 = sub[sub["confidence"] >= 0.5].sort_values("score", ascending=False).head(30)[cols]
            t2 = sub[sub["v2_confidence"] >= 0.5].sort_values("v2_score", ascending=False).head(30)[cols]
            pd.concat([t1.assign(list="v1 top 30"), t2.assign(list="v2 top 30")]).to_excel(
                xl, sheet_name=cause[:25], index=False)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
