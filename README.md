# Apptruism

Charities ranked on what their public IRS filings show, so a donor can see
where money is growing, where it is being spent and how a group compares
with others working on the same cause.

This is the 2026 rebuild of a 2020 idea. The original repo was a Windows
C# tool that parsed IRS Form 990 e-files from an AWS bucket the IRS has
since shut down. What survived from that version is the idea, the list of
fields worth pulling, and two spreadsheets in `seed/` with about 20,000
organizations hand-tagged by cause.

## What it does

1. `universe.py` reads the IRS Exempt Organizations master file, the list of
   every tax-exempt organization, and keeps the ones the score can read:
   501(c)(3)s that file a Form 990 or 990-EZ with income of $50,000 or more,
   about 373,000 of them. Organizations that have left the IRS list are
   marked inactive.
2. `irsxml.py` reads the IRS e-file XML, the returns themselves, for the
   newest 990 or 990-EZ of every organization we track: mission text,
   program descriptions, program spending, website, headcount and officers.
   ProPublica's extract carries none of that.
3. `fetch.py` pulls each organization's record from the ProPublica
   Nonprofit Explorer API (free, no key) into SQLite: who they are, and a
   financial extract of every Form 990 or 990-EZ on file.
4. `score.py` turns those filings into a 0-100 score from four components:
   donor growth, operating margin, reserves and officer pay share, with
   separate weights for the full 990 and the 990-EZ. A confidence figure,
   built from coverage, depth of history, recency, stability and whether
   the numbers reconcile, says how far to trust the score. Both are
   explained in the module docstring and on the app page.
5. `app.py` is a Streamlit page: filter by cause, state and size, see the
   ranking, click an organization to see its components and money over time.

Causes are the NTEE major groups, from the code the IRS assigns each
organization. The 2019 hand tags were keyword-driven and put more than half
the seed in "Education" (museums, hockey clubs and hospitals included), so
they are kept only as a secondary field and as a fallback for the 14% of
organizations without a code. The page says which source it used.

## Run it

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python fetch.py --load-seed --limit 500
./venv/bin/python score.py
./venv/bin/streamlit run app.py
```

To grow past the seed, `python universe.py` downloads the IRS master file
(about 340 MB) and queues every organization in the target set;
`fetch.py --limit N` then works through them.

Fetching is resumable. Run `fetch.py` again without `--limit` to pull the rest
of the seed list; it takes about an hour or two for all 20,000. Rerun
`score.py` after any fetch.

Or skip the fetch: if there is no `apptruism.db` when the app starts, it
downloads the latest published one from the repo's `data` release. A
GitHub Action rebuilds and republishes that file on the first of each month,
and a second, fast one rescores the published data whenever `score.py` or
`db.py` changes on master. Both can be run by hand from the Actions tab.
The app checks the release for a newer file about once an hour, so the
hosted copy on Streamlit Community Cloud follows on its own.

```bash
./venv/bin/python -m pytest
```

## Data

- ProPublica Nonprofit Explorer API v2: https://projects.propublica.org/nonprofits/api/
- IRS Form 990 e-file XML zips, if the raw returns are ever needed:
  https://www.irs.gov/charities-non-profits/form-990-series-downloads
- GivingTuesday 990 data lake, parsed extracts and an API:
  https://990data.givingtuesday.org/

## Layout

```
app.py          Streamlit page
universe.py     who belongs, from the IRS master file
irsxml.py       mission, program spending and officers from the IRS e-file XML
fetch.py        pull ProPublica data into apptruism.db
score.py        scoring rules and the scores table
db.py           SQLite schema and queries
propublica.py   API client and field normalization
seed/           2019 hand-tagged organizations and keyword taxonomy
review.py       top and bottom of each cause as a spreadsheet, for marking up
test_score.py   scoring tests
```

MIT licensed. IRS data is public domain; ProPublica asks for attribution,
which the app gives.

## Changing the score

The score is public so that it can be argued with. A change to a weight or a
curve in `score.py` should come with evidence: run `review.py`, which writes
the top and bottom of every cause to a spreadsheet, and say which rows the
change fixes and which it makes worse. `experiments/score_v2.py` is the
comparison that produced the current version and a template for the next
one. Rankings move when weights move, so changes land as their own commits
with the reasoning in the message.

Scoring changes so far, each with its evidence in the commit message:
the second version of the score (2026-09-08, `experiments/score_v2.py`),
and the reserve-aware margin floor with ranking within cause and size band
(2026-09-09), which lifted 13.6% of organizations by 11.8 points on
average, 87% of them under \$1M in revenue.

## Not yet

- The backfill of the full target set is running nightly (`backfill.yml`)
  and will take about a week from 2026-09-09. Until it finishes, the
  ranking covers the 2019 seed plus whatever has arrived so far.
- Program expense ratio as a score component. The figure now comes in
  through `irsxml.py`; adding it to the score is a scoring change and will
  come with evidence like the others.
- Anything from the 2020 pitch beyond ranking: maps, news, payroll giving,
  rewards.
