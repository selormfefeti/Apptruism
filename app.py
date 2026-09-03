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

NTEE_MAJOR = {
    "A": "Arts, Culture & Humanities", "B": "Education", "C": "Environment",
    "D": "Animal-Related", "E": "Health Care", "F": "Mental Health & Crisis",
    "G": "Disease & Disorders", "H": "Medical Research", "I": "Crime & Legal",
    "J": "Employment", "K": "Food, Agriculture & Nutrition", "L": "Housing & Shelter",
    "M": "Public Safety & Disaster", "N": "Recreation & Sports", "O": "Youth Development",
    "P": "Human Services", "Q": "International", "R": "Civil Rights & Advocacy",
    "S": "Community Improvement", "T": "Philanthropy & Grantmaking",
    "U": "Science & Technology", "V": "Social Science", "W": "Public & Societal Benefit",
    "X": "Religion-Related", "Y": "Mutual & Membership Benefit", "Z": "Unknown",
}
SIZE_ORDER = ["Under $100k", "$100k to $1M", "$1M to $10M", "Over $10M", "Unknown"]


@st.cache_resource
def database():
    db.ensure_database()
    return db.connect()


@st.cache_data
def ranking(stamp: str) -> pd.DataFrame:
    """The stamp is only a cache key: a rescore changes it and refreshes the page."""
    df = pd.DataFrame(db.ranking_rows(database()))
    if df.empty:
        return df
    parsed = df["components"].map(json.loads)
    for name in scoring.WEIGHTS:
        df[name] = parsed.map(lambda c, n=name: c[n]["value"])
    df["ntee_group"] = df["ntee_code"].map(
        lambda c: NTEE_MAJOR.get(str(c)[:1].upper(), "Unknown") if c else "Unknown")
    return df


@st.cache_data
def counts(stamp: str) -> dict:
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
    c = counts(STAMP)
    st.divider()
    st.caption(
        f"{c['scored']:,} scored of {c['fetched']:,} fetched, "
        f"from a seed of {c['seed']:,} organizations tagged in 2019. "
        f"{c['filings']:,} filings on file."
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
    sub = f" · {org['subcategory']}" if org["subcategory"] else ""
    subsection = f"501(c)({int(org['subsection_code'])})" if pd.notna(org["subsection_code"]) else "subsection n/a"
    st.caption(f"{org['category']}{sub} · {place} · {subsection} · NTEE {org['ntee_code'] or 'n/a'} "
               f"({org['ntee_group']}) · EIN {org['ein']}")
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
    st.dataframe(
        pd.DataFrame(rows), hide_index=True,
        column_config={"Points": st.column_config.ProgressColumn(
            "Points", min_value=0, max_value=100, format="%d")},
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
    st.markdown(scoring.__doc__.split("    python score.py")[0])
    st.dataframe(
        pd.DataFrame([{"Component": scoring.LABELS[k][0], "Weight": f"{v * 100:.0f}%"}
                      for k, v in scoring.WEIGHTS.items()]),
        hide_index=True,
    )
