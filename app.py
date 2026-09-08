"""
Apptruism — find and rank charities on what their public filings say.

One screen: filter the seed universe by cause, state and size, see the
ranking, click a row to see why an organization scored what it did and how
its money has moved over the years. The scoring rules are on the page, not
hidden behind it, because the whole point is that a donor can see them.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

import db
import propublica
import score as scoring

st.set_page_config(page_title="Apptruism", page_icon="🤝", layout="wide")

SIZE_ORDER = ["Under $100k", "$100k to $1M", "$1M to $10M", "Over $10M", "Unknown"]

# Written for a donor, not a developer. Dollar signs are escaped because
# Streamlit's markdown otherwise reads them as maths.
METHOD_TEXT = r"""
Every organization here files a Form 990 or 990-EZ with the IRS each year, and
those returns are public. The score reads a few years of them and asks four
questions:

- **Is support growing?** How fast contributions have grown, year over year,
  across the returns on file. This needs at least two years of \$1,000 or more.
- **Does it live within its means?** Revenue minus expenses, as a share of
  revenue, taken as the median of the last three years so one unusual year
  doesn't decide it. A small surplus scores best. Large deficits score low,
  and so do very large surpluses, since money piling up isn't being spent on
  the mission.
- **Could it survive a bad year?** How many months of expenses its net assets
  would cover. Six to twenty-four months scores best.
- **How much goes to the people running it?** Officer and director pay as a
  share of expenses, from the full Form 990 only. The shorter 990-EZ has no
  such line. A reported zero at an organization spending \$500,000 or more is
  treated as unknown rather than as perfect, because that line is often left
  blank.

Each answer becomes 0 to 100 points, and the score is their weighted average.
The full 990 and the 990-EZ use different weights, shown below, so filing the
shorter form is not itself a penalty.

**Confidence** says how far to trust the score. It multiplies five factors,
each between 0 and 1: how much of the formula could be computed, how many
years of data there are, how recent the newest return is, whether the latest
year looks typical, and whether the numbers reconcile from one year to the
next. A long, steady, consistent history scores near 1.0. A single year of
data can't get above 0.4, however good it looks.

**In its cause** ranks each organization only against others working on the
same cause, because a food pantry and a university shouldn't be compared on
one number.
"""

METHOD_LIMITS = r"""
**What this can't tell you.** The score measures financial health as the
filings report it, not impact. It has no way to see whether a program works.
Organizations that spend down reserves by design, such as grantmakers, can
look worse than they are. Organizations under \$50,000 file a postcard with
no financials and don't appear. Data comes from
[ProPublica's Nonprofit Explorer](https://projects.propublica.org/nonprofits/),
built from IRS e-filings, and is refreshed monthly. The scoring code is
[open source](https://github.com/selormfefeti/Apptruism); changes to it are
argued with evidence, in public.
"""


@st.cache_resource
def database(schema_version: int = db.SCHEMA_VERSION):
    """Keyed on the schema version so a code change that adds a column reopens it."""
    return db.connect()


# Runs on every script run, and is cheap when the data is already there. A
# download replaces the file under the cached connection, so drop that.
if db.ensure_database() == "downloaded":
    database.clear()


@st.cache_data
def ranking(stamp: str, schema_version: int = db.SCHEMA_VERSION) -> pd.DataFrame:
    """Both arguments are only cache keys: a rescore or a schema change refreshes the page."""
    df = pd.DataFrame(db.ranking_rows(database()))
    if df.empty:
        return df
    parsed = df["components"].map(json.loads)
    for name in scoring.COMPONENTS:
        df[name] = parsed.map(lambda c, n=name: c.get(n, {}).get("value"))
    return df


@st.cache_data
def counts(stamp: str, schema_version: int = db.SCHEMA_VERSION) -> dict:
    return db.counts(database())


def money(x) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    x = float(x)
    for cut, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(x) >= cut:
            return f"${x / cut:,.1f}{suffix}"
    return f"${x:,.0f}"


def fmt_value(name, value) -> str:
    if value is None:
        return "not available"
    kind = scoring.LABELS[name][1]
    if kind == "pct":
        return f"{value * 100:+.1f}%" if name in ("donor_growth", "margin") else f"{value * 100:.1f}%"
    if kind == "months":
        return f"{value:.1f} months"
    return f"{value:.0f}"


STAMP = db.scores_stamp(database())
CURRENT_YEAR = pd.Timestamp.today().year
df = ranking(STAMP)
if df.empty:
    st.title("Apptruism")
    st.warning("No data yet. The published database was not available when this app started; "
               "it is rebuilt monthly and downloaded on startup, so try again in a little while.")
    if db.LAST_DOWNLOAD_ERROR:
        st.caption(f"Download attempt failed with: {db.LAST_DOWNLOAD_ERROR}")
    st.caption("Running this locally? Build the data yourself, then refresh:")
    st.code("python fetch.py --load-seed --limit 300\npython score.py", language="bash")
    st.stop()

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("Apptruism")
    st.caption("Charities ranked on what their IRS filings show.")
    query = st.text_input("Search name or mission")
    categories = sorted(df["category"].dropna().unique())
    chosen_cats = st.multiselect("Cause", categories)
    states = sorted(df["state"].dropna().unique())
    chosen_states = st.multiselect("State", states)
    sizes = [s for s in SIZE_ORDER if s in set(df["size_band"])]
    chosen_sizes = st.multiselect("Size (latest revenue)", sizes)
    min_conf = st.slider("Minimum confidence", 0.0, 1.0, 0.7, 0.05,
                         help="Share of the scoring weight that could be computed from the data on file.")
    only_c3 = st.checkbox("501(c)(3) charities only", value=True,
                          help="Gifts to 501(c)(3)s are tax deductible. Unticking adds trade "
                               "associations, booster clubs, fraternal orders and the like.")
    hide_stale = st.checkbox(f"Hide filers with nothing since {CURRENT_YEAR - 3}", value=True,
                             help="An organization with no return in three years is probably inactive.")
    hide_gone = st.checkbox("Hide organizations no longer on the IRS list", value=True,
                            help="Revoked, merged or dissolved since they were tagged in 2019.")
    c = counts(STAMP)
    st.divider()
    st.caption(
        f"{c.get('scored', 0):,} scored of {c.get('fetched', 0):,} fetched, from {c.get('seed', 0):,} "
        f"organizations tagged in 2019 and an IRS list of {c.get('universe', 0):,} that could be scored. "
        f"{c.get('filings', 0):,} filings on file."
    )
    st.caption("Data: ProPublica Nonprofit Explorer, from IRS Form 990 e-files.")

view = df
if query:
    q = query.lower()
    view = view[view["name"].str.lower().str.contains(q, na=False)
                | view["mission"].str.lower().str.contains(q, na=False)]
if chosen_cats:
    view = view[view["category"].isin(chosen_cats)]
if chosen_states:
    view = view[view["state"].isin(chosen_states)]
if chosen_sizes:
    view = view[view["size_band"].isin(chosen_sizes)]
view = view[view["confidence"] >= min_conf]
if only_c3:
    view = view[view["subsection_code"] == 3]
if hide_stale:
    view = view[view["latest_year"] >= CURRENT_YEAR - 3]
if hide_gone:
    view = view[view["active"] == 1]
view = view.sort_values(["score", "confidence"], ascending=False).reset_index(drop=True)
view.insert(0, "rank", range(1, len(view) + 1))

# ---------------------------------------------------------------- ranking
st.subheader(f"{len(view):,} organizations")
if view.empty:
    st.info("Nothing matches those filters.")
    st.stop()

table_cols = ["rank", "name", "category", "state", "size_band", "latest_revenue",
              "score", "cause_pct", "confidence", "donor_growth", "latest_year"]
event = st.dataframe(
    view[table_cols],
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    height=420,
    column_config={
        "rank": st.column_config.NumberColumn("#", width="small"),
        "name": st.column_config.TextColumn("Organization", width="large"),
        "category": "Cause",
        "state": st.column_config.TextColumn("State", width="small"),
        "size_band": "Size",
        "latest_revenue": st.column_config.NumberColumn("Revenue", format="dollar"),
        "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
        "cause_pct": st.column_config.ProgressColumn(
            "In its cause", min_value=0, max_value=100, format="%.0f%%",
            help="Share of organizations with the same cause that this one scores at or above."),
        "confidence": st.column_config.NumberColumn("Confidence", format="%.2f"),
        "donor_growth": st.column_config.NumberColumn("Donor growth", format="percent"),
        "latest_year": st.column_config.NumberColumn("Latest year", format="%d"),
    },
)
picked = event.selection.rows
org = view.iloc[picked[0]] if picked else view.iloc[0]
if not picked:
    st.caption("Click a row to see why it scored what it did. Showing the top result.")

# ---------------------------------------------------------------- detail
st.divider()
left, right = st.columns([3, 2])
with left:
    st.markdown(f"### {org['name']}")
    place = ", ".join(p for p in (org["city"], org["state"]) if p)
    subsection = f"501(c)({int(org['subsection_code'])})" if pd.notna(org["subsection_code"]) else "subsection n/a"
    if org["cause_source"] == "NTEE":
        via = f"NTEE {org['ntee_code']}"
    elif org["cause_source"] == "2019 tag":
        via = "no NTEE code, cause from the 2019 hand tag"
    else:
        via = "no NTEE code"
    old_tag = ""
    if org["seed_category"] and org["seed_category"] != "Uncategorized":
        old_tag = f" · 2019 tag: {org['seed_category']}"
        if org["subcategory"]:
            old_tag += f" / {org['subcategory']}"
    st.caption(f"{org['category']} ({via}) · {place} · {subsection}{old_tag} · EIN {org['ein']}")
    if not org["active"]:
        st.warning("No longer on the IRS list of exempt organizations. Revoked, merged or dissolved.")
    if org["mission"]:
        st.write(org["mission"])
    links = [f"[ProPublica profile]({propublica.ORG_PAGE.format(ein=int(org['ein']))})"]
    if org["website"]:
        site = org["website"] if str(org["website"]).startswith("http") else f"http://{org['website']}"
        links.append(f"[Website]({site})")
    st.markdown(" · ".join(links))

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Score", f"{org['score']:.0f}")
    if pd.notna(org.get("cause_rank")):
        m2.metric("In its cause", f"{int(org['cause_rank'])} of {int(org['cause_total']):,}",
                  help=f"Scores at or above {org['cause_pct']:.0f}% of {org['category']} organizations.")
    else:
        m2.metric("In its cause", "n/a")
    m3.metric("Confidence", f"{org['confidence']:.2f}")
    m4.metric("Latest revenue", money(org["latest_revenue"]))
    m5.metric("Years on file", int(org["years_on_file"]))

    comps = json.loads(org["components"])
    rows = []
    for name, comp in comps.items():
        label = scoring.LABELS[name][0]
        rows.append({
            "Component": label,
            "Value": fmt_value(name, comp["value"]),
            "Points": None if comp["score"] is None else round(comp["score"]),
            "Weight": f"{comp['weight'] * 100:.0f}%",
        })
    st.markdown("**Score**")
    st.dataframe(
        pd.DataFrame(rows), hide_index=True,
        column_config={"Points": st.column_config.ProgressColumn(
            "Points", min_value=0, max_value=100, format="%d")},
    )
    factors = json.loads(org["confidence_factors"] or "{}")
    if factors:
        st.markdown(f"**Confidence {org['confidence']:.2f}**, the product of these factors")
        st.dataframe(
            pd.DataFrame([{"Factor": scoring.FACTOR_LABELS.get(k, k), "Value": v}
                          for k, v in factors.items()]),
            hide_index=True,
            column_config={"Value": st.column_config.ProgressColumn(
                "Value", min_value=0, max_value=1, format="%.2f")},
        )

with right:
    filings = pd.DataFrame(db.filings_for(database(), org["ein"]))
    if not filings.empty:
        trend = (filings.groupby("tax_year")[["revenue", "expenses", "contributions"]]
                 .last().rename(columns=str.title))
        trend.index = trend.index.astype(int).astype(str)  # keeps 2024 from rendering as 2,024
        st.markdown("**Money over time**")
        st.line_chart(trend)
        latest = filings.sort_values("tax_period").iloc[-1]
        detail = {
            "Form": latest["form"],
            "Tax year": str(int(latest["tax_year"])),
            "Revenue": money(latest["revenue"]),
            "Expenses": money(latest["expenses"]),
            "Contributions": money(latest["contributions"]),
            "Net assets": money(latest["net_assets"]),
            "Officer compensation": money(latest["officer_comp"]) if latest["form"] == "990" else "not on 990-EZ",
        }
        st.table(pd.DataFrame({"Latest filing": list(detail.values())}, index=list(detail.keys())))
        if latest.get("pdf_url"):
            st.markdown(f"[Latest return (PDF)]({latest['pdf_url']})")

# ---------------------------------------------------------------- method
with st.expander("How the score works"):
    st.markdown(METHOD_TEXT)
    st.dataframe(
        pd.DataFrame([
            {"Component": scoring.LABELS[k][0],
             **{f"Form {form}": f"{w[k] * 100:.0f}%" if k in w else "not on the form"
                for form, w in scoring.WEIGHTS.items()}}
            for k in scoring.COMPONENTS
        ]),
        hide_index=True,
    )
    st.markdown(METHOD_LIMITS)
