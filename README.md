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

1. `fetch.py` pulls each seed organization's record from the ProPublica
   Nonprofit Explorer API (free, no key) into SQLite: who they are, and a
   financial extract of every Form 990 or 990-EZ on file.
2. `score.py` turns those filings into a 0-100 score from six components:
   donor growth, filing consistency, operating margin, reserves, officer pay
   share and fundraising cost. Each is explained in the module docstring and
   on the app page. A confidence figure says how much of the score could be
   computed from the data available.
3. `app.py` is a Streamlit page: filter by cause, state and size, see the
   ranking, click an organization to see its components and money over time.

## Run it

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python fetch.py --load-seed --limit 500
./venv/bin/python score.py
./venv/bin/streamlit run app.py
```

Fetching is resumable. Run `fetch.py` again without `--limit` to pull the rest
of the seed list; it takes about an hour or two for all 20,000. Rerun
`score.py` after any fetch.

Or skip the fetch: if there is no `apptruism.db` when the app starts, it
downloads the latest published one from the repo's `data` release. A
GitHub Action rebuilds and republishes that file on the first of each month,
and can be run by hand from the Actions tab. The hosted copy on Streamlit
Community Cloud gets its data the same way.

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
change fixes and which it makes worse. Rankings move when weights move, so
changes land as their own commits with the reasoning in the message.

## Not yet

- Program expense ratio. ProPublica's extract does not carry program
  expenses; that needs the raw XML from the IRS zips.
- Anything from the 2020 pitch beyond ranking: maps, news, payroll giving,
  rewards.
