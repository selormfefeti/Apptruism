"""
Dump the top and bottom of the ranking per cause into one spreadsheet for a
human to mark up. The point is to find where the score disagrees with
judgment, so the curves and weights in score.py can be corrected.

    python review.py            writes review.xlsx, 30 top and 30 bottom per cause
    python review.py --n 50
"""

from __future__ import annotations

import argparse
import json

import pandas as pd

import db
import score as scoring


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--min-confidence", type=float, default=0.7)
    parser.add_argument("--out", default="review.xlsx")
    parser.add_argument("--all", action="store_true",
                        help="include every subsection, not just 501(c)(3)")
    args = parser.parse_args()

    df = pd.DataFrame(db.ranking_rows(db.connect()))
    parsed = df["components"].map(json.loads)
    for name in scoring.WEIGHTS:
        df[scoring.LABELS[name][0]] = parsed.map(lambda c, n=name: c[n]["value"])
    df = df[df["confidence"] >= args.min_confidence]
    if not args.all:
        df = df[df["subsection_code"] == 3]

    cols = ["ein", "name", "category", "subcategory", "state", "subsection_code", "size_band", "latest_year",
            "latest_revenue", "score", "confidence"] + [scoring.LABELS[n][0] for n in scoring.WEIGHTS]
    frames = []
    for cause, group in df.groupby("category"):
        group = group.sort_values("score", ascending=False)
        top = group.head(args.n).assign(end="top")
        bottom = group.tail(args.n).assign(end="bottom")
        frames.append(pd.concat([top, bottom]))
    out = pd.concat(frames)[["end"] + cols]
    out["verdict"] = ""
    out["note"] = ""
    with pd.ExcelWriter(args.out) as xl:
        out.to_excel(xl, sheet_name="review", index=False)
        summary = (df.groupby("category")["score"]
                   .describe()[["count", "mean", "50%", "min", "max"]].round(1))
        summary.to_excel(xl, sheet_name="by cause")
    print(f"wrote {args.out}: {len(out)} rows across {out['category'].nunique()} causes")


if __name__ == "__main__":
    main()
